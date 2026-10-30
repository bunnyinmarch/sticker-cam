// 启动装配：圆点动画 → 背景图 → 贴纸系统 → 按钮 → 摄像头 → 手势识别 → 拍照
import { initDots } from './dots.js';
import { buildButtons, buildTakePhoto } from './buttons.js';
import { createHandTracker } from './hands.js';
import { createStickerSystem } from './stickers.js';
import { takePhoto, downloadBlob } from './photo.js';
import { timestampName } from './util.js';

const $ = (id) => document.getElementById(id);

function setHint(text, showButton, soft) {
  const hintText = $('hintText');
  const btn = $('camStartBtn');
  const hint = $('screenHint');
  if (!hint || !hintText) return;
  hint.classList.toggle('soft', !!soft);
  if (text) {
    hintText.textContent = text;
    hint.classList.remove('hidden');
  } else {
    hint.classList.add('hidden');
  }
  if (btn) btn.hidden = !showButton;
}

async function boot() {
  const params = new URLSearchParams(location.search);
  if (params.get('embed') === '1') document.body.dataset.embed = '1';

  const stage = $('stage');
  const screen = $('screen');
  const video = $('video');
  const overlay = $('handOverlay');
  const stickerLayer = $('stickerLayer');

  // 1) 圆点升起动画
  initDots(stage, $('dotsLayer'));

  // 2) 背景图（拍照导出要用）—— 纯白面板 + 粉色相机，粉色饰条已去掉
  const bgImage = new Image();
  bgImage.src = 'assets/bg-plain.jpg';
  try { await bgImage.decode(); } catch { /* 忽略：导出时再画 */ }

  // 3) 贴纸系统
  const stickers = createStickerSystem({
    screenEl: screen,
    layerEl: stickerLayer,
    videoEl: video,
    onChange: () => refreshButtons(),
  });

  let buttons = null;
  function refreshButtons() {
    if (buttons && buttons.undo) {
      buttons.undo.classList.toggle('disabled', !stickers.canUndo);
    }
  }

  // 4) 按钮组 + Take a photo
  buttons = buildButtons($('btnRow'), stickers.ops);
  // 手写字体必须先加载完：getBBox() 量的是当前生效的字体，
  // 字体还没到位时量到的是回退字体宽度，"Take a photo" 会被整体缩得偏小。
  try {
    await Promise.all([
      document.fonts.load('58px Caveat'),
      document.fonts.load('20px "Zhi Mang Xing"'),
    ]);
  } catch { /* 字体加载失败就用回退字体 */ }
  buildTakePhoto($('takePhoto'), { color: getComputedStyle(document.documentElement)
    .getPropertyValue('--ink').trim() || '#7a7a7a' });
  refreshButtons();

  // 5) 贴纸清单
  try {
    await stickers.loadManifest();
  } catch (err) {
    console.error('[main] 贴纸清单加载失败：', err);
  }

  // 6) 手势识别
  const tracker = createHandTracker({
    video,
    overlay,
    onRelease: (pt) => {
      stickers.spawn(pt.x, pt.y);
    },
    onStatus: (state, msg) => {
      if (state === 'ready') setHint('');
      else if (state === 'loading') setHint(msg, false, true);
      else if (state === 'error') setHint(msg, false, false);
    },
  });
  // 默认不画白色手部骨架；调试时加 ?skeleton=1
  if (params.get('skeleton') === '1') tracker.setSkeletonVisible(true);

  // 7) 摄像头
  let cameraReady = false;
  async function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setHint('当前环境不支持摄像头（请用 http://localhost 或 https 打开）', true);
      return;
    }
    setHint('正在请求摄像头权限…', false);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          facingMode: 'user',
        },
        audio: false,
      });
      video.srcObject = stream;
      await video.play();
      cameraReady = true;
      setHint('');
      // 手势模型懒加载：摄像头就绪后才开始下载/初始化
      tracker.load().catch(() => { /* 已在 onStatus 里提示 */ });
    } catch (err) {
      const name = err && err.name ? err.name : 'Error';
      const msg = name === 'NotAllowedError'
        ? '请允许摄像头权限后重试'
        : name === 'NotFoundError'
          ? '没有找到摄像头'
          : `摄像头启动失败：${name}`;
      console.warn('[main] 摄像头失败：', err);
      setHint(msg, true);
    }
  }

  $('camStartBtn').addEventListener('click', startCamera);

  // 8) 渲染循环：手部检测 + 骨架重绘
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  let cw = 0;
  let ch = 0;
  function syncCanvas() {
    const w = screen.clientWidth;
    const h = screen.clientHeight;
    if (!w || !h) return;
    if (w === cw && h === ch) return;
    cw = w;
    ch = h;
    overlay.width = Math.round(w * dpr);
    overlay.height = Math.round(h * dpr);
    overlay.style.width = `${w}px`;
    overlay.style.height = `${h}px`;
    const octx = overlay.getContext('2d');
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    stickers.render();
  }

  function loop(ts) {
    syncCanvas();
    if (cameraReady) {
      try {
        tracker.processFrame(ts, cw, ch);
      } catch (err) {
        console.warn('[main] 手势循环异常：', err);
      }
    }
    requestAnimationFrame(loop);
  }
  requestAnimationFrame(loop);

  window.addEventListener('resize', () => {
    syncCanvas();
    stickers.render();
  });

  // 9) 拍照
  let lastShot = null;
  $('takePhoto').addEventListener('click', async () => {
    const btn = $('takePhoto');
    btn.disabled = true;
    try {
      const result = await takePhoto({
        bgImage,
        videoEl: video,
        stickers: stickers.list(),
        imageFor: (file) => stickers.imageFor(file),
        flashEl: $('flash'),
        modalEl: $('previewModal'),
        previewImg: $('previewImg'),
      });
      lastShot = result;
    } catch (err) {
      console.error('[main] 拍照失败：', err);
      alert('拍照失败，请重试');
    } finally {
      btn.disabled = false;
    }
  });

  $('downloadBtn').addEventListener('click', () => {
    if (!lastShot || !lastShot.blob) return;
    downloadBlob(lastShot.blob, `sticker-photo-${timestampName()}.png`);
  });

  $('retakeBtn').addEventListener('click', () => {
    $('previewModal').hidden = true;
  });

  $('previewModal').addEventListener('click', (ev) => {
    if (ev.target === $('previewModal')) $('previewModal').hidden = true;
  });

  // 10) 自动申请摄像头（浏览器会弹权限框）
  startCamera();

  window.__stickerCamera = { stickers, tracker, startCamera };
}

window.addEventListener('error', (ev) => {
  console.error('[fatal]', ev.error || ev.message);
});

boot().catch((err) => {
  console.error('[main] 启动失败：', err);
});
