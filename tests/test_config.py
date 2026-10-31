def test_ensure_repo_initialized_creates_default_config(phoenix_repo):
    import phoenix.config as config

    assert not (phoenix_repo / "phoenix.toml").exists()
    config.ensure_repo_initialized()
    assert (phoenix_repo / "phoenix.toml").exists()

    # Un deuxième appel ne doit PAS écraser une config déjà éditée par l'utilisateur
    (phoenix_repo / "phoenix.toml").write_text("[dotfiles]\npaths = [\"~/perso\"]\n")
    config.ensure_repo_initialized()
    assert "~/perso" in (phoenix_repo / "phoenix.toml").read_text()


def test_load_config_parses_custom_values(phoenix_repo):
    import phoenix.config as config
    config.ensure_repo_initialized()

    (phoenix_repo / "phoenix.toml").write_text("""
[dotfiles]
paths = ["~/.config/hypr", "~/.config/waybar"]
[dotfiles.exclude]
patterns = ["*.log", "*cache*"]
[services]
include_user_services = true
""")

    cfg = config.load_config()
    assert cfg.dotfiles_paths == ["~/.config/hypr", "~/.config/waybar"]
    assert cfg.exclude_patterns == ["*.log", "*cache*"]
    assert cfg.include_user_services is True


def test_load_config_defaults_when_sections_missing(phoenix_repo):
    import phoenix.config as config
    config.ensure_repo_initialized()
    (phoenix_repo / "phoenix.toml").write_text("")  # config vide

    cfg = config.load_config()
    assert cfg.dotfiles_paths == []
    assert cfg.exclude_patterns == []
    assert cfg.include_user_services is True
