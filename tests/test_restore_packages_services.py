from types import SimpleNamespace


def test_restore_packages_only_installs_missing(phoenix_repo, monkeypatch):
    import phoenix.restore as restore

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    (phoenix_repo / "packages" / "aur.txt").write_text("")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qq"]:
            return SimpleNamespace(stdout="hyprland\n", returncode=0)  # waybar manquant
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)

    restore.restore_packages(auto_yes=True, skip_aur=True)

    assert len(calls) == 1
    install_cmd = calls[0]
    assert install_cmd[:4] == ["sudo", "pacman", "-S", "--needed"]
    assert "waybar" in install_cmd
    assert "hyprland" not in install_cmd  # déjà installé, ne doit pas être repassé à pacman
    # --yes doit vraiment vouloir dire "aucune question", y compris côté pacman
    assert "--noconfirm" in install_cmd


def test_restore_packages_without_auto_yes_leaves_pacman_interactive(phoenix_repo, monkeypatch):
    """Sans --yes, pas de --noconfirm forcé : pacman garde son propre
    comportement interactif normal (double confirmation, mais volontaire)."""
    import phoenix.restore as restore

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    (phoenix_repo / "packages" / "aur.txt").write_text("")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qq"]:
            return SimpleNamespace(stdout="hyprland\n", returncode=0)
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)
    monkeypatch.setattr(restore, "confirm", lambda *a, **k: True)  # simule une réponse manuelle "oui"

    restore.restore_packages(auto_yes=False, skip_aur=True)

    assert len(calls) == 1
    assert "--noconfirm" not in calls[0]


def test_restore_aur_packages_get_noconfirm_when_auto_yes(phoenix_repo, monkeypatch):
    import phoenix.restore as restore

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("")
    (phoenix_repo / "packages" / "aur.txt").write_text("some-aur-pkg\n")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qq"]:
            return SimpleNamespace(stdout="", returncode=0)
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)
    monkeypatch.setattr(restore, "_detect_aur_helper", lambda: "yay")

    restore.restore_packages(auto_yes=True, skip_aur=False)

    assert len(calls) == 1
    assert calls[0][:4] == ["yay", "-S", "--needed", "--noconfirm"]
    assert "some-aur-pkg" in calls[0]


def test_restore_aur_without_helper_does_not_bootstrap_anything(phoenix_repo, monkeypatch, capsys):
    """Régression suite à l'audit : plus de compilation automatique d'un
    AUR helper (git clone + makepkg -si avec sudo). Sans helper détecté,
    on se contente de prévenir et de laisser les paquets AUR de côté —
    aucune commande système supplémentaire ne doit être lancée."""
    import phoenix.restore as restore

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("")
    (phoenix_repo / "packages" / "aur.txt").write_text("some-aur-pkg\n")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qq"]:
            return SimpleNamespace(stdout="", returncode=0)
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)
    monkeypatch.setattr(restore, "_detect_aur_helper", lambda: None)

    result = restore.restore_packages(auto_yes=True, skip_aur=False)

    # aucune commande d'installation/bootstrap lancée (pas de git clone, pas de makepkg)
    assert calls == []
    assert result.installed == []
    assert result.failed == []
    out = capsys.readouterr().out
    assert "manuellement" in out


def test_restore_packages_skips_install_when_nothing_missing(phoenix_repo, monkeypatch):
    import phoenix.restore as restore

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\n")
    (phoenix_repo / "packages" / "aur.txt").write_text("")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qq"]:
            return SimpleNamespace(stdout="hyprland\n", returncode=0)
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)
    restore.restore_packages(auto_yes=True, skip_aur=True)

    assert calls == []  # rien à installer, aucun appel pacman -S ne doit partir


def test_restore_services_enables_only_missing(phoenix_repo, monkeypatch):
    import phoenix.restore as restore

    (phoenix_repo / "services").mkdir()
    (phoenix_repo / "services" / "system.txt").write_text("NetworkManager.service\nbluetooth.service\n")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return SimpleNamespace(stdout="NetworkManager.service    enabled\n", returncode=0)
        calls.append(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)
    restore.restore_services(auto_yes=True)

    assert len(calls) == 1
    assert "bluetooth.service" in calls[0]
    assert "NetworkManager.service" not in calls[0]


# ---------------------------------------------------------------------------
# Robustesse : isolation des échecs (un paquet/service fautif ne doit plus
# faire échouer tout le lot), et résumé final de run_restore.
# ---------------------------------------------------------------------------

def test_restore_packages_isolates_single_failure_instead_of_failing_the_batch(phoenix_repo, monkeypatch):
    """Régression : un seul paquet introuvable/renommé faisait échouer
    `pacman -S` en bloc. Maintenant : retry un par un pour isoler le
    fautif, les autres s'installent quand même."""
    import phoenix.restore as restore

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\nintrouvable-pkg\n")
    (phoenix_repo / "packages" / "aur.txt").write_text("")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qq"]:
            return SimpleNamespace(stdout="hyprland\n", returncode=0)
        calls.append(cmd)
        if "-S" in cmd:
            targets = cmd[len(["sudo", "pacman", "-S", "--needed", "--noconfirm"]):]
            if len(targets) > 1:
                # le lot entier échoue à cause du paquet introuvable
                return SimpleNamespace(stdout="", stderr="error: target not found: introuvable-pkg", returncode=1)
            if "introuvable-pkg" in targets:
                return SimpleNamespace(stdout="", stderr="error: target not found: introuvable-pkg", returncode=1)
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)

    result = restore.restore_packages(auto_yes=True, skip_aur=True)

    # le lot a été tenté une fois (2 paquets), puis chaque paquet un par un (2 de plus)
    assert len(calls) == 3
    assert sorted(result.installed) == ["waybar"]
    assert result.failed == ["introuvable-pkg"]
    assert result.ok is False


def test_restore_packages_all_succeed_in_single_batch_call(phoenix_repo, monkeypatch):
    """Cas normal : pas de retry un par un si le lot passe du premier coup."""
    import phoenix.restore as restore

    (phoenix_repo / "packages").mkdir()
    (phoenix_repo / "packages" / "pacman.txt").write_text("hyprland\nwaybar\n")
    (phoenix_repo / "packages" / "aur.txt").write_text("")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd == ["pacman", "-Qq"]:
            return SimpleNamespace(stdout="", returncode=0)
        calls.append(cmd)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)

    result = restore.restore_packages(auto_yes=True, skip_aur=True)

    assert len(calls) == 1  # un seul appel, pas de fallback déclenché
    assert sorted(result.installed) == ["hyprland", "waybar"]
    assert result.failed == []
    assert result.ok is True


def test_restore_services_surfaces_stderr_on_failure_instead_of_swallowing_it(phoenix_repo, monkeypatch, capsys):
    """Régression : `check=False` sans lire stderr laissait une unité en
    échec (masquée, absente) passer pour "activée". Maintenant : lot puis
    isolation un par un, avec le détail de l'erreur affiché."""
    import phoenix.restore as restore

    (phoenix_repo / "services").mkdir()
    (phoenix_repo / "services" / "system.txt").write_text("NetworkManager.service\nunite-masquee.service\n")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return SimpleNamespace(stdout="", returncode=0)
        calls.append(cmd)
        targets = cmd[3:]  # après ["sudo", "systemctl", "enable"]
        if len(targets) > 1:
            return SimpleNamespace(stdout="", stderr="Failed to enable unit: Unit is masked.", returncode=1)
        if "unite-masquee.service" in targets:
            return SimpleNamespace(stdout="", stderr="Failed to enable unit: Unit is masked.", returncode=1)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)

    result = restore.restore_services(auto_yes=True)

    assert sorted(result.enabled) == ["NetworkManager.service"]
    assert result.failed == ["unite-masquee.service"]
    out = capsys.readouterr().out
    assert "masked" in out or "masquée" in out  # le détail de l'erreur est bien affiché, pas avalé


def test_restore_services_all_succeed_in_single_batch_call(phoenix_repo, monkeypatch):
    import phoenix.restore as restore

    (phoenix_repo / "services").mkdir()
    (phoenix_repo / "services" / "system.txt").write_text("bluetooth.service\n")

    calls = []

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            return SimpleNamespace(stdout="", returncode=0)
        calls.append(cmd)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(restore.subprocess, "run", fake_run)

    result = restore.restore_services(auto_yes=True)

    assert len(calls) == 1
    assert result.enabled == ["bluetooth.service"]
    assert result.failed == []
