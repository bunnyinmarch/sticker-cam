#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下载并本地化运行时依赖（MediaPipe 视觉任务 + 手部模型 + 手写字体）。

用法:
    python tools/fetch_deps.py [--force]

产物:
    assets/vendor/vision_bundle.mjs
    assets/vendor/wasm/vision_wasm_internal.js|.wasm
    assets/model/hand_landmarker.task
    assets/vendor/fonts/*.ttf + fonts.css
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "assets", "vendor")
WASM_DIR = os.path.join(VENDOR, "wasm")
MODEL_DIR = os.path.join(ROOT, "assets", "model")
FONT_DIR = os.path.join(VENDOR, "fonts")

MP_VERSION = "0.10.14"
MP_BASE = f"https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@{MP_VERSION}"
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

# 现代浏览器（Chrome/Edge/Firefox/Safari 16.4+）均支持 WASM SIMD，只取 simd 版，
# 避免把 ~9MB 的 nosimd 变体也打进包里。需要旧浏览器时把 nosimd 两项加进下面即可。
WASM_FILES = [
    "wasm/vision_wasm_internal.js",
    "wasm/vision_wasm_internal.wasm",
]

# 老 UA 会让 Google Fonts 返回整包单文件（TTF），而不是上百个 unicode-range 分片
LEGACY_UA = "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1)"
FONTS = [
    # (family query, 输出文件名, @font-face family 名)
    ("Caveat", "caveat-regular.ttf", "Caveat"),
    ("Zhi+Mang+Xing", "zhi-mang-xing-regular.ttf", "Zhi Mang Xing"),
]

UA_MODERN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def log(msg: str) -> None:
    print(msg, flush=True)


def download(url: str, dest: str, headers: dict | None = None) -> int:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA_MODERN})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    with open(dest, "wb") as fh:
        fh.write(data)
    return len(data)


def fetch_mediapipe(force: bool) -> None:
    log("[1/3] MediaPipe 视觉任务运行时")
    bundle = os.path.join(VENDOR, "vision_bundle.mjs")
    if force or not os.path.exists(bundle):
        n = download(f"{MP_BASE}/vision_bundle.mjs", bundle)
        log(f"      vision_bundle.mjs  {n:,} B")
    else:
        log("      vision_bundle.mjs  (已存在, 跳过)")

    for rel in WASM_FILES:
        dest = os.path.join(VENDOR, rel.replace("/", os.sep))
        if force or not os.path.exists(dest):
            n = download(f"{MP_BASE}/{rel}", dest)
            log(f"      {rel}  {n:,} B")
        else:
            log(f"      {rel}  (已存在, 跳过)")


def fetch_model(force: bool) -> None:
    log("[2/3] 手部关键点模型")
    dest = os.path.join(MODEL_DIR, "hand_landmarker.task")
    if force or not os.path.exists(dest):
        n = download(MODEL_URL, dest)
        log(f"      hand_landmarker.task  {n:,} B")
    else:
        log(f"      hand_landmarker.task  (已存在, 跳过)")


def fetch_fonts(force: bool) -> None:
    log("[3/3] 手写字体")
    css_parts = []
    for query, filename, family in FONTS:
        dest = os.path.join(FONT_DIR, filename)
        if force or not os.path.exists(dest):
            url = _font_url(query)
            if not url:
                raise RuntimeError(f"未能解析 {family} 的字体地址")
            n = download(url, dest, headers={"User-Agent": LEGACY_UA})
            log(f"      {filename}  {n:,} B  <- {family}")
        else:
            log(f"      {filename}  (已存在, 跳过)")
        css_parts.append(
            "@font-face {\n"
            f"  font-family: '{family}';\n"
            "  font-style: normal;\n"
            "  font-weight: 400;\n"
            "  font-display: swap;\n"
            f"  src: url('fonts/{filename}') format('truetype');\n"
            "}"
        )
    css_path = os.path.join(VENDOR, "fonts.css")
    with open(css_path, "w", encoding="utf-8") as fh:
        fh.write("/* 由 tools/fetch_deps.py 生成，请勿手改 */\n")
        fh.write("\n".join(css_parts) + "\n")
    log(f"      fonts.css  -> {css_path}")


def _font_url(query: str) -> str | None:
    url = f"https://fonts.googleapis.com/css2?family={query}"
    req = urllib.request.Request(url, headers={"User-Agent": LEGACY_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        css = resp.read().decode("utf-8", "replace")
    m = re.search(r"src:\s*url\(([^)]+)\)", css)
    return m.group(1).strip("'\"") if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已存在的文件也重新下载")
    args = ap.parse_args()

    try:
        fetch_mediapipe(args.force)
        fetch_model(args.force)
        fetch_fonts(args.force)
    except urllib.error.HTTPError as exc:
        log(f"[错误] HTTP {exc.code}: {exc.url}")
        return 1
    except Exception as exc:  # noqa: BLE001
        log(f"[错误] {type(exc).__name__}: {exc}")
        return 1

    log("")
    log("完成。运行时依赖已全部本地化，页面可离线运行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
