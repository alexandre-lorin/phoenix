import subprocess


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


def _init_git(repo):
    _git(repo, "init")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@localhost")


def test_rollback_restores_previous_snapshot_content(phoenix_repo, monkeypatch):
    import phoenix.rollback as rollback

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\n")
    _init_git(phoenix_repo)
    _git(phoenix_repo, "add", "-A")
    _git(phoenix_repo, "commit", "-m", "snapshot 1")

    first_commit = _git(phoenix_repo, "rev-parse", "--short", "HEAD").stdout.strip()

    # Deuxième snapshot : on ajoute un paquet
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    _git(phoenix_repo, "add", "-A")
    _git(phoenix_repo, "commit", "-m", "snapshot 2")

    assert "waybar" in (phoenix_repo / "packages" / "pacman.txt").read_text()

    ok = rollback.rollback_to(first_commit, auto_yes=True)
    assert ok is True
    assert "waybar" not in (phoenix_repo / "packages" / "pacman.txt").read_text()

    # L'historique n'est PAS perdu — le rollback est lui-même un commit
    log = _git(phoenix_repo, "log", "--oneline").stdout
    assert "snapshot 1" in log
    assert "snapshot 2" in log
    assert "rollback" in log


def test_rollback_to_unknown_commit_fails_cleanly(phoenix_repo):
    import phoenix.rollback as rollback

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\n")
    _init_git(phoenix_repo)
    _git(phoenix_repo, "add", "-A")
    _git(phoenix_repo, "commit", "-m", "snapshot 1")

    ok = rollback.rollback_to("deadbeef", auto_yes=True)
    assert ok is False


def test_rollback_removes_file_added_after_target_commit(phoenix_repo):
    """Régression du bug critique : `git checkout <ref> -- path` en mode
    overlay (le défaut) ne supprime jamais un fichier ajouté après <ref>.
    Un vrai rollback doit resynchroniser l'arbre exactement."""
    import phoenix.rollback as rollback

    _init_git(phoenix_repo)
    (phoenix_repo / "dotfiles" / "hypr").mkdir(parents=True)
    (phoenix_repo / "dotfiles" / "hypr" / "a.conf").write_text("v1")
    _git(phoenix_repo, "add", "-A")
    _git(phoenix_repo, "commit", "-m", "snapshot 1")
    first = _git(phoenix_repo, "rev-parse", "--short", "HEAD").stdout.strip()

    # snapshot 2 : un NOUVEAU fichier apparaît (pas juste une modif)
    (phoenix_repo / "dotfiles" / "hypr" / "b.conf").write_text("nouveau, jamais vu au premier snapshot")
    _git(phoenix_repo, "add", "-A")
    _git(phoenix_repo, "commit", "-m", "snapshot 2")

    assert (phoenix_repo / "dotfiles" / "hypr" / "b.conf").exists()

    ok = rollback.rollback_to(first, auto_yes=True)
    assert ok is True

    # le fichier ajouté après le commit cible ne doit plus exister
    assert not (phoenix_repo / "dotfiles" / "hypr" / "b.conf").exists()
    assert (phoenix_repo / "dotfiles" / "hypr" / "a.conf").read_text() == "v1"

    # et l'état du repo (working tree) doit être propre (rien en attente)
    status = _git(phoenix_repo, "status", "--porcelain").stdout
    assert status.strip() == ""


def test_rollback_handles_add_modify_and_delete_together(phoenix_repo):
    """Cas combiné : entre les deux snapshots, un fichier est modifié,
    un autre est ajouté, et un troisième est supprimé — le rollback doit
    tout resynchroniser correctement en une seule opération."""
    import phoenix.rollback as rollback

    _init_git(phoenix_repo)
    d = phoenix_repo / "dotfiles" / "hypr"
    d.mkdir(parents=True)
    (d / "modified.conf").write_text("v1")
    (d / "to_delete.conf").write_text("va disparaître")
    _git(phoenix_repo, "add", "-A")
    _git(phoenix_repo, "commit", "-m", "snapshot 1")
    first = _git(phoenix_repo, "rev-parse", "--short", "HEAD").stdout.strip()

    (d / "modified.conf").write_text("v2 — changé au snapshot 2")
    (d / "to_delete.conf").unlink()
    (d / "new.conf").write_text("apparu au snapshot 2")
    _git(phoenix_repo, "add", "-A")
    _git(phoenix_repo, "commit", "-m", "snapshot 2")

    ok = rollback.rollback_to(first, auto_yes=True)
    assert ok is True

    assert (d / "modified.conf").read_text() == "v1"        # modif annulée
    assert (d / "to_delete.conf").read_text() == "va disparaître"  # suppression annulée
    assert not (d / "new.conf").exists()                     # ajout annulé
