# Setup guide — Phoenix

From zero to `phoenix snapshot` running. Follow the order, don't skip steps.

---

## 0. Prerequisites

- Arch Linux (or pacman-based derivative). Not tested on anything else, don't try.
- Python 3.11+ (`python --version` — on up-to-date Arch this is already the case).
- `git` installed (`pacman -S git` if absent).
- An AUR helper (`yay` or `paru`) — optional, to be installed separately. Without a helper, `restore` reports ignored AUR packets; it no longer installs them automatically.

---

## 1. Installation

```bash
git clone <ton-repo-git-phoenix> phoenix-tool
cd phoenix-tool
pip install --user -e ".[dev]"
```

`[dev]` also installs `pytest` — useful for step 3.

Check that the command is accessible:

```bash
phoenix --help
```

If `command not found`: `~/.local/bin` is probably not in your `$PATH`. Add in your `~/.bashrc`/`~/.zshrc`/`~/.config/fish/config.fish`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## 2. First launch

```bash
phoenix snapshot
```

This first run will:
1. Create `~/phoenix-config/` (the Git repo that contains everything).
2. Drop a `phoenix.toml` with dotfile paths **by default, guessed** (Hyprland, Waybar, Alacritty, fish, kitty, rofi, wlogout, gitconfig).
3. Capture these paths and create a commit. It does not stop after creating the configuration. Prepare and reread `phoenix.toml` before running this first snapshot, in particular to exclude secrets and adapt the paths to the machine.

**Mandatory step before trusting the result:**

```bash
$EDITOR ~/phoenix-config/phoenix.toml
```

Edit the list `paths` under `[dotfiles]` to match your real structure. Example if you use GNU Stow with a folder `~/dotfiles/`:

```toml
[dotfiles]
paths = [
    "~/dotfiles/hypr/.config/hypr",
    "~/dotfiles/waybar/.config/waybar",
    "~/dotfiles/alacritty/.config/alacritty",
]
```

Then restart:

```bash
phoenix snapshot
```

And check what was captured:

```bash
cat ~/phoenix-config/packages/pacman.txt | wc -l   # doit être proche du nombre de paquets réels
cat ~/phoenix-config/dotfiles/manifest.json         # doit lister tes vrais chemins
```

If `packages/pacman.txt` is empty or absurdly short, or if `manifest.json` has paths that don't exist for you, **don't go any further** — tell me the exact error.

---

## 3. Validate with tests

Before trusting `restore` or `rollback` in real life, run the test suite — it never touches your real system, everything is in an isolated environment (`tmp_path` pytest):

```bash
cd phoenix-tool
pytest tests/ -v
```

37 tests. If they don't all pass, something is broken between what I delivered to you and your environment (Python version, etc.) — correct it before continuing, not after.

---

## 4. Check that the system is aligned

```bash
phoenix status
```

Should say `✓ Système aligné avec le dernier snapshot.` right after a `snapshot`. If it shows a discrepancy at this point, there's a bug — not supposed to happen right after capture.

---

## 5. Test `restore` — NEVER live on your main machine

`restore` reinstalls packages and overwrites dotfiles. You don't blind test this on the system you use every day.

**Recommended option: VM Arch.**

```bash
# Dans la VM, après avoir cloné/copié ton repo phoenix-config :
export PHOENIX_REPO=/chemin/vers/phoenix-config
phoenix restore --skip-aur   # d'abord sans AUR, pour limiter la casse potentielle
```

See what happens at each step (confirmations enabled, no `--yes` for this first test). If all goes well:

```bash
phoenix restore   # avec AUR cette fois
```

**Only after a clean VM restore**, you can consider `phoenix restore` on a real, freshly installed machine (the real use case: reinstall, new PC, system crash).

---

## 6. Daily workflow

Once 1 to 5 are committed:

```bash
phoenix snapshot     # après chaque modif de config que tu veux garder
phoenix status        # pour vérifier avant un restore ou juste par prudence
```

Idea: a cron/systemd timer which launches `phoenix snapshot` automatically (eg: every evening). Not provided by default — it's up to you to plug it in if you want, with a `systemd --user timer` which calls `phoenix snapshot`.

---

## 7. Advanced use cases

### Rollback — revert to a previous state of the repo

```bash
phoenix rollback                # liste les 15 derniers snapshots
phoenix rollback <hash>         # ramène le REPO à cet état (le système live n'est pas touché)
phoenix restore                 # applique cet état au système, si tu veux vraiment revenir en arrière
```

### Diff between two machines

Useful when you have a second job. Get the repo from the other machine (Git clone, USB key, whatever):

```bash
phoenix diff /chemin/vers/repo-de-lautre-machine
```

---

## Known pitfalls (read this before complaining that it doesn’t work)

| Symptom | Probable cause |
|---|---|
| `phoenix: command not found` | `~/.local/bin` not in `$PATH` — see step 1 |
| `manifest.json` empty or wrong paths | `phoenix.toml` never edited after first run — see step 2 |
| `restore` crashes on AUR packets | None `yay`/`paru`, bootstrap refused or failed — restart with `--skip-aur` then install a helper manually |
| `phoenix status` shows divergence right after snapshot | Potential bug — report it with the exact message, not just "it doesn't work" |
| Dotfiles with secrets (SSH keys, tokens) committed to the repo | Not managed automatically — checks `~/phoenix-config/dotfiles/` before any push to a remote, especially public |

---

## Security — last reminder before pushing to GitHub

Phoenix does **not** detect secrets automatically beyond generic patterns (`*cache*`, `*.log`, etc. in `phoenix.toml`). If your dotfiles contain clear API keys, tokens, or SSH configs, **manually check `~/phoenix-config/dotfiles/` before pushing to a public remote.** A quick `git log -p` or `grep -riE "token|key|secret|password" ~/phoenix-config/dotfiles/` before the first push is two minutes against a leak.
