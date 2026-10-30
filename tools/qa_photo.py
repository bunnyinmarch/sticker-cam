r"""校验导出的合成照片：尺寸、背景是否纯白、波点位置、贴纸是否被绿框裁住。

用法：
    python tools\qa_photo.py "D:\某目录\sticker-photo-*.png"
    python tools\qa_photo.py            # 默认校验当前用户桌面上的全部导出照片
"""
import glob
import os
import sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SC = 2                                   # EXPORT_SCALE
SX, SY, SW, SH = 277 * SC, 223 * SC, 459 * SC, 346 * SC   # 绿框在导出图里的位置

# 11 个暗红波点（背景图 1206x906 坐标系）
DOTS = [
    (1043.0, 573.0, 36.0), (1119.0, 192.0, 60.0), (1157.0, 399.0, 25.0),
    (1140.0, 786.0, 65.0), (128.5, 444.5, 29.0), (133.5, 107.5, 31.0),
    (-1.0, 234.5, 62.0), (332.5, 789.5, 31.0), (73.0, 669.5, 60.0),
    (801.0, 694.5, 14.5), (953.0, 68.0, 10.5),
]


def check(P):
    print('=' * 66)
    print('校验：', P)
    im = Image.open(P).convert('RGB')
    W, H = im.size
    size_ok = (W, H) == (1206 * SC, 906 * SC)
    print(f'导出图 {W}x{H}  (期望 {1206*SC}x{906*SC})  '
          f'{"OK" if size_ok else "尺寸不符"}  size={os.path.getsize(P):,} B')
    px = im.load()

    # 1) 背景：上/下饰条应已是纯白（不再有粉色）
    def band_stat(y0, y1, label):
        n = 0
        pink = 0
        for y in range(y0, y1):
            for x in range(0, W, 3):
                r, g, b = px[x, y]
                n += 1
                if r - g > 8 and r - b > 4:
                    pink += 1
        print(f'{label}: 采样 {n} 像素，可见粉色 {pink} 个')

    band_stat(0, 94, '顶部饰条')
    band_stat(H - 94, H, '底部饰条')

    # 2) 波点：11 个暗红圆点应落在正确坐标
    ok = 0
    for cx, cy, r in DOTS:
        x, y = int(cx * SC), int(cy * SC)
        c = px[max(0, min(W - 1, x)), max(0, min(H - 1, y))]
        dark_red = c[0] < 140 and c[1] < 70 and c[2] < 70 and (c[0] - c[1]) > 40
        ok += 1 if dark_red else 0
        if not dark_red:
            print(f'  波点 ({cx},{cy}) 颜色异常 {c}')
    print(f'波点颜色检查：{ok}/{len(DOTS)} 通过')

    # 3) 贴纸是否越框：绿框外不应出现"贴纸级别的彩色像素"（排除背景/相机/波点）
    #    贴纸素材颜色饱和度高，先在绿框内找一张贴纸的主色，再在框外找同色像素
    inside = {}
    for y in range(SY, SY + SH, 2):
        for x in range(SX, SX + SW, 2):
            r, g, b = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn > 90 and mx > 110:
                key = (r // 48, g // 48, b // 48)
                inside[key] = inside.get(key, 0) + 1
    top = sorted(inside.items(), key=lambda kv: -kv[1])[:14]
    print('绿框内主要彩色簇：', [(k, v) for k, v in top])

    outside = {}
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            if SX <= x < SX + SW and SY <= y < SY + SH:
                continue
            r, g, b = px[x, y]
            mx, mn = max(r, g, b), min(r, g, b)
            if mx - mn > 90 and mx > 110:
                key = (r // 48, g // 48, b // 48)
                outside[key] = outside.get(key, 0) + 1
    hits = [(k, v) for k, v in outside.items() if k in inside and inside[k] > 40]
    print('框外出现"与框内贴纸同色"的像素簇：', hits if hits else '无')

    # 4) 绿框外的相机区域应与 bg-plain.jpg 一致
    bg = Image.open(os.path.join(ROOT, 'assets', 'bg-plain.jpg')).convert('RGB')
    bgpx = bg.load()
    diff = 0
    for y in range(0, H, 7):
        for x in range(0, W, 7):
            if SX <= x < SX + SW and SY <= y < SY + SH:
                continue
            c = px[x, y]
            b = bgpx[x // SC, y // SC]
            if max(abs(c[0] - b[0]), abs(c[1] - b[1]), abs(c[2] - b[2])) > 26:
                diff += 1
    print(f'绿框外与背景图不一致的采样点：{diff}（波点/相机高光等会造成少量差异）')
    print()


def main():
    default = os.path.join(os.path.expanduser('~'), 'Desktop', 'sticker-photo-*.png')
    arg = sys.argv[1] if len(sys.argv) > 1 else default
    targets = sorted(glob.glob(arg)) or [arg]
    if not os.path.exists(targets[0]):
        print(f'[ERROR] 找不到 {targets[0]}', file=sys.stderr)
        sys.exit(1)
    for p in targets:
        check(p)
    print('=' * 66)
    print(f'共校验 {len(targets)} 张导出照片')


if __name__ == '__main__':
    main()
