# Phoenix

A Python tool for capturing and restoring an Arch Linux configuration: package lists, selected dotfiles and enabled services, with Git-backed snapshots and configuration comparison.

## Status

This repository publishes the 0.7.0 source snapshot. Unit-test history is documented, but a complete restore on another machine has not been established by this publication.

The local source review identified two capture risks that remain important: directory copying follows symlinks, and the existing snapshot copy can be removed before its replacement succeeds. Do not rely on this version as your only backup. Test with disposable directories and an isolated restore target first.

## Installation

Python 3.11 or newer is required.

```sh
git clone https://github.com/alexandre-lorin/phoenix.git
cd phoenix
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
phoenix --help
```

## Usage

The commands below change snapshots or machine configuration. Read the [setup guide](SETUP.md) and review the configured paths before running them.

```sh
phoenix snapshot
phoenix status
phoenix status --content
phoenix restore
```

The default snapshot repository is `~/phoenix-config/`; `PHOENIX_REPO` overrides it. Inspect the generated `phoenix.toml` before the first real snapshot.

A snapshot creates a Git commit in the snapshot repository. Restore may install packages and modify dotfiles or services. `restore --yes` skips confirmations and can propagate noninteractive options to package managers; it is not a safe preview mode. Keep credentials and private files out of captured paths, including when the snapshot repository is private.

## Tests

```sh
python -m pytest tests/ -v
```

Tests use fixtures and do not prove successful restoration of a real Arch installation. See the [detailed implementation and validation reference](docs/README-REFERENCE.md) for supported comparison, rollback and restore behavior.
