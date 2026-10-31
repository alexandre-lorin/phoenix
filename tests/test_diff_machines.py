import json
from pathlib import Path


def _write_snapshot(repo: Path, *, native: list[str], aur: list[str],
                     system_svc: list[str], hypr_content: str) -> None:
    (repo / "packages").mkdir(parents=True, exist_ok=True)
    (repo / "packages" / "pacman.txt").write_text("\n".join(native) + "\n")
    (repo / "packages" / "aur.txt").write_text("\n".join(aur) + "\n")
    (repo / "services").mkdir(exist_ok=True)
    (repo / "services" / "system.txt").write_text("\n".join(system_svc) + "\n")
    (repo / "services" / "user.txt").write_text("")
    (repo / "dotfiles" / "hypr").mkdir(parents=True, exist_ok=True)
    (repo / "dotfiles" / "hypr" / "hyprland.conf").write_text(hypr_content)
    (repo / "dotfiles" / "manifest.json").write_text(
        json.dumps({"hypr": "/home/user/.config/hypr"})
    )


def test_identical_machines_report_no_divergence(phoenix_repo, tmp_path):
    other = tmp_path / "other_repo"
    for repo in (phoenix_repo, other):
        _write_snapshot(
            repo, native=["hyprland", "waybar"], aur=["spotify"],
            system_svc=["NetworkManager.service"], hypr_content="monitor=DP-1,1920x1080,0x0,1",
        )

    import phoenix.diff as diff
    identical = diff.run_diff(str(other))
    assert identical is True


def test_divergent_machines_are_detected(phoenix_repo, tmp_path):
    other = tmp_path / "other_repo"
    _write_snapshot(
        phoenix_repo, native=["hyprland", "waybar"], aur=["spotify"],
        system_svc=["NetworkManager.service", "bluetooth.service"],
        hypr_content="monitor=DP-1,1920x1080,0x0,1",
    )
    _write_snapshot(
        other, native=["hyprland", "waybar", "docker"], aur=[],
        system_svc=["NetworkManager.service"],
        hypr_content="monitor=DP-1,2560x1440,0x0,1",
    )

    import phoenix.diff as diff
    pkg = diff.diff_packages(other)
    svc = diff.diff_services(other)
    dot = diff.diff_dotfiles(other)

    assert "docker" in pkg["native"].only_there
    assert "spotify" in pkg["aur"].only_here
    assert "bluetooth.service" in svc["system"].only_here
    assert "hyprland.conf" in dot["hypr"].differing_files
