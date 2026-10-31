"""
V4 — `phoenix restore`

Ordre imposé par la logique de dépendance, pas arbitraire :
1. Paquets d'abord — sans eux, les services/binaires référencés par les
   dotfiles n'existent pas encore (ex: waybar config sans waybar installé).
2. Services ensuite — ils dépendent des paquets, pas des dotfiles.
3. Dotfiles en dernier — c'est la couche la plus fréquemment modifiable
   par erreur, donc la plus dangereuse : elle passe en dernier et
   sauvegarde systématiquement ce qu'elle écrase.

Chaque étape destructive demande confirmation, sauf si --yes est passé.

`--yes` doit vouloir dire "ne me demande RIEN", pas juste "ne me demande
rien depuis Phoenix, mais pacman va prendre le relais tout seul". Donc
`auto_yes=True` propage `--noconfirm` à pacman/yay/paru, pas seulement
un bypass du `confirm()` interne — sinon un restore lancé sans supervision
(script de provisioning, VM de test) reste bloqué sur une invite qui
n'appartient pas à Phoenix.
Seule exception assumée : `sudo` lui-même peut demander un mot de passe.
Ce n'est pas une confirmation d'action, c'est une frontière d'authentification
— hors du périmètre de ce que `--yes` peut ou doit contourner. Un restore
vraiment non supervisé suppose un sudo sans mot de passe (NOPASSWD) déjà
configuré par ailleurs.

Robustesse (deuxième passe après l'audit de fiabilité) : un `restore` sert
justement le plus souvent des mois après le snapshot, sur une machine neuve
— exactement le moment où un paquet a été renommé/retiré des dépôts, ou où
une unité systemd a disparu avec son paquet. Un seul paquet/service fautif
ne doit plus faire échouer tout le lot :
- paquets/AUR : tentative en lot (rapide, cas normal), et seulement si ça
  échoue, retry un par un pour isoler précisément le(s) fautif(s).
- services : même logique, stderr de systemctl capturé et remonté au lieu
  d'être avalé silencieusement (`check=False` seul ne disait jamais pourquoi).
`run_restore` termine sur un résumé et un code de sortie qui reflète l'état
réel (0 si tout est passé, 1 s'il y a eu des échecs isolés) — pas un simple
"terminé" qui masquerait des paquets jamais installés.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .config import REPO_DIR, load_config
from .dotfiles import load_manifest
from .prompts import confirm


# ---------------------------------------------------------------------------
# Résultats structurés — pour le résumé final de run_restore
# ---------------------------------------------------------------------------

@dataclass
class PackageRestoreResult:
    installed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


@dataclass
class ServiceRestoreResult:
    enabled: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


@dataclass
class DotfilesRestoreResult:
    restored: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed


# ---------------------------------------------------------------------------
# Paquets
# ---------------------------------------------------------------------------

def _installed_packages() -> set[str]:
    result = subprocess.run(["pacman", "-Qq"], capture_output=True, text=True, check=True)
    return set(result.stdout.strip().splitlines())


def _detect_aur_helper() -> str | None:
    for helper in ("yay", "paru"):
        if shutil.which(helper):
            return helper
    return None


def _bootstrap_aur_helper() -> None:
    """Aucun AUR helper détecté : on n'en installe plus un automatiquement.

    Version précédente : clonait `yay-bin` depuis l'AUR et lançait
    `makepkg -si --noconfirm` avec sudo pour compiler et installer un
    paquet tiers non vérifié — trop invasif pour un outil dont le rôle
    est de restaurer *ta* config, pas d'installer un gestionnaire de
    paquets à ta place. Recommandation actée suite à l'audit de fiabilité :
    se contenter de prévenir et de laisser l'installation à l'utilisateur."""
    print(
        "[phoenix] Aucun AUR helper détecté (yay/paru). "
        "Paquets AUR ignorés — installe yay ou paru manuellement puis relance `phoenix restore`."
    )


def _install_with_isolation(cmd_prefix: list[str], packages: list[str], auto_yes: bool) -> tuple[list[str], list[str]]:
    """Installe `packages` via `cmd_prefix` (pacman -S --needed / yay -S --needed).
    Tente d'abord tout en un seul appel — le cas normal, rapide. Si ce lot
    échoue (un seul paquet introuvable/renommé suffit à faire échouer pacman
    en bloc), retente un par un pour isoler précisément le(s) fautif(s) au
    lieu de faire planter tout le restore. Retourne (installés, échoués)."""
    cmd = [*cmd_prefix, "--noconfirm"] if auto_yes else list(cmd_prefix)

    batch = subprocess.run([*cmd, *packages], capture_output=True, text=True)
    if batch.returncode == 0:
        return list(packages), []

    installed, failed = [], []
    for pkg in packages:
        r = subprocess.run([*cmd, pkg], capture_output=True, text=True)
        if r.returncode == 0:
            installed.append(pkg)
        else:
            failed.append(pkg)
            detail = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "échec inconnu"
            print(f"  ⚠ {pkg} : {detail}")
    return installed, failed


def restore_packages(auto_yes: bool = False, skip_aur: bool = False) -> PackageRestoreResult:
    pkg_dir = REPO_DIR / "packages"
    native_file = pkg_dir / "pacman.txt"
    aur_file = pkg_dir / "aur.txt"

    result = PackageRestoreResult()
    already = _installed_packages()

    if native_file.exists():
        native = [p for p in native_file.read_text().splitlines() if p]
        missing = [p for p in native if p not in already]
        if missing:
            print(f"[phoenix] {len(missing)} paquets natifs manquants sur {len(native)}.")
            if confirm(f"Installer {len(missing)} paquets via pacman ?", auto_yes):
                installed, failed = _install_with_isolation(
                    ["sudo", "pacman", "-S", "--needed"], missing, auto_yes
                )
                result.installed += installed
                result.failed += failed
                if failed:
                    print(f"[phoenix] ⚠ {len(failed)} paquet(s) natif(s) non installé(s) : {failed}")
        else:
            print("[phoenix] Paquets natifs : rien à installer.")

    if skip_aur:
        print("[phoenix] --skip-aur : paquets AUR ignorés.")
        return result

    if aur_file.exists():
        aur = [p for p in aur_file.read_text().splitlines() if p]
        missing_aur = [p for p in aur if p not in already]
        if not missing_aur:
            print("[phoenix] Paquets AUR : rien à installer.")
            return result

        helper = _detect_aur_helper()
        if not helper:
            _bootstrap_aur_helper()
            return result

        print(f"[phoenix] {len(missing_aur)} paquets AUR manquants sur {len(aur)}.")
        if confirm(f"Installer {len(missing_aur)} paquets AUR via {helper} ?", auto_yes):
            installed, failed = _install_with_isolation([helper, "-S", "--needed"], missing_aur, auto_yes)
            result.installed += installed
            result.failed += failed
            if failed:
                print(f"[phoenix] ⚠ {len(failed)} paquet(s) AUR non installé(s) : {failed}")

    return result


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
# `systemctl enable` ne demande jamais de confirmation interactive par
# lui-même (contrairement à pacman/yay) — rien à propager ici au-delà du
# `confirm()` interne de Phoenix, déjà couvert par `auto_yes`. Vérifié
# explicitement plutôt que supposé, dans le cadre du même audit que pacman.
#
# En revanche l'appel précédent (`check=False` sans lire stderr) avalait
# silencieusement toute erreur — une unité masquée ou absente semblait
# "activée" du point de vue de l'utilisateur. Même stratégie d'isolation
# que les paquets : lot d'abord, puis un par un si le lot échoue, avec le
# détail de l'erreur affiché plutôt qu'ignoré.

def _currently_enabled(user: bool = False) -> set[str]:
    cmd = ["systemctl"]
    if user:
        cmd.append("--user")
    cmd += ["list-unit-files", "--state=enabled", "--no-legend"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return {line.split()[0] for line in result.stdout.strip().splitlines() if line.strip()}


def _enable_with_isolation(cmd_prefix: list[str], units: list[str]) -> tuple[list[str], list[str]]:
    batch = subprocess.run([*cmd_prefix, *units], capture_output=True, text=True)
    if batch.returncode == 0:
        return list(units), []

    enabled, failed = [], []
    for unit in units:
        r = subprocess.run([*cmd_prefix, unit], capture_output=True, text=True)
        if r.returncode == 0:
            enabled.append(unit)
        else:
            failed.append(unit)
            detail = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "échec inconnu"
            print(f"  ⚠ {unit} : {detail}")
    return enabled, failed


def restore_services(auto_yes: bool = False) -> ServiceRestoreResult:
    svc_dir = REPO_DIR / "services"
    result = ServiceRestoreResult()

    system_file = svc_dir / "system.txt"
    if system_file.exists():
        wanted = {u for u in system_file.read_text().splitlines() if u}
        missing = sorted(wanted - _currently_enabled(user=False))
        if missing:
            print(f"[phoenix] {len(missing)} services système à activer.")
            if confirm(f"Activer {len(missing)} services système ?", auto_yes):
                enabled, failed = _enable_with_isolation(["sudo", "systemctl", "enable"], missing)
                result.enabled += enabled
                result.failed += failed
                if failed:
                    print(f"[phoenix] ⚠ {len(failed)} service(s) système non activé(s) : {failed}")
        else:
            print("[phoenix] Services système : rien à activer.")

    user_file = svc_dir / "user.txt"
    if user_file.exists():
        wanted = {u for u in user_file.read_text().splitlines() if u}
        missing = sorted(wanted - _currently_enabled(user=True))
        if missing:
            print(f"[phoenix] {len(missing)} services --user à activer.")
            if confirm(f"Activer {len(missing)} services --user ?", auto_yes):
                enabled, failed = _enable_with_isolation(["systemctl", "--user", "enable"], missing)
                result.enabled += enabled
                result.failed += failed
                if failed:
                    print(f"[phoenix] ⚠ {len(failed)} service(s) --user non activé(s) : {failed}")
        else:
            print("[phoenix] Services --user : rien à activer.")

    return result


# ---------------------------------------------------------------------------
# Dotfiles
# ---------------------------------------------------------------------------

def _backup_existing(target: Path) -> Path | None:
    if not target.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(f"{target.name}.phoenix-bak-{stamp}")
    shutil.move(str(target), str(backup))
    return backup


def restore_dotfiles(auto_yes: bool = False) -> DotfilesRestoreResult:
    result = DotfilesRestoreResult()
    manifest = load_manifest()
    if not manifest:
        print("[phoenix] Aucun manifest de dotfiles trouvé — rien à restaurer.")
        return result

    # V5 : on prévient si le système actuel diverge du snapshot AVANT d'écraser.
    # Ne bloque pas — restore sert justement parfois à écraser volontairement —
    # mais plus question d'écraser une modif à la main sans le savoir.
    try:
        from .divergence import diff_dotfiles
        live_diff = diff_dotfiles()
        divergent_names = [n for n, d in live_diff.items() if d.modified or d.added]
        if divergent_names:
            print(f"[phoenix] ⚠ Ces dotfiles ont changé sur le système depuis le dernier snapshot : {divergent_names}")
            print("[phoenix]   Restaurer maintenant écrasera ces changements (backup auto, mais quand même).")
    except Exception:
        pass  # la vérification est un bonus, pas un blocant si elle plante

    dotfiles_root = REPO_DIR / "dotfiles"

    for name, original_path in manifest.items():
        src = dotfiles_root / name
        target = Path(original_path).expanduser()

        if not src.exists():
            print(f"[phoenix] ✗ {name} absent du repo, skip.")
            result.failed.append(name)
            continue

        if not confirm(f"Restaurer {name} → {target} (écrase si existant, backup auto) ?", auto_yes):
            print(f"[phoenix] {name} ignoré.")
            continue

        try:
            backup = _backup_existing(target)
            if backup:
                print(f"  → ancien {target.name} sauvegardé : {backup}")

            target.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, target)
            else:
                shutil.copy2(src, target)
            print(f"  ✓ {name} restauré → {target}")
            result.restored.append(name)
        except OSError as e:
            print(f"  ⚠ {name} : échec de la restauration ({e})")
            result.failed.append(name)

    return result


# ---------------------------------------------------------------------------
# Orchestrateur
# ---------------------------------------------------------------------------

def _print_summary(pkg: PackageRestoreResult, svc: ServiceRestoreResult, dot: DotfilesRestoreResult) -> bool:
    """Affiche le résumé final. Retourne True si tout s'est bien passé
    (aucun échec isolé sur aucun des trois axes)."""
    all_ok = pkg.ok and svc.ok and dot.ok

    print()
    print(f"[phoenix] Restore terminé{'' if all_ok else ' avec avertissements'}.")
    print()
    print("Paquets :")
    print(f"  ✓ {len(pkg.installed)} installés")
    if pkg.failed:
        print(f"  ⚠ {len(pkg.failed)} indisponibles → {pkg.failed}")

    print("Services :")
    print(f"  ✓ {len(svc.enabled)} activés")
    if svc.failed:
        print(f"  ⚠ {len(svc.failed)} en échec → {svc.failed}")

    print("Dotfiles :")
    print(f"  ✓ {len(dot.restored)} restaurés")
    if dot.failed:
        print(f"  ⚠ {len(dot.failed)} en échec → {dot.failed}")

    return all_ok


def run_restore(auto_yes: bool = False, skip_aur: bool = False) -> None:
    if not REPO_DIR.exists():
        print(f"[phoenix] Aucun repo trouvé dans {REPO_DIR}. Rien à restaurer.")
        sys.exit(1)

    load_config()  # valide que phoenix.toml existe et se parse correctement

    print("[phoenix] === Étape 1/3 : paquets ===")
    pkg_result = restore_packages(auto_yes=auto_yes, skip_aur=skip_aur)

    print("[phoenix] === Étape 2/3 : services ===")
    svc_result = restore_services(auto_yes=auto_yes)

    print("[phoenix] === Étape 3/3 : dotfiles ===")
    dot_result = restore_dotfiles(auto_yes=auto_yes)

    all_ok = _print_summary(pkg_result, svc_result, dot_result)
    sys.exit(0 if all_ok else 1)
