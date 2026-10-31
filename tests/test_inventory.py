from types import SimpleNamespace


def _fake_pacman(cmd, capture_output=True, text=True, check=True):
    if cmd == ["pacman", "-Qqe"]:
        stdout = "hyprland\nwaybar\nspotify\nneovim\n"
    elif cmd == ["pacman", "-Qqem"]:
        stdout = "spotify\n"
    else:
        stdout = ""
    return SimpleNamespace(stdout=stdout, returncode=0)


def test_capture_packages_separates_native_and_aur(phoenix_repo, monkeypatch):
    import phoenix.inventory as inventory
    monkeypatch.setattr(inventory.subprocess, "run", _fake_pacman)

    counts = inventory.capture_packages()
    assert counts == {"native": 3, "aur": 1}

    native = (phoenix_repo / "packages" / "pacman.txt").read_text().splitlines()
    aur = (phoenix_repo / "packages" / "aur.txt").read_text().splitlines()

    assert set(native) == {"hyprland", "waybar", "neovim"}
    assert set(aur) == {"spotify"}
    assert "spotify" not in native  # le point qui compte : jamais dans les deux fichiers


def test_capture_packages_handles_zero_aur(phoenix_repo, monkeypatch):
    def fake(cmd, capture_output=True, text=True, check=True):
        if cmd == ["pacman", "-Qqe"]:
            return SimpleNamespace(stdout="hyprland\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    import phoenix.inventory as inventory
    monkeypatch.setattr(inventory.subprocess, "run", fake)

    counts = inventory.capture_packages()
    assert counts == {"native": 1, "aur": 0}
    assert (phoenix_repo / "packages" / "aur.txt").read_text() == "\n"
