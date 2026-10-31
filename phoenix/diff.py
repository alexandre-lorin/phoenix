"""
V6 — `phoenix diff <autre_repo>`

Compare DEUX repos Phoenix déjà snapshotés — pas deux systèmes live.
Raison : rien ne garantit que les deux machines tournent en même temps
ou soient accessibles simultanément. Le repo Git est la seule source
de vérité qu'on peut toujours comparer, via un clone local, un remote
pull, une clé USB — peu importe le transport.

Usage typique :
  git clone <remote-du-poste-2> /tmp/poste2-config
  phoenix diff /tmp/poste2-config
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_DIR


@dataclass
class SetDiff:
    only_here: set[str] = field(default_factory=set)
    only_there: set[str] = field(default_factory=set)


def _read_lines(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line for line in path.read_text().splitlines() if line}


def diff_packages(other_repo: Path) -> dict[str, SetDiff]:
    result = {}
    for label, filename in (("native", "pacman.txt"), ("aur", "aur.txt")):
        here = _read_lines(REPO_DIR / "packages" / filename)
        there = _read_lines(other_repo / "packages" / filename)
        result[label] = SetDiff(only_here=here - there, only_there=there - here)
    return result


def diff_services(other_repo: Path) -> dict[str, SetDiff]:
    result = {}
    for label, filename in (("system", "system.txt"), ("user", "user.txt")):
        here = _read_lines(REPO_DIR / "services" / filename)
        there = _read_lines(other_repo / "services" / filename)
        result[label] = SetDiff(only_here=here - there, only_there=there - here)
    return result


def _load_manifest(repo: Path) -> dict[str, str]:
    f = repo / "dotfiles" / "manifest.json"
    if not f.exists():
        return {}
    return json.loads(f.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not root.exists():
        return hashes
    if root.is_file():
        hashes["."] = _sha256(root)
        return hashes
    for path in root.rglob("*"):
        if path.is_file():
            hashes[str(path.relative_to(root))] = _sha256(path)
    return hashes


@dataclass
class DotfilesMachineDiff:
    only_here: list[str] = field(default_factory=list)     # ce nom de config n'existe que sur cette machine
    only_there: list[str] = field(default_factory=list)    # n'existe que sur l'autre
    differing_files: list[str] = field(default_factory=list)  # même config des deux côtés, contenu différent


def diff_dotfiles(other_repo: Path) -> dict[str, DotfilesMachineDiff]:
    manifest_here = _load_manifest(REPO_DIR)
    manifest_there = _load_manifest(other_repo)

    all_names = set(manifest_here) | set(manifest_there)
    result: dict[str, DotfilesMachineDiff] = {}

    for name in sorted(all_names):
        d = DotfilesMachineDiff()

        if name not in manifest_there:
            d.only_here.append(name)
            result[name] = d
            continue
        if name not in manifest_here:
            d.only_there.append(name)
            result[name] = d
            continue

        here_hashes = _hash_tree(REPO_DIR / "dotfiles" / name)
        there_hashes = _hash_tree(other_repo / "dotfiles" / name)

        all_files = set(here_hashes) | set(there_hashes)
        for rel in sorted(all_files):
            if here_hashes.get(rel) != there_hashes.get(rel):
                label = rel if rel != "." else name
                d.differing_files.append(label)

        result[name] = d

    return result


def print_report(other_repo: Path, pkg: dict, svc: dict, dot: dict) -> None:
    print(f"[phoenix] Comparaison : {REPO_DIR} (ici) vs {other_repo} (là-bas)")

    print("[phoenix] === Paquets ===")
    for label, d in pkg.items():
        if not d.only_here and not d.only_there:
            print(f"  {label}: identiques")
            continue
        if d.only_here:
            print(f"  {label}: seulement ici (+{len(d.only_here)}) → {sorted(d.only_here)}")
        if d.only_there:
            print(f"  {label}: seulement là-bas (+{len(d.only_there)}) → {sorted(d.only_there)}")

    print("[phoenix] === Services ===")
    for label, d in svc.items():
        if not d.only_here and not d.only_there:
            print(f"  {label}: identiques")
            continue
        if d.only_here:
            print(f"  {label}: seulement ici → {sorted(d.only_here)}")
        if d.only_there:
            print(f"  {label}: seulement là-bas → {sorted(d.only_there)}")

    print("[phoenix] === Dotfiles ===")
    for name, d in dot.items():
        if not d.only_here and not d.only_there and not d.differing_files:
            print(f"  {name}: identique")
            continue
        if d.only_here:
            print(f"  {name}: n'existe que sur cette machine")
        if d.only_there:
            print(f"  {name}: n'existe que sur l'autre machine")
        if d.differing_files:
            print(f"  {name}: contenu différent → {d.differing_files}")


def run_diff(other_repo_path: str) -> bool:
    """Retourne True si les deux repos sont identiques, False sinon."""
    other_repo = Path(other_repo_path).expanduser().resolve()

    if not other_repo.exists():
        print(f"[phoenix] Repo introuvable : {other_repo}")
        return False

    pkg = diff_packages(other_repo)
    svc = diff_services(other_repo)
    dot = diff_dotfiles(other_repo)

    print_report(other_repo, pkg, svc, dot)

    identical = all(not d.only_here and not d.only_there for d in pkg.values())
    identical &= all(not d.only_here and not d.only_there for d in svc.values())
    identical &= all(not d.only_here and not d.only_there and not d.differing_files for d in dot.values())

    print("[phoenix] ✓ Machines identiques." if identical else "[phoenix] ⚠ Divergence entre les deux machines.")
    return identical
