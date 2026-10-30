#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 5 张贴纸库大图切成独立的透明 PNG 贴纸。

难点：贴纸多是白色 / 浅色，压在纯白底上（白绒玩偶、白纽扣、白蝴蝶结…），
所以不能简单地"删掉所有白像素"，否则会把贴纸本身抠穿。

本脚本采用「边界泛洪 + 距离场软 alpha」：
  1. 近白像素（亮度 >= BG_T 且近中性）视为背景候选；
  2. 从裁剪块的四条边界泛洪，只删掉**与边界连通**的近白背景 ——
     被物体围住的白色镂空（纽扣孔、相框内白底）会被保留；
  3. 用倒角距离变换算出每个像素到背景的距离 d，
     alpha = clamp((d - 0.5) / (BAND - 0.5))：
     贴纸本体（d 大）不透明，边缘 1~BAND 像素平滑过渡，
     影子（d 小）自然变淡，不会留下灰色硬边。

用法:
    python tools/cut_stickers.py [--only lib1] [--sheet-only]

产物:
    assets/stickers/libN/MM.png     单张贴纸（透明 PNG）
    assets/stickers/manifest.json   库 -> 贴纸清单（含原始像素尺寸）
    assets/stickers/_contact_sheet.png  抠图总览，用于肉眼 QA
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import deque

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ASSETS, "stickers")

BG_T = 248        # 近白阈值
BAND = 5.0        # alpha 过渡带宽度（像素）
MAX_CHANNEL_SPREAD = 14   # 中性判定：max-min 超过该值就不算近白
MIN_COMPONENT_AREA = 250  # 连通域最小面积（噪点过滤）

# 各库布局。grid 模式用行/列带切格；components 模式直接用连通域（布局不规则时用）。
LIBS = [
    dict(id="lib1", file="lib1.jpg", name="纽扣", mode="grid",
         rows=[(144, 533), (556, 946), (973, 1364)],
         cols=[(0, 390), (409, 797), (817, 1205)]),
    dict(id="lib2", file="lib2.jpg", name="蝴蝶结", mode="grid",
         rows=[(26, 384), (423, 779), (801, 1200), (1203, 1595)],
         cols=[(10, 376), (420, 787), (814, 1189)]),
    dict(id="lib3", file="lib3.jpg", name="眼镜", mode="grid",
         rows=[(153, 296), (692, 819), (1234, 1349)],
         cols=[(19, 384), (431, 775), (830, 1188)],
         punch_holes=True),   # 镜片里的白要抠成透明
    dict(id="lib4", file="lib4.jpg", name="小熊玩偶", mode="components",
         min_area=1200),
    dict(id="lib5", file="lib5.jpg", name="树脂挂件", mode="grid",
         rows=[(90, 404), (611, 938), (1171, 1461)],
         cols=[(25, 354), (442, 747), (859, 1172)]),
]


# ---------------------------------------------------------------- 基础工具


def luminance(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def is_background_candidate(r, g, b):
    if max(r, g, b) - min(r, g, b) > MAX_CHANNEL_SPREAD:
        return False
    return luminance(r, g, b) >= BG_T


def find_components(img: Image.Image, min_area: int):
    """8 连通域，返回 [ (cells, bbox) ]。cells 是像素索引列表。"""
    W, H = img.size
    px = img.convert("RGB").load()
    mask = bytearray(W * H)
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if not is_background_candidate(r, g, b):
                mask[y * W + x] = 1

    comps = []
    stack: list[int] = []
    for y in range(H):
        for x in range(W):
            i = y * W + x
            if not mask[i]:
                continue
            mask[i] = 0
            stack.append(i)
            cells = []
            x0 = x1 = x
            y0 = y1 = y
            while stack:
                p = stack.pop()
                cells.append(p)
                py, pxx = divmod(p, W)
                if pxx < x0:
                    x0 = pxx
                if pxx > x1:
                    x1 = pxx
                if py < y0:
                    y0 = py
                if py > y1:
                    y1 = py
                for ny in range(py - 1, py + 2):
                    for nx in range(pxx - 1, pxx + 2):
                        if 0 <= ny < H and 0 <= nx < W:
                            ni = ny * W + nx
                            if mask[ni]:
                                mask[ni] = 0
                                stack.append(ni)
            if len(cells) >= min_area:
                comps.append((cells, (x0, y0, x1, y1)))
    return comps


def centroid_in_bbox(cell: int, W: int, bbox) -> bool:
    x, y = cell % W, cell // W
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def bbox_overlaps(a, b, tol: int = 0) -> bool:
    return not (a[2] + tol < b[0] or b[2] + tol < a[0]
                or a[3] + tol < b[1] or b[3] + tol < a[1])


def union_bbox(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


# ---------------------------------------------------------------- 抠图


def matte(crop: Image.Image) -> Image.Image:
    """对裁剪块做白底抠图，返回带 alpha 的 RGBA。"""
    W, H = crop.size
    rgb = crop.convert("RGB")
    px = rgb.load()

    # 1) 近白掩码
    white = bytearray(W * H)
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y]
            if is_background_candidate(r, g, b):
                white[y * W + x] = 1

    # 2) 从边界泛洪，得到"真背景"
    bg = bytearray(W * H)
    q: deque[int] = deque()
    for x in range(W):
        for i in (x, (H - 1) * W + x):
            if white[i] and not bg[i]:
                bg[i] = 1
                q.append(i)
    for y in range(H):
        for i in (y * W, y * W + W - 1):
            if white[i] and not bg[i]:
                bg[i] = 1
                q.append(i)
    while q:
        p = q.popleft()
        py, pxx = divmod(p, W)
        for ny, nx in ((py - 1, pxx), (py + 1, pxx), (py, pxx - 1), (py, pxx + 1)):
            if 0 <= ny < H and 0 <= nx < W:
                ni = ny * W + nx
                if white[ni] and not bg[ni]:
                    bg[ni] = 1
                    q.append(ni)

    # 3) 倒角距离变换：到最近背景像素的距离（3-4 倒角，/3 归一）
    INF = 10 ** 6
    d = [0 if bg[i] else INF for i in range(W * H)]
    for y in range(H):
        row = y * W
        for x in range(W):
            i = row + x
            if d[i] == 0:
                continue
            best = INF
            if x > 0:
                best = min(best, d[i - 1] + 3)
            if y > 0:
                best = min(best, d[i - W] + 3)
                if x > 0:
                    best = min(best, d[i - W - 1] + 4)
                if x < W - 1:
                    best = min(best, d[i - W + 1] + 4)
            d[i] = best
    for y in range(H - 1, -1, -1):
        row = y * W
        for x in range(W - 1, -1, -1):
            i = row + x
            if d[i] == 0:
                continue
            best = d[i]
            if x < W - 1:
                best = min(best, d[i + 1] + 3)
            if y < H - 1:
                best = min(best, d[i + W] + 3)
                if x < W - 1:
                    best = min(best, d[i + W + 1] + 4)
                if x > 0:
                    best = min(best, d[i + W - 1] + 4)
            d[i] = best

    # 4) alpha
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    opx = out.load()
    span = max(1.0, BAND - 0.5)
    for y in range(H):
        row = y * W
        for x in range(W):
            i = row + x
            if bg[i]:
                continue
            dist = d[i] / 3.0
            a = (dist - 0.5) / span
            a = 0.0 if a < 0 else (1.0 if a > 1 else a)
            if a <= 0:
                continue
            r, g, b = px[x, y]
            opx[x, y] = (r, g, b, int(round(a * 255)))
    return out


def punch_enclosed_white(sticker: Image.Image, min_area: int = 1500) -> Image.Image:
    """把「被贴纸自身围住的成片白色」抠成透明。

    眼镜的镜框是一圈实色，镜片里面是纯白。常规抠图只删掉「和图外连通」的白色，
    所以镜片这种被框住的白会留下来，看着像一块实心白板。

    这里在成品的 alpha 通道里再做一次：
      1. 找出「近白且不透明」的像素；
      2. 从图的四条边泛洪 —— 泛洪得到的还是背景附近的白；
      3. 泛洪不到的、且连成一大块的近白 = 被框住的镜片，整块置 alpha=0。

    镜片面积 5000~9000px，抗锯齿噪点只有几十 px，用面积阈值（min_area）区分，
    因此不会误伤贴纸自身 legit 的白色部件（白纽扣、白绒玩偶……）。
    """
    W, H = sticker.size
    px = sticker.load()

    white = bytearray(W * H)
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if a > 8 and max(r, g, b) >= 240 and (max(r, g, b) - min(r, g, b)) <= 16:
                white[y * W + x] = 1

    # 从四条边泛洪
    seen = bytearray(W * H)
    q: deque[int] = deque()
    for x in range(W):
        for i in (x, (H - 1) * W + x):
            if white[i] and not seen[i]:
                seen[i] = 1
                q.append(i)
    for y in range(H):
        for i in (y * W, y * W + W - 1):
            if white[i] and not seen[i]:
                seen[i] = 1
                q.append(i)
    while q:
        p = q.popleft()
        py, pxx = divmod(p, W)
        for ny, nx in ((py - 1, pxx), (py + 1, pxx), (py, pxx - 1), (py, pxx + 1)):
            if 0 <= ny < H and 0 <= nx < W:
                ni = ny * W + nx
                if white[ni] and not seen[ni]:
                    seen[ni] = 1
                    q.append(ni)

    # 剩下的近白 = 被围住的；按连通块面积筛选后清空
    out = sticker.copy()
    opx = out.load()
    for y in range(H):
        for x in range(W):
            i = y * W + x
            if not white[i] or seen[i]:
                continue
            # 收集这个连通块
            cells = []
            seen[i] = 1
            q.append(i)
            while q:
                p = q.popleft()
                cells.append(p)
                py, pxx = divmod(p, W)
                for ny, nx in ((py - 1, pxx), (py + 1, pxx), (py, pxx - 1), (py, pxx + 1)):
                    if 0 <= ny < H and 0 <= nx < W:
                        ni = ny * W + nx
                        if white[ni] and not seen[ni]:
                            seen[ni] = 1
                            q.append(ni)
            if len(cells) >= min_area:
                for p in cells:
                    py, pxx = divmod(p, W)
                    r, g, b, _ = opx[pxx, py]
                    opx[pxx, py] = (r, g, b, 0)
    return out


def pad_bbox(bbox, W, H, ratio=0.04, minimum=6):
    x0, y0, x1, y1 = bbox
    w = x1 - x0 + 1
    h = y1 - y0 + 1
    m = max(minimum, int(max(w, h) * ratio))
    return (max(0, x0 - m), max(0, y0 - m), min(W - 1, x1 + m), min(H - 1, y1 + m))


# ---------------------------------------------------------------- 主流程


def cells_for_grid(lib, comps, W, H):
    """按行/列带切格：每格取中心落在格内的连通域，再把与之重叠的连通域并进来。"""
    cells = []
    for (ry0, ry1) in lib["rows"]:
        for (cx0, cx1) in lib["cols"]:
            seeds = []
            for cells_pixels, bbox in comps:
                cx = sum(p % W for p in cells_pixels) // len(cells_pixels)
                cy = sum(p // W for p in cells_pixels) // len(cells_pixels)
                if cx0 <= cx <= cx1 and ry0 <= cy <= ry1:
                    seeds.append((cells_pixels, bbox))
            if not seeds:
                continue
            # 迭代并入与当前包围盒重叠的连通域（处理飘带跨格等情形）
            boxes = [b for _, b in seeds]
            changed = True
            while changed:
                changed = False
                for cells_pixels, bbox in comps:
                    if bbox in boxes:
                        continue
                    if any(bbox_overlaps(bbox, b, tol=2) for b in boxes):
                        boxes.append(bbox)
                        changed = True
            cells.append(union_bbox(boxes))
    return cells


def cut_library(lib, verbose=True):
    path = os.path.join(ASSETS, lib["file"])
    img = Image.open(path).convert("RGB")
    W, H = img.size
    comps = find_components(img, MIN_COMPONENT_AREA)

    if lib["mode"] == "grid":
        boxes = cells_for_grid(lib, comps, W, H)
    else:
        boxes = []
        for cells_pixels, bbox in comps:
            if len(cells_pixels) >= lib.get("min_area", 1200):
                boxes.append(bbox)
        boxes.sort(key=lambda b: (b[1] // 60, b[0]))

    out_dir = os.path.join(OUT, lib["id"])
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for idx, bbox in enumerate(boxes, start=1):
        padded = pad_bbox(bbox, W, H)
        crop = img.crop(padded)
        sticker = matte(crop)
        if lib.get("punch_holes"):
            sticker = punch_enclosed_white(sticker)
        # 裁到非透明区域
        alpha = sticker.getchannel("A")
        bball = alpha.getbbox()
        if bball:
            sticker = sticker.crop(bball)
        name = f"{idx:02d}.png"
        sticker.save(os.path.join(out_dir, name))
        items.append({"file": f"{lib['id']}/{name}", "w": sticker.width, "h": sticker.height})
    if verbose:
        print(f"  {lib['id']} ({lib['name']}): {len(items)} 张  -> {out_dir}")
    return items


def make_contact_sheet(manifest, path):
    """把所有贴纸拼成一张总览图，便于肉眼 QA。"""
    tiles = []
    for lib in manifest["libraries"]:
        for it in lib["items"]:
            p = os.path.join(OUT, it["file"])
            if os.path.exists(p):
                tiles.append((f"{lib['id']}/{os.path.basename(it['file'])}",
                              Image.open(p).convert("RGBA")))
    if not tiles:
        return
    cell = 190
    cols = 10
    rows = math.ceil(len(tiles) / cols)
    pad = 6
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (245, 245, 245, 255))
    for i, (label, im) in enumerate(tiles):
        cx = (i % cols) * cell + pad
        cy = (i // cols) * cell + pad
        box = (cell - pad * 2)
        w, h = im.size
        sc = min(box / w, box / h)
        nw, nh = max(1, int(w * sc)), max(1, int(h * sc))
        tile = im.resize((nw, nh), Image.LANCZOS)
        # 棋盘底，方便看清透明区域
        for yy in range(0, nh, 12):
            for xx in range(0, nw, 12):
                if ((xx // 12 + yy // 12) % 2) == 0:
                    for dy in range(min(12, nh - yy)):
                        for dx in range(min(12, nw - xx)):
                            r, g, b, a = tile.getpixel((xx + dx, yy + dy))
                            tile.putpixel((xx + dx, yy + dy),
                                          (min(255, r + 18), min(255, g + 18), min(255, b + 18), a))
        sheet.alpha_composite(tile, (cx + (box - nw) // 2, cy + (box - nh) // 2))
    sheet.convert("RGB").save(path, "JPEG", quality=88)
    print(f"  联系表 -> {path}  ({len(tiles)} 张)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只处理某个库，如 lib1")
    ap.add_argument("--sheet-only", action="store_true", help="只重建联系表")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    manifest = {"libraries": []}

    if not args.sheet_only:
        for lib in LIBS:
            if args.only and lib["id"] != args.only:
                continue
            print(f"[{lib['id']}] {lib['name']}")
            items = cut_library(lib)
            manifest["libraries"].append(
                {"id": lib["id"], "name": lib["name"], "items": items})

        if args.only:
            # 只处理单个库时，保留 manifest 里其它库的数据
            mp = os.path.join(OUT, "manifest.json")
            if os.path.exists(mp):
                with open(mp, "r", encoding="utf-8") as fh:
                    old = json.load(fh)
                merged = {l["id"]: l for l in old["libraries"]}
                for l in manifest["libraries"]:
                    merged[l["id"]] = l
                manifest["libraries"] = [merged[k] for k in sorted(merged)]
        else:
            with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, ensure_ascii=False, indent=2)
            total = sum(len(l["items"]) for l in manifest["libraries"])
            print(f"  manifest.json 已写出，共 {total} 张贴纸")

    mp = os.path.join(OUT, "manifest.json")
    if os.path.exists(mp):
        with open(mp, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        make_contact_sheet(manifest, os.path.join(OUT, "_contact_sheet.jpg"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
