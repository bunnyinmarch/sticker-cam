"""把本地静态站推到 GitHub 并开启 GitHub Pages（不需要安装 git/gh）。

用法：
    python tools\\gh_auth.py          # 先授权，token 存到 tools/.gh_token
    python tools\\publish_github.py   # 建仓库 + 推文件 + 开 Pages

全程走 GitHub REST API（api.github.com）：

  A. Contents API 引导（.gitkeep）-> 建出 main 分支
  B. Blobs API 逐个上传（并发）
  C. Trees API 组树
  D. Commits API 提交
  E. Refs API 更新 main
  F. Pages API 开启（Deploy from a branch: main / root）

关键坑：Blobs API 在**完全空的仓库**上会返回 409 "Git Repository is empty."，
所以先用 Contents API 推一个引导文件，仓库非空之后其它接口才正常工作。
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
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(ROOT, "tools", ".gh_token")
REPO_NAME = "sticker-cam"
DESCRIPTION = "捏合召唤贴纸相机 —— 拇指和食指捏住再松开，相机绿屏里随机冒出一张贴纸"
UA = "sticker-camera-publisher"

SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode", "node_modules", "dist"}
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
            last = "HTTP %s %s" % (e.code, e.read().decode()[:300])
            if e.code in (401, 403, 404, 422):
                break
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as e:
            last = repr(e)
        time.sleep(2 + i * 2)
    raise RuntimeError("%s %s failed: %s" % (method, url, last))


def collect_files(root):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            # 只带 .gitignore 这一个隐藏文件，.gh_token / .env 之类一律不上传
            if fn.startswith(".") and fn != ".gitignore":
                continue
            out.append((rel, full))
    return sorted(out)


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

    try:
        r = api("POST", "/user/repos", {
            "name": REPO_NAME, "description": DESCRIPTION, "private": False,
            "auto_init": False, "has_issues": True, "has_wiki": False,
        })
        print("[2] 已建仓库: %s" % r["html_url"])
    except RuntimeError as e:
        if "already exists" in str(e):
            print("[2] 仓库已存在，继续")
        else:
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

    files = collect_files(ROOT)
    total = sum(os.path.getsize(f[1]) for f in files)
    print("[4] 本地 %d 个文件（%.1f MB）" % (len(files), total / 1048576))

    remote = fetch_remote_tree(base_sha)
    reused, changed = [], []
    for rel, full in files:
        (reused if remote.get(rel) == git_blob_sha(full) else changed).append(rel)
    print("[5] 未变化复用 %d 个，需要上传 %d 个: %s"
          % (len(reused), len(changed), ", ".join(changed) or "（无）"))

    uploaded = {}
    todo = [(rel, full) for rel, full in files if rel in set(changed)]
    done = [0]
    t0 = time.time()
    if todo:
        with ThreadPoolExecutor(max_workers=5) as ex:
            for rel, sha, size in ex.map(upload_blob, todo):
                uploaded[rel] = sha
                done[0] += 1
                if done[0] % 10 == 0 or done[0] == len(todo):
                    print("    %d/%d  (%.0fs)" % (done[0], len(todo), time.time() - t0))

    tree = []
    for rel, _ in files:
        sha = uploaded.get(rel) or remote.get(rel) or git_blob_sha(os.path.join(ROOT, rel))
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": sha})

    r = api("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO_NAME), {"tree": tree}, tries=6)
    tree_sha = r["sha"]
    print("[6] tree: %s（%d 个文件）" % (tree_sha, len(tree)))

    r = api("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO_NAME), {
        "message": "更新贴纸相机",
        "tree": tree_sha,
        "parents": [base_sha],
    }, tries=6)
    commit_sha = r["sha"]
    print("[7] commit: %s" % commit_sha)

    api("PATCH", "/repos/%s/%s/git/refs/heads/main" % (OWNER, REPO_NAME),
        {"sha": commit_sha, "force": True}, tries=6)
    print("[8] main 已更新")

    try:
        r = api("POST", "/repos/%s/%s/pages" % (OWNER, REPO_NAME),
                {"source": {"branch": "main", "path": "/"}}, tries=4)
        print("[9] Pages 已开启: %s" % r.get("html_url"))
    except RuntimeError as e:
        if "already exists" in str(e).lower():
            print("[9] Pages 已存在")
        else:
            print("[9] API 开 Pages 失败（需网页点一下）: %s" % e)

    print("\n站点地址: https://%s.github.io/%s/" % (OWNER, REPO_NAME))
    return 0


if __name__ == "__main__":
    sys.exit(main())
