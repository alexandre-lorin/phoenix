from tests.conftest import write_config


def _setup_hypr(phoenix_repo, fake_home, content="monitor=DP-1,1920x1080,0x0,1"):
    import phoenix.config as config
    config.ensure_repo_initialized()

    hypr = fake_home / ".config" / "hypr"
    hypr.mkdir(parents=True)
    (hypr / "hyprland.conf").write_text(content)
    write_config(phoenix_repo, [str(hypr)])

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()

    return hypr


# ---------------------------------------------------------------------------
# V2 — diff de contenu textuel
# ---------------------------------------------------------------------------

def test_content_diff_shows_actual_line_changes(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,2560x1440,0x0,1  # modifié")

    import phoenix.dotdiff as dotdiff
    stored = phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf"
    live = hypr / "hyprland.conf"

    text = dotdiff.content_diff(stored, live)
    assert "2560x1440" in text
    assert "1920x1080" in text


def test_content_diff_empty_when_identical(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home)

    import phoenix.dotdiff as dotdiff
    stored = phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf"
    live = hypr / "hyprland.conf"

    text = dotdiff.content_diff(stored, live)
    assert text.strip() == ""


def test_print_content_diffs_only_covers_modified_files(phoenix_repo, fake_home, capsys):
    hypr = _setup_hypr(phoenix_repo, fake_home)
    (hypr / "hyprland.conf").write_text("monitor=DP-1,2560x1440,0x0,1")
    (hypr / "nouveau.conf").write_text("bind = SUPER, Q, killactive")  # added, pas modified

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.print_content_diffs(dot)

    out = capsys.readouterr().out
    assert "hyprland.conf" in out
    assert "2560x1440" in out
    # le fichier ajouté n'a pas de diff de contenu (rien à comparer)
    assert "nouveau.conf" not in out


def test_content_diff_binary_file_gives_clean_message_not_raw_output(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home)

    # remplace le fichier stocké et le live par des binaires différents
    stored = phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf"
    live = hypr / "hyprland.conf"
    stored.write_bytes(b"\x00\x01\x02\x03BINARYSTORED")
    live.write_bytes(b"\x00\x01\x02\x03BINARYLIVE\xff\xfe")

    import phoenix.dotdiff as dotdiff

    rendered = dotdiff.render_diff(stored, live)
    assert "binaire" in rendered
    # jamais les octets bruts affichés directement
    assert "BINARYLIVE" not in rendered


def test_print_content_diffs_shows_clean_message_for_binary(phoenix_repo, fake_home, capsys):
    hypr = _setup_hypr(phoenix_repo, fake_home)
    stored = phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf"
    live = hypr / "hyprland.conf"
    stored.write_bytes(b"\x00\x01old")
    live.write_bytes(b"\x00\x01new")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.print_content_diffs(dot)

    out = capsys.readouterr().out
    assert "binaire" in out
    assert "Binary files" not in out  # pas le message brut de git non plus


# ---------------------------------------------------------------------------
# V3 — résolution interactive
# ---------------------------------------------------------------------------

def test_resolve_revert_restores_versioned_content(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home, content="original")
    (hypr / "hyprland.conf").write_text("modifié à la main")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "r")

    assert (hypr / "hyprland.conf").read_text() == "original"
    # backup de la version locale conservé, jamais de suppression sèche
    backups = list(hypr.glob("hyprland.conf.phoenix-bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "modifié à la main"


def test_resolve_keep_leaves_local_untouched(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home, content="original")
    (hypr / "hyprland.conf").write_text("modifié à la main")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "g")

    assert (hypr / "hyprland.conf").read_text() == "modifié à la main"
    assert not list(hypr.glob("*.phoenix-bak-*"))


def test_resolve_delete_removes_untracked_addition(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home)
    (hypr / "nouveau.conf").write_text("bind = SUPER, Q, killactive")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "d")

    assert not (hypr / "nouveau.conf").exists()
    assert list(hypr.glob("nouveau.conf.phoenix-bak-*"))


def test_resolve_restore_brings_back_deleted_file(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home)
    (hypr / "extra.conf").write_text("keepme")

    import phoenix.dotfiles as dotfiles
    dotfiles.capture_dotfiles()  # re-capture pour que extra.conf soit dans le snapshot

    (hypr / "extra.conf").unlink()

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "r")

    assert (hypr / "extra.conf").read_text() == "keepme"


def test_resolve_skip_does_nothing(phoenix_repo, fake_home):
    hypr = _setup_hypr(phoenix_repo, fake_home, content="original")
    (hypr / "hyprland.conf").write_text("modifié à la main")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "s")

    assert (hypr / "hyprland.conf").read_text() == "modifié à la main"
    assert not list(hypr.glob("*.phoenix-bak-*"))


def test_resolve_no_divergence_prints_nothing_to_do(phoenix_repo, fake_home, capsys):
    _setup_hypr(phoenix_repo, fake_home)

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "r")

    out = capsys.readouterr().out
    assert "Rien à résoudre" in out


def test_resolve_with_show_content_prints_diff_before_prompt(phoenix_repo, fake_home, capsys):
    hypr = _setup_hypr(phoenix_repo, fake_home, content="original")
    (hypr / "hyprland.conf").write_text("modifié à la main")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "s", show_content=True)

    out = capsys.readouterr().out
    assert "--- diff : hypr/hyprland.conf ---" in out
    assert "modifié à la main" in out
    assert "original" in out
    # le diff (imprimé via print()) doit précéder le message de skip qui suit la décision
    assert out.index("--- diff :") < out.index("ignoré")


def test_resolve_without_show_content_does_not_print_diff(phoenix_repo, fake_home, capsys):
    hypr = _setup_hypr(phoenix_repo, fake_home, content="original")
    (hypr / "hyprland.conf").write_text("modifié à la main")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "s", show_content=False)

    out = capsys.readouterr().out
    assert "--- diff :" not in out


def test_resolve_show_content_binary_shows_clean_message(phoenix_repo, fake_home, capsys):
    hypr = _setup_hypr(phoenix_repo, fake_home)
    stored = phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf"
    live = hypr / "hyprland.conf"
    stored.write_bytes(b"\x00\x01old")
    live.write_bytes(b"\x00\x01new")

    import phoenix.divergence as divergence
    import phoenix.dotdiff as dotdiff

    dot = divergence.diff_dotfiles()
    dotdiff.resolve_interactive(dot, input_fn=lambda _: "s", show_content=True)

    out = capsys.readouterr().out
    assert "binaire" in out
