"""
DotDiff — V2 (diff de contenu) et V3 (actions sélectives) pour `phoenix status`.

Rappel du brief : DotDiff n'est pas un projet à part, c'est un sous-ensemble
naturel de Phoenix. V0 (comparaison basique) et V1 (sortie lisible) existent
déjà — c'est exactement ce que fait `phoenix status` / divergence.py. Ce
module n'ajoute que ce qui manquait :

- V2 : le vrai diff textuel d'un fichier modifié (au lieu de juste son nom)
- V3 : la résolution fichier par fichier — garder le local ou revenir à la
  version versionnée, sans jamais tout écraser en bloc

Diff textuel via `git diff --no-index` (cf. stack recommandée du brief) :
pas besoin de réimplémenter un algorithme de diff, et pas besoin non plus
d'une dépendance `diff` séparée puisque git est déjà utilisé par Phoenix
(git_utils.py). `--no-index` fonctionne même entre deux fichiers qui ne
sont pas dans le même repo Git, ce qui est exactement notre cas ici
(dotfiles/<name>/... dans le repo Phoenix vs. le fichier live sur le disque).

Sur un binaire modifié, `git diff --no-index` sort juste "Binary files ...
differ" — illisible, mais surtout pas un vrai diff exploitable. On le
détecte pour afficher un message clair plutôt que ce bruit brut.

V4 du brief (« phoenix diff comme commande native ») : le nom `phoenix diff`
est déjà pris par la V6 de Phoenix (comparaison entre deux machines). Plutôt
que de créer une collision de noms, ce module s'intègre comme options sur
la commande native existante `phoenix status` :

    phoenix status --content              # V2 : affiche le diff textuel réel
    phoenix status --resolve              # V3 : résolution interactive, fichier par fichier
    phoenix status --resolve --content    # V3, avec le diff affiché juste avant chaque décision
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from .config import REPO_DIR
from .divergence import DotfilesDiff
from .dotfiles import load_manifest

_WHOLE_PATH_NEVER_CAPTURED = "(tout le chemin — jamais capturé)"
_WHOLE_PATH_ABSENT_LIVE = "(tout le chemin — absent du système)"


def _stored_and_live(dotfiles_root: Path, live_root: Path, name: str, rel: str) -> tuple[Path, Path]:
    if rel == ".":
        return dotfiles_root / name, live_root
    return dotfiles_root / name / rel, live_root / rel


def _label(name: str, rel: str) -> str:
    return name if rel == "." else f"{name}/{rel}"


# ---------------------------------------------------------------------------
# V2 — diff de contenu textuel
# ---------------------------------------------------------------------------

def content_diff(stored: Path, live: Path) -> str:
    """Diff unifié brut entre la version versionnée (stored) et la version
    live — sortie brute de `git diff --no-index`, peut contenir le message
    "Binary files ... differ" si l'un des deux fichiers est binaire. Utiliser
    `render_diff` pour un affichage propre."""
    result = subprocess.run(
        ["git", "diff", "--no-index", "--no-color", "--", str(stored), str(live)],
        capture_output=True, text=True,
    )
    return result.stdout


def _is_binary_diff(diff_text: str) -> bool:
    return "Binary files" in diff_text


def render_diff(stored: Path, live: Path) -> str:
    """Diff prêt à afficher : message clair si binaire ou si rien à montrer,
    plutôt que le output brut (et illisible pour un binaire) de git."""
    text = content_diff(stored, live)
    if _is_binary_diff(text):
        return "  (fichier binaire — pas de diff textuel affichable)"
    if not text.strip():
        return "  (aucune différence)"
    return text


def print_content_diffs(dot: dict[str, DotfilesDiff]) -> None:
    """Affiche le diff textuel réel pour chaque fichier modifié — limité
    aux dotfiles suivis par Phoenix, jamais un `git diff` brut du repo entier."""
    manifest = load_manifest()
    dotfiles_root = REPO_DIR / "dotfiles"

    any_shown = False
    for name, d in dot.items():
        if not d.modified:
            continue
        original_path = manifest.get(name)
        if not original_path:
            continue
        live_root = Path(original_path).expanduser()

        for rel in d.modified:
            stored, live = _stored_and_live(dotfiles_root, live_root, name, rel)
            label = _label(name, rel)
            print(f"[phoenix] --- diff : {label} ---")
            print(render_diff(stored, live))
            any_shown = True

    if not any_shown:
        print("[phoenix] Aucun fichier modifié à afficher en diff de contenu.")


# ---------------------------------------------------------------------------
# V3 — actions sélectives, fichier par fichier
# ---------------------------------------------------------------------------

def _backup_existing(target: Path) -> Path | None:
    """Même convention que restore.py : jamais de suppression sèche."""
    if not target.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(f"{target.name}.phoenix-bak-{stamp}")
    shutil.move(str(target), str(backup))
    return backup


def _copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)


def _revert_to_snapshot(stored: Path, live: Path, label: str) -> None:
    backup = _backup_existing(live)
    if backup:
        print(f"  → ancien fichier sauvegardé : {backup}")
    _copy(stored, live)
    print(f"  ✓ {label} : revenu à la version versionnée.")


def _discard_local(live: Path, label: str) -> None:
    backup = _backup_existing(live)
    print(f"  → {label} : retiré du système (sauvegardé : {backup}).")


def _restore_removed(stored: Path, live: Path, label: str) -> None:
    _copy(stored, live)
    print(f"  ✓ {label} : restauré depuis le snapshot.")


def resolve_interactive(dot: dict[str, DotfilesDiff], input_fn=input, show_content: bool = False) -> None:
    """Parcourt chaque fichier divergent et demande une action, un par un.
    Volontairement pas de mode --yes ici : "garder" et "revenir" ne sont pas
    un simple oui/non, forcer un choix par défaut irait à l'encontre du but
    même de V3 (« sans tout écraser en bloc »).

    `show_content=True` (via `phoenix status --resolve --content`) affiche le
    diff textuel du fichier juste avant de demander la décision — pratique
    pour savoir sur quoi on tranche sans avoir à lancer `--content` à part
    en amont. Uniquement pertinent pour les fichiers modifiés : les fichiers
    ajoutés/supprimés n'ont pas de contenu à comparer des deux côtés."""
    manifest = load_manifest()
    dotfiles_root = REPO_DIR / "dotfiles"
    touched = False

    for name, d in dot.items():
        original_path = manifest.get(name)
        if not original_path:
            continue
        live_root = Path(original_path).expanduser()
        stored_root = dotfiles_root / name

        # Cas particuliers : tout le chemin d'un coup (pas de fichier individuel)
        if d.added == [_WHOLE_PATH_NEVER_CAPTURED]:
            touched = True
            ans = input_fn(f"[phoenix] {name} présent en local, jamais capturé — (g)arder / (d)élete ? [g/d] ").strip().lower()
            if ans in ("d", "delete", "supprimer"):
                _discard_local(live_root, name)
            else:
                print(f"  → {name} conservé (capturé au prochain snapshot).")
            continue

        if d.removed == [_WHOLE_PATH_ABSENT_LIVE]:
            touched = True
            ans = input_fn(f"[phoenix] {name} absent du système, présent dans le snapshot — (g)arder supprimé / (r)estaurer ? [g/r] ").strip().lower()
            if ans in ("r", "restaurer", "restore"):
                _restore_removed(stored_root, live_root, name)
            else:
                print(f"  → {name} reste supprimé.")
            continue

        for rel in d.modified:
            touched = True
            stored, live = _stored_and_live(dotfiles_root, live_root, name, rel)
            label = _label(name, rel)
            if show_content:
                print(f"[phoenix] --- diff : {label} ---")
                print(render_diff(stored, live))
            ans = input_fn(f"[phoenix] {label} modifié — (g)arder local / (r)evenir au snapshot / (s)kip ? [g/r/s] ").strip().lower()
            if ans in ("r", "revenir", "revert"):
                _revert_to_snapshot(stored, live, label)
            elif ans in ("g", "garder", "keep"):
                print(f"  → {label} : modif locale conservée.")
            else:
                print(f"  → {label} : ignoré.")

        for rel in d.added:
            touched = True
            _, live = _stored_and_live(dotfiles_root, live_root, name, rel)
            label = _label(name, rel)
            ans = input_fn(f"[phoenix] {label} nouveau, jamais capturé — (g)arder local / (d)élete / (s)kip ? [g/d/s] ").strip().lower()
            if ans in ("d", "delete", "supprimer"):
                _discard_local(live, label)
            else:
                print(f"  → {label} : conservé (sera capturé au prochain snapshot si voulu).")

        for rel in d.removed:
            touched = True
            stored, live = _stored_and_live(dotfiles_root, live_root, name, rel)
            label = _label(name, rel)
            ans = input_fn(f"[phoenix] {label} supprimé du système — (g)arder supprimé / (r)estaurer / (s)kip ? [g/r/s] ").strip().lower()
            if ans in ("r", "restaurer", "restore"):
                _restore_removed(stored, live, label)
            else:
                print(f"  → {label} : reste supprimé.")

    if not touched:
        print("[phoenix] Rien à résoudre — aucun dotfile divergent.")

