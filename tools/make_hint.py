#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「解释中文.JPG」里的手写中文提示裁成一张透明 PNG，用在页面相机下方。

用户要求页面上的中文提示"字体和上传的解释中文图片一致"。逐款比对过
Caveat / Zhi Mang Xing / Ma Shan Zheng / Long Cang / ZCOOL KuaiLe /
ZCOOL QingKe HuangYou / ZCOOL XiaoWei / Liu Jian Mao Cao 等手写体，
都不是参考图那一款（参考图是商用手写体，网上没有可自由取用的同款）。
所以直接用参考图本身的笔迹：裁出墨迹范围 -> 取反灰度做 alpha -> 染成页面的灰色。

用法:
    python tools/make_hint.py [--src <解释中文.JPG>] [--color 6f6f6f] [--width 1400]

产物:
    assets/hint-cn.png    透明底 + 灰色手写中文（含两侧的 ☆）
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 源图默认取当前用户桌面上的「AI交互图片参考\解释中文.JPG」
DEFAULT_SRC = os.path.join(os.path.expanduser("~"), "Desktop", "AI交互图片参考", "解释中文.JPG")
DST = os.path.join(ROOT, "assets", "hint-cn.png")

INK_THRESHOLD = 140       # 判定"有墨"的灰度阈值
ALPHA_CUT = 12            # 低于此 alpha 直接归零（去掉 JPEG 噪点）
ALPHA_GAIN = 1.25         # alpha 对比度增益


def ink_bbox(img: Image.Image):
    g = img.convert("L")
    w, h = g.size
    px = g.load()
    xs, ys = [], []
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if px[x, y] < INK_THRESHOLD:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise RuntimeError("参考图里没找到墨迹")
    return min(xs), min(ys), max(xs), max(ys)


def build(src: str, color: str, width: int) -> Image.Image:
    im = Image.open(src).convert("RGB")
    print(f"源图 {im.size[0]}x{im.size[1]}")
    box = ink_bbox(im)
    print(f"墨迹范围 {box}")
    # 往外留 6px 余量，避免裁掉笔画尖
    x0 = max(0, box[0] - 6)
    y0 = max(0, box[1] - 6)
    x1 = min(im.size[0], box[2] + 7)
    y1 = min(im.size[1], box[3] + 7)
    crop = im.crop((x0, y0, x1, y1)).convert("L")

    # 灰度取反 -> alpha，并压掉噪点
    raw = crop.point(lambda v: 255 - v)
    raw = raw.point(lambda v: 0 if v <= ALPHA_CUT else min(255, int((v - ALPHA_CUT) * ALPHA_GAIN)))

    # 按目标宽度等比缩放
    if width and width < raw.size[0]:
        h = max(1, round(raw.size[1] * width / raw.size[0]))
        raw = raw.resize((width, h), Image.LANCZOS)

    r, g, b = (int(color[i:i + 2], 16) for i in (0, 2, 4))
    out = Image.new("RGBA", raw.size, (r, g, b, 0))
    out.putalpha(raw)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC, help="解释中文 图片路径")
    ap.add_argument("--color", default="6f6f6f", help="文字颜色（十六进制，不带 #）")
    ap.add_argument("--width", type=int, default=1400, help="输出宽度（0 = 原尺寸）")
    args = ap.parse_args()

    if not os.path.exists(args.src):
        print(f"[ERROR] 找不到 {args.src}", file=sys.stderr)
        return 1

    out = build(args.src, args.color, args.width)
    out.save(DST, "PNG", optimize=True)
    print(f"已写出 {DST}  {out.size[0]}x{out.size[1]}  "
          f"({os.path.getsize(DST):,} B)  颜色 #{args.color}")
    print(f"宽高比 {out.size[0] / out.size[1]:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
