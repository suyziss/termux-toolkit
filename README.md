# Suyziss Termux Toolkit

**Version: 1.2.28**  
A dependency-free command-line toolkit for Termux on Android (including ARM64) and ordinary Linux. Requires Python 3.9+; no third-party Python packages and no root access.

## Features

- **System information** — OS, architecture, Python, storage and available RAM.
- **Network diagnostics** — DNS resolution and HTTPS reachability.
- **Storage cleaner** — calculates folder sizes; dry-run by default; refuses paths outside your home directory.
- **Package status** — lists installed or upgradable Termux packages without changing them.
- **ZIP backup** — archives a folder and skips common generated folders.
- **Process viewer** — read-only process listing; does not stop processes.
- **System report** — exports a JSON report with device and process information.
- **Interactive menu** — launch the main tools from a numbered menu.
- **Global command** — install a \`toolkit\` launcher so commands work from any directory.

## Install

In Termux, run each command separately:

\`\`\`bash
pkg update
pkg install python git
git clone https://github.com/suyziss/termux-toolkit.git
cd termux-toolkit
python termux_toolkit.py --help
\`\`\`

No \`pip install\` step is required.

## Install the short command

From the project directory:

\`\`\`bash
python termux_toolkit.py install-command
\`\`\`

After that, use \`toolkit\` from any directory:

\`\`\`bash
toolkit version
toolkit info
toolkit menu
\`\`\`

The installer refuses to overwrite an unrelated existing \`toolkit\` command. To remove only the launcher later:

\`\`\`bash
toolkit uninstall-command
\`\`\`

Your project files are not deleted by the uninstaller.

## Commands

\`\`\`bash
toolkit info
toolkit network
toolkit network github.com example.com
toolkit clean
toolkit clean .cache tmp
toolkit clean .cache --apply
toolkit packages installed
toolkit packages upgradable
toolkit processes
toolkit processes --limit 60
toolkit report
toolkit report -o ~/storage/shared/termux-report.json
toolkit backup ~/storage/shared/Documents -o ~/backups
toolkit menu
\`\`\`

If you have not installed the global launcher, replace \`toolkit\` with \`python termux_toolkit.py\`.

## Safety

- The cleaner is **dry-run by default**. Review the listed paths before using \`--apply\`. It refuses the home directory itself, paths outside the home directory, and symbolic-link targets.
- The process viewer is read-only. It does not kill or modify processes.
- The package command only displays package information. It does not install, remove, or upgrade packages.
- Backups are ordinary ZIP files, not encrypted. Do not share archives containing passwords, tokens, private keys, or other secrets.
- Network diagnostics make DNS lookups and HTTPS requests to the hostnames you specify.
- The JSON report includes basic system details and a short process listing. Review it before sharing.

## Compatibility

Designed for Termux on Android (including ARM64) and Linux with Python 3.9+. No root access is required. The \`packages\` command requires Termux's \`pkg\` utility. Some hardware details may be hidden by Android.

## Project structure

\`\`\`text
termux-toolkit/
├── termux_toolkit.py
├── README.md
├── CHANGELOG.md
├── LICENSE
└── .gitignore
\`\`\`

## License

MIT. See [LICENSE](LICENSE).
