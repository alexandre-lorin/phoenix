"""
V3 — `phoenix snapshot`

Déclenche V0 (paquets) + V1 (dotfiles) + V2 (services), puis commit.

Si la capture des dotfiles refuse (collision de basename détectée —
voir DotfilesCollisionError dans dotfiles.py), on stoppe avant le commit :
paquets/services peuvent déjà être écrits sur disque à ce stade, mais rien
n'est committé tant que la capture entière n'a pas réussi. Le prochain
snapshot réussi les récupérera normalement — pas de commit corrompu ou
partiel, juste un repo avec des fichiers non commités en attendant.
"""
from __future__ import annotations

import sys

from .config import ensure_repo_initialized
from .dotfiles import DotfilesCollisionError, capture_dotfiles
from .git_utils import commit_diffstat, commit_snapshot
from .inventory import capture_packages
from .services import capture_services


def run_snapshot() -> None:
    ensure_repo_initialized()

    print("[phoenix] Capture paquets...")
    pkg_counts = capture_packages()
    print(f"  → natifs: {pkg_counts['native']} | AUR: {pkg_counts['aur']}")

    print("[phoenix] Capture dotfiles...")
    try:
        dot_results = capture_dotfiles()
    except DotfilesCollisionError as e:
        print(f"[phoenix] ✗ Capture des dotfiles refusée :\n{e}")
        print("[phoenix] Snapshot annulé — corrige phoenix.toml puis relance.")
        sys.exit(1)

    for path, status in dot_results.items():
        marker = "✓" if status.startswith("OK") else "✗"
        print(f"  {marker} {path} — {status}")

    print("[phoenix] Capture services...")
    svc_counts = capture_services()
    print(f"  → système: {svc_counts['system']} | user: {svc_counts['user']}")

    print("[phoenix] Commit...")
    rev = commit_snapshot()
    if rev:
        print(f"[phoenix] Snapshot committé : {rev}")
        stat = commit_diffstat(rev)
        if stat:
            print(stat)
    else:
        print("[phoenix] Rien de nouveau depuis le dernier snapshot.")
