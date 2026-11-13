"""Run the MariaDB application with an automatically assigned public HTTPS URL."""
import argparse
import getpass
import hmac
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import APP_BUILD, DB_CONFIG_PATH, Store, load_db_config, make_server, password_hash


def tunnel_url(line):
    match = re.search(r'https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\b', line)
    return match.group(0) if match else None


def load_or_setup(path):
    required = ('RESTFLOW_DB_HOST', 'RESTFLOW_DB_USER', 'RESTFLOW_DB_DATABASE', 'RESTFLOW_DB_DEMO_DATABASE')
    if not Path(path).exists() and not all(os.environ.get(name) for name in required):
        if Path(path).resolve() != DB_CONFIG_PATH.resolve():
            raise RuntimeError('지정한 DB 설정 파일이 없습니다. --db-config 경로를 확인하세요.')
        print('MariaDB 최초 설정을 시작합니다. PC의 MariaDB 서비스가 실행 중이어야 합니다.')
        result = subprocess.run([sys.executable, str(ROOT / 'setup_mariadb.py')], cwd=ROOT)
        if result.returncode:
            raise RuntimeError('MariaDB 설정에 실패했습니다. MariaDB 서비스와 계정 정보를 확인하세요.')
    return load_db_config(path)


def prepare_password(store):
    with store.connect() as db:
        row = db.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone()
    if not hmac.compare_digest(row['password_hash'], password_hash('1234', row['salt'])):
        return
    print('외부 접속 전에 관리자 비밀번호를 설정합니다. 입력한 글자는 표시되지 않습니다.')
    while True:
        password = getpass.getpass('새 비밀번호 (8~128자): ')
        if not 8 <= len(password) <= 128:
            print('8~128자로 입력하세요.'); continue
        if password != getpass.getpass('비밀번호 확인: '):
            print('비밀번호가 일치하지 않습니다.'); continue
        store.logout(store.change_password('1234', password))
        print('설정 완료. 관리자 로그인에 이 비밀번호를 사용하세요.')
        return


def download_tunnel(runtime):
    binary = runtime / 'cloudflared.exe'
    if binary.exists():
        return binary
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
    return binary


def parser():
    result = argparse.ArgumentParser(description='MariaDB 서버와 외부 QR 접속을 함께 실행합니다. 기본은 실제 센서 모드입니다.')
    result.add_argument('--demo', action='store_true', help='가상 데이터로 시연 (별도 demo DB)')
    result.add_argument('--port', type=int, default=8000)
    result.add_argument('--db-config', default=os.environ.get('RESTFLOW_DB_CONFIG', str(DB_CONFIG_PATH)))
    return result


def run(args):
    if sys.platform != 'win32':
        raise RuntimeError('이 실행 도구는 Windows용입니다. 고정 서버는 server.py와 PUBLIC_URL을 사용하세요.')
    if not 1 <= args.port <= 65535:
        raise RuntimeError('포트는 1~65535 범위로 지정하세요.')
    print(f'RestFlow 버전: {APP_BUILD}\n실행 폴더: {ROOT}',flush=True)
    config = load_or_setup(args.db_config)
    try:
        store = Store(config, args.demo)
    except Exception as error:
        raise RuntimeError(f'MariaDB 연결 실패: {error}. MariaDB 서비스와 db_config.json을 확인하세요.') from error
    prepare_password(store)
    runtime = ROOT / '.runtime'
    runtime.mkdir(exist_ok=True)
    # Bind before creating a tunnel, so an old server cannot receive its traffic.
    try:
        server = make_server('127.0.0.1', args.port, store)
    except OSError as error:
        raise RuntimeError(f'포트 {args.port}를 사용할 수 없습니다. 기존 서버를 Ctrl+C로 종료하거나 start_public.bat --port 8001로 실행하세요.') from error
    tunnel = None
    thread = None
    lines = queue.Queue()
    try:
        binary = download_tunnel(runtime)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        tunnel = subprocess.Popen([str(binary), 'tunnel', '--no-autoupdate', '--protocol', 'http2', '--url', f'http://127.0.0.1:{args.port}'],
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
            raise RuntimeError('공개 주소 연결 시간이 초과되었습니다. 인터넷/회사/학교 네트워크 제한을 확인하세요.\n' + ''.join(recent[-8:]))
        server.public_url = public_url
        print('\n모드: ' + ('가상 데이터 시연 (demo DB)' if args.demo else '실제 센서 연결 (live DB)'))
        print('방문객 주소 / 기기 API_BASE: ' + public_url)
        print('관리자: ' + public_url + '/admin')
        print('열린 관리자 화면에서 로그인 → QR 생성 버튼을 누르세요.')
        print('이 창을 켜두세요. 종료: Ctrl+C. 재실행하면 주소와 QR이 바뀝니다.')
        print('실제 기기는 새 API_BASE와 서버 인증서에 맞는 ROOT_CA를 설정해야 합니다.')
        webbrowser.open(f'http://127.0.0.1:{args.port}/admin')
        while thread.is_alive() and tunnel.poll() is None:
            try:
                lines.get(timeout=1)
            except queue.Empty:
                pass
        raise RuntimeError('서버 또는 외부 연결이 종료되었습니다. 다시 실행하고 QR을 새로 생성하세요.')
    finally:
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill(); tunnel.wait()
        if thread is not None:
            server.shutdown(); thread.join(timeout=5)
        server.server_close()


if __name__ == '__main__':
    try:
        run(parser().parse_args())
    except KeyboardInterrupt:
        print('\n외부 접속을 종료했습니다. MariaDB 데이터는 유지됩니다.')
    except Exception as error:
        print(f'\n실행 실패: {error}', file=sys.stderr)
        sys.exit(1)
