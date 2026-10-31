from pathlib import Path

from tests.conftest import write_config


def test_capture_creates_manifest_and_copies_files(phoenix_repo, fake_home):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,1920x1080,0x0,1")
    (hypr / "cache_junk").mkdir()
    (hypr / "cache_junk" / "bruit.log").write_text("bruit")

    write_config(phoenix_repo, [str(hypr)], exclude=["*cache*", "*.log"])

    import phoenix.dotfiles as dotfiles
    results = dotfiles.capture_dotfiles()

    assert (phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf").exists()
    assert not (phoenix_repo / "dotfiles" / "hypr" / "cache_junk").exists()

    manifest = dotfiles.load_manifest()
    assert manifest["hypr"] == str(hypr)


def test_capture_refuses_on_basename_collision_and_copies_nothing(phoenix_repo, fake_home):
    """Régression du bug critique : deux chemins configurés avec la même
    feuille (ex. ~/a/nvim et ~/b/nvim) écrasaient silencieusement l'un
    l'autre dans le manifest. Maintenant : refus net, rien n'est copié."""
    import phoenix.config as config
    config.ensure_repo_initialized()

    nvim_a = fake_home / "a" / "nvim"
    nvim_b = fake_home / "b" / "nvim"
    nvim_a.mkdir(parents=True)
    nvim_b.mkdir(parents=True)
    (nvim_a / "init.vim").write_text("config A")
    (nvim_b / "init.vim").write_text("config B")

    write_config(phoenix_repo, [str(nvim_a), str(nvim_b)])

    import phoenix.dotfiles as dotfiles
    import pytest

    with pytest.raises(dotfiles.DotfilesCollisionError) as exc_info:
        dotfiles.capture_dotfiles()

    assert "nvim" in str(exc_info.value)
    # rien ne doit avoir été copié — pas de dossier dotfiles/nvim tronqué
    assert not (phoenix_repo / "dotfiles" / "nvim").exists()
    # pas de manifest écrit non plus (pas de demi-état)
    assert dotfiles.load_manifest() == {}


def test_capture_allows_distinct_basenames(phoenix_repo, fake_home):
    """S'assure que le fix de collision ne bloque pas le cas normal
    (basenames tous différents)."""
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    waybar = fake_home / ".config" / "waybar"
    hypr.mkdir(parents=True)
    waybar.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("hypr config")
    (waybar / "config.jsonc").write_text("waybar config")

    write_config(phoenix_repo, [str(hypr), str(waybar)])

    import phoenix.dotfiles as dotfiles
    results = dotfiles.capture_dotfiles()

    assert (phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf").exists()
    assert (phoenix_repo / "dotfiles" / "waybar" / "config.jsonc").exists()
    assert all(status.startswith("OK") for status in results.values())


def test_snapshot_aborts_cleanly_on_collision(phoenix_repo, fake_home, capsys, monkeypatch):
    """`phoenix snapshot` doit s'arrêter avant tout commit si la capture
    des dotfiles est refusée — pas de commit avec un manifest tronqué."""
    import phoenix.config as config
    config.ensure_repo_initialized()

    nvim_a = fake_home / "a" / "nvim"
    nvim_b = fake_home / "b" / "nvim"
    nvim_a.mkdir(parents=True)
    nvim_b.mkdir(parents=True)
    (nvim_a / "init.vim").write_text("A")
    (nvim_b / "init.vim").write_text("B")
    write_config(phoenix_repo, [str(nvim_a), str(nvim_b)])

    import phoenix.snapshot as snapshot
    import phoenix.inventory as inventory
    import phoenix.services as services

    monkeypatch.setattr(inventory, "_run", lambda cmd: [])
    monkeypatch.setattr(services, "_list_enabled", lambda user=False: [])

    import pytest
    with pytest.raises(SystemExit) as exc_info:
        snapshot.run_snapshot()
    assert exc_info.value.code == 1

    out = capsys.readouterr().out
    assert "refusée" in out
    # pas de commit créé
    assert not (phoenix_repo / ".git").exists()


def test_restore_recreates_deleted_file_at_correct_path(phoenix_repo, fake_home):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,1920x1080,0x0,1")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    import shutil
    shutil.rmtree(hypr)
    assert not hypr.exists()

    import phoenix.restore as restore
    restore.restore_dotfiles(auto_yes=True)

    assert (hypr / "hyprland.conf").exists()
    assert (hypr / "hyprland.conf").read_text() == "monitor=DP-1,1920x1080,0x0,1"


def test_restore_backs_up_existing_file_instead_of_deleting(phoenix_repo, fake_home):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("original")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    # L'utilisateur modifie le fichier live à la main après le snapshot
    (hypr / "hyprland.conf").write_text("modifié à la main, pas encore re-snapshoté")

    import phoenix.restore as restore
    restore.restore_dotfiles(auto_yes=True)

    # Le contenu restauré doit être celui du snapshot...
    assert (hypr / "hyprland.conf").read_text() == "original"
    # ...et un backup de la version écrasée doit exister quelque part
    backups = list(hypr.parent.glob("hypr.phoenix-bak-*"))
    assert len(backups) == 1
