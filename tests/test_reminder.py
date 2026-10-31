from datetime import datetime, timedelta

from tests.conftest import write_config


def _setup_hypr_with_commit(phoenix_repo, fake_home, content="original"):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text(content)
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    import phoenix.git_utils as git_utils
    git_utils.commit_snapshot()

    return hypr


def _backdate_last_commit(phoenix_repo, days_ago: int) -> None:
    """Simule un snapshot vieux de `days_ago` jours en réécrivant la date du
    dernier commit (git commit --amend --date, avec GIT_COMMITTER_DATE pour
    aussi bouger la date de commit utilisée par `log --format=%ct`)."""
    import subprocess

    past = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    subprocess.run(
        ["git", "-C", str(phoenix_repo), "commit", "--amend", "--no-edit",
         "--date", past],
        capture_output=True, text=True,
        env={"GIT_COMMITTER_DATE": past, "PATH": "/usr/bin:/bin"},
    )


def test_no_snapshot_ever_returns_none_days(phoenix_repo, fake_home):
    import phoenix.config as config
    config.ensure_repo_initialized()

    import phoenix.reminder as reminder
    assert reminder.days_since_last_snapshot() is None


def test_fresh_snapshot_no_reminder(phoenix_repo, fake_home):
    _setup_hypr_with_commit(phoenix_repo, fake_home)

    import phoenix.reminder as reminder
    fire, days = reminder.should_remind(threshold_days=7)

    assert fire is False
    assert days == 0


def test_old_snapshot_but_no_divergence_no_reminder(phoenix_repo, fake_home):
    _setup_hypr_with_commit(phoenix_repo, fake_home)
    _backdate_last_commit(phoenix_repo, days_ago=30)

    import phoenix.reminder as reminder
    fire, days = reminder.should_remind(threshold_days=7)

    # rien n'a dérivé, même si le dernier snapshot est vieux : rien à signaler
    assert fire is False
    assert days is not None and days >= 29


def test_old_snapshot_with_divergence_fires_reminder(phoenix_repo, fake_home):
    hypr = _setup_hypr_with_commit(phoenix_repo, fake_home)
    _backdate_last_commit(phoenix_repo, days_ago=30)
    (hypr / "hyprland.conf").write_text("modifié à la main, jamais re-snapshoté")

    import phoenix.reminder as reminder
    fire, days = reminder.should_remind(threshold_days=7)

    assert fire is True
    assert days is not None and days >= 29


def test_recent_divergence_under_threshold_does_not_fire(phoenix_repo, fake_home):
    hypr = _setup_hypr_with_commit(phoenix_repo, fake_home)
    (hypr / "hyprland.conf").write_text("modifié à la main, mais tout frais")

    import phoenix.reminder as reminder
    fire, days = reminder.should_remind(threshold_days=7)

    assert fire is False
    assert days == 0


def test_run_reminder_returns_true_when_nothing_to_signal(phoenix_repo, fake_home, capsys):
    _setup_hypr_with_commit(phoenix_repo, fake_home)

    import phoenix.reminder as reminder
    ok = reminder.run_reminder(threshold_days=7)

    assert ok is True
    assert "rien à signaler" in capsys.readouterr().out


def test_run_reminder_returns_false_and_warns_when_stale(phoenix_repo, fake_home, capsys):
    hypr = _setup_hypr_with_commit(phoenix_repo, fake_home)
    _backdate_last_commit(phoenix_repo, days_ago=30)
    (hypr / "hyprland.conf").write_text("modifié à la main")

    import phoenix.reminder as reminder
    ok = reminder.run_reminder(threshold_days=7)

    out = capsys.readouterr().out
    assert ok is False
    assert "dérive" in out


def test_run_reminder_quiet_suppresses_output(phoenix_repo, fake_home, capsys):
    hypr = _setup_hypr_with_commit(phoenix_repo, fake_home)
    _backdate_last_commit(phoenix_repo, days_ago=30)
    (hypr / "hyprland.conf").write_text("modifié à la main")

    import phoenix.reminder as reminder
    capsys.readouterr()  # purge les prints de setup (init config/repo)
    ok = reminder.run_reminder(threshold_days=7, quiet=True)

    assert ok is False
    assert capsys.readouterr().out == ""


def test_reminder_not_reset_by_a_rollback_commit(phoenix_repo, fake_home):
    """Bout en bout : un rollback fréquent sans jamais relancer un vrai
    `snapshot` ne doit pas faire taire le reminder — le rollback crée un
    commit, mais ce n'est pas un snapshot."""
    import subprocess

    hypr = _setup_hypr_with_commit(phoenix_repo, fake_home)
    _backdate_last_commit(phoenix_repo, days_ago=30)
    (hypr / "hyprland.conf").write_text("modifié à la main, jamais re-snapshoté")

    # un rollback juste maintenant (commit récent, mais PAS un snapshot)
    subprocess.run(["git", "-C", str(phoenix_repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(phoenix_repo), "commit", "--allow-empty", "-m", "rollback: retour à l'état de abc1234"],
        check=True,
    )

    import phoenix.reminder as reminder
    fire, days = reminder.should_remind(threshold_days=7)

    # le rollback est tout récent, mais le dernier vrai snapshot reste vieux
    assert fire is True
    assert days is not None and days >= 29
