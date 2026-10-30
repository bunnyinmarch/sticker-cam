#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把背景图上下两条粉色饰条换成纯白面板（保留右上角 BACK 爱心涂鸦）。

背景图1.JPG 的最上/最下各有一条粉色横条（#E8C2D9），用户要求「去掉粉色框，
换成纯白 + 暗红波点背景」。这里只处理饰条，中间面板和相机机身原样保留。

原理（饰条里的粉色像素 = 粉色底 × k + 黑色笔画 × (1-k)）：
  1. 逐行统计"粉色像素占比"，占比高的行即为饰条行（上下各一段）；
  2. 饰条内像素分两类：
     - 粉色缩放像素 (r,g,b) ≈ k·(232,194,217)  → 输出 (V·k, V·k, V·k)
       纯粉色(k=1)变面板白，纯黑笔画(k=0)仍是黑，半灰笔画仍是等效灰；
     - 粉色↔白的过渡像素 → 直接输出面板白；
  3. V 取面板本身的底色 (253,253,253)，所以饰条与面板之间没有接缝。

用法:
    python tools/make_bg.py [--preview]

产物:
    assets/bg-plain.jpg          去粉色饰条后的背景图（页面与导出共用）
    assets/bg-plain-preview.jpg  上下对比图（上原图 / 下新图），用于肉眼 QA
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "bg-nodots.jpg")
DST = os.path.join(ROOT, "assets", "bg-plain.jpg")
PREVIEW = os.path.join(ROOT, "assets", "bg-plain-preview.jpg")

PINK = (232, 194, 217)      # 饰条原色 #E8C2D9
PANEL = 253                # 白色面板底色
TOL_RES = 12               # 拟合残差阈值（JPEG 噪声容忍度）
_PP = PINK[0] ** 2 + PINK[1] ** 2 + PINK[2] ** 2
_DD = sum((v - 255) ** 2 for v in PINK)


def _fit(a, b, c):
    """最小二乘拟合 C ≈ k·P，返回 (k, 残差)。"""
    k = (a * PINK[0] + b * PINK[1] + c * PINK[2]) / _PP
    res = abs(a - k * PINK[0]) + abs(b - k * PINK[1]) + abs(c - k * PINK[2])
    return k, res


def _fit_blend(a, b, c):
    """最小二乘拟合 C ≈ t·P + (1-t)·255，返回 (t, 残差)。"""
    d = (PINK[0] - 255, PINK[1] - 255, PINK[2] - 255)
    t = ((a - 255) * d[0] + (b - 255) * d[1] + (c - 255) * d[2]) / _DD
    res = (abs(a - (t * PINK[0] + (1 - t) * 255))
           + abs(b - (t * PINK[1] + (1 - t) * 255))
           + abs(c - (t * PINK[2] + (1 - t) * 255)))
    return t, res


def classify(r: int, g: int, b: int):
    """返回 ('pink', k) / ('blend', t) / (None, None)。

    两种模型都用最小二乘 + 残差阈值判定，才能扛住 JPEG 压缩带来的偏色。
    """
    k, res = _fit(r, g, b)
    if -0.05 <= k <= 1.15 and res <= TOL_RES:
        return "pink", min(max(k, 0.0), 1.0)
    t, res = _fit_blend(r, g, b)
    if -0.05 <= t <= 1.05 and res <= TOL_RES:
        return "blend", min(max(t, 0.0), 1.0)
    return None, None


def band_rows(img: Image.Image):
    """找出上下两段饰条的行范围（含过渡行）。"""
    W, H = img.size
    px = img.convert("RGB").load()
    is_pink_row = []
    for y in range(H):
        n = 0
        for x in range(0, W, 2):
            r, g, b = px[x, y]
            kind, k = classify(r, g, b)
            if kind == "pink" and k > 0.9:
                n += 1
        is_pink_row.append(n > (W / 2) * 0.5)

    top_end = -1
    for y in range(H):
        if is_pink_row[y]:
            top_end = y
        elif top_end >= 0:
            break
    bot_start = H
    for y in range(H - 1, -1, -1):
        if is_pink_row[y]:
            bot_start = y
        elif bot_start < H:
            break
    return (0, top_end), (bot_start, H - 1)


def whiten(img: Image.Image) -> Image.Image:
    W, H = img.size
    out = img.convert("RGB")
    px = out.load()
    (t0, t1), (b0, b1) = band_rows(out)
    # 饰条与面板之间是 2~3 行的柔和过渡带，那几行"粉色占比"没到一半，
    # 检测不到，这里各向外多带 8 行，交给像素分类器处理（非粉色的像素原样保留）。
    t1 = min(H - 1, t1 + 8)
    b0 = max(0, b0 - 8)
    print(f"  上饰条行 {t0}..{t1}    下饰条行 {b0}..{b1}")
    for y in list(range(t0, t1 + 1)) + list(range(b0, b1 + 1)):
        for x in range(W):
            r, g, b = px[x, y]
            kind, v = classify(r, g, b)
            if kind == "pink":
                lum = round(PANEL * v)
                px[x, y] = (lum, lum, lum)
            elif kind == "blend":
                px[x, y] = (PANEL, PANEL, PANEL)
    # 收尾：饰条里只应剩黑白灰，任何残留的偏色像素一律中性化，
    # 否则 JPEG 的 4:2:0 色度抽样会把零星粉点晕开成粉雾。
    for y in list(range(t0, t1 + 1)) + list(range(b0, b1 + 1)):
        for x in range(W):
            r, g, b = px[x, y]
            if max(r, g, b) - min(r, g, b) > 3:
                lum = round((r + g + b) / 3)
                px[x, y] = (lum, lum, lum)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="额外生成上下对比图")
    args = ap.parse_args()

    if not os.path.exists(SRC):
        print(f"[ERROR] 找不到 {SRC}", file=sys.stderr)
        return 1

    src = Image.open(SRC)
    print(f"原图 {src.size[0]}x{src.size[1]}")
    out = whiten(src)
    out.save(DST, "JPEG", quality=92, subsampling=0)
    print(f"已写出 {DST}")

    # 校验：饰条区域不该再有肉眼可见的粉色（面板本身是灰白，r-g 很小）
    px = out.convert("RGB").load()
    W, H = out.size
    leftovers = 0
    for y in list(range(0, 47)) + list(range(859, H)):
        for x in range(W):
            r, g, b = px[x, y]
            if r - g > 8 and r - b > 4:
                leftovers += 1
    print(f"饰条残留粉色像素: {leftovers}  (验收要求 = 0)")

    if args.preview:
        canvas = Image.new("RGB", (out.size[0], out.size[1] * 2), (255, 255, 255))
        canvas.paste(src.convert("RGB"), (0, 0))
        canvas.paste(out, (0, out.size[1]))
        canvas.save(PREVIEW, "JPEG", quality=88)
        print(f"对比图(上原图/下新图) -> {PREVIEW}")

    return 0 if leftovers == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
