"""GitHub 设备授权流：申请一次性码 -> 轮询直到用户授权 -> 把 token 写到本地文件。

用法：
    python tools\\gh_auth.py

和 `gh auth login --web` 走的是同一套机制（github.com/login/device），
好处是 token 只落在本机文件里（tools/.gh_token，已被 .gitignore 排除），不经过聊天窗口。

注意：github.com 在部分网络下会间歇性不通，所以所有请求都带重试。
"""
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CLIENT_ID = "178c6fc778ccc68e1d6a"      # GitHub CLI 的 OAuth client id
SCOPE = "repo read:org"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_FILE = os.path.join(ROOT, "tools", ".gh_token")
UA = "sticker-camera-publisher"


def post(url, data, tries=40, timeout=12, gap=2.5):
    """POST + 重试（网络抖动时自动重连）。返回解析后的 JSON。"""
    body = urllib.parse.urlencode(data).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers={
                "Accept": "application/json",
                "User-Agent": UA,
            })
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            last = "HTTP %s %s" % (e.code, e.read()[:200])
            if e.code in (403, 404):
                break
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, OSError) as e:
            last = repr(e)
        time.sleep(gap)
    raise RuntimeError("POST %s failed after %d tries: %s" % (url, i + 1, last))


def main():
    d = post("https://github.com/login/device/code",
             {"client_id": CLIENT_ID, "scope": SCOPE})
    print("=" * 62)
    print("  打开 https://github.com/login/device")
    print("  输入设备码： %s" % d["user_code"])
    print("  （%s 秒内有效）" % d.get("expires_in"))
    print("=" * 62)

    device_code = d["device_code"]
    interval = int(d.get("interval", 5))
    deadline = time.time() + int(d.get("expires_in", 900)) - 20

    while time.time() < deadline:
        time.sleep(interval)
        try:
            r = post("https://github.com/login/oauth/access_token", {
                "client_id": CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            }, tries=6, timeout=12, gap=3)
        except RuntimeError:
            continue

        if "access_token" in r:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(r["access_token"])
            print("授权成功，token 已写入：%s" % TOKEN_FILE)
            print("权限： %s" % (r.get("scope") or "(未返回)"))
            return 0

        err = r.get("error", "")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        print("失败：%s %s" % (err, r.get("error_description", "")), file=sys.stderr)
        return 1

    print("设备码已过期，请重跑本脚本。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
