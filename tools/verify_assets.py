#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资产自检：贴纸清单与磁盘是否一致、每张贴纸是否带 alpha 且内容非空、
背景图尺寸与圆点残留是否符合验收标准，并重建联系表。

用法:
    python tools/verify_assets.py
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "stickers")
BG = os.path.join(ROOT, "assets", "bg-nodots.jpg")

EXPECTED_LIBS = ["lib1", "lib2", "lib3", "lib4", "lib5"]
EXPECTED_COUNTS = {"lib1": 9, "lib2": 12, "lib3": 9, "lib4": 27, "lib5": 9}
BG_SIZE = (1206, 906)

# 圆点（用于检查残留）
DOTS = [
    (1043, 573, 36), (1119, 192, 60), (1157, 399, 25), (1140, 786, 65),
    (128, 444, 29), (133, 107, 31), (-1, 234, 62), (332, 789, 31),
    (73, 669, 60), (801, 694, 14), (953, 68, 10),
]


def fail(msg: str, errors: list[str]):
    print(f"  [FAIL] {msg}")
    errors.append(msg)


def main() -> int:
    errors: list[str] = []
    mp = os.path.join(OUT, "manifest.json")
    if not os.path.exists(mp):
        print("[FAIL] manifest.json 不存在，请先运行 cut_stickers.py")
        return 1

    with open(mp, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    libs = manifest.get("libraries", [])
    ids = [l["id"] for l in libs]
    if ids != EXPECTED_LIBS:
        fail(f"库列表不符：{ids} != {EXPECTED_LIBS}", errors)

    total = 0
    print("贴纸检查：")
    for lib in libs:
        items = lib.get("items", [])
        total += len(items)
        exp = EXPECTED_COUNTS.get(lib["id"])
        if exp is not None and len(items) != exp:
            fail(f"{lib['id']} 数量 {len(items)} != 预期 {exp}", errors)
        for it in items:
            p = os.path.join(OUT, it["file"])
            if not os.path.exists(p):
                fail(f"缺文件 {it['file']}", errors)
                continue
            im = Image.open(p)
            if im.mode not in ("RGBA", "LA"):
                fail(f"{it['file']} 没有 alpha 通道（mode={im.mode}）", errors)
                continue
            bbox = im.getchannel("A").getbbox()
            if not bbox:
                fail(f"{it['file']} 全部透明", errors)
                continue
            if (bbox[2] - bbox[0], bbox[3] - bbox[1]) != (im.width, im.height):
                fail(f"{it['file']} 四周有多余透明边（bbox={bbox} size={im.size}）", errors)
        print(f"  {lib['id']:<5} {lib.get('name',''):<8} {len(items):>3} 张  OK")
    print(f"  合计 {total} 张（预期 {sum(EXPECTED_COUNTS.values())}）")
    if total != sum(EXPECTED_COUNTS.values()):
        fail(f"贴纸总数 {total} != 预期 {sum(EXPECTED_COUNTS.values())}", errors)

    # 背景图
    print("背景检查：")
    if not os.path.exists(BG):
        fail("bg-nodots.jpg 不存在", errors)
    else:
        bg = Image.open(BG)
        if bg.size != BG_SIZE:
            fail(f"bg-nodots.jpg 尺寸 {bg.size} != {BG_SIZE}", errors)
        else:
            px = bg.convert("RGB").load()
            W, H = bg.size
            dark = 0
            total_px = 0
            for (cx, cy, r) in DOTS:
                for y in range(max(0, cy - 3), min(H, cy + 4)):
                    for x in range(max(0, cx - 3), min(W, cx + 4)):
                        rr, gg, bb = px[x, y]
                        total_px += 1
                        if rr < 205 and gg < 115 and bb < 115 and (rr - gg) >= 25 and (rr - bb) >= 25:
                            dark += 1
            ratio = dark / max(1, total_px)
            print(f"  尺寸 {bg.size}  圆点域残留暗红 {ratio * 100:.2f}%")
            if ratio >= 0.02:
                fail(f"圆点域残留 {ratio * 100:.2f}% >= 2%", errors)
            else:
                print("  圆点残留 OK")

    # 重建联系表
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from cut_stickers import make_contact_sheet
        make_contact_sheet(manifest, os.path.join(OUT, "_contact_sheet.jpg"))
    except Exception as exc:  # noqa: BLE001
        print(f"  [警告] 联系表重建失败：{exc}")

    print()
    if errors:
        print(f"自检未通过，共 {len(errors)} 项问题：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("自检全部通过 ✔")
    return 0


if __name__ == "__main__":
    sys.exit(main())
