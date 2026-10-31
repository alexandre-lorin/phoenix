"""
`phoenix rollback` — le point 4 du brief d'origine, jamais formalisé
comme item de roadmap mais explicitement demandé :
"Permet un snapshot avant/après pour tester une modif risquée sans
perdre l'état précédent."

Principe : le repo Git EST déjà l'historique. Rollback ne fait que
ramener packages/services/dotfiles à l'état d'un commit antérieur,
puis commit ce retour comme un nouveau point (jamais de perte
d'historique — `git log` garde tout, y compris le rollback lui-même).

`git checkout <ref> -- <path>` seul ne suffit PAS pour ça : en mode
"overlay" (le défaut), il met à jour les fichiers qui existent à <ref>
mais ne supprime jamais ceux qui ont été ajoutés dans des commits
ultérieurs. Un fichier ajouté après le commit cible survivrait donc au
"rollback", qui ne serait alors qu'un rollback partiel silencieux — exactement
le genre de garantie cassée qu'on ne peut pas se permettre sur cette commande.
`--no-overlay` resynchronise l'arbre exactement : tout ce qui n'existe pas
à <ref> sous les chemins donnés est supprimé du disque ET de l'index.

Ça ne touche PAS le système live. Après rollback, il faut lancer
`phoenix restore` pour appliquer l'état revenu en arrière au système.
Séparer les deux évite qu'un rollback foire silencieusement en
mélangeant "changer d'avis sur le repo" et "toucher au système".
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .config import REPO_DIR
from .prompts import confirm


@dataclass
class SnapshotEntry:
    commit_hash: str
    date: str
    message: str


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO_DIR), *args], capture_output=True, text=True)


def list_snapshots(limit: int = 15) -> list[SnapshotEntry]:
    result = _git("log", f"-n{limit}", "--date=short", "--format=%h|%ad|%s")
    entries = []
    for line in result.stdout.strip().splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            entries.append(SnapshotEntry(commit_hash=parts[0], date=parts[1], message=parts[2]))
    return entries


def print_snapshots(entries: list[SnapshotEntry]) -> None:
    if not entries:
        print("[phoenix] Aucun snapshot dans l'historique.")
        return
    print("[phoenix] Historique des snapshots :")
    for e in entries:
        print(f"  {e.commit_hash}  {e.date}  {e.message}")


def rollback_to(commit_ref: str, auto_yes: bool = False) -> bool:
    """Ramène packages/services/dotfiles/phoenix.toml à l'état EXACT d'un
    commit antérieur (fichiers ajoutés après <commit_ref> supprimés, pas
    seulement fichiers modifiés écrasés). Retourne True si effectué,
    False si annulé ou en erreur."""

    check = _git("cat-file", "-e", commit_ref)
    if check.returncode != 0:
        print(f"[phoenix] Commit introuvable : {commit_ref}")
        return False

    show = _git("show", "-s", "--format=%h %ad %s", "--date=short", commit_ref)
    print(f"[phoenix] Cible du rollback : {show.stdout.strip()}")

    if not confirm(
        f"Ramener le repo à l'état de {commit_ref} ? (le système live n'est PAS touché — il faudra `phoenix restore` après)",
        auto_yes,
    ):
        print("[phoenix] Rollback annulé.")
        return False

    checkout_targets = ["packages", "services", "dotfiles", "phoenix.toml"]
    existing_at_ref = []
    for target in checkout_targets:
        probe = _git("cat-file", "-e", f"{commit_ref}:{target}")
        if probe.returncode == 0:
            existing_at_ref.append(target)

    if not existing_at_ref:
        print(f"[phoenix] Aucun des chemins attendus n'existe dans {commit_ref} — rien à restaurer.")
        return False

    # --no-overlay : synchronise l'arbre exactement, supprime ce qui a été
    # ajouté après commit_ref plutôt que de le laisser traîner (voir docstring).
    checkout = _git("checkout", "--no-overlay", commit_ref, "--", *existing_at_ref)
    if checkout.returncode != 0:
        print(f"[phoenix] Échec du checkout : {checkout.stderr.strip()}")
        return False

    _git("add", "-A")
    status = _git("status", "--porcelain")
    if not status.stdout.strip():
        print("[phoenix] Le repo était déjà dans cet état — rien à committer.")
        return True

    _git("commit", "-m", f"rollback: retour à l'état de {commit_ref}")
    rev = _git("rev-parse", "--short", "HEAD")
    print(f"[phoenix] Rollback effectué et committé : {rev.stdout.strip()}")
    print("[phoenix] Le système live n'a pas bougé — lance `phoenix restore` pour l'appliquer.")
    return True
