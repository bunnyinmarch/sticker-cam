// 手绘风格按钮组（样式参考"按钮图.JPG"）：手绘抖边方框 + 手写字。
//
// 尺寸说明：下面所有数字都是「背景图坐标系」下的像素（背景图 1206x906），
// 页面里用 .btn-row { height: 3.07cqw } 统一缩放，所以窗口怎么变按钮都等比。
// 比例来自「整体参考图」：按钮高 27px、宽依次 27/27/37/37/42/47（相机宽 556），
// 换算到我们的相机宽 770 后即下表。
import { mulberry32 } from './util.js';

// —— 配色：整体偏灰，避免和粉色相机抢眼 ——
const STROKE = '#b3b3b3';   // 手绘方框
const INK = '#8c8c8c';      // 方框里的符号 / 文字

/** 生成一圈带随机抖动的点，再用二次贝塞尔把边磨圆，得到"手画方框" */
function wobblyRect(w, h, seed, amp = 1.7) {
  const rnd = mulberry32(seed);
  const per = 3;
  const pts = [];
  const edges = [
    [[0, 0], [w, 0]],
    [[w, 0], [w, h]],
    [[w, h], [0, h]],
    [[0, h], [0, 0]],
  ];
  for (const [a, b] of edges) {
    for (let i = 0; i < per; i++) {
      const t = i / per;
      pts.push([
        a[0] + (b[0] - a[0]) * t + (rnd() - 0.5) * amp * 2,
        a[1] + (b[1] - a[1]) * t + (rnd() - 0.5) * amp * 2,
      ]);
    }
  }
  const n = pts.length;
  let d = `M ${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let i = 0; i < n; i++) {
    const p = pts[i];
    const q = pts[(i + 1) % n];
    const mx = ((p[0] + q[0]) / 2).toFixed(1);
    const my = ((p[1] + q[1]) / 2).toFixed(1);
    d += ` Q ${p[0].toFixed(1)} ${p[1].toFixed(1)} ${mx} ${my}`;
  }
  return d + ' Z';
}

function polar(cx, cy, r, deg) {
  const a = (deg * Math.PI) / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}

/** 旋转图标：环形箭头 + 箭头尖 */
function arrowIcon(cx, cy, r, ccw) {
  const start = ccw ? 40 : -40;
  const end = ccw ? -230 : 230;
  const p0 = polar(cx, cy, r, start);
  const p1 = polar(cx, cy, r, end);
  const d = `M ${p0.x.toFixed(1)} ${p0.y.toFixed(1)} A ${r} ${r} 0 1 ${ccw ? 0 : 1} ${p1.x.toFixed(1)} ${p1.y.toFixed(1)}`;
  // 末端切线方向，箭头顺着走
  const t = ((end + (ccw ? -90 : 90)) * Math.PI) / 180;
  const tx = Math.cos(t);
  const ty = Math.sin(t);
  const hx = p1.x + tx * (r * 0.6);
  const hy = p1.y + ty * (r * 0.6);
  const nx = -ty;
  const ny = tx;
  const s = r * 0.4;
  const head = `M ${hx.toFixed(1)} ${hy.toFixed(1)} L ${(p1.x + nx * s).toFixed(1)} ${(p1.y + ny * s).toFixed(1)} L ${(p1.x - nx * s).toFixed(1)} ${(p1.y - ny * s).toFixed(1)} Z`;
  return { arc: d, head };
}

const HAND_FONT = '"Caveat", "Segoe Print", "Comic Sans MS", cursive';

function svgButton({ w, h, seed, rotate, content, stroke }) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.setAttribute('width', String(w));
  svg.setAttribute('height', String(h));

  const g = document.createElementNS(NS, 'g');
  g.setAttribute('transform', `rotate(${rotate} ${w / 2} ${h / 2})`);

  const path = document.createElementNS(NS, 'path');
  path.setAttribute('d', wobblyRect(w, h, seed));
  path.setAttribute('fill', '#fff');
  path.setAttribute('stroke', stroke);
  path.setAttribute('stroke-width', '2');
  path.setAttribute('stroke-linejoin', 'round');
  g.appendChild(path);

  const inner = document.createElementNS(NS, 'g');
  inner.innerHTML = content;
  g.appendChild(inner);

  svg.appendChild(g);
  return svg;
}

/**
 * 构建 6 个按钮：− / + / 逆时针15° / 顺时针15° / Delete / Undo
 * handlers: { shrink, grow, rotateCCW, rotateCW, del, undo }
 * 尺寸单位 = 背景图像素
 */
export function buildButtons(container, handlers) {
  if (!container) return null;
  container.innerHTML = '';

  const H = 37;                 // 统一高度
  const defs = [
    { id: 'shrink', label: '缩小贴纸', w: 37, h: H, seed: 11, rotate: -3.2, handler: handlers.shrink,
      content: `<text x="18.5" y="26" text-anchor="middle" font-family='${HAND_FONT}' font-size="22" fill="${INK}">−</text>` },
    { id: 'grow', label: '放大贴纸', w: 37, h: H, seed: 22, rotate: 2.4, handler: handlers.grow,
      content: `<text x="18.5" y="26" text-anchor="middle" font-family='${HAND_FONT}' font-size="22" fill="${INK}">+</text>` },
    { id: 'rotCCW', label: '逆时针旋转 15 度', w: 51, h: H, seed: 33, rotate: -2.2, handler: handlers.rotateCCW, arrow: 'ccw' },
    { id: 'rotCW', label: '顺时针旋转 15 度', w: 51, h: H, seed: 66 - 22, rotate: 3.0, handler: handlers.rotateCW, arrow: 'cw' },
    { id: 'delete', label: '删除选中的贴纸', w: 58, h: H, seed: 55, rotate: -2.4, handler: handlers.del,
      content: `<text x="29" y="24" text-anchor="middle" font-family='${HAND_FONT}' font-size="14" fill="${INK}">Delete</text>` },
    { id: 'undo', label: '撤销上一步', w: 65, h: H, seed: 66, rotate: 2.6, handler: handlers.undo,
      content: `<text x="24" y="24" text-anchor="middle" font-family='${HAND_FONT}' font-size="15" fill="${INK}">Undo</text>` },
  ];

  const buttons = {};
  for (const d of defs) {
    let content = d.content;
    if (d.arrow) {
      const ccw = d.arrow === 'ccw';
      const { arc, head } = arrowIcon(13, H / 2, 6, ccw);
      content = `<path d="${arc}" fill="none" stroke="${INK}" stroke-width="1.6" stroke-linecap="round"/>` +
                `<path d="${head}" fill="${INK}"/>` +
                `<text x="31" y="22" text-anchor="middle" font-family='${HAND_FONT}' font-size="13" fill="${INK}">15</text>` +
                `<text x="41" y="17" text-anchor="middle" font-family='${HAND_FONT}' font-size="9" fill="${INK}">°</text>`;
    } else if (d.id === 'undo') {
      // Undo 右侧跟一个小回转箭头（参考图里就是这个样式）
      const { arc, head } = arrowIcon(50, H / 2, 5.5, false);
      content += `<path d="${arc}" fill="none" stroke="${INK}" stroke-width="1.6" stroke-linecap="round"/>` +
                  `<path d="${head}" fill="${INK}"/>`;
    }
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'hand-btn';
    btn.id = `btn-${d.id}`;
    btn.title = d.label || d.id;
    btn.setAttribute('aria-label', d.label || d.id);
    btn.appendChild(svgButton({ ...d, content, stroke: STROKE }));
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      d.handler && d.handler(btn);
    });
    container.appendChild(btn);
    buttons[d.id] = btn;
  }
  return buttons;
}

/**
 * "Take a photo ♡" —— 手写体 + 一条手抖的下划线。
 * 整体宽度由 CSS 用 cqw 控制（.take-photo svg { width: 10cqw }），
 * 内部坐标按「整体参考图」的比例排：
 *   基线 y=90、爱心中线 y=70、下划线 y=148、画布高 158
 * 渲染后 ≈ 文字高 10.5px、爱心高 7.4px（背景图像素），下划线紧贴文字底部。
 */
export function buildTakePhoto(svgHost, opts = {}) {
  const color = opts.color || '#7a7a7a';
  const NS = 'http://www.w3.org/2000/svg';
  const FONT_SIZE = 58;
  const textX = 16;
  const textY = 90;
  const HEART_S = 60;
  const GAP = 16;
  const H = 158;

  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', `0 0 10 10`);

  const text = document.createElementNS(NS, 'text');
  text.setAttribute('x', String(textX));
  text.setAttribute('y', String(textY));
  text.setAttribute('font-family', HAND_FONT);
  text.setAttribute('font-size', String(FONT_SIZE));
  text.setAttribute('fill', color);
  text.textContent = 'Take a photo';
  svg.appendChild(text);

  // 先量出文字实际宽度，再据此摆爱心和下划线，保证永远不压字
  svgHost.innerHTML = '';
  svgHost.appendChild(svg);
  let tw = 300;
  try {
    const bb = text.getBBox();
    if (bb && bb.width > 0) tw = bb.width;
  } catch { /* 字体未就绪时用估算值 */ }

  const heartX = textX + tw + GAP;
  const heartY = 74;
  const totalW = Math.ceil(heartX + HEART_S * 1.5 + 10);
  svg.setAttribute('viewBox', `0 0 ${totalW} ${H}`);
  svg.setAttribute('width', String(totalW));
  svg.setAttribute('height', String(H));

  // 手绘爱心（空心，跟参考图一致）
  const heart = document.createElementNS(NS, 'path');
  heart.setAttribute('d',
    `M ${heartX} ${heartY + 0.32 * HEART_S} ` +
    `C ${heartX - 0.45 * HEART_S} ${heartY - 0.05 * HEART_S} ${heartX - 0.40 * HEART_S} ${heartY - 0.38 * HEART_S} ${heartX} ${heartY - 0.16 * HEART_S} ` +
    `C ${heartX + 0.40 * HEART_S} ${heartY - 0.38 * HEART_S} ${heartX + 0.45 * HEART_S} ${heartY - 0.05 * HEART_S} ${heartX} ${heartY + 0.32 * HEART_S}`);
  heart.setAttribute('fill', 'none');
  heart.setAttribute('stroke', color);
  heart.setAttribute('stroke-width', '3');
  heart.setAttribute('stroke-linecap', 'round');
  svg.appendChild(heart);

  // 手抖下划线（从 T 一直划到爱心下面）
  const rnd = mulberry32(777);
  const line = document.createElementNS(NS, 'path');
  let d = '';
  const x0 = textX;
  const x1 = heartX + HEART_S * 1.2;
  const y0 = 148;
  const seg = 9;
  for (let i = 0; i <= seg; i++) {
    const x = x0 + ((x1 - x0) * i) / seg;
    const y = y0 + (rnd() - 0.5) * 3.2;
    d += i === 0 ? `M ${x.toFixed(1)} ${y.toFixed(1)}` : ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
  }
  line.setAttribute('d', d);
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke', color);
  line.setAttribute('stroke-width', '2');
  line.setAttribute('stroke-linecap', 'round');
  svg.appendChild(line);

  return svg;
}
