import os

from types import SimpleNamespace

from tests.conftest import write_config


def test_fresh_snapshot_has_no_divergence(phoenix_repo, fake_home):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,1920x1080,0x0,1")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    import phoenix.divergence as divergence
    diff = divergence.diff_dotfiles()

    assert all(not d.modified and not d.added and not d.removed for d in diff.values())


def test_manual_edit_and_new_file_are_detected(phoenix_repo, fake_home):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,1920x1080,0x0,1")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    (hypr / "hyprland.conf").write_text("monitor=DP-1,2560x1440,0x0,1  # modifié")
    (hypr / "nouveau.conf").write_text("bind = SUPER, Q, killactive")

    import phoenix.divergence as divergence
    diff = divergence.diff_dotfiles()

    assert "hyprland.conf" in diff["hypr"].modified
    assert "nouveau.conf" in diff["hypr"].added


def test_deleted_live_file_is_detected_as_removed(phoenix_repo, fake_home):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("a")
    (hypr / "extra.conf").write_text("b")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    (hypr / "extra.conf").unlink()

    import phoenix.divergence as divergence
    diff = divergence.diff_dotfiles()

    assert "extra.conf" in diff["hypr"].removed


def test_hash_tree_prunes_excluded_directories_instead_of_walking_them(tmp_path, monkeypatch):
    """Régression perf : un dossier exclu par pattern (ex. un cache de
    plugin manager) ne doit plus être descendu du tout par os.walk — pas
    seulement filtré après coup. On instrumente os.walk pour vérifier
    qu'il ne visite jamais ce sous-arbre."""
    import phoenix.divergence as divergence

    root = tmp_path / "cfg"
    root.mkdir()
    (root / "keep.conf").write_text("gardé")

    excluded = root / "node_modules"
    excluded.mkdir()
    (excluded / "a.js").write_text("a")
    (excluded / "sub").mkdir()
    (excluded / "sub" / "b.js").write_text("b")

    visited_dirs = []
    real_walk = os.walk

    def spy_walk(top, *a, **k):
        for dirpath, dirnames, filenames in real_walk(top, *a, **k):
            visited_dirs.append(dirpath)
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(divergence.os, "walk", spy_walk)

    hashes = divergence._hash_tree(root, ["node_modules"])

    assert "keep.conf" in hashes
    assert not any("a.js" in k or "b.js" in k for k in hashes)
    # le sous-arbre exclu ne doit jamais avoir été visité par os.walk
    assert not any("node_modules" in d for d in visited_dirs)


def test_hash_tree_still_excludes_by_filename_pattern(tmp_path):
    """S'assure que le fix de pruning ne casse pas l'exclusion par nom de
    fichier (pas seulement par nom de dossier)."""
    import phoenix.divergence as divergence

    root = tmp_path / "cfg"
    root.mkdir()
    (root / "keep.conf").write_text("gardé")
    (root / "bruit.log").write_text("bruit")

    hashes = divergence._hash_tree(root, ["*.log"])

    assert "keep.conf" in hashes
    assert "bruit.log" not in hashes


def test_run_status_computes_dotfiles_diff_only_once(phoenix_repo, fake_home, monkeypatch):
    """Régression perf : `phoenix status --content` appelait diff_dotfiles()
    deux fois (une dans run_status, une dans cli.py pour l'affichage). Le
    hash de tout l'arbre des dotfiles était donc calculé deux fois pour
    une seule invocation. run_status() doit maintenant renvoyer le diff
    déjà calculé pour que l'appelant le réutilise."""
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("v1")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    import phoenix.divergence as divergence

    # évite d'appeler pacman/systemctl réels, hors-sujet pour ce test
    def fake_run(cmd, *a, **k):
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(divergence.subprocess, "run", fake_run)

    call_count = {"n": 0}
    real_diff_dotfiles = divergence.diff_dotfiles

    def counting_diff_dotfiles():
        call_count["n"] += 1
        return real_diff_dotfiles()

    monkeypatch.setattr(divergence, "diff_dotfiles", counting_diff_dotfiles)

    aligned, dot = divergence.run_status()

    assert call_count["n"] == 1
    assert "hypr" in dot
