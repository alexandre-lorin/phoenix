"""
V2 — Capture des services systemd activés.
"""
from __future__ import annotations

import subprocess

from .config import REPO_DIR, load_config


def _list_enabled(user: bool = False) -> list[str]:
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += ["list-unit-files", "--state=enabled", "--no-legend"]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    units = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        unit = line.split()[0]
        units.append(unit)
    return sorted(units)


def capture_services() -> dict[str, int]:
    cfg = load_config()
    svc_dir = REPO_DIR / "services"
    svc_dir.mkdir(parents=True, exist_ok=True)

    system_units = _list_enabled(user=False)
    (svc_dir / "system.txt").write_text("\n".join(system_units) + "\n", encoding="utf-8")

    counts = {"system": len(system_units), "user": 0}

    if cfg.include_user_services:
        user_units = _list_enabled(user=True)
        (svc_dir / "user.txt").write_text("\n".join(user_units) + "\n", encoding="utf-8")
        counts["user"] = len(user_units)

    return counts


if __name__ == "__main__":
    counts = capture_services()
    print(f"[phoenix] Services système : {counts['system']} | user : {counts['user']}")
