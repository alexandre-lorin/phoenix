"""
V0 — Inventaire des paquets.

pacman -Qqe   : tous les paquets installés explicitement (natifs + AUR).
pacman -Qqem  : sous-ensemble AUR/foreign uniquement.
On sépare les deux pour que le restore sache quoi passer à pacman
vs à un AUR helper (yay/paru).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .config import REPO_DIR


def _run(cmd: list[str]) -> list[str]:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return [line for line in result.stdout.strip().splitlines() if line]


def capture_packages() -> dict[str, int]:
    """Écrit repo/packages/pacman.txt et repo/packages/aur.txt. Retourne les compteurs."""
    pkg_dir = REPO_DIR / "packages"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    all_explicit = _run(["pacman", "-Qqe"])
    aur_foreign = set(_run(["pacman", "-Qqem"]))
    native = sorted(set(all_explicit) - aur_foreign)
    aur = sorted(aur_foreign)

    (pkg_dir / "pacman.txt").write_text("\n".join(native) + "\n", encoding="utf-8")
    (pkg_dir / "aur.txt").write_text("\n".join(aur) + "\n", encoding="utf-8")

    return {"native": len(native), "aur": len(aur)}


if __name__ == "__main__":
    counts = capture_packages()
    print(f"[phoenix] Paquets natifs : {counts['native']} | AUR : {counts['aur']}")
