#!/usr/bin/env python3
"""Suyziss Termux Translate: dependency-free terminal translator."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.mymemory.translated.net/get"
USER_AGENT = "Suyziss-Termux-Translate/1.0"


def translate_text(text: str, source: str, target: str, timeout: int) -> tuple[str, str | None]:
    if not text.strip():
        raise ValueError("Text is empty.")

    params = {
        "q": text,
        "langpair": f"{source}|{target}",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Translation request failed: {exc}") from exc

    if data.get("responseStatus") not in (200, "200"):
        message = data.get("responseDetails") or "Unknown API error"
        raise RuntimeError(f"Translation failed: {message}")

    result = data.get("responseData", {}).get("translatedText", "").strip()
    if not result:
        raise RuntimeError("Translator returned an empty result.")

    detected = None
    matches = data.get("matches") or []
    if matches:
        detected = matches[0].get("source")
    return result, detected


def get_clipboard() -> str:
    command = "termux-clipboard-get"
    if not shutil_which(command):
        raise RuntimeError("termux-clipboard-get is not installed. Install termux-api or pass text directly.")
    import subprocess
    result = subprocess.run([command], text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not read the Termux clipboard.")
    return result.stdout


def set_clipboard(text: str) -> None:
    command = "termux-clipboard-set"
    if not shutil_which(command):
        raise RuntimeError("termux-clipboard-set is not installed. Install termux-api or omit --copy.")
    import subprocess
    result = subprocess.run([command], input=text, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Could not write the Termux clipboard.")


def shutil_which(command: str) -> str | None:
    import shutil
    return shutil.which(command)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ttranslate",
        description="Translate text from Termux without third-party Python packages.",
    )
    parser.add_argument("text", nargs="*", help="Text to translate. If omitted, read stdin.")
    parser.add_argument("-s", "--source", default="auto", help="Source language code, e.g. en, ru, ky, de. Default: auto")
    parser.add_argument("-t", "--target", required=True, help="Target language code, e.g. en, ru, ky, de")
    parser.add_argument("-c", "--copy", action="store_true", help="Copy the result using termux-clipboard-set")
    parser.add_argument("--clipboard", action="store_true", help="Translate text from the Termux clipboard")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds")
    args = parser.parse_args()

    if args.clipboard and args.text:
        parser.error("Use either text arguments or --clipboard, not both.")

    if args.clipboard:
        text = get_clipboard()
    elif args.text:
        text = " ".join(args.text)
    else:
        text = sys.stdin.read()

    source = args.source
    # MyMemory uses an explicit source language in langpair. "auto" is handled
    # with its automatic matching behavior by using the same API with "en" fallback.
    if source == "auto":
        source = "en"

    try:
        result, detected = translate_text(text, source, args.target, args.timeout)
        print(result)
        if args.copy:
            set_clipboard(result)
            print("Copied to clipboard.", file=sys.stderr)
        if detected and args.source == "auto" and detected != "en":
            print(f"Detected source: {detected}", file=sys.stderr)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
