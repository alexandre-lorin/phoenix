def test_ensure_git_repo_initializes(phoenix_repo):
    import phoenix.git_utils as git_utils

    assert not (phoenix_repo / ".git").exists()
    git_utils.ensure_git_repo()
    assert (phoenix_repo / ".git").exists()
    assert (phoenix_repo / ".gitignore").exists()

    # Idempotent : un deuxième appel ne casse rien
    git_utils.ensure_git_repo()
    assert (phoenix_repo / ".git").exists()


def test_commit_snapshot_returns_none_when_nothing_changed(phoenix_repo):
    import phoenix.git_utils as git_utils

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\n")

    rev1 = git_utils.commit_snapshot()
    assert rev1 is not None

    rev2 = git_utils.commit_snapshot()  # rien n'a changé depuis
    assert rev2 is None


def test_commit_snapshot_commits_real_changes(phoenix_repo):
    import phoenix.git_utils as git_utils

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\n")
    rev1 = git_utils.commit_snapshot()

    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    rev2 = git_utils.commit_snapshot()

    assert rev2 is not None
    assert rev2 != rev1


def test_commit_diffstat_reports_changed_file_on_first_commit(phoenix_repo):
    """git show --stat doit fonctionner même sur le tout premier commit
    (pas de parent) — pas besoin de cas spécial pour l'arbre vide."""
    import phoenix.git_utils as git_utils

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")

    rev = git_utils.commit_snapshot()
    stat = git_utils.commit_diffstat(rev)

    assert "pacman.txt" in stat
    assert "insertion" in stat or "+" in stat


def test_commit_diffstat_reports_changes_on_subsequent_commit(phoenix_repo):
    import phoenix.git_utils as git_utils

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\n")
    git_utils.commit_snapshot()

    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    rev2 = git_utils.commit_snapshot()

    stat = git_utils.commit_diffstat(rev2)
    assert "pacman.txt" in stat


def test_last_snapshot_timestamp_returns_none_without_any_commit(phoenix_repo):
    import phoenix.git_utils as git_utils

    git_utils.ensure_git_repo()
    assert git_utils.last_snapshot_timestamp() is None


def test_last_snapshot_timestamp_ignores_rollback_commits(phoenix_repo):
    """Régression : un rollback crée un commit ("rollback: ..."), mais ça
    ne doit pas compter comme un nouveau snapshot pour le calcul de
    dérive du reminder (V5). Sinon rollback souvent sans jamais relancer
    un vrai `snapshot` réinitialiserait le compteur à tort."""
    import subprocess

    import phoenix.git_utils as git_utils

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\n")
    git_utils.commit_snapshot()

    snapshot_ts = git_utils.last_snapshot_timestamp()
    assert snapshot_ts is not None

    # un commit de rollback, plus récent, sans passer par commit_snapshot()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    subprocess.run(["git", "-C", str(phoenix_repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(phoenix_repo), "commit", "-m", "rollback: retour à l'état de abc1234"],
        check=True,
    )

    # le dernier commit "snapshot" reste le premier, pas le rollback
    assert git_utils.last_snapshot_timestamp() == snapshot_ts
