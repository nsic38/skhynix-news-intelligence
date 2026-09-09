from __future__ import annotations

import http.server
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8000

print("뉴스 업데이트 확인...")
result = subprocess.run([sys.executable, str(ROOT / "update_news.py")], cwd=ROOT)

if result.returncode != 0:
    print("뉴스 업데이트 중 오류가 있었습니다. 기존 저장 데이터를 사용해 웹을 엽니다.")

print()
print(f"웹 실행: http://localhost:{PORT}")
print("종료: Ctrl+C")
print()

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

socketserver.TCPServer.allow_reuse_address = True

def open_browser():
    time.sleep(0.8)
    webbrowser.open(f"http://localhost:{PORT}")

threading.Thread(target=open_browser, daemon=True).start()

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n웹 서버 종료.")
