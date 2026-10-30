"""把本地静态站推到 GitHub，并触发 GitHub Actions 自动部署到 Pages（不需要安装 git/gh）。

用法：
    python tools\\gh_auth.py          # 先授权，token 存到 tools/.gh_token
    python tools\\publish_github.py   # 增量推送 + 触发部署

全程走 GitHub REST API（api.github.com）：

  A. 读 main 当前 commit 及其 tree（作为 base_tree）
  B. 本地算 git blob sha，跟远端 tree 比对，只上传**真正变化**的文件
  C. Trees API：base_tree + 变化项 + 删除项（sha=null）
  D. Commits API 提交
  E. Refs API 更新 main
  F. push 触发 .github/workflows/pages.yml，Actions 负责部署 Pages

三个坑（都踩过）：

  1. Blobs API 在**完全空的仓库**上会返回 409 "Git Repository is empty."，
     所以首次要用 Contents API 推一个引导文件把 main 分支建出来。
  2. Trees API **拒绝写 .github/workflows/ 下的文件**（HTTP 404），
     即使换成 Contents API 也一样（缺 workflow scope）。
     所以这类文件只能靠 base_tree 从远端继承，或用 GitHub 网页版编辑。
  3. 连着推太多次会撞上 GitHub **二级速率限制**（secondary rate limit），
     脚本会识别 403 并自动退避重试。
"""
import base64
import hashlib
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(ROOT, "tools", ".gh_token")
REPO_NAME = "sticker-cam"
DESCRIPTION = "捏合召唤贴纸相机 —— 拇指和食指捏住再松开，相机绿屏里随机冒出一张贴纸"
UA = "sticker-camera-publisher"

SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode", "node_modules", "dist"}
# Trees API 写不了这个前缀，只能从远端继承
API_UNWRITABLE = ".github/workflows/"
TOKEN = ""
OWNER = ""


def api(method, path, body=None, tries=8, timeout=120):
    url = path if path.startswith("http") else "https://api.github.com" + path
    data = None
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": UA,
        "Authorization": "Bearer " + TOKEN,
    }
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                txt = r.read().decode()
                return json.loads(txt) if txt else {}
        except urllib.error.HTTPError as e:
            code = e.code
            detail = e.read().decode()[:300]
            last = "HTTP %s %s" % (code, detail)
            # 401 是 token 真没权限，没得救；其余都值得重试
            if code == 401:
                break
            if code == 403 and ("rate limit" in detail.lower() or "abuse" in detail.lower()):
                wait = 60 + i * 30
                print("    [限流] 等 %d 秒后重试..." % wait, flush=True)
                time.sleep(wait)
                continue
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as e:
            last = repr(e)
        time.sleep(2 + i * 2)
    raise RuntimeError("%s %s failed: %s" % (method, url, last))


def collect_files(root):
    """本地要同步的文件（相对路径, 绝对路径）。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and (not d.startswith(".") or d == ".github")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            # 只带 .gitignore 这一个隐藏文件，.gh_token / .env 之类一律不上传
            if fn.startswith(".") and fn != ".gitignore":
                continue
            out.append((rel, full))
    return sorted(out)


def _norm(b):
    """比较文本用：统一行尾、去掉尾部空白。"""
    return b.replace(b"\r\n", b"\n").rstrip()


def git_blob_sha(path):
    """本地算 git blob sha，和远端 tree 对比就能跳过没变的文件。"""
    with open(path, "rb") as f:
        data = f.read()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def fetch_remote_tree(commit_sha):
    """取远端 commit 的完整文件表： {相对路径: blob sha}"""
    r = api("GET", "/repos/%s/%s/git/trees/%s?recursive=1"
            % (OWNER, REPO_NAME, commit_sha), tries=6)
    if r.get("truncated"):
        print("    [warn] 远端 tree 被截断，本次全量上传")
        return {}
    return {e["path"]: e["sha"] for e in r.get("tree", []) if e.get("type") == "blob"}


def upload_blob(item):
    rel, full = item
    with open(full, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    r = api("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO_NAME),
            {"content": b64, "encoding": "base64"}, tries=6, timeout=180)
    return rel, r["sha"], len(data)


def main():
    global TOKEN, OWNER
    if not os.path.exists(TOKEN_FILE):
        print("没有 token，请先运行： python tools\\gh_auth.py", file=sys.stderr)
        return 1
    TOKEN = open(TOKEN_FILE, encoding="utf-8").read().strip()
    OWNER = api("GET", "/user")["login"]
    print("[1] 账号: %s" % OWNER)

    # 先读一下仓库在不在，别一上来就 POST 建仓库（白白吃一次写配额）
    try:
        r = api("GET", "/repos/%s/%s" % (OWNER, REPO_NAME), tries=4)
        print("[2] 仓库已存在: %s" % r["html_url"])
    except RuntimeError:
        try:
            r = api("POST", "/user/repos", {
                "name": REPO_NAME, "description": DESCRIPTION, "private": False,
                "auto_init": False, "has_issues": True, "has_wiki": False,
            }, tries=4)
            print("[2] 已建仓库: %s" % r["html_url"])
        except RuntimeError as e:
            print("[2] 建仓库失败: %s" % e, file=sys.stderr)
            return 1

    try:
        br = api("GET", "/repos/%s/%s/git/ref/heads/main" % (OWNER, REPO_NAME))
        base_sha = br["object"]["sha"]
        print("[3] main 已存在: %s" % base_sha)
    except RuntimeError:
        boot = api("PUT", "/repos/%s/%s/contents/.gitkeep" % (OWNER, REPO_NAME), {
            "message": "初始化仓库",
            "content": base64.b64encode(b"").decode(),
            "branch": "main",
        }, tries=6)
        base_sha = boot["commit"]["sha"]
        print("[3] 引导提交已建: %s" % base_sha)

    commit = api("GET", "/repos/%s/%s/git/commits/%s" % (OWNER, REPO_NAME, base_sha), tries=6)
    base_tree = commit["tree"]["sha"]
    remote = fetch_remote_tree(base_sha)
    print("[4] 远端 tree: %s（%d 个文件）" % (base_tree, len(remote)))

    files = collect_files(ROOT)
    local_paths = {rel for rel, _ in files}
    total = sum(os.path.getsize(f[1]) for f in files)
    print("[5] 本地 %d 个文件（%.1f MB）" % (len(files), total / 1048576))

    changed = []
    for rel, full in files:
        if rel.startswith(API_UNWRITABLE):
            # Trees API 写不了这个前缀，只能继承远端那份；
            # 但如果内容真的变了，要提醒用户去网页版改
            if remote.get(rel) and remote[rel] != git_blob_sha(full):
                same = False
                try:
                    rb = api("GET", "/repos/%s/%s/git/blobs/%s"
                             % (OWNER, REPO_NAME, remote[rel]), tries=4)
                    same = _norm(base64.b64decode(rb["content"])) == \
                        _norm(open(full, "rb").read())
                except RuntimeError:
                    same = False
                if not same:
                    print("    [注意] %s 与远端不一致：API 改不了 .github/workflows/，"
                          "请到 GitHub 网页版修改" % rel)
            continue
        if remote.get(rel) != git_blob_sha(full):
            changed.append((rel, full))
    print("[6] 需要上传 %d 个: %s"
          % (len(changed), ", ".join(r for r, _ in changed) or "（无）"))

    # 本地删掉了、远端还在的文件 -> 显式置空 sha 让树里删掉
    removed = [p for p in remote
               if p not in local_paths and not p.startswith(API_UNWRITABLE)]
    if removed:
        print("    同时删除 %d 个远端文件: %s" % (len(removed), ", ".join(removed)))

    uploaded = {}
    done = [0]
    t0 = time.time()
    if changed:
        with ThreadPoolExecutor(max_workers=5) as ex:
            for rel, sha, size in ex.map(upload_blob, changed):
                uploaded[rel] = sha
                done[0] += 1
                if done[0] % 10 == 0 or done[0] == len(changed):
                    print("    %d/%d  (%.0fs)" % (done[0], len(changed), time.time() - t0))

    # base_tree 继承远端已有文件，只把变化的写进去 —— 传全量树反而会被
    # .github/workflows/ 那条限制卡住
    entries = []
    for rel, _ in changed:
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": uploaded[rel]})
    for rel in removed:
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": None})

    if not entries:
        print("[7] 内容与远端完全一致，跳过提交")
        print("[8] main 无需更新")
    else:
        r = api("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO_NAME),
                {"base_tree": base_tree, "tree": entries}, tries=6)
        tree_sha = r["sha"]
        print("[7] tree: %s（改 %d / 删 %d）" % (tree_sha, len(changed), len(removed)))

        r = api("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO_NAME), {
            "message": "更新贴纸相机",
            "tree": tree_sha,
            "parents": [base_sha],
        }, tries=6)
        commit_sha = r["sha"]
        print("[8] commit: %s" % commit_sha)

        api("PATCH", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO_NAME),
            {"sha": commit_sha, "force": True}, tries=6)
        print("[9] main 已更新")

    print("\n推送完成，push 会触发 .github/workflows/pages.yml 自动部署。")
    print("站点地址: https://%s.github.io/%s/" % (OWNER, REPO_NAME))
    return 0


if __name__ == "__main__":
    sys.exit(main())
