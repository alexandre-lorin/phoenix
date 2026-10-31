"""
DotDiff V5 — rappel périodique.

Objectif du brief : notifier si des dotfiles ont dérivé depuis plus de
X jours sans nouveau snapshot. `phoenix status` répond déjà à "est-ce
que ça a dérivé ?" à l'instant T, mais rien ne rappelle qu'on n'a pas
relancé `snapshot` depuis un moment — ce module ajoute cet axe temporel.

Volontairement lecture seule, comme le reste de la détection de
divergence : ce module ne fait jamais de snapshot à la place de
l'utilisateur, il se contente de le rappeler.

Usage typique — pas un daemon, un simple hook périodique :

    # crontab -e (une fois par jour, par exemple)
    0 9 * * * PHOENIX_REPO=/home/user/phoenix-config /usr/bin/phoenix reminder

    # ou dans .bashrc/.zshrc, pour un rappel à chaque nouvelle session shell
    phoenix reminder --days 7 --quiet || echo "⚠ dotfiles en dérive, phoenix snapshot ?"

`phoenix reminder` seul seule affiche un message explicite ; `--quiet`
ne fait que fixer le code de sortie, pour scripting/hooks.
"""
from __future__ import annotations

from datetime import datetime

from .divergence import diff_dotfiles
from .git_utils import last_snapshot_timestamp

DEFAULT_THRESHOLD_DAYS = 7


def _dotfiles_have_diverged() -> bool:
    dot = diff_dotfiles()
    return any(d.added or d.removed or d.modified for d in dot.values())


def days_since_last_snapshot(now: datetime | None = None) -> int | None:
    """None si aucun snapshot n'a jamais été fait (rien à comparer)."""
    last = last_snapshot_timestamp()
    if last is None:
        return None
    now = now or datetime.now()
    return (now - last).days


def should_remind(threshold_days: int = DEFAULT_THRESHOLD_DAYS, now: datetime | None = None) -> tuple[bool, int | None]:
    """Retourne (faut_il_rappeler, jours_depuis_dernier_snapshot).

    Rappelle seulement si LES DEUX conditions sont vraies :
    - les dotfiles ont dérivé du dernier snapshot (pas paquets/services — V5
      du brief cible spécifiquement les dotfiles)
    - ça fait plus de `threshold_days` jours que le dernier snapshot
    Une dérive fraîche (< seuil) n'est pas encore un problème, elle sera
    absorbée au prochain `phoenix snapshot` normal."""
    days = days_since_last_snapshot(now)
    if days is None:
        return False, None
    if days < threshold_days:
        return False, days
    if not _dotfiles_have_diverged():
        return False, days
    return True, days


def run_reminder(threshold_days: int = DEFAULT_THRESHOLD_DAYS, quiet: bool = False) -> bool:
    """Retourne True si rien à signaler, False si le rappel doit se déclencher
    (code de sortie 1 côté CLI — exploitable en hook shell/cron)."""
    fire, days = should_remind(threshold_days)

    if days is None:
        if not quiet:
            print("[phoenix] Aucun snapshot trouvé — lance `phoenix snapshot` pour commencer.")
        return True

    if not fire:
        if not quiet:
            print(f"[phoenix] ✓ Dernier snapshot il y a {days} jour(s) (seuil {threshold_days}j) — rien à signaler.")
        return True

    if not quiet:
        print(
            f"[phoenix] ⚠ Dotfiles en dérive depuis plus de {threshold_days} jours "
            f"(dernier snapshot il y a {days} jours)."
        )
        print("[phoenix]   → `phoenix status --content` pour voir le détail, "
              "`phoenix snapshot` pour les capturer.")
    return False
