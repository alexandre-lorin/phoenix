# Phoenix

Complete cloning of Arch config (packages, dotfiles, services) versioned in Git.

**→ [SETUP.md](.././SETUP.md) for the complete installation, step by step, with pitfalls to avoid.**

## Quick install

```bash
git clone <ton repo> phoenix-tool
cd phoenix-tool
pip install --user -e .
```

`tomllib` is part of the stdlib since Python 3.11 — check that you are on it (`python --version`). On Arch this is already the basic case.

## Usage

```bash
phoenix snapshot
phoenix restore              # interactif, demande confirmation à chaque étape
phoenix restore --yes        # non-interactif de bout en bout : ni Phoenix ni pacman/yay ne demandent quoi que ce soit
phoenix restore --skip-aur   # ignore les paquets AUR
```

First run: creates `~/phoenix-config/` (override with `PHOENIX_REPO=/autre/path`) and a `phoenix.toml` with default paths. **Edit this file** to match your real dotfile structure before the first real snapshot.

⚠️ Phoenix captures configured files as is. Checks that they do not contain tokens, API keys or other secrets before pushing the repository to a remote (even private) — the Git history keeps everything, even after later deleting the file.

Each `phoenix snapshot`:
1. Exports `pacman -Qqe` (native) and `pacman -Qqem` (AUR) separately → `packages/`
2. Copies the paths listed in `phoenix.toml` → `dotfiles/` — **refuses and writes nothing** if two configured paths share the same final name (e.g. two different `nvim` folders) rather than letting the second silently overwrite the first
3. Exports activated `systemctl` services (system + user, only if `include_user_services = true`) → `services/`
4. Commit everything with a timestamped message

## Implementation status

| Step | Status |
|---|---|
| V0 — packet inventory | ✅ |
| V1 — capture dotfiles | ✅ |
| V2 — services & systemd | ✅ |
| V3 — `phoenix snapshot` | ✅ |
| V4 — `phoenix restore` | ✅ |
| V5 — divergence detection | ✅ |
| V6 — diff between two machines | ✅ |
| Rollback (point 4 of the brief) | ✅ |
| DotDiff V0-V1 — comparison + readable output | ✅ (= `phoenix status`) |
| DotDiff V2 — text content diff | ✅ (`phoenix status --content`) |
| DotDiff V3 — selective file-by-file actions | ✅ (`phoenix status --resolve`) |
| DotDiff V5 — periodic drift reminder | ✅ (`phoenix reminder`) |

## Reliability — audit and fixes (feature freeze while I close this)

A technical review highlighted bugs that directly affected the three central guarantees of the tool (capture → restore → rollback). All fixed with dedicated regression test:

- **Capture — basename collision.** Two paths configured with the same leaf (`~/a/nvim` and `~/b/nvim`) caused the second to silently overwrite the first in the manifest — unrecoverable data loss since the first was never copied. `capture_dotfiles` (and therefore `phoenix snapshot`) now refuses **before** to copy anything as soon as a collision is detected, with a clear message to support this.
- **Rollback — incomplete resynchronization.** `git checkout <ref> -- <path>` (overlay mode, the default) never deletes a file added after `<ref>` — a "rollback" therefore left files lying around that were supposed to no longer exist. Replaced by `git checkout --no-overlay`, which resynchronizes the tree exactly (adds undone, edits undone, deletes undone).
- **`diff_services` ignored `include_user_services`.** With the flag set to `false`, `phoenix status` still compared the `--user` units to a never-updated `services/user.txt`, generating false positives in continuous. `diff_services` now skips the `user` axis entirely if the flag is disabled.
- **`restore --yes` wasn't really non-interactive.** The bypass only covered the internal confirmations of Phoenix; `pacman`/`yay`/`paru` still asked their own question. `--noconfirm` is now propagated to these commands when `--yes` is passed — a scripted restore (test VM, provisioning) no longer blocks on them. (The only exception assumed: a `sudo` without a password remains a prerequisite for a completely unsupervised restore — it is not a confirmation of action, it is an authentication boundary, outside the scope of `--yes`.)

### Robust Restore (second pass, once the trust engine is stabilized)

A `restore` is most often used months after the snapshot, on a new machine — exactly the time when a package has been renamed/removed from the repositories, or a systemd unit has disappeared with its package. Three fixes so that it no longer causes everything to fail altogether:

- **Packages/AUR — failure isolation.** `pacman -S`/`yay -S` failed entirely if a single package in the batch was not found, including dozens of others that could have installed without issue. Now: batch attempt first (fast, normal case), and only if it fails, retry packet by packet to precisely isolate the faulty one(s) — the others install anyway.
- **Services — stderr remounted instead of swallowed.** `systemctl enable ... check=False` without reading output caused a hidden or absent unit to appear "on" from the user's perspective. Same isolation strategy as packets, with error details displayed.
- **Final summary + faithful exit code.** `phoenix restore` now displays a report (`✓ N installés`, `⚠ N indisponibles`, etc. for each axis) and exits with the code `1` if there was any isolated failure — no more "Restore completed." optimistic when packages have never been installed.
- **No more automatic AUR helper bootstrap.** The old version cloned `yay-bin` from the AUR and launched `makepkg -si --noconfirm` with sudo to compile and install an unverified third-party package — too invasive for a tool supposed to restore *your* config, not install a package manager for you. Without `yay`/`paru` detected, `phoenix restore` prevents and leaves AUR packets aside; It's up to you to install them manually.

### Nice-to-have (third pass, polish once the rest is stable)

- **`_hash_tree` now prunes excluded folders instead of browsing them and then filtering.** `os.walk` + `dirnames[:] = [...]` prevents going down into a folder excluded by pattern (plugin manager cache, `node_modules`...) rather than listing all its contents and then throwing it away. Zero functional difference, just less I/O paid for nothing each `phoenix status`.
- **No more double calculation of diff dotfiles on `phoenix status --content`/`--resolve`.** `run_status()` now returns the already calculated diff (`(aligned, dot)`) instead of `cli.py` calling `diff_dotfiles()` a second time behind — the hash of the entire dotfile tree is no longer done twice for a single invocation.
- **`phoenix snapshot` shows a `git diff --stat` after the commit.** Knowing that a commit took place said nothing about its contents; now the number of affected files and the +/- are visible immediately, without having to launch `git show` by hand.
- **The reminder (V5) no longer counts rollback commits as snapshots.** `last_snapshot_timestamp` now specifically looks for the last commit whose message begins with `snapshot:` — a frequent `rollback` without ever restarting a real `snapshot` no longer resets the drift counter wrongly.

## Tests

Formal pytest suite — 92 tests, all testable-without-real-Arch:

```bash
pip install --user -e ".[dev]"
pytest tests/ -v
```

Covers: roundtrip capture/restore dotfiles (with backup), capture refusal on collision, divergence detection (including compliance with `include_user_services`), diff between two machines, rollback via real Git (including exact resynchronization on combined add+modify+delete, and the clean failure case on an unknown commit), propagation of `--noconfirm` in mode `--yes`. **What it DOES NOT cover**: anything that actually calls `pacman`/`systemctl`/`makepkg` — only your machine can validate that.

## `phoenix rollback` (point 4 from the original brief)

The Git repo already has the full history. Rollback rolls `packages/services/dotfiles/phoenix.toml` back to the **exact** state of a previous commit — including deleting files that appeared after that commit, not just overwriting ones that already existed — without ever losing history: the rollback itself becomes a new commit, so `git log` keeps everything, including roundtrips.

```bash
phoenix rollback                # liste les 15 derniers snapshots
phoenix rollback <hash>         # revient à cet état (demande confirmation)
phoenix rollback <hash> --yes   # sans confirmation
```

Rollback does **not** touch the live system — only the repo. To apply the rollback state, run `phoenix restore` next. Voluntary separation: “changing your mind about the repo” and “tampering with the system” should never be the same accidental operation.

## `phoenix status` (V5)

Read only, zero writes to the system. Compare the current state to the last committed snapshot:

```bash
phoenix status
```

- **Packages**: what has been installed/uninstalled by hand since the last `snapshot`.
- **Services**: services activated/deactivated manually.
- **Dotfiles**: diff by hash SHA-256, file by file — modified, added, deleted.

Exit code `0` = nothing moved, `1` = discrepancy detected. Usable in pre-check before `restore`:

```bash
phoenix status || echo "snapshot avant de restaurer, sinon tu perds tes modifs manuelles"
```

`restore` also calls a divergence check on dotfiles before overwriting them and displays a warning — it doesn't block (the goal of `restore` is sometimes to overwrite on purpose), but you can no longer say you didn't know.

### DotDiff — `phoenix status --content` / `--resolve`

Subset of `status`, not a separate tool (the versioned Git repo is already the only source of truth, no need to open another one).

```bash
phoenix status --content    # V2 : diff textuel réel (git diff --no-index) pour chaque dotfile modifié
phoenix status --resolve    # V3 : résolution interactive, fichier par fichier
```

`--resolve` requires, for each divergent file, an individual action — never to “overwrite everything as a whole”:

- **modified**: keep the local modification / return to the versioned version (auto backup, `.phoenix-bak-<timestamp>`, never dry deletion) / skip
- **new (never captured)**: keep / delete (auto backup) / skip
- **deleted from system**: keep deleted / restore from snapshot / skip

No `--yes` flag on `--resolve`: this is a per-file choice, not a global yes/no — forcing one by default would defeat the very purpose of this feature.

The name `phoenix diff` is already taken by V6 (comparison between two machines) - hence the integration as options of `status` rather than a new subcommand.

Two careful details:

- **`phoenix status --resolve --content`**: the textual diff of each modified file is displayed just before the question, no need to launch `--content` separately beforehand to know what we are deciding on.
- **Binary files**: `git diff --no-index` outputs an unreadable `"Binary files ... differ"` on a modified binary. DotDiff detects this and instead displays a clear message (`fichier binaire — pas de diff textuel affichable`), both in `--content` and in `--resolve --content`.

### DotDiff V5 — `phoenix reminder`

Periodic reminder: signals if the dotfiles have drifted **and** that it has been more than X days (default 7) without a new snapshot. A fresh drift is no problem — it will be absorbed at the next normal `phoenix snapshot`; it is the prolonged forgetting that deserves a reminder. Read only, never take a snapshot for you.

```bash
phoenix reminder                # seuil par défaut : 7 jours
phoenix reminder --days 14
phoenix reminder --quiet        # rien à l'écran, juste le code de sortie (pour hooks/scripts)
```

Exit code `0` = nothing to report, `1` = callback triggered. Not a daemon — plug into a systemd cron/timer or shell hook:

```bash
# crontab -e, une fois par jour
0 9 * * * PHOENIX_REPO=/home/user/phoenix-config /usr/bin/phoenix reminder

# .bashrc / .zshrc, rappel à l'ouverture d'un nouveau shell
phoenix reminder --quiet || echo "⚠ dotfiles en dérive depuis un moment — phoenix status ?"
```

## `phoenix diff <autre_repo>` (V6)

Compare **two already snapshotted Phoenix repositories** — not two live systems. Voluntary: there is no guarantee that your laptop and a future second station will be turned on at the same time. The Git repo is the only source of truth that is always comparable, regardless of the transport (Git clone, USB key, network share).

```bash
git clone <remote-du-poste-2> /tmp/poste2-config
phoenix diff /tmp/poste2-config
```

Sorts packages/services/dotfiles that differ between the two, hash-based for dotfiles. Exit code `0` = identical machines, `1` = discrepancy.

## How `restore` works

Fixed order: **packages → services → dotfiles**. This isn't arbitrary — dotfiles reference binaries that should already be installed, and services depend on packages, not the other way around.

1. **Packages**: compares `packages/pacman.txt` and `aur.txt` to what is already installed, installs only the missing one. If no AUR helper (`yay`/`paru`) is found and there are AUR packages to install, warn and leave these packages aside — install `yay`/`paru` yourself then restart.
2. **Services**: Enables missing units (`systemctl enable`), system and `--user` separately.
3. **Dotfiles**: restores via the `manifest.json` generated to the last snapshot (name → full original path). **Any existing file/folder at the target is renamed to `.phoenix-bak-<timestamp>` before overwriting — never outright deletion.**

Each step requires individual confirmation (`o/N`), except with `--yes`.

## What is NOT managed (voluntarily, for the moment)

- **Secrets** (SSH keys, tokens in configs) are not automatically excluded beyond generic patterns. Check `dotfiles/` before pushing to a remote repo, especially if public.
- No automatic rollback if `restore` crashes en route — the `.phoenix-bak-*` backups exist, but it's up to you to roll them back manually for now.
- V5 (divergence detection) does not yet exist: if you modify a config by hand without restarting `snapshot`, `restore` has no way of knowing and will overwrite silently at the next restore.
