"""
Phoenix CLI.

Volontairement en argparse pur (stdlib) : zéro dépendance à installer
sur une machine qui vient d'être réinstallée. C'est justement le
scénario où Phoenix doit tourner sans friction.
"""
from __future__ import annotations

import argparse
import sys

from .diff import run_diff
from .divergence import run_status
from .dotdiff import print_content_diffs, resolve_interactive
from .reminder import DEFAULT_THRESHOLD_DAYS, run_reminder
from .restore import run_restore
from .rollback import list_snapshots, print_snapshots, rollback_to
from .snapshot import run_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phoenix", description="Clonage complet de config Arch.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("snapshot", help="Capture l'état complet du système et commit.")

    restore = sub.add_parser("restore", help="Réinstalle paquets, services et dotfiles depuis le repo.")
    restore.add_argument("--yes", action="store_true", help="Skip toutes les confirmations (non-interactif).")
    restore.add_argument("--skip-aur", action="store_true", help="N'installe pas les paquets AUR.")

    status = sub.add_parser("status", help="Compare le système actuel au dernier snapshot (lecture seule).")
    status.add_argument("--content", action="store_true", help="Affiche le diff textuel réel des dotfiles modifiés (DotDiff V2). Combiné avec --resolve : affiché juste avant chaque décision.")
    status.add_argument("--resolve", action="store_true", help="Résolution interactive fichier par fichier : garder le local ou revenir au snapshot (DotDiff V3).")

    diff = sub.add_parser("diff", help="Compare ce repo à un autre repo Phoenix (autre machine).")
    diff.add_argument("other_repo", help="Chemin vers le repo Phoenix de l'autre machine.")

    rollback = sub.add_parser("rollback", help="Revient à l'état d'un snapshot antérieur (repo seulement).")
    rollback.add_argument("commit", nargs="?", help="Hash du commit cible. Omis = affiche la liste.")
    rollback.add_argument("--yes", action="store_true", help="Skip la confirmation.")

    reminder = sub.add_parser("reminder", help="Rappelle si des dotfiles ont dérivé depuis trop longtemps sans nouveau snapshot (lecture seule).")
    reminder.add_argument("--days", type=int, default=DEFAULT_THRESHOLD_DAYS, help=f"Seuil en jours avant rappel (défaut : {DEFAULT_THRESHOLD_DAYS}).")
    reminder.add_argument("--quiet", action="store_true", help="Pas de sortie texte, juste le code de sortie (pour hooks/scripts).")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "snapshot":
        run_snapshot()
    elif args.command == "restore":
        run_restore(auto_yes=args.yes, skip_aur=args.skip_aur)
    elif args.command == "status":
        aligned, dot = run_status()
        if args.resolve:
            resolve_interactive(dot, show_content=args.content)
        elif args.content:
            print_content_diffs(dot)
        sys.exit(0 if aligned else 1)
    elif args.command == "diff":
        identical = run_diff(args.other_repo)
        sys.exit(0 if identical else 1)
    elif args.command == "rollback":
        if not args.commit:
            print_snapshots(list_snapshots())
            print("[phoenix] Usage : phoenix rollback <hash>")
            sys.exit(0)
        ok = rollback_to(args.commit, auto_yes=args.yes)
        sys.exit(0 if ok else 1)
    elif args.command == "reminder":
        ok = run_reminder(threshold_days=args.days, quiet=args.quiet)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
