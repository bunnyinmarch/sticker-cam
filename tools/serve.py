#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地预览服务器（多线程，避免一次加载几十张贴纸时被单线程 http.server 卡住）。

用法:
    python tools/serve.py [端口]        # 默认 8123
    然后浏览器打开 http://localhost:8123/
"""
from __future__ import annotations

import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # 开发期禁用缓存，改完刷新立刻生效
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, fmt, *args):  # 安静一点
        if "404" in (fmt % args):
            sys.stderr.write("[404] %s\n" % (fmt % args))


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8123
    handler = partial(Handler, directory=ROOT)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"本地预览: http://localhost:{port}/")
    print(f"嵌入版:   http://localhost:{port}/embed.html")
    print("按 Ctrl+C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
