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
APP_VERSION = "1.2.30"
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
    print(f"Версия        : {data['toolkit']}")
    print(f"Система       : {data['os']}")
    print(f"Архитектура   : {data['architecture']}")
    print(f"Python        : {data['python']}")
    print(f"Имя устройства: {data['hostname']}")
    print(f"Домашняя папка: {data['home']}")
    print(f"Среда         : {'Termux' if data['termux'] else 'Linux / другая'}")
    storage = data.get("storage")
    if storage:
        print(f"Память всего  : {human_bytes(storage['total_bytes'])}")
        print(f"Занято        : {human_bytes(storage['used_bytes'])}")
        print(f"Свободно      : {human_bytes(storage['free_bytes'])}")
    memory = data.get("memory", {})
    if "MemTotal" in memory:
        print(f"ОЗУ всего     : {human_bytes(memory['MemTotal'])}")
    if "MemAvailable" in memory:
        print(f"ОЗУ доступно  : {human_bytes(memory['MemAvailable'])}")
    return 0


def network_check(args: argparse.Namespace) -> int:
    heading("Проверка сети")
    failed = False
    for host in args.host:
        print(f"\n[{host}]")
        try:
            started = time.perf_counter()
            records = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            elapsed = (time.perf_counter() - started) * 1000
            addresses = sorted({item[4][0] for item in records})
            print(paint(f"DNS: доступен ({elapsed:.1f} ms)", "32"))
            for address in addresses[:5]:
                print(f"  {address}")
        except socket.gaierror as exc:
            print(paint(f"DNS: ошибка ({exc})", "31"))
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
                print(paint(f"HTTPS: доступен (HTTP {response.status}, {elapsed:.1f} ms)", "32"))
        except urllib.error.HTTPError as exc:
            print(f"HTTPS: доступен (HTTP {exc.code})")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(paint(f"HTTPS: ошибка ({exc})", "31"))
            failed = True
    return 1 if failed else 0


def safe_clean_targets(raw_paths: list[str]) -> list[Path]:
    targets: list[Path] = []
    for raw in raw_paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = HOME / candidate
        if candidate.is_symlink():
            raise ValueError(f"Запрещена символическая ссылка: {candidate}")
        resolved = candidate.resolve()
        if resolved == HOME or HOME not in resolved.parents:
            raise ValueError(f"Нельзя очищать путь вне домашней папки или саму домашнюю папку: {candidate}")
        if resolved.exists() and not resolved.is_dir():
            raise ValueError(f"Это не папка: {resolved}")
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
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    heading("Очистка хранилища")
    total = 0
    existing: list[Path] = []
    for path in targets:
        if not path.exists():
            print(f"Пропуск (не найдено): {path}")
            continue
        size = directory_size(path)
        total += size
        existing.append(path)
        print(f"{path} — {human_bytes(size)}")
    print(f"\nМожно освободить: {human_bytes(total)}")
    if not args.apply:
        print("Проверочный режим: ничего не удалено. Для очистки добавьте --apply.")
        return 0
    if not existing:
        print("Нет папок для очистки.")
        return 0
    if not args.yes and input("Удалить содержимое этих папок? [д/н] ").strip().lower() not in ("д", "да", "y", "yes"):
        print("Отменено.")
        return 0
    removed = 0
    for path in existing:
        if path.is_symlink() or path.resolve() == HOME or HOME not in path.resolve().parents:
            print(f"Пропущен небезопасный путь: {path}")
            continue
        for child in path.iterdir():
            try:
                if child.is_symlink() or child.is_file():
                    child.unlink()
                elif child.is_dir():
                    shutil.rmtree(child)
                removed += 1
            except OSError as exc:
                print(f"Не удалось удалить {child}: {exc}")
    print(f"Удалено элементов: {removed}.")
    return 0


def package_manager(args: argparse.Namespace) -> int:
    if not IS_TERMUX:
        print("Команда packages работает только в Termux и требует утилиту pkg.")
        return 1
    command = ["pkg", "list-installed"] if args.action == "installed" else ["pkg", "list-upgradable"]
    heading("Пакеты Termux")
    try:
        result = run_command(command, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Не удалось выполнить {' '.join(command)}: {exc}")
        return 1
    output = (result.stdout + "\n" + result.stderr).strip()
    print(output if output else "Информация о пакетах не получена.")
    return result.returncode


def backup_folder(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    if not source.is_absolute():
        source = Path.cwd() / source
    if source.is_symlink():
        print("Исходная папка не должна быть символической ссылкой.", file=sys.stderr)
        return 2
    source = source.resolve()
    if not source.is_dir():
        print(f"Исходная папка не найдена: {source}", file=sys.stderr)
        return 2
    destination = Path(args.output).expanduser()
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Не удалось создать папку назначения: {exc}", file=sys.stderr)
        return 1
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = destination / f"{source.name or 'backup'}-{stamp}.zip"
    excluded = {".git", "__pycache__", ".cache", "node_modules"}
    count = 0
    heading("Резервная копия папки")
    print(f"Источник: {source}")
    print(f"Архив: {archive}")
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
        print(f"Ошибка создания копии: {exc}", file=sys.stderr)
        return 1
    print(f"Готово: файлов {count}, {human_bytes(archive.stat().st_size)}")
    print("Создан обычный ZIP-архив без шифрования.")
    return 0


def show_processes(args: argparse.Namespace) -> int:
    heading("Запущенные процессы")
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
                print(f"... показаны первые {args.limit} процессов")
            return 0
    print("Не удалось получить список процессов на этом устройстве.")
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
        print(f"Не удалось сохранить отчёт: {exc}", file=sys.stderr)
        return 1
    print(f"Отчёт о системе сохранён: {output}")
    return 0


def translate_command(args: argparse.Namespace) -> int:
    translator = Path(__file__).resolve().with_name("translate.py")
    if not translator.is_file():
        print(f"Файл переводчика не найден: {translator}", file=sys.stderr)
        return 1
    command = [sys.executable, str(translator)]
    if args.source:
        command.extend(["--source", args.source])
    command.extend(["--target", args.target])
    if args.copy:
        command.append("--copy")
    if args.clipboard:
        command.append("--clipboard")
    if args.timeout:
        command.extend(["--timeout", str(args.timeout)])
    if args.text:
        command.extend(args.text)
    try:
        result = subprocess.run(command, text=True, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Не удалось запустить переводчик: {exc}", file=sys.stderr)
        return 1
    return result.returncode


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
                print(f"Отказ: команда с таким именем уже занята: {launcher}", file=sys.stderr)
                return 2
        launcher.write_text(content, encoding="utf-8")
        launcher.chmod(0o755)
    except OSError as exc:
        print(f"Не удалось установить команду: {exc}", file=sys.stderr)
        return 1
    print(f"Установлено: {launcher}")
    print("Теперь можно выполнить: toolkit info")
    return 0


def uninstall_command(args: argparse.Namespace) -> int:
    prefix = Path(os.environ.get("PREFIX", str(HOME / ".local")))
    launcher = prefix / "bin" / "toolkit"
    if not launcher.is_file():
        print("Команда toolkit ещё не установлена.")
        return 0
    try:
        content = launcher.read_text(errors="replace")
        if "Suyziss Termux Toolkit launcher" not in content and not ("termux_toolkit.py" in content and "termux-toolkit" in content):
            print("Отказ: эта команда не принадлежит Toolkit.")
            return 2
        if not args.yes and input("Удалить команду toolkit? [д/н] ").strip().lower() not in ("д", "да", "y", "yes"):
            print("Отменено.")
            return 0
        launcher.unlink()
    except OSError as exc:
        print(f"Не удалось удалить команду toolkit: {exc}", file=sys.stderr)
        return 1
    print("Команда toolkit удалена. Файлы проекта не изменены.")
    return 0


def interactive_menu(_: argparse.Namespace) -> int:
    actions = {
        "1": ("Информация об устройстве", ["info"]),
        "2": ("Проверка сети", ["network"]),
        "3": ("Очистка хранилища (сначала проверка)", ["clean"]),
        "4": ("Пакеты Termux", ["packages"]),
        "5": ("Запущенные процессы", ["processes"]),
        "6": ("Сохранить системный отчёт", ["report"]),
        "7": ("Установить команду toolkit", ["install-command"]),
        "8": ("Резервная копия папки", None),
        "9": ("Перевести текст", None),
        "10": ("Файловый менеджер TUI", ["files"]),
    }
    while True:
        heading(f"{APP_NAME} v{APP_VERSION}")
        for key, (label, _) in actions.items():
            print(f"  {key}. {label}")
        print("  0. Выход")
        choice = input("\nВыбор: ").strip()
        if choice == "0":
            return 0
        if choice not in actions:
            print("Нет такого пункта.")
            continue
        label, command = actions[choice]
        if command is None and label == "Резервная копия папки":
            source = input("Какую папку сохранить: ").strip()
            if not source:
                continue
            output = input("Куда сохранить [текущая папка]: ").strip() or "."
            command = ["backup", source, "-o", output]
        elif command is None and label == "Перевести текст":
            command = ["trans"]
        try:
            parsed = build_parser().parse_args(command)
            code = int(parsed.func(parsed))
            if code:
                print(f"Команда завершилась с кодом {code}.")
        except (KeyboardInterrupt, EOFError):
            print("\nОтменено.")
        input("\nНажмите Enter, чтобы вернуться в меню...")



def open_file_manager(args: argparse.Namespace) -> int:
    explorer = Path(__file__).resolve().with_name("tui_explorer.py")
    if not explorer.is_file():
        print(f"Файловый менеджер не найден: {explorer}", file=sys.stderr)
        return 1
    command = [sys.executable, str(explorer)]
    if args.path:
        command.append(args.path)
    try:
        result = subprocess.run(command, check=False)
    except OSError as exc:
        print(f"Не удалось запустить файловый менеджер: {exc}", file=sys.stderr)
        return 1
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolkit",
        description=f"{APP_NAME} v{APP_VERSION} — набор инструментов для Termux/Android и Linux.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("version", help="Показать версию Toolkit")
    p.set_defaults(func=lambda _: (print(f"{APP_NAME} v{APP_VERSION}") or 0))

    p = sub.add_parser("info", help="Показать сведения об устройстве, системе, ОЗУ и памяти")
    p.set_defaults(func=system_info)

    p = sub.add_parser("network", help="Проверить DNS и доступность сайтов по HTTPS")
    p.add_argument("host", nargs="*", default=["github.com", "google.com"])
    p.add_argument("--timeout", type=int, default=8)
    p.set_defaults(func=network_check)

    p = sub.add_parser("clean", help="Проверить или очистить выбранные папки (по умолчанию только проверка)")
    p.add_argument("paths", nargs="*", default=[".cache"])
    p.add_argument("--apply", action="store_true", help="Действительно удалить содержимое папок")
    p.add_argument("--yes", action="store_true", help="Не спрашивать подтверждение (используйте осторожно)")
    p.set_defaults(func=clean_storage)

    p = sub.add_parser("packages", help="Показать установленные или доступные для обновления пакеты Termux")
    p.add_argument("action", choices=("installed", "upgradable"), nargs="?", default="upgradable")
    p.set_defaults(func=package_manager)

    p = sub.add_parser("backup", help="Создать ZIP-копию папки")
    p.add_argument("source")
    p.add_argument("-o", "--output", default=".")
    p.set_defaults(func=backup_folder)

    p = sub.add_parser("processes", help="Показать процессы без возможности их изменения")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=show_processes)

    p = sub.add_parser("report", help="Сохранить системный отчёт в JSON")
    p.add_argument("-o", "--output", default=f"termux-toolkit-report-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
    p.set_defaults(func=export_report)

    p = sub.add_parser("trans", aliases=["translate"], help="Перевести текст")
    p.add_argument("text", nargs="*", help="Текст для перевода")
    p.add_argument("-s", "--source", default="auto", help="Код исходного языка")
    p.add_argument("-t", "--target", default="ru", help="Код языка перевода (по умолчанию ru)")
    p.add_argument("-c", "--copy", action="store_true", help="Скопировать перевод в буфер Termux")
    p.add_argument("--clipboard", action="store_true", help="Перевести содержимое буфера Termux")
    p.add_argument("--timeout", type=int, default=20, help="Тайм-аут запроса в секундах")
    p.set_defaults(func=translate_command)

    p = sub.add_parser("install-command", help="Установить команду toolkit для запуска из любой папки")
    p.set_defaults(func=install_command)

    p = sub.add_parser("uninstall-command", help="Удалить только команду запуска Toolkit")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=uninstall_command)

    p = sub.add_parser("files", help="Открыть файловый менеджер TUI со стрелочной навигацией")
    p.add_argument("path", nargs="?", default=None, help="Начальная папка")
    p.set_defaults(func=open_file_manager)

    p = sub.add_parser("menu", help="Открыть главное меню")
    p.set_defaults(func=interactive_menu)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\nОтменено.")
        return 130
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
