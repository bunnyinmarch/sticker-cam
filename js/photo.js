// 拍照：把「粉色机身 + 屏幕内容 + 背景圆点」合成成一张完整的相机照片。
import { DOTS, BG_W, BG_H } from './dots.js';
import { timestampName } from './util.js';

export const EXPORT_SCALE = 2;

// 相机屏幕（绿框）在背景图上的位置
export const SCREEN_RECT = { x: 277, y: 223, w: 459, h: 346 };

/**
 * 合成整张相机照片。
 * @returns {{canvas: HTMLCanvasElement, blob: Blob|null, dataUrl: string}}
 */
export function composePhoto({ bgImage, videoEl, stickers = [], imageFor }) {
  const W = BG_W * EXPORT_SCALE;
  const H = BG_H * EXPORT_SCALE;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingQuality = 'high';

  // 1) 背景
  if (bgImage) {
    ctx.drawImage(bgImage, 0, 0, W, H);
  } else {
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, W, H);
  }

  // 2) 背景圆点
  ctx.fillStyle = '#6A0C0C';
  for (const d of DOTS) {
    ctx.beginPath();
    ctx.arc(d.cx * EXPORT_SCALE, d.cy * EXPORT_SCALE, d.r * EXPORT_SCALE, 0, Math.PI * 2);
    ctx.fill();
  }

  // 3) 摄像头画面 -> 屏幕区域（object-fit:cover + 水平镜像）
  const sx = SCREEN_RECT.x * EXPORT_SCALE;
  const sy = SCREEN_RECT.y * EXPORT_SCALE;
  const sw = SCREEN_RECT.w * EXPORT_SCALE;
  const sh = SCREEN_RECT.h * EXPORT_SCALE;

  ctx.save();
  ctx.beginPath();
  ctx.rect(sx, sy, sw, sh);
  ctx.clip();
  ctx.fillStyle = '#0b0b0b';
  ctx.fillRect(sx, sy, sw, sh);

  const vw = videoEl && videoEl.videoWidth ? videoEl.videoWidth : 0;
  const vh = videoEl && videoEl.videoHeight ? videoEl.videoHeight : 0;
  if (vw && vh) {
    const cover = Math.max(sw / vw, sh / vh);
    const dw = vw * cover;
    const dh = vh * cover;
    const ox = sx + (sw - dw) / 2;
    const oy = sy + (sh - dh) / 2;
    ctx.translate(ox + dw, oy);
    ctx.scale(-1, 1);
    ctx.drawImage(videoEl, 0, 0, dw, dh);
  }
  ctx.restore();   // 结束视频的镜像/位移变换

  // 4) 贴纸 —— 单独套一层裁剪，保证只会出现在绿框内
  //    （贴纸坐标 fx/fy 已经是"镜像后的屏幕坐标"，不能再叠加视频的镜像变换）
  ctx.save();
  ctx.beginPath();
  ctx.rect(sx, sy, sw, sh);
  ctx.clip();
  for (const st of stickers) {
    const img = imageFor && imageFor(st.file);
    if (!img || !img.complete || !img.naturalWidth) continue;
    const h = st.scale * sh;
    const w = h * st.aspect;
    const cx = sx + st.fx * sw;
    const cy = sy + st.fy * sh;
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate((st.rot * Math.PI) / 180);
    ctx.drawImage(img, -w / 2, -h / 2, w, h);
    ctx.restore();
  }
  ctx.restore();

  return canvas;
}

function toBlob(canvas) {
  return new Promise((resolve) => {
    if (canvas.toBlob) {
      canvas.toBlob((b) => resolve(b), 'image/png');
    } else {
      resolve(null);
    }
  });
}

/** 拍一张：合成 -> 闪白 -> 弹预览 */
export async function takePhoto(opts) {
  const {
    bgImage, videoEl, stickers, imageFor,
    flashEl, modalEl, previewImg,
    onDownload, onRetake,
  } = opts;

  const canvas = composePhoto({ bgImage, videoEl, stickers, imageFor });

  // 闪白
  if (flashEl) {
    flashEl.classList.remove('on');
    void flashEl.offsetHeight;
    flashEl.classList.add('on');
  }

  let blob = await toBlob(canvas);
  if (!blob) {
    // PNG 失败时降级为 JPEG
    const dataUrlJpg = canvas.toDataURL('image/jpeg', 0.92);
    if (previewImg) previewImg.src = dataUrlJpg;
    if (modalEl) modalEl.hidden = false;
    return { canvas, blob: null, dataUrl: dataUrlJpg };
  }

  const dataUrl = canvas.toDataURL('image/png');
  if (previewImg) previewImg.src = dataUrl;
  if (modalEl) modalEl.hidden = false;

  if (onDownload) {
    onDownload({
      blob,
      dataUrl,
      filename: `sticker-photo-${timestampName()}.png`,
    });
  }
  if (onRetake) onRetake();
  return { canvas, blob, dataUrl };
}

/** 触发浏览器下载 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
