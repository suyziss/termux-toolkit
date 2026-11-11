#!/usr/bin/env python3
"""Termux Toolkit: small, dependency-free utilities for Termux and Linux."""
from __future__ import annotations

import argparse
import datetime as dt
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

APP_VERSION = "1.0.0"
HOME = Path.home().resolve()


def heading(title: str) -> None:
    print(f"\n\033[1;36m== {title} ==\033[0m")


def human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def run_command(args: list[str], timeout: int = 25) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)


def system_info(_: argparse.Namespace) -> int:
    heading("System information")
    print(f"Toolkit       : {APP_VERSION}")
    print(f"OS            : {platform.platform()}")
    print(f"Architecture  : {platform.machine()}")
    print(f"Python        : {platform.python_version()}")
    print(f"Hostname      : {socket.gethostname()}")
    print(f"Home          : {HOME}")
    try:
        import android  # type: ignore
        print(f"Android       : {getattr(android, '__version__', 'detected')}")
    except Exception:
        if "com.termux" in os.environ.get("PREFIX", ""):
            print("Environment   : Termux")
    try:
        usage = shutil.disk_usage(HOME)
        print(f"Storage total : {human_bytes(usage.total)}")
        print(f"Storage used  : {human_bytes(usage.used)}")
        print(f"Storage free  : {human_bytes(usage.free)}")
    except OSError as exc:
        print(f"Storage       : unavailable ({exc})")
    # Linux memory information; Android may expose only a subset.
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        try:
            values = {}
            for line in meminfo.read_text(errors="replace").splitlines():
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable"):
                    values[key] = int(rest.strip().split()[0]) * 1024
            if "MemTotal" in values:
                print(f"RAM total     : {human_bytes(values['MemTotal'])}")
            if "MemAvailable" in values:
                print(f"RAM available : {human_bytes(values['MemAvailable'])}")
        except (OSError, ValueError, IndexError):
            pass
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
            print(f"DNS: OK ({elapsed:.1f} ms)")
            for address in addresses[:5]:
                print(f"  {address}")
        except socket.gaierror as exc:
            print(f"DNS: FAILED ({exc})")
            failed = True
            continue
        url = f"https://{host}/"
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "TermuxToolkit/1.0"})
        try:
            started = time.perf_counter()
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                elapsed = (time.perf_counter() - started) * 1000
                print(f"HTTPS: OK (HTTP {response.status}, {elapsed:.1f} ms)")
        except urllib.error.HTTPError as exc:
            # An HTTP response, even 403/405, proves the server was reached.
            print(f"HTTPS: reachable (HTTP {exc.code})")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"HTTPS: FAILED ({exc})")
            failed = True
    return 1 if failed else 0


def safe_clean_targets(raw_paths: list[str]) -> list[Path]:
    targets: list[Path] = []
    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = HOME / candidate
        resolved = candidate.resolve()
        if resolved == HOME or HOME not in resolved.parents:
            raise ValueError(f"Refusing path outside your home directory or the home itself: {candidate}")
        if candidate.is_symlink():
            raise ValueError(f"Refusing symbolic link: {candidate}")
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
        print("Dry run only. Nothing was deleted. Add --apply to perform the cleanup.")
        return 0
    if not existing:
        print("Nothing to clean.")
        return 0
    if not args.yes:
        answer = input("Delete the contents of these directories? [y/N] ").strip().lower()
        if answer != "y":
            print("Cancelled.")
            return 0
    removed = 0
    for path in existing:
        # Re-check the path immediately before mutation.
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
    if "com.termux" not in os.environ.get("PREFIX", "") and shutil.which("pkg") is None:
        print("The 'pkg' command was not found. This feature is intended for Termux.")
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
    source = source.resolve()
    if not source.is_dir() or source.is_symlink():
        print(f"Source must be an existing directory: {source}", file=sys.stderr)
        return 2
    destination = Path(args.output).expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    destination.mkdir(parents=True, exist_ok=True)
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
                if any(part in excluded for part in item.relative_to(source).parts):
                    continue
                if item.is_symlink() or not item.is_file():
                    continue
                zf.write(item, item.relative_to(source))
                count += 1
    except (OSError, zipfile.BadZipFile) as exc:
        try:
            archive.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1
    print(f"Done: {count} file(s), {human_bytes(archive.stat().st_size)}")
    print("Keep a second copy somewhere safe; this archive is not encrypted.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="termux-toolkit",
        description="Useful, dependency-free diagnostics and maintenance tools for Termux/Android.",
        epilog="Examples: python termux_toolkit.py info | network | clean | packages | backup",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("info", help="Show device, OS, RAM and storage information")
    p.set_defaults(func=system_info)
    p = sub.add_parser("network", help="Check DNS and HTTPS reachability")
    p.add_argument("host", nargs="*", default=["github.com", "google.com"], help="Hostnames to check")
    p.add_argument("--timeout", type=int, default=8, help="HTTPS timeout in seconds")
    p.set_defaults(func=network_check)
    p = sub.add_parser("clean", help="Inspect or clean selected folders (dry-run by default)")
    p.add_argument("paths", nargs="*", default=[".cache"], help="Directories inside your home folder")
    p.add_argument("--apply", action="store_true", help="Actually delete directory contents")
    p.add_argument("--yes", action="store_true", help="Skip confirmation (use carefully)")
    p.set_defaults(func=clean_storage)
    p = sub.add_parser("packages", help="List installed or upgradable Termux packages")
    p.add_argument("action", choices=("installed", "upgradable"), nargs="?", default="upgradable")
    p.set_defaults(func=package_manager)
    p = sub.add_parser("backup", help="Create a ZIP backup of a folder")
    p.add_argument("source", help="Folder to back up")
    p.add_argument("-o", "--output", default=".", help="Directory for the ZIP archive")
    p.set_defaults(func=backup_folder)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
