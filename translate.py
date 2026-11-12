#!/usr/bin/env python3
"""Suyziss Termux Translate: simple Russian-first terminal translator."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.mymemory.translated.net/get"
USER_AGENT = "Suyziss-Termux-Translate/1.1"

LANGUAGES = {
    "русский": "ru", "рус": "ru", "английский": "en", "англ": "en",
    "кыргызский": "ky", "кыргызча": "ky", "кыргыз": "ky",
    "казахский": "kk", "украинский": "uk", "немецкий": "de",
    "французский": "fr", "испанский": "es", "турецкий": "tr",
    "китайский": "zh-CN", "японский": "ja", "корейский": "ko",
    "итальянский": "it", "польский": "pl", "португальский": "pt",
}


def normalize_language(value: str) -> str:
    value = value.strip().lower()
    return LANGUAGES.get(value, value)


def detect_source(text: str) -> str:
    """Small offline heuristic; user can always override with --source."""
    letters = [char.lower() for char in text if char.isalpha()]
    if not letters:
        return "en"
    cyrillic = sum("а" <= char <= "я" or char in "ёөүңієїґ" for char in letters)
    if cyrillic / len(letters) < 0.25:
        return "en"
    if any(char in text.lower() for char in "өүң"):
        return "ky"
    if any(char in text.lower() for char in "іїєґ"):
        return "uk"
    return "ru"


def translate_text(text: str, source: str, target: str, timeout: int) -> str:
    if not text.strip():
        raise ValueError("Введите текст для перевода.")
    if len(text.encode("utf-8")) > 500:
        raise ValueError("Слишком длинный текст для одного запроса (лимит сервиса — 500 байт). Разделите его на несколько частей.")
    params = {"q": text, "langpair": f"{source}|{target}"}
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Не удалось связаться с сервисом перевода: {exc}") from exc
    if data.get("responseStatus") not in (200, "200"):
        message = data.get("responseDetails") or "неизвестная ошибка API"
        raise RuntimeError(f"Сервис перевода вернул ошибку: {message}")
    result = data.get("responseData", {}).get("translatedText", "").strip()
    if not result:
        raise RuntimeError("Сервис вернул пустой перевод.")
    return result


def get_clipboard() -> str:
    import shutil
    import subprocess
    if not shutil.which("termux-clipboard-get"):
        raise RuntimeError("Не найдена команда termux-clipboard-get. Установите Termux:API и пакет termux-api.")
    result = subprocess.run(["termux-clipboard-get"], text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Не удалось прочитать буфер обмена.")
    return result.stdout


def set_clipboard(text: str) -> None:
    import shutil
    import subprocess
    if not shutil.which("termux-clipboard-set"):
        raise RuntimeError("Не найдена команда termux-clipboard-set. Установите Termux:API и пакет termux-api.")
    result = subprocess.run(["termux-clipboard-set"], input=text, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Не удалось записать перевод в буфер обмена.")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ttranslate",
        description="Простой переводчик для Termux. По умолчанию переводит на русский.",
        epilog="Пример: toolkit trans -t en Привет. Названия языков тоже принимаются: -t английский",
    )
    parser.add_argument("text", nargs="*", help="Текст для перевода; если не указан, будет запрос ввода")
    parser.add_argument("-s", "--source", default="auto", help="Исходный язык: auto, ru, en, ky и т. д.")
    parser.add_argument("-t", "--target", default="ru", help="Язык результата; по умолчанию ru")
    parser.add_argument("-c", "--copy", action="store_true", help="Скопировать перевод в буфер обмена")
    parser.add_argument("--clipboard", action="store_true", help="Взять исходный текст из буфера обмена")
    parser.add_argument("--timeout", type=int, default=20, help="Тайм-аут запроса в секундах")
    args = parser.parse_args()

    if args.clipboard and args.text:
        parser.error("Укажите текст или --clipboard, но не оба варианта сразу.")

    if args.clipboard:
        try:
            text = get_clipboard()
        except RuntimeError as exc:
            print(f"Ошибка: {exc}", file=sys.stderr)
            return 1
    elif args.text:
        text = " ".join(args.text)
    elif sys.stdin.isatty():
        print("Введите текст для перевода (одна строка).")
        try:
            text = input("Текст: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\\nОтменено.")
            return 130
        if not text:
            print("Текст не введён.")
            return 1
        target = input(f"На какой язык? [{args.target}]: ").strip()
        if target:
            args.target = target
    else:
        text = sys.stdin.read()

    source = normalize_language(args.source)
    target = normalize_language(args.target)
    if source == "auto":
        source = detect_source(text)
        print(f"Определён исходный язык: {source}", file=sys.stderr)

    try:
        result = translate_text(text, source, target, args.timeout)
        print(result)
        if args.copy:
            set_clipboard(result)
            print("Перевод скопирован в буфер обмена.", file=sys.stderr)
    except (RuntimeError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
