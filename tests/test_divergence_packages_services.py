from types import SimpleNamespace

from tests.conftest import write_config


def test_diff_packages_detects_manual_install_and_removal(phoenix_repo, monkeypatch):
    import phoenix.divergence as divergence

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    (phoenix_repo / "packages" / "aur.txt").write_text("")

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qqe"]:
            # docker installé à la main, waybar désinstallé depuis le snapshot
            return SimpleNamespace(stdout="hyprland\ndocker\n", returncode=0)
        if cmd == ["pacman", "-Qqem"]:
            return SimpleNamespace(stdout="", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(divergence.subprocess, "run", fake_run)

    result = divergence.diff_packages()
    assert result["native"].added == {"docker"}
    assert result["native"].removed == {"waybar"}


def test_diff_services_detects_manual_changes(phoenix_repo, monkeypatch):
    import phoenix.divergence as divergence

    (phoenix_repo / "services").mkdir()
    (phoenix_repo / "services" / "system.txt").write_text("NetworkManager.service\n")
    (phoenix_repo / "services" / "user.txt").write_text("")

    def fake_run(cmd, *args, **kwargs):
        if "--user" in cmd:
            return SimpleNamespace(stdout="", returncode=0)
        return SimpleNamespace(stdout="NetworkManager.service    enabled\nssh.service    enabled\n", returncode=0)

    monkeypatch.setattr(divergence.subprocess, "run", fake_run)

    result = divergence.diff_services()
    assert result["system"].added == {"ssh.service"}
    assert result["system"].removed == set()


def test_diff_services_skips_user_axis_when_disabled(phoenix_repo, monkeypatch):
    """Régression : avec include_user_services=false, diff_services ne doit
    même pas regarder les unités --user, sinon un vieux/absent user.txt
    remonte des divergences fantômes pour un axe jamais suivi."""
    import phoenix.divergence as divergence

    (phoenix_repo / "services").mkdir()
    (phoenix_repo / "services" / "system.txt").write_text("NetworkManager.service\n")
    # user.txt délibérément absent ou obsolète (comme après un toggle du flag)
    (phoenix_repo / "services" / "user.txt").write_text("some-old-tracked-unit.service\n")

    write_config(phoenix_repo, [], include_user_services=False)

    def fake_run(cmd, *args, **kwargs):
        if "--user" in cmd:
            # plein d'unités --user standards, jamais destinées à être suivies
            return SimpleNamespace(
                stdout="gpg-agent.socket    enabled\ndirmngr.socket    enabled\n", returncode=0
            )
        return SimpleNamespace(stdout="NetworkManager.service    enabled\n", returncode=0)

    monkeypatch.setattr(divergence.subprocess, "run", fake_run)

    result = divergence.diff_services()
    assert "user" not in result
    assert "system" in result
    assert result["system"].added == set()
    assert result["system"].removed == set()


def test_diff_services_includes_user_axis_when_enabled(phoenix_repo, monkeypatch):
    import phoenix.divergence as divergence

    (phoenix_repo / "services").mkdir()
    (phoenix_repo / "services" / "system.txt").write_text("")
    (phoenix_repo / "services" / "user.txt").write_text("")

    write_config(phoenix_repo, [], include_user_services=True)

    def fake_run(cmd, *args, **kwargs):
        if "--user" in cmd:
            return SimpleNamespace(stdout="gpg-agent.socket    enabled\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(divergence.subprocess, "run", fake_run)

    result = divergence.diff_services()
    assert "user" in result
    assert result["user"].added == {"gpg-agent.socket"}
