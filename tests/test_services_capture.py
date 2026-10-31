from types import SimpleNamespace

from tests.conftest import write_config


def _fake_systemctl(cmd, capture_output=True, text=True, check=False):
    if "--user" in cmd:
        stdout = "app-tray.service    enabled\n"
    else:
        stdout = "NetworkManager.service    enabled\nbluetooth.service    enabled\n"
    return SimpleNamespace(stdout=stdout, returncode=0)


def test_capture_services_writes_system_and_user(phoenix_repo, monkeypatch):
    import phoenix.config as config
    config.ensure_repo_initialized()
    # include_user_services=true, sinon user.txt n'est jamais écrit
    (phoenix_repo / "phoenix.toml").write_text("""
[dotfiles]
paths = []
[dotfiles.exclude]
patterns = []
[services]
include_user_services = true
""")

    import phoenix.services as services
    monkeypatch.setattr(services.subprocess, "run", _fake_systemctl)

    counts = services.capture_services()
    assert counts == {"system": 2, "user": 1}

    system_content = (phoenix_repo / "services" / "system.txt").read_text()
    user_content = (phoenix_repo / "services" / "user.txt").read_text()
    assert "NetworkManager.service" in system_content
    assert "app-tray.service" in user_content


def test_capture_services_skips_user_when_disabled(phoenix_repo, monkeypatch):
    import phoenix.config as config
    config.ensure_repo_initialized()
    write_config(phoenix_repo, [])  # include_user_services=false par défaut du helper

    import phoenix.services as services
    monkeypatch.setattr(services.subprocess, "run", _fake_systemctl)

    counts = services.capture_services()
    assert counts["user"] == 0
    assert not (phoenix_repo / "services" / "user.txt").exists()
