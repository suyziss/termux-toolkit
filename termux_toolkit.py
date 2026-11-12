#!/usr/bin/env python3
"""Suyziss Termux Toolkit: practical, dependency-free Android/Termux utilities."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

APP_NAME = "Suyziss Termux Toolkit"
APP_VERSION = "1.2.28"
HOME = Path.home().resolve()
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "") or shutil.which("pkg") is not None
NO_COLOR = not sys.stdout.isatty() or "NO_COLOR" in os.environ


def paint(value: str, code: str) -> str:
    return value if NO_COLOR else f"\033[{code}m{value}\033[0m"


def heading(title: str) -> None:
    print("\n" + paint(f"== {title} ==", "1;36"))


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def run_command(args: list[str], timeout: int = 25) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def collect_system_info() -> dict:
    result = {
        "toolkit": APP_VERSION,
        "timestamp": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "os": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "home": str(HOME),
        "termux": IS_TERMUX,
    }
    try:
        usage = shutil.disk_usage(HOME)
        result["storage"] = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        }
    except OSError:
        result["storage"] = None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            memory = {}
            for line in meminfo.read_text(errors="replace").splitlines():
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    memory[key] = int(rest.strip().split()[0]) * 1024
            result["memory"] = memory
        except (OSError, ValueError, IndexError):
            result["memory"] = {}
    return result


def system_info(_: argparse.Namespace) -> int:
    data = collect_system_info()
    heading(APP_NAME)
    print(f"Version       : {data['toolkit']}")
    print(f"OS            : {data['os']}")
    print(f"Architecture  : {data['architecture']}")
    print(f"Python        : {data['python']}")
    print(f"Hostname      : {data['hostname']}")
    print(f"Home          : {data['home']}")
    print(f"Environment   : {'Termux' if data['termux'] else 'Linux / other'}")
    storage = data.get("storage")
    if storage:
        print(f"Storage total : {human_bytes(storage['total_bytes'])}")
        print(f"Storage used  : {human_bytes(storage['used_bytes'])}")
        print(f"Storage free  : {human_bytes(storage['free_bytes'])}")
    memory = data.get("memory", {})
    if "MemTotal" in memory:
        print(f"RAM total     : {human_bytes(memory['MemTotal'])}")
    if "MemAvailable" in memory:
        print(f"RAM available : {human_bytes(memory['MemAvailable'])}")
    return 0


def network_check(args: argparse.Namespace) -> int:
    heading("Network diagnostics")
    failed = False
    for host in args.host:
        print(f"\n[{host}]")
        try:
            started = time.perf_counter()
            records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            elapsed = (time.perf_counter() - started) * 1000
            addresses = sorted({item[4][0] for item in records})
            print(paint(f"DNS: OK ({elapsed:.1f} ms)", "32"))
            for address in addresses[:5]:
                print(f"  {address}")
        except socket.gaierror as exc:
            print(paint(f"DNS: FAILED ({exc})", "31"))
            failed = True
            continue
        request = urllib.request.Request(
            f"https://{host}/", method="HEAD",
            headers={"User-Agent": f"TermuxToolkit/{APP_VERSION}"},
        )
        try:
            started = time.perf_counter()
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                elapsed = (time.perf_counter() - started) * 1000
                print(paint(f"HTTPS: OK (HTTP {response.status}, {elapsed:.1f} ms)", "32"))
        except urllib.error.HTTPError as exc:
            print(f"HTTPS: reachable (HTTP {exc.code})")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(paint(f"HTTPS: FAILED ({exc})", "31"))
            failed = True
    return 1 if failed else 0


def safe_clean_targets(raw_paths: list[str]) -> list[Path]:
    targets: list[Path] = []
    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = HOME / candidate
        if candidate.is_symlink():
            raise ValueError(f"Refusing symbolic link: {candidate}")
        resolved = candidate.resolve()
        if resolved == HOME or HOME not in resolved.parents:
            raise ValueError(f"Refusing path outside your home directory or the home itself: {candidate}")
        if resolved.exists() and not resolved.is_dir():
            raise ValueError(f"Not a directory: {resolved}")
        targets.append(resolved)
    return targets


def directory_size(path: Path) -> int:
    total = 0
    try:
        for item in path.rglob("*"):
            try:
                if item.is_file() and not item.is_symlink():
                    total += item.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def clean_storage(args: argparse.Namespace) -> int:
    try:
        targets = safe_clean_targets(args.paths)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    heading("Storage cleaner")
    total = 0
    existing: list[Path] = []
    for path in targets:
        if not path.exists():
            print(f"Skip (not found): {path}")
            continue
        size = directory_size(path)
        total += size
        existing.append(path)
        print(f"{path} — {human_bytes(size)}")
    print(f"\nPotentially removable: {human_bytes(total)}")
    if not args.apply:
        print("Dry run only. Nothing was deleted. Add --apply to perform cleanup.")
        return 0
    if not existing:
        print("Nothing to clean.")
        return 0
    if not args.yes and input("Delete the contents of these directories? [y/N] ").strip().lower() != "y":
        print("Cancelled.")
        return 0
    removed = 0
    for path in existing:
        if path.is_symlink() or path.resolve() == HOME or HOME not in path.resolve().parents:
            print(f"Skipped unsafe path: {path}")
            continue
        for child in path.iterdir():
            try:
                if child.is_symlink() or child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
                removed += 1
            except OSError as exc:
                print(f"Could not remove {child}: {exc}")
    print(f"Removed {removed} item(s).")
    return 0


def package_manager(args: argparse.Namespace) -> int:
    if not IS_TERMUX:
        print("The packages command requires Termux and its 'pkg' utility.")
        return 1
    command = ["pkg", "list-installed"] if args.action == "installed" else ["pkg", "list-upgradable"]
    heading("Termux packages")
    try:
        result = run_command(command, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Could not run {' '.join(command)}: {exc}")
        return 1
    output = (result.stdout + "\n" + result.stderr).strip()
    print(output if output else "No package information returned.")
    return result.returncode


def backup_folder(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    if source.is_symlink():
        print("Source must not be a symbolic link.", file=sys.stderr)
        return 2
    source = source.resolve()
    if not source.is_dir():
        print(f"Source must be an existing directory: {source}", file=sys.stderr)
        return 2
    destination = Path(args.output).expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Cannot create destination: {exc}", file=sys.stderr)
        return 1
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = destination / f"{source.name or 'backup'}-{stamp}.zip"
    excluded = {".git", "__pycache__", ".cache", "node_modules"}
    count = 0
    heading("Folder backup")
    print(f"Source: {source}")
    print(f"Archive: {archive}")
    try:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for item in source.rglob("*"):
                if item == archive or any(part in excluded for part in item.relative_to(source).parts):
                    continue
                if item.is_symlink() or not item.is_file():
                    continue
                zf.write(item, item.relative_to(source))
                count += 1
    except (OSError, zipfile.BadZipFile) as exc:
        archive.unlink(missing_ok=True)
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Done: {count} file(s), {human_bytes(archive.stat().st_size)}")
    print("This is a normal ZIP archive, not encrypted.")
    return 0


def show_processes(args: argparse.Namespace) -> int:
    heading("Running processes")
    commands = [
        ["ps", "-A", "-o", "PID,PPID,USER,STAT,%CPU,%MEM,NAME"],
        ["ps", "-A"],
    ]
    for command in commands:
        try:
            result = run_command(command, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.splitlines()
            print("\n".join(lines[: args.limit + 1]))
            if len(lines) > args.limit + 1:
                print(f"... showing first {args.limit} processes")
            return 0
    print("Could not read the process list on this device.")
    return 1


def export_report(args: argparse.Namespace) -> int:
    data = collect_system_info()
    data["processes"] = None
    try:
        result = run_command(["ps", "-A"], timeout=15)
        if result.returncode == 0:
            data["processes"] = result.stdout.splitlines()[:101]
    except (OSError, subprocess.TimeoutExpired):
        pass
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Could not write report: {exc}", file=sys.stderr)
        return 1
    print(f"System report saved: {output}")
    return 0


def install_command(_: argparse.Namespace) -> int:
    prefix = Path(os.environ.get("PREFIX", str(HOME / ".local")))
    bindir = prefix / "bin"
    launcher = bindir / "toolkit"
    script = Path(__file__).resolve()
    python = Path(sys.executable).resolve()
    content = (
        "#!/usr/bin/env sh\n"
        "# Suyziss Termux Toolkit launcher\n"
        f"exec {shlex.quote(str(python))} {shlex.quote(str(script))} \"$@\"\n"
    )
    try:
        bindir.mkdir(parents=True, exist_ok=True)
        if launcher.exists():
            existing = launcher.read_text(errors="replace")
            if "Suyziss Termux Toolkit launcher" not in existing and not ("termux_toolkit.py" in existing and "termux-toolkit" in existing):
                print(f"Refusing to overwrite an unrelated command: {launcher}", file=sys.stderr)
                return 2
        launcher.write_text(content, encoding="utf-8")
        launcher.chmod(0o755)
    except OSError as exc:
        print(f"Could not install command: {exc}", file=sys.stderr)
        return 1
    print(f"Installed: {launcher}")
    print("You can now run: toolkit info")
    return 0


def uninstall_command(args: argparse.Namespace) -> int:
    prefix = Path(os.environ.get("PREFIX", str(HOME / ".local")))
    launcher = prefix / "bin" / "toolkit"
    if not launcher.is_file():
        print("The toolkit command is not installed.")
        return 0
    try:
        content = launcher.read_text(errors="replace")
        if "Suyziss Termux Toolkit launcher" not in content and not ("termux_toolkit.py" in content and "termux-toolkit" in content):
            print("Refusing to remove a command that does not belong to this toolkit.")
            return 2
        if not args.yes and input("Remove the toolkit command? [y/N] ").strip().lower() != "y":
            print("Cancelled.")
            return 0
        launcher.unlink()
    except OSError as exc:
        print(f"Could not uninstall command: {exc}", file=sys.stderr)
        return 1
    print("The toolkit launcher was removed. Project files were not changed.")
    return 0


def interactive_menu(_: argparse.Namespace) -> int:
    actions = {
        "1": ("Device information", ["info"]),
        "2": ("Network diagnostics", ["network"]),
        "3": ("Storage cleaner (dry run)", ["clean"]),
        "4": ("Termux packages", ["packages"]),
        "5": ("Running processes", ["processes"]),
        "6": ("Export system report", ["report"]),
        "7": ("Install toolkit command", ["install-command"]),
        "8": ("Folder backup", None),
    }
    while True:
        heading(f"{APP_NAME} v{APP_VERSION}")
        for key, (label, _) in actions.items():
            print(f"  {key}. {label}")
        print("  0. Exit")
        choice = input("\nSelect: ").strip()
        if choice == "0":
            return 0
        if choice not in actions:
            print("Invalid selection.")
            continue
        label, command = actions[choice]
        if command is None:
            source = input("Folder to back up: ").strip()
            if not source:
                continue
            output = input("Output directory [current]: ").strip() or "."
            command = ["backup", source, "-o", output]
        try:
            parsed = build_parser().parse_args(command)
            code = int(parsed.func(parsed))
            if code:
                print(f"Command finished with exit code {code}.")
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
        input("\nPress Enter to return to the menu...")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolkit",
        description=f"{APP_NAME} v{APP_VERSION} — utilities for Termux/Android and Linux.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version", help="Show toolkit version")
    p.set_defaults(func=lambda _: (print(f"{APP_NAME} v{APP_VERSION}") or 0))

    p = sub.add_parser("info", help="Show device, OS, RAM and storage information")
    p.set_defaults(func=system_info)

    p = sub.add_parser("network", help="Check DNS and HTTPS reachability")
    p.add_argument("host", nargs="*", default=["github.com", "google.com"])
    p.add_argument("--timeout", type=int, default=8)
    p.set_defaults(func=network_check)

    p = sub.add_parser("clean", help="Inspect or clean selected folders (dry-run by default)")
    p.add_argument("paths", nargs="*", default=[".cache"])
    p.add_argument("--apply", action="store_true", help="Actually delete directory contents")
    p.add_argument("--yes", action="store_true", help="Skip confirmation; use carefully")
    p.set_defaults(func=clean_storage)

    p = sub.add_parser("packages", help="List installed or upgradable Termux packages")
    p.add_argument("action", choices=("installed", "upgradable"), nargs="?", default="upgradable")
    p.set_defaults(func=package_manager)

    p = sub.add_parser("backup", help="Create a ZIP backup of a folder")
    p.add_argument("source")
    p.add_argument("-o", "--output", default=".")
    p.set_defaults(func=backup_folder)

    p = sub.add_parser("processes", help="Show running processes (read-only)")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=show_processes)

    p = sub.add_parser("report", help="Export a JSON system report")
    p.add_argument("-o", "--output", default=f"termux-toolkit-report-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
    p.set_defaults(func=export_report)

    p = sub.add_parser("install-command", help="Install the global 'toolkit' shell command")
    p.set_defaults(func=install_command)

    p = sub.add_parser("uninstall-command", help="Remove only the toolkit shell launcher")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=uninstall_command)

    p = sub.add_parser("menu", help="Open the interactive menu")
    p.set_defaults(func=interactive_menu)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
