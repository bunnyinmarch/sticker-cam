// 暗红圆点：从画面下方向上"升起"，落到背景图里原本的位置后停住，尺寸始终不变。
// 坐标为背景图 1206x906 的原图像素（背景图已预先去掉烙印圆点，见 tools/remove_dots.py）。

export const BG_W = 1206;
export const BG_H = 906;

/** 11 个圆点：圆心 + 半径（边缘被裁切的两个由外接框反推真实圆心） */
export const DOTS = [
  { cx: 1043.0, cy: 573.0, r: 36.0 },
  { cx: 1119.0, cy: 192.0, r: 60.0 },
  { cx: 1157.0, cy: 399.0, r: 25.0 },
  { cx: 1140.0, cy: 786.0, r: 65.0 },   // 右侧被裁切
  { cx: 128.5, cy: 444.5, r: 29.0 },
  { cx: 133.5, cy: 107.5, r: 31.0 },
  { cx: -1.0, cy: 234.5, r: 62.0 },     // 左侧被裁切
  { cx: 332.5, cy: 789.5, r: 31.0 },
  { cx: 73.0, cy: 669.5, r: 60.0 },
  { cx: 801.0, cy: 694.5, r: 14.5 },
  { cx: 953.0, cy: 68.0, r: 10.5 },
];

const RISE_MS = 1100;
const STAGGER_MS = 70;

/**
 * 在舞台里生成圆点并播放升起动画。
 * 尺寸用百分比表示，因此窗口缩放时圆点跟着缩放；动画只改 translate，不改宽高。
 */
export function initDots(stageEl, layerEl) {
  if (!stageEl || !layerEl) return [];

  const stageH = stageEl.getBoundingClientRect().height || BG_H;
  const nodes = [];

  DOTS.forEach((d, i) => {
    const el = document.createElement('div');
    el.className = 'dot';
    el.style.left = `${(d.cx / BG_W) * 100}%`;
    el.style.top = `${(d.cy / BG_H) * 100}%`;
    el.style.width = `${((d.r * 2) / BG_W) * 100}%`;
    el.style.height = `${((d.r * 2) / BG_H) * 100}%`;
    el.style.marginLeft = `${(-d.r / BG_W) * 100}%`;
    el.style.marginTop = `${(-d.r / BG_H) * 100}%`;
    layerEl.appendChild(el);
    nodes.push(el);
  });

  // 先把圆点放到舞台下方，再逐个过渡到目标位置
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      nodes.forEach((el, i) => {
        const d = DOTS[i];
        const rise = stageH + d.r * 2 + 24;
        el.style.transition = 'none';
        el.style.transform = `translateY(${rise}px)`;
        // 强制回流，确保初始位移生效后再启动过渡
        void el.offsetHeight;
        el.style.transition = `transform ${RISE_MS}ms cubic-bezier(.22,.9,.28,1) ${i * STAGGER_MS}ms`;
        el.style.transform = 'translateY(0)';
      });
    });
  });

  return nodes;
}
