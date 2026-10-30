// 贴纸核心：贴纸池调度、生成、选中、拖拽、缩放/旋转、删除与整体撤销。
//
// 坐标系说明：
//  - 贴纸位置 fx / fy 是相对"相机屏幕"的比例（0~1），因此窗口缩放时贴纸跟着缩放；
//  - 贴纸大小 scale 是"高度占屏幕高度的比例"（初始 0.18）；
//  - rot 是角度，CSS 约定正角 = 顺时针。

import { clamp, shuffle, shake } from './util.js';

const MAX_STICKERS = 60;
const HISTORY_LIMIT = 100;
const INITIAL_SCALE = 0.18;
const SCALE_MIN = 0.03;
const SCALE_MAX = 2.0;
const ROTATE_STEP = 15;

export function createStickerSystem({ screenEl, layerEl, videoEl, onChange }) {
  const state = {
    manifest: null,
    stickers: [],       // {id, seq, libId, file, aspect, fx, fy, scale, rot, el}
    selectedId: null,
    history: [],
    seq: 0,
    pools: {},          // libId -> {deck: [], cursor: 0}
    images: new Map(),  // file -> HTMLImageElement（导出时复用）
  };

  let drag = null;

  const screenSize = () => ({
    w: screenEl.clientWidth || 1,
    h: screenEl.clientHeight || 1,
  });

  /* ---------------- 资产 ---------------- */

  async function loadManifest() {
    const res = await fetch('assets/stickers/manifest.json', { cache: 'force-cache' });
    if (!res.ok) throw new Error(`manifest 加载失败: ${res.status}`);
    state.manifest = await res.json();

    for (const lib of state.manifest.libraries) {
      state.pools[lib.id] = { deck: [], cursor: 0 };
    }
    // 预加载所有贴纸图片（同时用于拍照导出）
    const jobs = [];
    for (const lib of state.manifest.libraries) {
      for (const it of lib.items) {
        const img = new Image();
        img.decoding = 'async';
        const url = `assets/stickers/${it.file}`;
        state.images.set(it.file, img);
        jobs.push(new Promise((resolve) => {
          img.onload = img.onerror = () => resolve();
          img.src = url;
        }));
      }
    }
    await Promise.all(jobs);
    return state.manifest;
  }

  /* ---------------- 池调度（5 库各自独立轮换） ---------------- */

  function pickFromPool() {
    const libs = state.manifest.libraries;
    const lib = libs[Math.floor(Math.random() * libs.length)];
    const pool = state.pools[lib.id];
    if (!pool.deck.length || pool.cursor >= pool.deck.length) {
      pool.deck = shuffle(lib.items.map((_, i) => i));
      pool.cursor = 0;
    }
    const idx = pool.deck[pool.cursor++];
    return { lib, item: lib.items[idx], index: idx };
  }

  /* ---------------- 坐标换算 ---------------- */

  /** 视频归一化坐标 -> 屏幕像素坐标（视频是 object-fit:cover 且水平镜像） */
  function videoToScreen(nx, ny) {
    const { w: sw, h: sh } = screenSize();
    const vw = videoEl.videoWidth || 1;
    const vh = videoEl.videoHeight || 1;
    const s = Math.max(sw / vw, sh / vh);
    const dispW = vw * s;
    const dispH = vh * s;
    const offX = (sw - dispW) / 2;
    const offY = (sh - dispH) / 2;
    const ux = offX + nx * dispW;
    const uy = offY + ny * dispH;
    return { x: sw - ux, y: uy };   // 镜像
  }

  /* ---------------- 渲染 ---------------- */

  function render() {
    const { w, h } = screenSize();
    for (const st of state.stickers) {
      if (!st.el) continue;
      const hh = st.scale * h;
      const ww = hh * st.aspect;
      st.el.style.width = `${ww}px`;
      st.el.style.height = `${hh}px`;
      st.el.style.transform =
        `translate(-50%,-50%) translate(${st.fx * w}px, ${st.fy * h}px) rotate(${st.rot}deg)`;
      st.el.style.zIndex = String(100 + st.seq);
    }
  }

  function select(id) {
    state.selectedId = id;
    for (const st of state.stickers) {
      if (st.el) st.el.classList.toggle('selected', st.id === id);
    }
    onChange && onChange(state);
  }

  function snapshot() {
    return state.stickers.map((st) => ({
      id: st.id, seq: st.seq, libId: st.libId, file: st.file, aspect: st.aspect,
      fx: st.fx, fy: st.fy, scale: st.scale, rot: st.rot,
    }));
  }

  function pushHistory(snap) {
    state.history.push(snap || snapshot());
    if (state.history.length > HISTORY_LIMIT) state.history.shift();
  }

  function restore(snap) {
    for (const st of state.stickers) st.el && st.el.remove();
    state.stickers = snap.map((d) => ({
      ...d,
      el: makeEl(d),
    }));
    for (const st of state.stickers) layerEl.appendChild(st.el);
    if (!state.stickers.some((s) => s.id === state.selectedId)) select(null);
    render();
    onChange && onChange(state);
  }

  /* ---------------- 贴纸元素 ---------------- */

  function makeEl(d) {
    const el = document.createElement('img');
    el.className = 'sticker';
    el.draggable = false;
    el.alt = '';
    el.src = `assets/stickers/${d.file}`;
    el.dataset.id = d.id;
    el.addEventListener('pointerdown', onStickerPointerDown);
    return el;
  }

  /* ---------------- 生成 ---------------- */

  function spawn(nx, ny) {
    if (!state.manifest) return null;
    const p = videoToScreen(nx, ny);
    const { w, h } = screenSize();
    return spawnAtFraction(w ? p.x / w : 0.5, h ? p.y / h : 0.5);
  }

  /** 直接按屏幕比例生成（调试预览用，不经过视频坐标换算） */
  function spawnAtFraction(fx0, fy0) {
    if (state.stickers.length >= MAX_STICKERS) return null;
    if (!state.manifest) return null;

    const { lib, item, index } = pickFromPool();
    const { w, h } = screenSize();
    const jx = (Math.random() - 0.5) * 0.12;
    const jy = (Math.random() - 0.5) * 0.12;
    const fx = clamp(fx0 + jx, 0, 1);
    const fy = clamp(fy0 + jy, 0, 1);

    pushHistory();

    const st = {
      id: `s${++state.seq}`,
      seq: state.seq,
      libId: lib.id,
      file: item.file,
      aspect: item.w / item.h,
      fx,
      fy,
      scale: INITIAL_SCALE,
      rot: Math.random() * 36 - 18,
    };
    st.el = makeEl(st);
    layerEl.appendChild(st.el);
    state.stickers.push(st);
    render();
    select(st.id);
    onChange && onChange(state);
    return st;
  }

  /* ---------------- 交互 ---------------- */

  function localPoint(st, clientX, clientY) {
    const { w, h } = screenSize();
    const rect = screenEl.getBoundingClientRect();
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    const cx = st.fx * w;
    const cy = st.fy * h;
    const dx = px - cx;
    const dy = py - cy;
    const a = (-st.rot * Math.PI) / 180;
    return {
      lx: dx * Math.cos(a) - dy * Math.sin(a),
      ly: dx * Math.sin(a) + dy * Math.cos(a),
      px,
      py,
    };
  }

  function onStickerPointerDown(ev) {
    ev.stopPropagation();
    const el = ev.currentTarget;
    const st = state.stickers.find((s) => s.id === el.dataset.id);
    if (!st) return;
    select(st.id);

    const { w, h } = screenSize();
    const rect = screenEl.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;
    drag = {
      st,
      offX: px - st.fx * w,
      offY: py - st.fy * h,
      startFx: st.fx,
      startFy: st.fy,
      moved: false,
      pre: snapshot(),
    };
    el.classList.add('dragging');
    el.setPointerCapture(ev.pointerId);
  }

  function onPointerMove(ev) {
    if (!drag) return;
    const { w, h } = screenSize();
    const rect = screenEl.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;
    let fx = (px - drag.offX) / w;
    let fy = (py - drag.offY) / h;
    fx = clamp(fx, 0, 1);
    fy = clamp(fy, 0, 1);
    if (Math.abs(fx - drag.startFx) > 0.002 || Math.abs(fy - drag.startFy) > 0.002) {
      drag.moved = true;
    }
    drag.st.fx = fx;
    drag.st.fy = fy;
    render();
  }

  function onPointerUp(ev) {
    if (!drag) return;
    const { st } = drag;
    if (st.el) {
      st.el.classList.remove('dragging');
      try { st.el.releasePointerCapture(ev.pointerId); } catch { /* ignore */ }
    }
    if (drag.moved) pushHistory(drag.pre);
    drag = null;
    onChange && onChange(state);
  }

  layerEl.addEventListener('pointermove', onPointerMove);
  layerEl.addEventListener('pointerup', onPointerUp);
  layerEl.addEventListener('pointercancel', onPointerUp);
  layerEl.addEventListener('pointerdown', (ev) => {
    if (ev.target === layerEl) select(null);
  });

  /* ---------------- 按钮操作 ---------------- */

  function selected() {
    return state.stickers.find((s) => s.id === state.selectedId) || null;
  }

  function requireSelected(btn) {
    const st = selected();
    if (!st) {
      if (btn) shake(btn);
      return null;
    }
    return st;
  }

  const ops = {
    shrink(btn) {
      const st = requireSelected(btn);
      if (!st) return;
      pushHistory();
      st.scale = clamp(st.scale / 1.1, SCALE_MIN, SCALE_MAX);
      render();
      onChange && onChange(state);
    },
    grow(btn) {
      const st = requireSelected(btn);
      if (!st) return;
      pushHistory();
      st.scale = clamp(st.scale * 1.1, SCALE_MIN, SCALE_MAX);
      render();
      onChange && onChange(state);
    },
    rotateCCW(btn) {
      const st = requireSelected(btn);
      if (!st) return;
      pushHistory();
      st.rot -= ROTATE_STEP;   // CSS 正角为顺时针，逆时针即减
      render();
      onChange && onChange(state);
    },
    rotateCW(btn) {
      const st = requireSelected(btn);
      if (!st) return;
      pushHistory();
      st.rot += ROTATE_STEP;
      render();
      onChange && onChange(state);
    },
    del(btn) {
      // 删除"当前选中"的那张（点一下贴纸选中，再按 Delete）
      const target = requireSelected(btn);
      if (!target) return;
      pushHistory();
      target.el && target.el.remove();
      state.stickers = state.stickers.filter((s) => s !== target);
      select(null);
      render();
      onChange && onChange(state);
    },
    undo(btn) {
      if (!state.history.length) { if (btn) shake(btn); return; }
      const snap = state.history.pop();
      restore(snap);
    },
  };

  return {
    state,
    loadManifest,
    spawn,
    spawnAtFraction,
    select,
    ops,
    render,
    get selected() { return selected(); },
    get canUndo() { return state.history.length > 0; },
    get count() { return state.stickers.length; },
    /** 导出用：当前所有贴纸的数值状态 */
    list() { return state.stickers; },
    imageFor(file) { return state.images.get(file); },
  };
}
