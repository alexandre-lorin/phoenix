"""
Wrapper Git minimal. Pas de lib externe — subprocess suffit, ça évite
une dépendance pour trois commandes.
"""
from __future__ import annotations

import subprocess
from datetime import datetime

from .config import REPO_DIR


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_DIR), *args], capture_output=True, text=True)


def ensure_git_repo() -> None:
    if not (REPO_DIR / ".git").exists():
        _git("init")
        _git("config", "user.name", "phoenix")
        _git("config", "user.email", "phoenix@localhost")
        gitignore = REPO_DIR / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*.swp\n*~\n", encoding="utf-8")
        print(f"[phoenix] Repo Git initialisé dans {REPO_DIR}")


def commit_snapshot() -> str | None:
    """Commit tout ce qui a changé. Retourne le hash court, ou None si rien à commit."""
    ensure_git_repo()
    _git("add", "-A")

    status = _git("status", "--porcelain")
    if not status.stdout.strip():
        return None

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _git("commit", "-m", f"snapshot: {timestamp}")

    rev = _git("rev-parse", "--short", "HEAD")
    return rev.stdout.strip()


def commit_diffstat(rev: str) -> str:
    """Résumé `--stat` de ce qu'un commit a changé (fichiers touchés,
    +/- lignes). `git show` gère nativement le tout premier commit (sans
    parent) comme un diff contre l'arbre vide, pas besoin de cas spécial.

    Sert à répondre concrètement à "qu'est-ce que ce snapshot vient de
    committer ?" — savoir qu'un commit a eu lieu ne dit rien de son
    contenu tant qu'on n'a pas lancé `git log`/`git show` à la main."""
    result = _git("show", "--stat", "--format=", rev)
    return result.stdout.strip()


def last_snapshot_timestamp() -> datetime | None:
    """Date du dernier commit *de type snapshot* (message préfixé
    "snapshot: "), pas simplement le dernier commit du repo. `rollback`
    crée lui aussi un commit ("rollback: retour à l'état de ...") — s'il
    comptait comme un snapshot ici, quelqu'un qui rollback souvent sans
    jamais relancer un vrai `snapshot` verrait le compteur de dérive du
    reminder (V5) se réinitialiser à tort, alors que le système n'a
    jamais été re-capturé depuis le vrai dernier snapshot."""
    if not (REPO_DIR / ".git").exists():
        return None
    result = _git("log", "--format=%ct %s")
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        ts, _, subject = line.partition(" ")
        if subject.startswith("snapshot:"):
            return datetime.fromtimestamp(int(ts))
    return None
