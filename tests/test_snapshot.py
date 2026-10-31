from tests.conftest import write_config


def test_snapshot_prints_diffstat_after_successful_commit(phoenix_repo, fake_home, capsys, monkeypatch):
    """Régression : savoir qu'un commit a eu lieu ne dit rien de son
    contenu. `phoenix snapshot` doit afficher un résumé concret
    (fichiers touchés) plutôt qu'un simple hash de commit opaque."""
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,1920x1080,0x0,1")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.snapshot as snapshot
    import phoenix.inventory as inventory
    import phoenix.services as services

    monkeypatch.setattr(inventory, "_run", lambda cmd: [])
    monkeypatch.setattr(services, "_list_enabled", lambda user=False: [])

    snapshot.run_snapshot()

    out = capsys.readouterr().out
    assert "Snapshot committé" in out
    assert "hyprland.conf" in out


def test_snapshot_prints_nothing_new_without_diffstat_on_second_run(phoenix_repo, fake_home, capsys, monkeypatch):
    """Un deuxième snapshot sans rien de changé ne doit pas essayer
    d'afficher un diffstat vide ou planter dessus."""
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,1920x1080,0x0,1")
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.snapshot as snapshot
    import phoenix.inventory as inventory
    import phoenix.services as services

    monkeypatch.setattr(inventory, "_run", lambda cmd: [])
    monkeypatch.setattr(services, "_list_enabled", lambda user=False: [])

    snapshot.run_snapshot()
    capsys.readouterr()  # purge la sortie du premier snapshot

    snapshot.run_snapshot()
    out = capsys.readouterr().out
    assert "Rien de nouveau depuis le dernier snapshot." in out
