"""One-command Windows public demo. No router or IP configuration needed."""
import getpass
import hmac
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import Store, password_hash


def tunnel_url(line):
    match = re.search(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\b', line)
    return match.group(0) if match else None


def prepare_password(store):
    with store.connect() as db:
        row = db.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone()
    if not hmac.compare_digest(row['password_hash'], password_hash('1234', row['salt'])):
        return
    print('외부 접속 전에 관리자 비밀번호를 설정합니다. 입력한 글자는 표시되지 않습니다.')
    while True:
        password = getpass.getpass('새 비밀번호 (8자 이상): ')
        if len(password) < 8 or len(password) > 128:
            print('8~128자로 입력하세요.'); continue
        if password != getpass.getpass('비밀번호 확인: '):
            print('비밀번호가 일치하지 않습니다.'); continue
        store.logout(store.change_password('1234', password))
        print('설정 완료. 관리자 로그인에 이 비밀번호를 사용하세요.')
        return


def main():
    if sys.platform != 'win32':
        raise RuntimeError('이 실행 도구는 Windows용입니다.')
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    # Use a free local port, so an old demo on 8000 cannot receive tunnel traffic.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    prepare_password(Store(runtime / 'demo.sqlite3', True))
    binary = runtime / 'cloudflared.exe'
    if not binary.exists():
        print('Cloudflare 연결 도구를 처음 한 번 다운로드합니다...')
        machine = os.environ.get('PROCESSOR_ARCHITEW6432', os.environ.get('PROCESSOR_ARCHITECTURE', '')).lower()
        arch = 'arm64' if machine == 'arm64' else 'amd64' if machine == 'amd64' else '386'
        url = f'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-{arch}.exe'
        partial = binary.with_suffix('.download')
        try:
            with urllib.request.urlopen(url, timeout=60) as source, partial.open('wb') as dest:
                while chunk := source.read(1024 * 1024):
                    dest.write(chunk)
            partial.replace(binary)
        finally:
            partial.unlink(missing_ok=True)
    lines = queue.Queue()
    tunnel = None
    server = None
    try:
        tunnel = subprocess.Popen([str(binary), 'tunnel', '--no-autoupdate', '--protocol', 'http2', '--url', f'http://127.0.0.1:{port}'],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        def read_output():
            for line in tunnel.stdout:
                lines.put(line)
        threading.Thread(target=read_output, daemon=True).start()
        print('외부 접속 주소를 연결하는 중입니다...')
        deadline = time.monotonic() + 90
        public_url = None
        recent = []
        while time.monotonic() < deadline:
            if tunnel.poll() is not None:
                raise RuntimeError('Cloudflare 연결이 종료되었습니다. 인터넷 연결을 확인하세요.\n' + ''.join(recent[-8:]))
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                continue
            recent.append(line); recent = recent[-20:]
            public_url = tunnel_url(line)
            if public_url:
                break
        if not public_url:
            raise RuntimeError('공개 주소 연결 시간이 초과되었습니다. 인터넷 또는 회사/학교 네트워크 제한을 확인하세요.\n' + ''.join(recent[-8:]))
        env = dict(os.environ, PUBLIC_URL=public_url)
        server = subprocess.Popen([sys.executable, str(ROOT / 'server.py'), '--demo', '--host', '127.0.0.1', '--port', str(port)], cwd=ROOT, env=env)
        deadline = time.monotonic() + 20
        while True:
            if server.poll() is not None:
                raise RuntimeError('서버를 시작하지 못했습니다.')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError('서버 시작 시간이 초과되었습니다.')
                time.sleep(0.25)
        print('\n방문객 주소: ' + public_url)
        print('열린 관리자 화면에서 로그인 → QR 생성 버튼을 누르세요.')
        print('이 창을 켜두세요. 종료: Ctrl+C. 재실행하면 주소와 QR이 바뀝니다.')
        # Local administration stays available even while the public tunnel connects.
        webbrowser.open(f'http://127.0.0.1:{port}/admin')
        while server.poll() is None and tunnel.poll() is None:
            try:
                lines.get(timeout=1)
            except queue.Empty:
                pass
        raise RuntimeError('서버 또는 외부 연결이 종료되었습니다. 다시 실행하고 QR을 새로 생성하세요.')
    finally:
        for process in (server, tunnel):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n외부 접속을 종료했습니다.')
    except Exception as error:
        print(f'\n실행 실패: {error}', file=sys.stderr)
        sys.exit(1)
