# Termux Toolkit

A compact collection of practical utilities for **Termux on Android** and ordinary Linux. Python 3.9+; no third-party packages required.

## Features

- **System info** — OS, architecture, Python version, storage and available RAM.
- **Network check** — DNS resolution and HTTPS reachability for selected hosts.
- **Storage cleaner** — estimates folder size first; dry-run by default; only works inside your home directory.
- **Package status** — lists installed or upgradable packages using Termux `pkg`.
- **ZIP backup** — archives a selected folder and skips common generated folders.

## Install

In Termux:

```bash
pkg update
pkg install python git
git clone https://github.com/suyziss/termux-toolkit.git
cd termux-toolkit
python termux_toolkit.py --help
```

No `pip install` step is needed.

## Commands

```bash
# Device information
python termux_toolkit.py info

# Check DNS and HTTPS
python termux_toolkit.py network
python termux_toolkit.py network github.com example.com

# Inspect cache size (does not delete anything)
python termux_toolkit.py clean
python termux_toolkit.py clean .cache tmp

# Delete contents only after reviewing the dry-run
python termux_toolkit.py clean .cache --apply

# Package lists
python termux_toolkit.py packages installed
python termux_toolkit.py packages upgradable

# Back up a folder to ZIP
python termux_toolkit.py backup ~/storage/shared/Documents -o ~/backups
```

## Safety notes

- The cleaner is **dry-run by default**. It refuses the home directory itself, paths outside the home directory, and symbolic-link targets. Review the listed paths before using `--apply`.
- The backup command creates a normal ZIP file, **not an encrypted archive**. Do not store passwords, tokens, private keys, or other secrets in a backup you plan to share.
- Network checks make DNS lookups and HTTPS requests to the hostnames you provide. Use only hosts you intend to contact.
- The package command only displays package information; it does not install, remove, or upgrade packages.
- Android may limit which hardware and memory details are visible to ordinary apps.

## Compatibility

Designed for Termux on Android (including ARM64) and Linux with Python 3.9+. Some commands, especially `packages`, require Termux's `pkg` utility.

## Project structure

```text
termux-toolkit/
├── termux_toolkit.py
├── README.md
├── LICENSE
└── .gitignore
```

## License

MIT. See [LICENSE](LICENSE).
