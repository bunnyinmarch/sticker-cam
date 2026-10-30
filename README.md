# 捏合召唤贴纸相机

> 拇指和食指捏住再松开 → 相机绿屏里随机冒出一张贴纸 → 和摄像头画面合成一张照片。

**在线体验：** <https://bunnyinmarch.github.io/sticker-cam/>

| | |
| --- | --- |
| 仓库 | <https://github.com/bunnyinmarch/sticker-cam>（公开） |
| 主页 | <https://bunnyinmarch.github.io/sticker-cam/> |
| 嵌入版 | <https://bunnyinmarch.github.io/sticker-cam/embed.html> |

一个**零依赖、零构建**的纯静态网页项目。所有资源（MediaPipe wasm、手部模型、字体）都
已本地化到 `assets/`，断网也能跑。

---

## 快速开始

```bash
cd ~/Documents/sticker-camera
python tools\serve.py 8123
```

打开 <http://localhost:8123/>，允许摄像头权限即可。详见 [run.md](run.md)。

> ⚠️ 必须用 `http://localhost` 或 `https://` 打开。`file://` 不算安全上下文，
> 浏览器拿不到摄像头。手写字体与手绘 SVG 也依赖本地字体文件，所以**离线可用**。

---

## 功能对照

| 需求 | 实现位置 | 说明 |
| --- | --- | --- |
| 暗红圆点从下往上出现，尺寸不变 | `js/dots.js` + `assets/bg-plain.jpg` | 背景图里烙印的 11 个圆点已被 Python 抹掉，DOM 圆点再"升起"到原位；位置/尺寸用百分比，随窗口缩放 |
| 背景去掉粉色饰条，改纯白 | `tools/make_bg.py` → `assets/bg-plain.jpg` | 最小二乘拟合把粉色饰条像素映射成面板灰；黑色笔画仍黑、右上角 BACK 爱心/箭头完好 |
| 绿框内实时摄像头画面 | `js/main.js` | `object-fit: cover` + 水平镜像 |
| 识别五指、捏合生成贴纸 | `js/hands.js` | MediaPipe `HandLandmarker`，**松开瞬间**在指尖位置生成 |
| 贴纸从 5 个库里逐个抠出随机抽 | `js/stickers.js` + `tools/cut_stickers.py` | 66 张透明 PNG；5 库各自独立轮换，库内一轮不重复 |
| 眼镜贴纸镜框内的白色抠成透明 | `tools/cut_stickers.py` | lib3 的 9 张镜片镜框内白色被挖空，透出背景 |
| 贴纸只在绿框内 | `js/stickers.js` + `js/photo.js` | 坐标是屏幕比例 `fx/fy`，钳制在 0~1；导出时再单独套一层裁剪 |
| 刚开始拍摄时绿框内没有贴纸 | `js/main.js` | 页面加载后绿框是空的，贴纸只由捏合手势召唤 |
| 6 个编辑按钮 | `js/buttons.js` | 手绘抖边方框 + 手写字，SVG 生成；`title` / `aria-label` 为中文 |
| `Delete` 删除**当前选中**的贴纸 | `js/stickers.js` | 先点贴纸选中 → 再按 Delete；没选中时按钮抖动提示，不会误删 |
| 手写英文 "Take a photo ♡" | `js/buttons.js` | 先用 `getBBox()` 量文字宽度再摆爱心，保证不压字 |
| 手写中文提示（与参考图同一笔迹） | `assets/hint-cn.png` | 直接用「解释中文」参考图的**原笔迹**裁成的透明灰 PNG，由 `tools/make_hint.py` 生成 |
| 不画白色手部骨架 | `js/hands.js` | 默认关闭；调试时加 `?skeleton=1` |
| 拍照并合成 | `js/photo.js` | 合成「机身 + 屏幕内容 + 背景圆点」，导出 **2412×1812** PNG |

---

## 目录结构

```
sticker-camera/
├─ index.html              主页
├─ embed.html              嵌入版外壳（共用 js/ 与 styles.css）
├─ styles.css
├─ js/
│  ├─ main.js              启动装配、渲染循环、拍照按钮
│  ├─ dots.js              11 个圆点的坐标与升起动画
│  ├─ buttons.js           6 个手绘按钮 + "Take a photo ♡"
│  ├─ hands.js             手部识别、捏合状态机、骨架绘制
│  ├─ stickers.js          贴纸池、生成、选中、拖拽、变换、撤销
│  ├─ photo.js             合成照片、导出、下载
│  └─ util.js              工具函数（clamp / shuffle / 随机数 / 时间戳）
├─ assets/
│  ├─ bg.jpg               原始背景图（只读）
│  ├─ bg-nodots.jpg        抹掉烙印圆点后的背景图（中间产物）
│  ├─ bg-plain.jpg         ★页面实际使用：纯白底 + 粉色相机（粉色饰条已去掉）
│  ├─ bg-plain-preview.jpg bg-plain.jpg 的整体预览图
│  ├─ hint-cn.png          中文提示（参考图原笔迹，透明灰 PNG，1400×96）
│  ├─ lib1.jpg … lib5.jpg  5 个贴纸库原图（只读）
│  ├─ stickers/            66 张透明 PNG + manifest.json + 联系表
│  │  ├─ lib1/01.png … lib5/09.png
│  │  ├─ manifest.json     运行时读这个
│  │  └─ _contact_sheet.jpg 抠图结果的可视化核对图
│  ├─ model/hand_landmarker.task   手部模型（7.8 MB）
│  └─ vendor/              MediaPipe wasm（9.6 MB）+ 字体
├─ tools/
│  ├─ serve.py             本地多线程预览服务器
│  ├─ fetch_deps.py        下载并本地化依赖
│  ├─ remove_dots.py       抹掉背景烙印圆点
│  ├─ make_bg.py           去粉色饰条 → bg-plain.jpg（纯白 + 暗红波点）
│  ├─ make_hint.py         中文提示 → hint-cn.png（参考图原笔迹）
│  ├─ cut_stickers.py      贴纸抠图
│  ├─ qa_photo.py          导出照片回归校验（波点/贴纸位置）
│  └─ verify_assets.py     资产自检
├─ run.md                  快速启动
└─ README.md
```

---

## 工作原理

### 贴纸为什么会"冒出来"

1. `js/hands.js` 每帧调用 `landmarker.detectForVideo(video, ts)` 拿到 21 个手部关键点。
2. 计算 **拇指尖(4) ↔ 食指尖(8) 的距离 ÷ 手掌尺度(腕0→中指根9)**，得到 `ratio`。
3. 状态机（带滞回，防抖动）：
   - `ratio < 0.38` 连续 2 帧 → 进入捏合，记录指尖中点
   - 捏合持续 ≥ 120 ms 后 `ratio > 0.52` → **松开** → 在记录的位置生成贴纸
4. 手离开画面会取消捏合但**不会**生成贴纸（避免手一撤就乱冒）。

阈值集中在 `js/hands.js` 顶部，现场如果不准直接改这四个常量：

```js
export const PINCH_ENTER = 0.38;   // 进入捏合
export const PINCH_EXIT  = 0.52;   // 退出捏合（滞回）
export const MIN_HOLD_MS = 120;    // 最短捏合时长
export const MIN_FRAMES  = 2;      // 最少命中帧数
```

### 贴纸抽取规则

5 个库**各自独立**维护一副牌堆：随机选一个库 → 从该库牌堆取一张 → 该库取完一轮才重新洗牌。
所以同一库里不会出现连续两张重复，但不同库之间可能同时出现风格相近的贴纸。

### 坐标与缩放

- 贴纸位置 `fx/fy` = 相对相机屏幕的比例（0~1），大小 `scale` = 高度占屏高的比例（初始 0.18）
- 旋转 `rot` 单位为度，**CSS 约定正角 = 顺时针**，所以逆时针是 `rot -= 15`
- 浏览器窗口缩放时贴纸同步缩放，不需要重新计算
- 导出时换算成像素：`cx = 屏幕左上x + fx × 屏宽`，`cy = 屏幕左上y + fy × 屏高`，
  其中屏幕矩形是 `js/photo.js` 的 `SCREEN_RECT = {x:277, y:223, w:459, h:346}`（背景图像素，导出 ×2）
- 摄像头画面的水平镜像**只作用于视频本身**：视频和贴纸在 canvas 里各套一层
  `save / clip / restore`，贴纸不会跟着被镜像，也永远画不出绿框

### 撤销

每次「生成 / 拖拽 / 缩放 / 旋转 / 删除」前都压一份快照进历史（上限 100 步）。
`Undo` 弹栈并整体重建 DOM。历史空时按钮变灰。

### 删除

`Delete` 只作用于**当前选中**的那一张：先点贴纸（会高亮）→ 再按 Delete。
没选中任何贴纸时按钮会左右抖动一下提示，不会误删别的。
删除后选中态清空，但**不会**自动改选其它贴纸（避免连按误删）。

---

## 常用改动

| 想改什么 | 改哪里 |
| --- | --- |
| 页面背景色（现在是 `#ffffff`） | `styles.css` 顶部 `--page-bg` |
| 导出倍率（现在 ×2 = 2412×1812） | `js/photo.js` 的 `EXPORT_SCALE` |
| 贴纸初始大小 | `js/stickers.js` 的 `INITIAL_SCALE` |
| 贴纸数量上限 | `js/stickers.js` 的 `MAX_STICKERS` |
| 旋转步长 | `js/stickers.js` 的 `ROTATE_STEP` |
| 捏合灵敏度 | `js/hands.js` 的 `PINCH_ENTER` / `PINCH_EXIT` |
| 圆点颜色 | `js/dots.js` 之外，页面里是 `styles.css` 的 `.dot`；导出用的 `#6A0C0C` 在 `js/photo.js` |
| 中文提示文案 / 字体 | 改 `tools/make_hint.py` 的文案并重跑（或直接换 `assets/hint-cn.png`） |
| 手写字体 | `assets/vendor/fonts.css` |

### BACK 爱心（暂未启用）

背景图右上角的 BACK 箭头旁有一颗手绘爱心。目前只是**透明命中层**，
`pointer-events: none`，点不动。将来要做成可点击控件：

```css
/* styles.css */
.back-heart {
  pointer-events: auto;   /* 打开点击 */
  cursor: pointer;
}
```

```js
// js/main.js 里加
document.getElementById('backHeart').addEventListener('click', () => {
  location.href = '你的目标地址';
});
```

爱心在 1206×906 背景图上的包围盒是 `[1037,17] → [1143,110]`
（left 85.99% / top 1.88% / width 8.88% / height 10.38%），已在 CSS 里写好。

---

## 嵌入到别的网页

`embed.html` 和主页共用同一套 `js/` 和 `styles.css`，只是去掉了多余留白。用 `<iframe>`：

```html
<iframe
  src="https://your-site.com/sticker-camera/embed.html"
  style="width:100%; aspect-ratio:1206/906; border:0;"
  allow="camera"
  title="捏合召唤贴纸相机"></iframe>
```

要点：

- **`allow="camera"` 必须加**，否则 iframe 里拿不到摄像头权限
- 父页面如果是 https，iframe 的 src 也必须是 https（混合内容会被拦）
- 所有路径都是相对路径，放在子目录也能用
- 想全屏铺满可以去掉 `embed.html` 外壳，直接嵌 `index.html`

---

## 发布到公网

整站是纯静态的，把 `sticker-camera/` 整个目录上传到任意静态托管即可，**不需要构建**：

- GitHub Pages：推到仓库 → Settings → Pages → Source 选 **GitHub Actions**
  （本仓库已内置 `.github/workflows/pages.yml`，push 到 `main` 会自动部署）
- Vercel / Netlify：拖目录上去即可
- 自建 Nginx：把目录扔进 `html/` 即可

注意事项：

1. **必须是 https**（`http://localhost` 除外），否则 `getUserMedia` 被拒。
2. 首次访问会下载 9.6 MB wasm + 7.8 MB 模型，模型是**摄像头就绪后才懒加载**的，
   所以首屏不会卡；网络慢时可以给 `assets/` 配长缓存。
3. 整个项目约 **28 MB**，其中 wasm 和模型占绝大部分。

---

## 资产重建

原始素材（`bg.jpg`、`lib1~5.jpg`）在 `assets/` 里保持只读，加工产物都是派生文件：

```bash
python tools\remove_dots.py --preview   # bg.jpg → bg-nodots.jpg（抹掉 11 个烙印圆点）
python tools\make_bg.py --preview        # bg-nodots.jpg → bg-plain.jpg（去掉粉色饰条）
python tools\make_hint.py                # 解释中文.JPG → assets/hint-cn.png
python tools\cut_stickers.py             # lib1~5.jpg → 66 张透明 PNG + manifest.json
python tools\verify_assets.py            # 自检
python tools\qa_photo.py                 # 导出照片回归校验（默认扫桌面上的 sticker-photo-*.png）
python tools\gh_auth.py                  # 申请 GitHub token（存到 tools/.gh_token，不入库）
python tools\publish_github.py           # 推送更新到 GitHub 并刷新 Pages
```

> `tools/make_hint.py` 默认从
> 桌面上的 `AI交互图片参考\解释中文.JPG` 取源图，
> 可以用 `--src` / `--color` / `--width` 覆盖。
>
> `tools/publish_github.py` 走 GitHub REST API 直推，**不需要本机装 git 或 gh**。
> 首次使用先跑 `tools/gh_auth.py` 拿一个设备码授权（token 落在 `tools/.gh_token`，已被 `.gitignore` 排除）。
> 脚本只上传**内容有变化**的文件（本地算 git blob sha 和远端比对），没变的不重传；
> 内容与远端完全一致时会直接跳过提交，不会白触发一次 Pages 重建。
> 连续推送容易撞上 GitHub 的**二级速率限制**（`secondary rate limit`），脚本会自动退避重试。

### 抠图算法（`tools/cut_stickers.py`）

难点是**浅色贴纸压在白底上**会被抠穿。做法：

1. **边界泛洪**：从图片四边向内 flood-fill，标记"背景色"区域
2. **倒角距离场软 alpha**：对每像素算到背景的距离，距离 < 5px 的过渡带按距离给软 alpha，
   近白（阈值 248）且中性（max-min ≤ 14）才算背景 —— 这样白纽扣、白绒玩偶、白蝴蝶结
   内部不会被误判成背景
3. lib1/2/3/5 用网格带切格；lib4（27 件、疏密不均）用连通域
4. 网格模式下按质心归属 + 包围盒重叠迭代合并，处理蝴蝶结飘带跨格的情况
5. **lib3（眼镜）额外做一步"封闭区域挖空"**：镜框内部的白色原本会被当成实心抠下来，
   所以对每张眼镜找出被镜框完全包住的封闭白区，单独挖成透明，让镜片能透出背景

产物共 **66 张**：lib1=9、lib2=12、lib3=9、lib4=27、lib5=9。
`assets/stickers/_contact_sheet.jpg` 是全部 66 张的核对图。

### 去圆点算法（`tools/remove_dots.py`）

按**颜色**检测暗红连通域（`#6A0C0C`）→ 3px 扩张 → 由边界向内扩散填补 → 洞内轻模糊。
不是按"圆形"建模，所以能和面板渐变、机身边缘自然衔接。
检出 12 个连通域，排除机身上一条细竖线后正好 **11 个**。

### 去粉色饰条（`tools/make_bg.py`）

背景图上下各有一条粉色饰条，要换成纯白又不能破坏 1206×906 的尺寸和 `SCREEN_RECT` 坐标，
所以**不裁剪、只改色**：

1. 定位饰条所在行（上/下），行范围向外扩 8 行做缓冲
2. 对每种粉色拟合一个**最小二乘缩放模型**（`PANEL × k`），
   残差小于阈值的像素判为粉色饰条 → 映射成面板灰
3. 另拟合一条"粉→白过渡"模型处理饰条边缘的渐变带
4. 收尾把残余偏色像素中性化，黑色笔画仍黑、白色填充仍白
   （右上角 BACK 的爱心和箭头因此完整保留在白底上）
5. 输出 `bg-plain.jpg`（JPEG quality=92, subsampling=0），
   `--preview` 会额外生成一张上下对比图 `bg-plain-preview.jpg`

实测：饰条残留粉色像素 = 0，饰条非灰像素 = 0。

### 中文提示（`tools/make_hint.py`）

参考图里的中文是**商用手写体**，网上没有可商用的同款字体，
所以逐个比对过 Caveat / 芝麻行楷 / 马善政 / 龙藏 / 站酷快乐体 / 站酷庆科黄油体 /
站酷小薇 / 柳剑毛草之后，改为**直接使用参考图的原笔迹**：

1. 裁出墨迹包围盒
2. 反灰度当 alpha（`ALPHA_CUT=12`、`ALPHA_GAIN=1.25`），把白底抠成透明
3. 缩放到宽 1400，染成 `#6f6f6f`
4. 输出 `assets/hint-cn.png`（1400×96，宽高比 14.583）

页面里用 `<img class="hint-cn">` 显示，`width: 22.9cqw`（= 276 背景图像素，
与「整体参考图」里的中文行等宽），高度按图片自身比例。

代价是文字不可编辑；改文案就重跑 `tools/make_hint.py`。

---

## 已知限制

- **摄像头权限每次刷新都要重新点**「开启摄像头」—— Electron 内置浏览器的行为，
  真实 Chrome 会记住授权。
- 捏合阈值已经在**真人手**上验证可用（连续捏合可稳定召唤贴纸），
  但不同人的手大小/距离不同，个别情况仍可微调 `js/hands.js` 顶部的四个常量。
- 手势识别限制为**同时只跟 1 只手**（`numHands: 1`）。
- 页面**没有做移动端触摸手势**（捏合手势和鼠标拖拽共用一套指针事件，
  移动端浏览器上双指会被当成缩放手势）。
- 中文提示是**图片**，屏幕阅读器读的是 `alt` 文本；换文案需要重跑 `tools/make_hint.py`。
- 导出照片会触发浏览器下载，**默认落在系统「下载」目录**；
  在 Electron 内置浏览器里实测落在**桌面**（`sticker-photo-*.png`）。

---

## 依赖

| 组件 | 版本 / 来源 | 位置 |
| --- | --- | --- |
| MediaPipe Tasks Vision | 官方 npm `@mediapipe/tasks-vision` | `assets/vendor/vision_bundle.mjs` |
| HandLandmarker 模型 | 官方 `hand_landmarker.task` | `assets/model/` |
| Caveat（英文手写） | Google Fonts | `assets/vendor/fonts/` |
| 芝麻行楷（按钮里的中文，如「下载照片」「重拍」） | 站酷字体 | `assets/vendor/fonts/` |
| 中文提示笔迹 | 直接取自参考图「解释中文」原图 | `assets/hint-cn.png` |
| Pillow（仅构建期用） | 13.0.0 | `pip install pillow` |

运行时**不依赖任何 npm 包、不需要 node、不需要构建**。
