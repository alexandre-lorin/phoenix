import json


def test_diff_against_nonexistent_repo_reports_false(phoenix_repo):
    import phoenix.diff as diff
    result = diff.run_diff("/tmp/ce-chemin-nexiste-vraiment-pas-12345")
    assert result is False


def test_dotfiles_only_on_one_machine_is_reported(phoenix_repo, tmp_path):
    import phoenix.diff as diff

    (phoenix_repo / "dotfiles" / "hypr").mkdir(parents=True)
    (phoenix_repo / "dotfiles" / "hypr" / "hyprland.conf").write_text("a")
    (phoenix_repo / "dotfiles" / "manifest.json").write_text(
        json.dumps({"hypr": "/home/user/.config/hypr"})
    )
    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("")
    (phoenix_repo / "packages" / "aur.txt").write_text("")
    (phoenix_repo / "services").mkdir()
    (phoenix_repo / "services" / "system.txt").write_text("")
    (phoenix_repo / "services" / "user.txt").write_text("")

    other = tmp_path / "other_repo"
    other.mkdir()  # repo vide : jamais eu de dotfiles capturés

    dot = diff.diff_dotfiles(other)
    assert "hypr" in dot
    assert dot["hypr"].only_here == ["hypr"]
    assert dot["hypr"].only_there == []
