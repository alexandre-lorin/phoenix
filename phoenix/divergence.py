"""
V5 — Détection de divergence.

Objectif : répondre à "qu'est-ce qui a changé sur le système depuis mon
dernier snapshot ?" AVANT que restore écrase quoi que ce soit à l'aveugle.

Trois axes, tous en lecture seule — aucune écriture sur le système ici :
- paquets : installés à la main depuis le dernier snapshot, ou supprimés
- services : activés/désactivés à la main
- dotfiles : contenu modifié depuis la dernière capture (hash-based)

`phoenix status` expose ça. Code de sortie 0 = rien n'a bougé,
1 = divergence détectée (exploitable dans un script/hook pre-restore).
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_DIR, load_config
from .dotfiles import load_manifest


# ---------------------------------------------------------------------------
# Paquets
# ---------------------------------------------------------------------------

@dataclass
class PackageDiff:
    added: set[str] = field(default_factory=set)    # installés à la main, pas dans le snapshot
    removed: set[str] = field(default_factory=set)   # dans le snapshot, plus installés


def _current_explicit_and_aur() -> tuple[set[str], set[str]]:
    all_explicit = set(subprocess.run(
        ["pacman", "-Qqe"], capture_output=True, text=True, check=True
    ).stdout.strip().splitlines())
    aur_foreign = set(subprocess.run(
        ["pacman", "-Qqem"], capture_output=True, text=True, check=True
    ).stdout.strip().splitlines())
    native = all_explicit - aur_foreign
    return native, aur_foreign


def diff_packages() -> dict[str, PackageDiff]:
    pkg_dir = REPO_DIR / "packages"
    current_native, current_aur = _current_explicit_and_aur()

    result = {}
    for label, current, filename in (
        ("native", current_native, "pacman.txt"),
        ("aur", current_aur, "aur.txt"),
    ):
        f = pkg_dir / filename
        stored = set(f.read_text().splitlines()) if f.exists() else set()
        stored = {s for s in stored if s}
        result[label] = PackageDiff(
            added=current - stored,
            removed=stored - current,
        )
    return result


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

@dataclass
class ServiceDiff:
    added: set[str] = field(default_factory=set)
    removed: set[str] = field(default_factory=set)


def _current_enabled(user: bool = False) -> set[str]:
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += ["list-unit-files", "--state=enabled", "--no-legend"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {line.split()[0] for line in result.stdout.strip().splitlines() if line.strip()}


def diff_services() -> dict[str, ServiceDiff]:
    """Diff les services système systématiquement. Les services `--user` ne
    sont diffés que si `include_user_services` est activé dans phoenix.toml —
    sinon la comparaison se ferait contre un `user.txt` jamais mis à jour
    (ou jamais écrit), et remonterait des divergences fantômes pour des
    unités que l'utilisateur n'a jamais demandé de suivre."""
    cfg = load_config()
    svc_dir = REPO_DIR / "services"
    result = {}

    axes = [("system", False, "system.txt")]
    if cfg.include_user_services:
        axes.append(("user", True, "user.txt"))

    for label, user, filename in axes:
        f = svc_dir / filename
        stored = set(f.read_text().splitlines()) if f.exists() else set()
        stored = {s for s in stored if s}
        current = _current_enabled(user=user)
        result[label] = ServiceDiff(
            added=current - stored,
            removed=stored - current,
        )
    return result


# ---------------------------------------------------------------------------
# Dotfiles (hash-based)
# ---------------------------------------------------------------------------

@dataclass
class DotfilesDiff:
    modified: list[str] = field(default_factory=list)  # existe des deux côtés, contenu différent
    added: list[str] = field(default_factory=list)      # présent en live, absent du snapshot
    removed: list[str] = field(default_factory=list)    # présent dans le snapshot, absent en live


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _hash_tree(root: Path, exclude_patterns: list[str]) -> dict[str, str]:
    """Hash chaque fichier sous `root`, sauf ceux exclus par `exclude_patterns`.

    Élague les dossiers exclus (`dirnames[:] = ...`) AVANT qu'os.walk n'y
    descende, plutôt que de parcourir tout l'arbre (`rglob("*")`) et filtrer
    après coup. Sans ça, un dossier volumineux exclu par pattern (cache de
    plugin manager, node_modules...) était quand même intégralement listé
    à chaque `phoenix status` — coût I/O payé pour rien, potentiellement
    plusieurs secondes sur un dossier à plusieurs dizaines de milliers de
    fichiers, même si aucun de ses fichiers n'était jamais hashé."""
    hashes: dict[str, str] = {}
    if root.is_file():
        hashes["."] = _sha256(root)
        return hashes

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _matches_any(d, exclude_patterns)]
        for filename in filenames:
            if _matches_any(filename, exclude_patterns):
                continue
            path = Path(dirpath) / filename
            hashes[str(path.relative_to(root))] = _sha256(path)
    return hashes


def diff_dotfiles() -> dict[str, DotfilesDiff]:
    cfg = load_config()
    manifest = load_manifest()
    dotfiles_root = REPO_DIR / "dotfiles"

    result: dict[str, DotfilesDiff] = {}

    for name, original_path in manifest.items():
        live = Path(original_path).expanduser()
        stored = dotfiles_root / name

        d = DotfilesDiff()

        if not live.exists() and not stored.exists():
            result[name] = d
            continue
        if not live.exists():
            d.removed.append("(tout le chemin — absent du système)")
            result[name] = d
            continue
        if not stored.exists():
            d.added.append("(tout le chemin — jamais capturé)")
            result[name] = d
            continue

        live_hashes = _hash_tree(live, cfg.exclude_patterns)
        stored_hashes = _hash_tree(stored, cfg.exclude_patterns)

        for rel, h in live_hashes.items():
            if rel not in stored_hashes:
                d.added.append(rel)
            elif stored_hashes[rel] != h:
                d.modified.append(rel)
        for rel in stored_hashes:
            if rel not in live_hashes:
                d.removed.append(rel)

        result[name] = d

    return result


# ---------------------------------------------------------------------------
# Rapport
# ---------------------------------------------------------------------------

def has_any_divergence(pkg: dict, svc: dict, dot: dict) -> bool:
    for d in pkg.values():
        if d.added or d.removed:
            return True
    for d in svc.values():
        if d.added or d.removed:
            return True
    for d in dot.values():
        if d.added or d.removed or d.modified:
            return True
    return False


def print_report(pkg: dict, svc: dict, dot: dict) -> None:
    print("[phoenix] === Paquets ===")
    for label, d in pkg.items():
        if not d.added and not d.removed:
            print(f"  {label}: OK, rien de divergent")
            continue
        if d.added:
            print(f"  {label}: +{len(d.added)} installés à la main → {sorted(d.added)}")
        if d.removed:
            print(f"  {label}: -{len(d.removed)} désinstallés depuis le snapshot → {sorted(d.removed)}")

    print("[phoenix] === Services ===")
    for label, d in svc.items():
        if not d.added and not d.removed:
            print(f"  {label}: OK, rien de divergent")
            continue
        if d.added:
            print(f"  {label}: +{len(d.added)} activés à la main → {sorted(d.added)}")
        if d.removed:
            print(f"  {label}: -{len(d.removed)} désactivés depuis le snapshot → {sorted(d.removed)}")

    print("[phoenix] === Dotfiles ===")
    for name, d in dot.items():
        if not d.added and not d.removed and not d.modified:
            print(f"  {name}: OK, rien de divergent")
            continue
        if d.modified:
            print(f"  {name}: {len(d.modified)} fichier(s) modifié(s) → {d.modified}")
        if d.added:
            print(f"  {name}: {len(d.added)} fichier(s) nouveau(x), pas dans le dernier snapshot → {d.added}")
        if d.removed:
            print(f"  {name}: {len(d.removed)} fichier(s) supprimé(s) depuis le snapshot → {d.removed}")


def run_status() -> tuple[bool, dict[str, DotfilesDiff]]:
    """Retourne (True si tout est aligné, le diff dotfiles déjà calculé).

    Le diff dotfiles est renvoyé pour que l'appelant (`phoenix status
    --content`/`--resolve`) puisse le réutiliser au lieu de rappeler
    `diff_dotfiles()` une seconde fois — hasher tout l'arbre des dotfiles
    deux fois pour une seule invocation de `status` était du travail
    redondant, même une fois `_hash_tree` élagué correctement."""
    pkg = diff_packages()
    svc = diff_services()
    dot = diff_dotfiles()

    print_report(pkg, svc, dot)

    diverged = has_any_divergence(pkg, svc, dot)
    if diverged:
        print("[phoenix] ⚠ Divergence détectée — `phoenix snapshot` avant tout `restore` pour ne rien perdre.")
    else:
        print("[phoenix] ✓ Système aligné avec le dernier snapshot.")
    return not diverged, dot
