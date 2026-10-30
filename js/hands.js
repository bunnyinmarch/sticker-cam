// 手部识别：MediaPipe HandLandmarker + 捏合状态机 + 手部骨架绘制。
// 手势语义（已确认）：捏住拇指与食指定位，**松开瞬间**在指尖位置生成贴纸。

import { dist, clamp } from './util.js';

/* ---------------- 可调参数（现场实测可改） ---------------- */
export const PINCH_ENTER = 0.38;   // 进入捏合：指尖距 / 手掌尺度 低于该值
export const PINCH_EXIT = 0.52;    // 退出捏合（滞回，防抖动）
export const MIN_HOLD_MS = 120;    // 捏合至少持续这么久才算有效
export const MIN_FRAMES = 2;       // 至少连续命中 2 帧

// MediaPipe 手部骨架连线
const HAND_CONNECTIONS = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17],
];

/** 五指伸展判定：返回 {thumb,index,middle,ring,pinky} 的 true/false */
export function fingerStates(lm) {
  const tips = [4, 8, 12, 16, 20];
  const pips = [3, 6, 10, 14, 18];
  const scale = Math.max(1e-6, dist(lm[0], lm[9]));
  const out = {};
  const names = ['thumb', 'index', 'middle', 'ring', 'pinky'];
  for (let i = 0; i < 5; i++) {
    // 指尖到腕的距离明显大于第二关节到腕的距离 => 该指伸直
    out[names[i]] = dist(lm[tips[i]], lm[0]) > dist(lm[pips[i]], lm[0]) * 1.12;
  }
  out.scale = scale;
  return out;
}

export function createHandTracker({ video, overlay, onRelease, onStatus }) {
  let landmarker = null;
  let loading = false;
  let lastTs = -1;

  let pinched = false;
  let pinchStart = 0;
  let pinchFrames = 0;
  let pinchPoint = null;      // 视频归一化坐标 {x, y}
  let lastLandmarks = null;
  // 默认不画手部骨架（页面上不要那条白色的手），需要调试时用 ?skeleton=1 打开
  let skeletonVisible = false;
  let lastDrawn = false;      // 画布上是否还留着上一帧的骨架

  const ctx = overlay ? overlay.getContext('2d') : null;

  async function load() {
    if (landmarker || loading) return landmarker;
    loading = true;
    onStatus && onStatus('loading', '正在载入手势识别模型…');
    try {
      // 本地化的 MediaPipe（相对路径 → 绝对 URL，兼容部署到任意子目录）
      const vision = await import('../assets/vendor/vision_bundle.mjs');
      const wasmBase = new URL('assets/vendor/wasm', document.baseURI).href;
      const modelUrl = new URL('assets/model/hand_landmarker.task', document.baseURI).href;

      const fileset = await vision.FilesetResolver.forVisionTasks(wasmBase);
      const opts = {
        baseOptions: { modelAssetPath: modelUrl, delegate: 'GPU' },
        runningMode: 'VIDEO',
        numHands: 1,
        minHandDetectionConfidence: 0.5,
        minHandPresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      };
      try {
        landmarker = await vision.HandLandmarker.createFromOptions(fileset, opts);
      } catch (gpuErr) {
        console.warn('[hands] GPU 不可用，退回 CPU：', gpuErr);
        opts.baseOptions.delegate = 'CPU';
        landmarker = await vision.HandLandmarker.createFromOptions(fileset, opts);
      }
      onStatus && onStatus('ready', '手势识别已就绪');
    } catch (err) {
      console.error('[hands] 模型加载失败：', err);
      onStatus && onStatus('error', '手势识别模型加载失败（摄像头仍可用）');
      throw err;
    } finally {
      loading = false;
    }
    return landmarker;
  }

  function drawSkeleton(lm, w, h) {
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    lastDrawn = !!lm;
    if (!lm) return;
    ctx.save();
    ctx.lineWidth = Math.max(1.6, w / 220);
    ctx.strokeStyle = 'rgba(255,255,255,0.92)';
    ctx.shadowColor = 'rgba(0,0,0,0.55)';
    ctx.shadowBlur = 4;
    for (const [a, b] of HAND_CONNECTIONS) {
      ctx.beginPath();
      ctx.moveTo(lm[a].x * w, lm[a].y * h);
      ctx.lineTo(lm[b].x * w, lm[b].y * h);
      ctx.stroke();
    }
    ctx.fillStyle = 'rgba(255,255,255,0.95)';
    for (const p of lm) {
      ctx.beginPath();
      ctx.arc(p.x * w, p.y * h, ctx.lineWidth * 1.5, 0, Math.PI * 2);
      ctx.fill();
    }
    // 捏合点提示环
    if (pinched && pinchPoint) {
      ctx.beginPath();
      ctx.arc(pinchPoint.x * w, pinchPoint.y * h, ctx.lineWidth * 3.4, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255,120,170,0.95)';
      ctx.stroke();
    }
    ctx.restore();
  }

  /**
   * 每帧调用一次。检测到手部并处理捏合状态机；发生"松开"时回调 onRelease。
   * @returns {boolean} 是否检测到手
   */
  function processFrame(ts, screenW, screenH) {
    if (!landmarker || !video || video.readyState < 2) return false;
    if (ts <= lastTs) ts = lastTs + 1;
    lastTs = ts;

    let res;
    try {
      res = landmarker.detectForVideo(video, ts);
    } catch (err) {
      console.warn('[hands] 检测异常：', err);
      return false;
    }

    const lm = res && res.landmarks && res.landmarks.length ? res.landmarks[0] : null;
    lastLandmarks = lm;

    if (overlay && ctx) {
      if (skeletonVisible) drawSkeleton(lm, screenW, screenH);
      else if (lastDrawn) { ctx.clearRect(0, 0, screenW, screenH); lastDrawn = false; }
    }

    if (!lm) {
      // 手离开画面：取消捏合，但不生成贴纸
      if (pinched) {
        pinched = false;
        pinchFrames = 0;
        pinchPoint = null;
      }
      return false;
    }

    const scale = Math.max(1e-6, dist(lm[0], lm[9]));
    const ratio = dist(lm[4], lm[8]) / scale;

    if (!pinched) {
      if (ratio < PINCH_ENTER) {
        pinchFrames += 1;
        if (pinchFrames === 1) {
          pinchStart = performance.now();
          pinchPoint = { x: (lm[4].x + lm[8].x) / 2, y: (lm[4].y + lm[8].y) / 2 };
        } else {
          pinchPoint = { x: (lm[4].x + lm[8].x) / 2, y: (lm[4].y + lm[8].y) / 2 };
        }
        if (pinchFrames >= MIN_FRAMES) pinched = true;
      } else {
        pinchFrames = 0;
      }
    } else if (ratio > PINCH_EXIT) {
      // 松开 —— 生成贴纸
      const held = performance.now() - pinchStart;
      const point = pinchPoint;
      pinched = false;
      pinchFrames = 0;
      pinchPoint = null;
      if (held >= MIN_HOLD_MS && point && onRelease) {
        onRelease({ x: clamp(point.x, 0, 1), y: clamp(point.y, 0, 1) });
      }
    }

    return true;
  }

  return {
    load,
    processFrame,
    get landmarks() { return lastLandmarks; },
    get pinched() { return pinched; },
    setSkeletonVisible(v) { skeletonVisible = v; },
  };
}
