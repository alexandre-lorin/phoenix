"""
V1 — Capture des dotfiles.

Copie chaque chemin listé dans phoenix.toml vers repo/dotfiles/<nom>,
en excluant le bruit (cache, logs, .git interne, etc.).

Un manifest.json garde la correspondance nom → chemin d'origine complet.
Sans lui, le restore (V4) ne peut pas savoir où replacer les choses —
"hypr" doit retourner dans ~/.config/hypr, pas dans ~/hypr.

La clé du manifest est `src.name` (la feuille du chemin, ex. "nvim" pour
~/.config/nvim). Deux chemins configurés avec la même feuille collisionnent
donc sur la même clé — et donc sur le même dossier dest_root/<nom>. C'est
irrécupérable : le second écrase le premier avant même que Git n'ait vu
passer le premier, il n'y a rien à restaurer après coup. D'où le choix
fail-closed : on détecte la collision AVANT de copier quoi que ce soit et
on arrête tout, plutôt qu'un avertissement qu'on peut ignorer par erreur.
"""
from __future__ import annotations

import fnmatch
import json
import shutil
from collections import defaultdict
from pathlib import Path

from .config import REPO_DIR, load_config

MANIFEST_FILE = REPO_DIR / "dotfiles" / "manifest.json"


class DotfilesCollisionError(Exception):
    """Deux chemins configurés partagent la même feuille (basename) —
    ils écraseraient le même dossier dans le repo. Capture refusée."""


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _make_ignore(patterns: list[str]):
    def _ignore(directory: str, names: list[str]) -> set[str]:
        return {n for n in names if _matches_any(n, patterns)}
    return _ignore


def _detect_collisions(paths: list[str]) -> dict[str, list[str]]:
    """Regroupe les chemins configurés par basename. Retourne uniquement
    les groupes avec 2+ chemins distincts (les vraies collisions)."""
    by_name: dict[str, list[str]] = defaultdict(list)
    for raw_path in paths:
        name = Path(raw_path).expanduser().name
        by_name[name].append(raw_path)
    return {name: group for name, group in by_name.items() if len(group) > 1}


def capture_dotfiles() -> dict[str, str]:
    """Copie les chemins configurés. Retourne {chemin: statut}.

    Lève DotfilesCollisionError sans rien copier si deux chemins configurés
    partagent la même feuille — fail closed, pas de capture partielle."""
    cfg = load_config()

    collisions = _detect_collisions(cfg.dotfiles_paths)
    if collisions:
        lines = [
            f"  \"{name}\" : {' vs '.join(group)}"
            for name, group in sorted(collisions.items())
        ]
        raise DotfilesCollisionError(
            "Chemins en collision dans phoenix.toml — même nom de dossier/fichier final, "
            "capture refusée (le second écraserait le premier sans retour possible) :\n"
            + "\n".join(lines)
            + "\n→ Renomme un des deux dossiers, ou capture-les depuis un chemin parent commun."
        )

    dest_root = REPO_DIR / "dotfiles"
    dest_root.mkdir(parents=True, exist_ok=True)

    ignore = _make_ignore(cfg.exclude_patterns)
    results: dict[str, str] = {}
    manifest: dict[str, str] = {}

    for raw_path in cfg.dotfiles_paths:
        src = Path(raw_path).expanduser()
        if not src.exists():
            results[raw_path] = "ABSENT — skip"
            continue

        dest = dest_root / src.name
        manifest[src.name] = str(src)  # nom → chemin d'origine complet, résolu

        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest, ignore=ignore, symlinks=False)
            results[raw_path] = f"OK (dossier → {dest.relative_to(REPO_DIR)})"
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            results[raw_path] = f"OK (fichier → {dest.relative_to(REPO_DIR)})"

    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return results


def load_manifest() -> dict[str, str]:
    """Charge la correspondance nom → chemin d'origine, pour le restore."""
    if not MANIFEST_FILE.exists():
        return {}
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    for path, status in capture_dotfiles().items():
        print(f"[phoenix] {path} : {status}")
