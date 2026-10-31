"""
Fixtures partagées. Chaque test reçoit un repo Phoenix isolé dans un
tmp_path pytest — jamais de contact avec ~/phoenix-config réel.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def phoenix_repo(tmp_path, monkeypatch):
    """Reconfigure tous les modules phoenix pour pointer sur un repo temporaire.
    Retourne le Path du repo."""
    repo = tmp_path / "repo"
    repo.mkdir()

    modules = [
        "phoenix.config", "phoenix.dotfiles", "phoenix.inventory",
        "phoenix.services", "phoenix.snapshot", "phoenix.restore",
        "phoenix.divergence", "phoenix.diff", "phoenix.dotdiff", "phoenix.reminder", "phoenix.rollback",
        "phoenix.git_utils",
    ]
    for name in modules:
        mod = importlib.import_module(name)
        importlib.reload(mod)
        if hasattr(mod, "REPO_DIR"):
            monkeypatch.setattr(mod, "REPO_DIR", repo, raising=False)

    import phoenix.config as config
    monkeypatch.setattr(config, "CONFIG_FILE", repo / "phoenix.toml", raising=False)

    import phoenix.dotfiles as dotfiles
    monkeypatch.setattr(dotfiles, "MANIFEST_FILE", repo / "dotfiles" / "manifest.json", raising=False)

    return repo


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return home


def write_config(
    repo: Path,
    dotfiles_paths: list[str],
    exclude: list[str] | None = None,
    include_user_services: bool = False,
) -> None:
    import phoenix.config as config
    paths_toml = ", ".join(f'"{p}"' for p in dotfiles_paths)
    exclude_toml = ", ".join(f'"{p}"' for p in (exclude or []))
    (repo / "phoenix.toml").write_text(f"""
[dotfiles]
paths = [{paths_toml}]
[dotfiles.exclude]
patterns = [{exclude_toml}]
[services]
include_user_services = {"true" if include_user_services else "false"}
""")
