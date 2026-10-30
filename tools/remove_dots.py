#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把背景图里烙印的暗红圆点抹掉（补绘回原本的白色渐变面板）。

背景图1.JPG 自带 11 个暗红圆点，而页面需要圆点"从下往上升起"，
所以必须先把烙印圆点从图上擦掉，再由 DOM 元素负责动画。

做法（不依赖"圆"这种形状假设）：
  1. 按颜色找出暗红像素（#6A0C0C 附近），取面积 > 阈值��连通域 = 一个圆点；
  2. 每个连通域向外扩张 GROW 像素，吸收抗锯齿过渡带；
  3. 用"扩散填补"（由边界向内逐层推进、每格取已知邻居均值）把洞填平 ——
     面板本身是平滑渐变，扩散出来的结果与四周自然无缝，不会有接缝或月牙。

用法:
    python tools/remove_dots.py [--preview]

产物:
    assets/bg-nodots.jpg          擦掉圆点后的背景图
    assets/bg-nodots-preview.jpg   左右对比图（左原图 / 右补绘），用于肉眼 QA
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import deque

from PIL import Image, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "assets", "bg.jpg")
DST = os.path.join(ROOT, "assets", "bg-nodots.jpg")
PREVIEW = os.path.join(ROOT, "assets", "bg-nodots-preview.jpg")

# 暗红识别：接近 #6A0C0C，且明显偏红（排除黑色墨线与粉色机身）
MIN_R, MAX_R = 40, 205
MAX_GB = 115
MIN_RED_DIFF = 30

MIN_BLOB_AREA = 120     # 小于此面积视为噪点
GROW = 3                # 吸收抗锯齿边缘的扩张量
BLUR = 1.2              # 填补区轻微模糊，消除扩散留下的细微纹理


def find_dark_red(img: Image.Image):
    """返回暗红像素的连通域列表，每个连通域是一个像素坐标集合。"""
    W, H = img.size
    px = img.convert("RGB").load()
    mask = bytearray(W * H)
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if MIN_R <= r <= MAX_R and g <= MAX_GB and b <= MAX_GB \
                    and (r - g) >= MIN_RED_DIFF and (r - b) >= MIN_RED_DIFF:
                mask[y * W + x] = 1

    blobs = []
    stack: list[int] = []
    for y in range(H):
        for x in range(W):
            i = y * W + x
            if not mask[i]:
                continue
            mask[i] = 0
            stack.append(i)
            cells = []
            while stack:
                p = stack.pop()
                cells.append(p)
                py, pxx = divmod(p, W)
                for ny, nx in ((py - 1, pxx), (py + 1, pxx), (py, pxx - 1), (py, pxx + 1)):
                    if 0 <= ny < H and 0 <= nx < W:
                        ni = ny * W + nx
                        if mask[ni]:
                            mask[ni] = 0
                            stack.append(ni)
            if len(cells) >= MIN_BLOB_AREA:
                xs = [p % W for p in cells]
                ys = [p // W for p in cells]
                bw = max(xs) - min(xs) + 1
                bh = max(ys) - min(ys) + 1
                # 排除细长的相机机身细节（那不是装饰圆点）
                if min(bw, bh) < 12 or (min(bw, bh) / max(bw, bh)) < 0.45:
                    continue
                blobs.append(cells)
    return blobs


def dilate(cells, W, H, grow):
    """把连通域向外扩张 grow 像素。"""
    out = set(cells)
    frontier = list(cells)
    for _ in range(grow):
        nxt = []
        for p in frontier:
            py, px = divmod(p, W)
            for ny, nx in ((py - 1, px), (py + 1, px), (py, px - 1), (py, px + 1)):
                if 0 <= ny < H and 0 <= nx < W:
                    ni = ny * W + nx
                    if ni not in out:
                        out.add(ni)
                        nxt.append(ni)
        frontier = nxt
    return out


def diffusion_fill(img: Image.Image, holes: set[int]) -> None:
    """由边界向内扩散填补 holes 里的像素（原地修改 img）。"""
    W, H = img.size
    px = img.load()
    hole = set(holes)

    # 边界种子：有已知邻居的洞像素
    queue = deque()
    queued = set()
    for p in list(hole):
        py, pxx = divmod(p, W)
        known = []
        for ny, nx in ((py - 1, pxx), (py + 1, pxx), (py, pxx - 1), (py, pxx + 1)):
            if 0 <= ny < H and 0 <= nx < W:
                ni = ny * W + nx
                if ni not in hole:
                    known.append(nx + ny * W)
        if known:
            queue.append(p)
            queued.add(p)

    filled = set()
    while queue:
        p = queue.popleft()
        if p in filled:
            continue
        py, pxx = divmod(p, W)
        vals = []
        for ny, nx in ((py - 1, pxx), (py + 1, pxx), (py, pxx - 1), (py, pxx + 1)):
            if 0 <= ny < H and 0 <= nx < W:
                ni = ny * W + nx
                if ni not in hole or ni in filled:
                    vals.append(px[nx, ny])
        if not vals:
            continue
        r = sum(v[0] for v in vals) // len(vals)
        g = sum(v[1] for v in vals) // len(vals)
        b = sum(v[2] for v in vals) // len(vals)
        px[pxx, py] = (r, g, b)
        filled.add(p)
        for ny, nx in ((py - 1, pxx), (py + 1, pxx), (py, pxx - 1), (py, pxx + 1)):
            if 0 <= ny < H and 0 <= nx < W:
                ni = ny * W + nx
                if ni in hole and ni not in queued:
                    queued.add(ni)
                    queue.append(ni)


def inpaint(img: Image.Image) -> tuple[Image.Image, int]:
    W, H = img.size
    out = img.convert("RGB")
    blobs = find_dark_red(out)
    blobs.sort(key=len, reverse=True)
    W2, H2 = out.size
    for cells in blobs:
        xs = [p % W2 for p in cells]
        ys = [p // W2 for p in cells]
        print(f"  blob area={len(cells):6d}  bbox=[{min(xs)},{min(ys)} -> {max(xs)},{max(ys)}]"
              f"  center=({sum(xs)//len(xs)},{sum(ys)//len(ys)})")

    all_holes: set[int] = set()
    for cells in blobs:
        holes = dilate(cells, W, H, GROW)
        all_holes |= holes

    diffusion_fill(out, all_holes)

    # 填补区轻微模糊，消除扩散的细微纹理（只动洞内像素）
    if all_holes:
        blurred = out.filter(ImageFilter.GaussianBlur(radius=BLUR))
        bpx = blurred.load()
        opx = out.load()
        for p in all_holes:
            py, pxx = divmod(p, W)
            opx[pxx, py] = bpx[pxx, py]

    return out, len(blobs)


def residual_ratio(img: Image.Image, holes) -> float:
    """洞区内残留的暗红像素占比（验收 < 2%）。"""
    px = img.convert("RGB").load()
    total = len(holes)
    if not total:
        return 0.0
    dark = 0
    for p in holes:
        py, pxx = divmod(p, img.size[0])
        r, g, b = px[pxx, py]
        if r < 205 and g < 115 and b < 115 and (r - g) >= 25 and (r - b) >= 25:
            dark += 1
    return dark / total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true", help="额外生成左右对比图")
    args = ap.parse_args()

    if not os.path.exists(SRC):
        print(f"[ERROR] 找不到 {SRC}", file=sys.stderr)
        return 1

    src = Image.open(SRC)
    print(f"原图 {src.size[0]}x{src.size[1]}")

    out, nblob = inpaint(src)

    # 复算洞区用于残留统计
    holes = set()
    for cells in find_dark_red(src.convert("RGB")):
        holes |= dilate(cells, src.size[0], src.size[1], GROW)

    out.save(DST, "JPEG", quality=92, subsampling=1)
    ratio = residual_ratio(out, holes)
    print(f"已写出 {DST}")
    print(f"圆点域残留暗红像素: {ratio * 100:.2f}%  (验收要求 < 2%)")

    if args.preview:
        w, h = out.size
        canvas = Image.new("RGB", (w * 2, h), (255, 255, 255))
        canvas.paste(src.convert("RGB"), (0, 0))
        canvas.paste(out, (w, 0))
        canvas.save(PREVIEW, "JPEG", quality=90)
        print(f"对比图(左原图/右补绘) -> {PREVIEW}")

    return 0 if ratio < 0.02 else 2


if __name__ == "__main__":
    sys.exit(main())
