# 快速启动

## 1. 起本地服务（必须）

摄像头需要**安全上下文**，`file://` 直接打开会拿不到摄像头权限，所以要起一个本地服务：

```bash
cd ~/Documents/sticker-camera
python tools\serve.py 8123
```

看到 `本地预览: http://localhost:8123/` 就成了。

> 必须用 `tools/serve.py`，不要用 `python -m http.server`——后者是单线程，
> 页面一次并发请求 66 张贴纸会被卡住。

## 2. 打开页面

| 地址 | 说明 |
| --- | --- |
| `http://localhost:8123/` | 主页（纯白波点背景 + 粉色相机 + 按钮组 + 拍照） |
| `http://localhost:8123/embed.html` | 嵌入版外壳（去留白，和主页共用同一套 js/） |

浏览器会弹摄像头权限框 → 点**允许** → 画面开始出现在绿色方框里。

## 3. 玩

打开页面时**绿框里是空的**——贴纸只靠捏合手势召唤。

1. 手伸到镜头前（默认不显示手部骨架）。
2. **拇指和食指捏在一起**（捏住别动），再**松开** —— 松开的一瞬间，指尖位置会冒出一张贴纸。
3. 点贴纸选中它（会高亮），用下面的按钮调整：
   - `−` 缩小 10%
   - `+` 放大 10%
   - `⟲` 逆时针 15°
   - `⟳` 顺时针 15°
   - `Delete` **删掉当前选中的那张**（没选中时按钮会抖一下提示，不会误删）
   - `Undo` 整体退回上一步
4. 贴纸位置直接用鼠标拖。
5. 点 **Take a photo ♡** → 弹出照片预览 → **下载照片** / **重拍**。

> 下载的文件名形如 `sticker-photo-20261030-130218.png`，尺寸固定 **2412×1812**（背景图 ×2）。
> 浏览器默认存到「下载」目录；内置浏览器里实测落在**桌面**。

## 调试参数

| 参数 | 作用 |
| --- | --- |
| `?skeleton=1` | 画出白色手部骨架（默认关闭） |
| `?embed=1` | 嵌入版样式（也可以直接开 `embed.html`） |

例：`http://localhost:8123/?skeleton=1`

## 4. 常用维护命令

```bash
python tools\verify_assets.py          # 自检：贴纸数量 / alpha / 背景尺寸 / 圆点残留
python tools\cut_stickers.py           # 从 lib1~5.jpg 重新抠出 66 张透明 PNG
python tools\remove_dots.py --preview  # 从 bg.jpg 重新抹掉烙印圆点 → bg-nodots.jpg
python tools\make_bg.py --preview      # 从 bg-nodots.jpg 去掉粉色饰条 → bg-plain.jpg（纯白底）
python tools\make_hint.py              # 从「解释中文.JPG」重新生成 assets/hint-cn.png
python tools\qa_photo.py              # 校验导出照片（默认扫桌面上的 sticker-photo-*.png）
python tools\fetch_deps.py             # 重新下载 MediaPipe wasm / 模型 / 字体（联网时）
```

## 5. 发布成公开链接

整站是**纯静态**的，没有构建步骤。把 `sticker-camera/` 整个目录传到任意静态托管
（GitHub Pages / Vercel / Netlify / 自建 Nginx）即可，**必须走 https**，否则摄像头不给权限。

所有资源引用都是相对路径，可以放在子目录里（如 `https://xxx.com/camera/`），
不需要改任何代码。

详细说明见 [README.md](README.md)。
