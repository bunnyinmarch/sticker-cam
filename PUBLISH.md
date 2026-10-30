# 发布到 GitHub Pages（分享链接）

> ✅ **已经发布好了**
>
> | | |
> | --- | --- |
> | 仓库 | <https://github.com/bunnyinmarch/sticker-cam>（公开） |
> | 主页 | <https://bunnyinmarch.github.io/sticker-cam/> |
> | 嵌入版 | <https://bunnyinmarch.github.io/sticker-cam/embed.html> |
>
> 下面是**怎么重新发布**和**另一条路（装 git）**，按需看。

整站是**纯静态**的，没有构建步骤。发布只需要「装 Git → 提交 → 建仓库 → 开 Pages」四步。

发布后的地址形如：

- 主页 `https://<你的用户名>.github.io/sticker-cam/`
- 嵌入版 `https://<你的用户名>.github.io/sticker-cam/embed.html`

> ⚠️ **必须是 https**（`http://localhost` 除外），否则浏览器不给摄像头权限。
> GitHub Pages 自带 https 证书，天然满足要求。

---

## 方式 A：API 直推（推荐，不需要装 git）

本机没装 git、GitHub Release CDN 又下不动安装包时走这条路。仓库里已经带了脚本：

```powershell
# 1) 授权：打印一个设备码，在浏览器打开 https://github.com/login/device 输入它
python tools\gh_auth.py

# 2) 推送：建仓库（若不存在）+ 推全部文件 + 刷新 Pages
python tools\publish_github.py
```

- token 落在 `tools/.gh_token`，已被 `.gitignore` 排除，**不会进仓库**
- `publish_github.py` 走 `api.github.com` 的 Contents / Blobs / Trees / Commits / Refs / Pages 接口
- **坑**：Blobs API 在**完全空的仓库**上会返回 `409 Git Repository is empty.`，
  所以脚本先用 Contents API 推一个 `.gitkeep` 引导文件把 `main` 分支建出来，再走 blob 流程
- 脚本只上传**内容有变化**的文件（本地算 git blob sha 与远端比对），
  内容完全一致时直接跳过提交，不白触发一次 Pages 重建
- 连续推送容易撞上 GitHub **二级速率限制**（`secondary rate limit`），脚本会自动退避重试

### 部署方式：GitHub Actions

仓库内置 `.github/workflows/pages.yml`：

- `push` 到 `main` → 自动把 `index.html / embed.html / styles.css / js / assets`
  打包成 artifact 部署到 GitHub Pages
- `tools/` 和文档不进产物，线上只暴露站点本身
- 手动触发：Actions 页 → *Deploy to GitHub Pages* → *Run workflow*

> 仓库 Settings → Pages → Source 需选 **GitHub Actions**。
> 早先用 "Deploy from a branch"（legacy Jekyll 构建器）已不稳定，
> 同样是内容、构建却会随机 `Page build failed.`，换 Actions 后构建过程可读、可重跑。

> ⚠️ **`.github/workflows/` 下的文件改不了 API**：Trees API 和 Contents API 都会返回
> `404 Not Found`（GitHub 不允许用 API 改工作流文件）。
> `tools/publish_github.py` 会自动**继承**远端那份，不会覆盖；
> 真要改工作流，得去 GitHub 网页版编辑
> <https://github.com/bunnyinmarch/sticker-cam/edit/main/.github/workflows/pages.yml>。

---

## 方式 B：装 Git 走标准流程

本机默认没装 Git。用 winget 一条命令：

```powershell
winget install --id Git.Git -e --source winget
```

**装完要关掉并重开 PowerShell**（PATH 才会生效），然后验证：

```powershell
git --version
```

能看到 `git version 2.x.x` 就成了。

---

## 步骤 1 · 配置身份（只需一次）

```powershell
git config --global user.name "你的GitHub用户名"
git config --global user.email "你的GitHub邮箱"
```

---

## 步骤 2 · 初始化仓库并提交

```powershell
cd ~/Documents/sticker-camera
git init
git branch -M main
git add -A
git commit -m "捏合召唤贴纸相机：首个版本"
```

提交内容：**108 个文件 / 26.6 MB**（最大的三个是 MediaPipe wasm 9 MB、手部模型 7.5 MB、
中文字体 3.9 MB）。`.gitignore` 已经排掉 `__pycache__` 等临时产物。

---

## 步骤 3 · 在 GitHub 网页建仓库

打开 <https://github.com/new>：

| 填什么 | 值 |
| --- | --- |
| Owner | 你的账号 |
| Repository name | `sticker-cam` |
| Description | 捏合召唤贴纸相机 |
| Visibility | **Public**（公开） |

> **不要勾选** "Add a README file" / "Add .gitignore" / "Choose a license"。
> 勾了远端就会多一个提交，第 4 步推送会冲突。

然后点 **Create repository**。

> **为什么必须公开？** 免费账号的 GitHub Pages 只能从公开仓库发布，
> 私有仓库需要 GitHub Pro。项目里只有贴纸素材、相机背景和代码，没有任何密钥或个人信息。

---

## 步骤 4 · 推送代码

```powershell
cd ~/Documents/sticker-camera
git remote add origin https://github.com/<你的用户名>/sticker-cam.git
git push -u origin main
```

推送时 Git Credential Manager 会自动弹出浏览器窗口 → 登录 GitHub → 点授权。
（如果它问你要密码而不是弹窗，说明凭据助手没接管，需要改用 Personal Access Token 当密码。）

---

## 步骤 5 · 开启 GitHub Pages

打开 `https://github.com/<你的用户名>/sticker-cam/settings/pages`：

- **Build and deployment → Source**：选 **GitHub Actions**
- 仓库里已经带了 `.github/workflows/pages.yml`，push 到 `main` 就会自动部署
- 点 **Save**

等 1～3 分钟，页面顶部会出现：

> Your site is live at https://<你的用户名>.github.io/sticker-cam/

> 想看部署进度：仓库 **Actions** 页 → *Deploy to GitHub Pages* → 点进某次运行看日志。

---

## 步骤 6 · 验证并分享

打开主页链接，检查三件事：

1. 页面渲染正常（纯白波点背景 + 粉色相机 + 按钮组）
2. 点「开启摄像头」能拿到权限（**必须是 https**）
3. 捏一下手指能召唤贴纸，点 **Take a photo ♡** 能出照片

然后把 `https://<你的用户名>.github.io/sticker-cam/` 发给别人即可。

---

## 以后更新代码

```powershell
cd ~/Documents/sticker-camera
git add -A
git commit -m "描述这次改了什么"
git push
```

Pages 会自动重新发布，**链接不变**，等 1～2 分钟生效。

---

## 常见问题

| 现象 | 原因 / 解决 |
| --- | --- |
| 打开是 404 | Pages 的 Source 没设成 **GitHub Actions**；或者还在构建，等 1～3 分钟 |
| 构建报 `Page build failed.` | 老式 "Deploy from a branch"（legacy Jekyll）构建器不稳，换成 **GitHub Actions** 即可（仓库已带 workflow） |
| 推送报 `secondary rate limit` | 连着推太多次触发 GitHub 限流，等几分钟再推；脚本已内置退避重试 |
| 摄像头起不来 | 必须是 https。Pages 自带 https；若你是本地 `http://` 测试则需要 `localhost` |
| 首屏很慢、一直转圈 | 首次要下 9 MB wasm + 7.5 MB 手部模型，模型是摄像头就绪后才懒加载的，等一会儿就好 |
| 贴纸不出现 | 确认页面顶部没有红条提示模型加载失败；手势要在**绿框里**做 |
| 想撤回 | 把仓库改成 Private（Pages 会同时停用） |
| 想换自定义域名 | Settings → Pages → Custom domain，填域名后按提示加 CNAME |

---

## 不想每次都开本地服务？

本地开发用 `python tools\serve.py 8123`（见 [run.md](run.md)），
但**给别人分享**必须走 GitHub Pages 或者任何 https 静态托管——
`file://` 和 `http://` 都拿不到摄像头权限。
