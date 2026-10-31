"""
Phoenix — configuration centrale.

Toute la logique lit ce module. Rien n'est hardcodé ailleurs.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HOME = Path.home()

# Où vit le repo Git versionné. Override possible via env PHOENIX_REPO.
REPO_DIR = Path(os.environ.get("PHOENIX_REPO", HOME / "phoenix-config"))

# Fichier de config utilisateur (créé au premier run si absent).
CONFIG_FILE = REPO_DIR / "phoenix.toml"

DEFAULT_CONFIG = """\
# Phoenix — config des chemins à capturer.
# Édite cette liste selon TA structure réelle (Stow, dotfiles perso, etc.)

[dotfiles]
paths = [
    "~/.config/hypr",
    "~/.config/waybar",
    "~/.config/alacritty",
    "~/.config/fish",
    "~/.config/kitty",
    "~/.config/rofi",
    "~/.config/wlogout",
    "~/.gitconfig",
]

# Motifs exclus lors de la copie des dotfiles (bruit, cache, secrets).
[dotfiles.exclude]
patterns = [
    "*.cache",
    "*cache*",
    "*.log",
    "*.lock",
    "__pycache__",
    "*.pyc",
    ".git",
    "node_modules",
    "*history*",
]

[services]
# Inclure les services --user en plus des services système.
include_user_services = true
"""


@dataclass
class PhoenixConfig:
    dotfiles_paths: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    include_user_services: bool = True


def ensure_repo_initialized() -> None:
    """Crée le repo + config par défaut si c'est le premier run."""
    REPO_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(DEFAULT_CONFIG, encoding="utf-8")
        print(f"[phoenix] Config créée : {CONFIG_FILE}")
        print("[phoenix] → Édite-la avant ton premier snapshot si les chemins par défaut ne collent pas.")


def load_config() -> PhoenixConfig:
    ensure_repo_initialized()
    with open(CONFIG_FILE, "rb") as f:
        raw = tomllib.load(f)

    dotfiles = raw.get("dotfiles", {})
    services = raw.get("services", {})

    return PhoenixConfig(
        dotfiles_paths=dotfiles.get("paths", []),
        exclude_patterns=dotfiles.get("exclude", {}).get("patterns", []),
        include_user_services=services.get("include_user_services", True),
    )
