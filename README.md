# Suyziss Termux Toolkit

**Version: 1.2.29**  
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
- **Global command** — install a `toolkit` launcher so commands work from any directory.
- **Termux Translate** — translate terminal text between language codes using a remote translation API, with optional clipboard integration.

## Install

In Termux:

```bash
pkg update
pkg install python git
git clone https://github.com/suyziss/termux-toolkit.git
cd termux-toolkit
python3 translate.py --help
```

No `pip install` step is required.

## Termux Translate

Translate text directly from the shell:

```bash
python3 translate.py -t ru "Hello, how are you?"
python3 translate.py -s ru -t en "Привет, как дела?"
python3 translate.py -s en -t ky "Welcome to Termux"
```

Read from stdin:

```bash
echo "Good morning" | python3 translate.py -t ru
```

Translate the Termux clipboard and copy the result back:

```bash
python3 translate.py --clipboard -t ru --copy
```

For clipboard support, install Termux:API and the Termux API package:

```bash
pkg install termux-api
```

The translator is dependency-free, but it requires network access and uses the MyMemory translation API. Do not send passwords, API keys, private messages, or other sensitive data.

## Install a short command

From the project directory:

```bash
mkdir -p "$PREFIX/bin"
cp ttranslate "$PREFIX/bin/ttranslate"
chmod +x "$PREFIX/bin/ttranslate"
```

Then:

```bash
ttranslate -t ru "Hello from Termux"
```

## Existing toolkit commands

```bash
python3 termux_toolkit.py info
python3 termux_toolkit.py network
python3 termux_toolkit.py clean
python3 termux_toolkit.py packages upgradable
python3 termux_toolkit.py processes
python3 termux_toolkit.py report
python3 termux_toolkit.py backup ~/storage/shared/Documents -o ~/backups
python3 termux_toolkit.py menu
```

## Safety

- Translation sends the text you provide to the configured remote translation service.
- The translator does not require root and does not modify system files.
- Clipboard operations require Termux:API.
- Existing toolkit cleanup and backup safety rules remain unchanged.

## Compatibility

Designed for Termux on Android and Linux with Python 3.9+. No root access is required.

## License

MIT. See LICENSE.
