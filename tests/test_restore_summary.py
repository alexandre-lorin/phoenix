import pytest

from tests.conftest import write_config


def _prep_minimal_repo(phoenix_repo):
    import phoenix.config as config
    config.ensure_repo_initialized()
    write_config(phoenix_repo, [])


def test_run_restore_exits_zero_when_everything_succeeds(phoenix_repo, monkeypatch, capsys):
    _prep_minimal_repo(phoenix_repo)

    import phoenix.restore as restore

    monkeypatch.setattr(
        restore, "restore_packages",
        lambda auto_yes, skip_aur: restore.PackageRestoreResult(installed=["hyprland", "waybar"]),
    )
    monkeypatch.setattr(
        restore, "restore_services",
        lambda auto_yes: restore.ServiceRestoreResult(enabled=["bluetooth.service"]),
    )
    monkeypatch.setattr(
        restore, "restore_dotfiles",
        lambda auto_yes: restore.DotfilesRestoreResult(restored=["hypr", "waybar"]),
    )

    with pytest.raises(SystemExit) as exc_info:
        restore.run_restore(auto_yes=True)
    assert exc_info.value.code == 0

    out = capsys.readouterr().out
    assert "avec avertissements" not in out
    assert "2 installés" in out
    assert "1 activés" in out
    assert "2 restaurés" in out


def test_run_restore_exits_one_when_something_failed(phoenix_repo, monkeypatch, capsys):
    _prep_minimal_repo(phoenix_repo)

    import phoenix.restore as restore

    monkeypatch.setattr(
        restore, "restore_packages",
        lambda auto_yes, skip_aur: restore.PackageRestoreResult(installed=["hyprland"], failed=["introuvable-pkg"]),
    )
    monkeypatch.setattr(
        restore, "restore_services",
        lambda auto_yes: restore.ServiceRestoreResult(enabled=["bluetooth.service"]),
    )
    monkeypatch.setattr(
        restore, "restore_dotfiles",
        lambda auto_yes: restore.DotfilesRestoreResult(restored=["hypr"]),
    )

    with pytest.raises(SystemExit) as exc_info:
        restore.run_restore(auto_yes=True)
    assert exc_info.value.code == 1

    out = capsys.readouterr().out
    assert "avec avertissements" in out
    assert "introuvable-pkg" in out


def test_run_restore_summary_reports_service_and_dotfile_failures_too(phoenix_repo, monkeypatch, capsys):
    _prep_minimal_repo(phoenix_repo)

    import phoenix.restore as restore

    monkeypatch.setattr(
        restore, "restore_packages",
        lambda auto_yes, skip_aur: restore.PackageRestoreResult(installed=["hyprland"]),
    )
    monkeypatch.setattr(
        restore, "restore_services",
        lambda auto_yes: restore.ServiceRestoreResult(enabled=[], failed=["unite-masquee.service"]),
    )
    monkeypatch.setattr(
        restore, "restore_dotfiles",
        lambda auto_yes: restore.DotfilesRestoreResult(restored=[], failed=["nvim"]),
    )

    with pytest.raises(SystemExit) as exc_info:
        restore.run_restore(auto_yes=True)
    assert exc_info.value.code == 1

    out = capsys.readouterr().out
    assert "unite-masquee.service" in out
    assert "nvim" in out
