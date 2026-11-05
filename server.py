"""RestFlow: window-based congestion, SQLite storage, visitor/admin HTTP API."""
import argparse
import hashlib
import hmac
import io
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
WINDOW = 600
OFFLINE = 120
MAX_BODY = 2_800_000

class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def integer(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise Problem(400, f'{name}: {lo}~{hi} 정수가 필요합니다')
    return value


def text_value(value, maximum, name):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Problem(400, f'{name}: 1~{maximum}자 문자열이 필요합니다')
    return value.strip()


def visitor_url(value):
    value=text_value(value,2048,'방문객 접속 주소')
    try:
        parsed=urlparse(value)
        port=parsed.port
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError()
        if any(c.isspace() or ord(c)<32 for c in value):raise ValueError()
    except ValueError:
        raise Problem(400,'사용자명·비밀번호가 없는 올바른 http(s) 주소를 입력하세요')
    return value


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),200_000).hex()


def password_value(value):
    if not isinstance(value,str) or not 4<=len(value)<=128:
        raise Problem(400,'비밀번호는 4~128자로 입력하세요')
    return value


class Store:
    def __init__(self, path, demo=False):
        self.path, self.demo = str(path), demo
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS toilets(id INTEGER PRIMARY KEY, name TEXT NOT NULL,
              stalls INTEGER NOT NULL, x INTEGER NOT NULL, y INTEGER NOT NULL, reset_at REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, toilet_id INTEGER UNIQUE NOT NULL REFERENCES toilets(id),
              token_hash TEXT NOT NULL, last_seen REAL, quality TEXT NOT NULL DEFAULT 'unknown');
            CREATE TABLE IF NOT EXISTS sessions(device_id TEXT NOT NULL REFERENCES devices(id), boot_id TEXT NOT NULL,
              last_seq INTEGER NOT NULL, PRIMARY KEY(device_id,boot_id));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, device_id TEXT NOT NULL REFERENCES devices(id),
              boot_id TEXT NOT NULL, seq INTEGER NOT NULL, direction TEXT NOT NULL,
              occurred_at REAL NOT NULL, received_at REAL NOT NULL,
              UNIQUE(device_id,boot_id,seq));
            CREATE INDEX IF NOT EXISTS event_time ON events(occurred_at);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL NOT NULL, action TEXT NOT NULL);
            ''')
            if 'active' not in {r['name'] for r in db.execute('PRAGMA table_info(toilets)')}:
                db.execute('ALTER TABLE toilets ADD COLUMN active INTEGER NOT NULL DEFAULT 1')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS admin_credentials(id INTEGER PRIMARY KEY CHECK(id=1),salt TEXT NOT NULL,password_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,expires_at REAL NOT NULL);
            ''')
            if not db.execute('SELECT 1 FROM admin_credentials WHERE id=1').fetchone():
                salt=secrets.token_hex(16)
                db.execute('INSERT INTO admin_credentials VALUES(1,?,?)',(salt,password_hash('1234',salt)))
            if not db.execute('SELECT count(*) FROM toilets').fetchone()[0]:
                db.executemany('INSERT INTO toilets(id,name,stalls,x,y) VALUES(?,?,?,?,?)', [
                    (1,'화장실 A',4,22,28), (2,'화장실 B',4,78,48)])
                if demo:
                    db.execute('INSERT INTO toilets(id,name,stalls,x,y) VALUES(3,?,?,?,?)',('화장실 C',3,28,78))
        if demo and not self.all_devices():
            for t in self.snapshot()['toilets']:
                self.register({'id':f'demo-{t["id"]}', 'toilet_id':t['id']})
            self.simulate()

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def all_devices(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT d.id,d.toilet_id,d.last_seen,d.quality FROM devices d JOIN toilets t ON t.id=d.toilet_id WHERE t.active=1')]

    def login(self, password):
        password=password_value(password)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone()
            if not hmac.compare_digest(row['password_hash'],password_hash(password,row['salt'])):
                raise Problem(401,'비밀번호가 올바르지 않습니다')
            return self.new_session(db)

    def new_session(self,db):
        token=secrets.token_urlsafe(32)
        db.execute('DELETE FROM admin_sessions WHERE expires_at<=?',(time.time(),))
        db.execute('INSERT INTO admin_sessions VALUES(?,?)',(digest(token),time.time()+8*3600))
        return token

    def session_valid(self,token):
        if not token:return False
        with self.connect() as db:
            return db.execute('SELECT 1 FROM admin_sessions WHERE token_hash=? AND expires_at>?',(digest(token),time.time())).fetchone() is not None

    def logout(self,token):
        with self.connect() as db:db.execute('DELETE FROM admin_sessions WHERE token_hash=?',(digest(token),))

    def change_password(self,current,new):
        current=password_value(current);new=password_value(new)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone()
            if not hmac.compare_digest(row['password_hash'],password_hash(current,row['salt'])):
                raise Problem(401,'현재 비밀번호가 올바르지 않습니다')
            salt=secrets.token_hex(16)
            db.execute('UPDATE admin_credentials SET salt=?,password_hash=? WHERE id=1',(salt,password_hash(new,salt)))
            db.execute('DELETE FROM admin_sessions')
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),'admin password changed'))
            return self.new_session(db)

    def create(self,data):
        name=text_value(data.get('name'),40,'화장실 이름')
        stalls=integer(data.get('stalls'),1,100,'운영 칸 수')
        x=integer(data.get('x',50),3,97,'지도 x');y=integer(data.get('y',50),3,97,'지도 y')
        with self.connect() as db:
            tid=db.execute('INSERT INTO toilets(name,stalls,x,y) VALUES(?,?,?,?)',(name,stalls,x,y)).lastrowid
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'toilet created: {tid}'))
        if self.demo:self.register({'id':f'demo-{tid}','toilet_id':tid})
        return {'id':tid,'created':True}

    def delete(self,tid):
        with self.connect() as db:
            if not db.execute('UPDATE toilets SET active=0 WHERE id=? AND active=1',(tid,)).rowcount:
                raise Problem(404,'화장실을 찾을 수 없습니다')
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'toilet removed: {tid}'))
        return {'deleted':True}

    def register(self, data):
        device = text_value(data.get('id'),64,'장치 ID')
        if not device.isascii() or not all(c.isalnum() or c in '-_' for c in device):
            raise Problem(400, '장치 ID는 영문·숫자·하이픈·밑줄을 사용하세요')
        toilet = integer(data.get('toilet_id'),1,2_147_483_647,'화장실 ID')
        token = secrets.token_urlsafe(32)
        try:
            with self.connect() as db:
                if not db.execute('SELECT 1 FROM toilets WHERE id=? AND active=1',(toilet,)).fetchone():
                    raise Problem(404,'화장실을 찾을 수 없습니다')
                db.execute('INSERT INTO devices(id,toilet_id,token_hash) VALUES(?,?,?)',(device,toilet,digest(token)))
                db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'device registered: {device}'))
        except sqlite3.IntegrityError:
            raise Problem(409,'화장실이 없거나 이미 등록된 장치/화장실입니다')
        return {'id':device,'token':token}

    def authenticate_device(self, device, token, db):
        row = db.execute('SELECT d.* FROM devices d JOIN toilets t ON t.id=d.toilet_id WHERE d.id=? AND t.active=1',(device,)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'],digest(token)):
            raise Problem(401,'장치 인증에 실패했습니다')
        return row

    def ingest(self, data, token, heartbeat=False, now=None):
        now = time.time() if now is None else now
        device = text_value(data.get('device_id'),64,'device_id')
        quality = data.get('quality','good')
        if quality not in ('good','degraded','fault'):
            raise Problem(400,'quality 값이 올바르지 않습니다')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.authenticate_device(device,token,db)
            if heartbeat:
                db.execute('UPDATE devices SET last_seen=?,quality=? WHERE id=?',(now,quality,device))
                return {'accepted':True}
            boot = text_value(data.get('boot_id'),64,'boot_id')
            seq = integer(data.get('seq'),1,2_147_483_647,'seq')
            direction = data.get('direction')
            if direction not in ('in','out'):
                raise Problem(400,'direction은 in 또는 out입니다')
            at = data.get('occurred_at')
            if type(at) not in (int,float) or not math.isfinite(at) or not now-86400 <= at <= now+30:
                raise Problem(400,'occurred_at은 최근 24시간 이내 UTC Unix 초여야 합니다')
            existing = db.execute('SELECT * FROM events WHERE device_id=? AND boot_id=? AND seq=?',(device,boot,seq)).fetchone()
            if existing:
                if existing['direction'] != direction or existing['occurred_at'] != at:
                    raise Problem(409,'동일 이벤트 키에 다른 내용이 있습니다')
                db.execute('UPDATE devices SET last_seen=?,quality=? WHERE id=?',(now,quality,device))
                return {'accepted':False,'duplicate':True}
            session = db.execute('SELECT last_seq FROM sessions WHERE device_id=? AND boot_id=?',(device,boot)).fetchone()
            if session and seq <= session['last_seq']:
                raise Problem(409,'순서번호가 역전됐습니다. 큐를 순서대로 전송하세요')
            db.execute('INSERT INTO events(device_id,boot_id,seq,direction,occurred_at,received_at) VALUES(?,?,?,?,?,?)',
                       (device,boot,seq,direction,at,now))
            db.execute('INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(device_id,boot_id) DO UPDATE SET last_seq=excluded.last_seq',(device,boot,seq))
            db.execute('UPDATE devices SET last_seen=?,quality=? WHERE id=?',(now,quality,device))
            return {'accepted':True,'duplicate':False}

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            rows = db.execute('SELECT t.*,d.id device_id,d.last_seen,d.quality FROM toilets t LEFT JOIN devices d ON d.toilet_id=t.id WHERE t.active=1 ORDER BY t.id').fetchall()
            result=[]
            for row in rows:
                t=dict(row)
                counts = db.execute('''SELECT direction,count(*) n FROM events WHERE device_id=?
                  AND occurred_at>=? AND occurred_at<=? GROUP BY direction''',
                  (t['device_id'],max(now-WINDOW,t['reset_at']),now)).fetchall()
                counts={r['direction']:r['n'] for r in counts}
                prev=db.execute("SELECT count(*) FROM events WHERE device_id=? AND direction='in' AND occurred_at>=? AND occurred_at<?",(t['device_id'],max(now-2*WINDOW,t['reset_at']),now-WINDOW)).fetchone()[0]
                ins,outs=counts.get('in',0),counts.get('out',0)
                score=(.6*ins+.4*max(0,ins-outs)+.2*max(0,ins-prev))/t['stalls']
                online = t['last_seen'] is not None and now-t['last_seen'] <= OFFLINE
                healthy=online and t['quality']=='good'
                level = ('busy' if score>=2 else 'moderate' if score>=.8 else 'quiet') if healthy else 'unknown'
                t.update(level=level,online=online,score=round(score,2),entries=ins,exits=outs,previous_entries=prev)
                result.append(t)
            settings={r['key']:r['value'] for r in db.execute("SELECT * FROM settings WHERE key IN ('map','visitor_url')")}
        return {'toilets':result,'updated_at':now,'window_seconds':WINDOW,'demo':self.demo,'settings':settings}

    def history(self,toilet_id,now=None):
        now=time.time() if now is None else now
        end=int(now//600)*600
        with self.connect() as db:
            device=db.execute('SELECT id FROM devices WHERE toilet_id=?',(toilet_id,)).fetchone()
            rows=db.execute('''SELECT cast(occurred_at/600 AS INTEGER)*600 bucket,direction,count(*) n FROM events
              WHERE device_id=? AND occurred_at>=? AND occurred_at<? GROUP BY bucket,direction''',
              (device['id'] if device else '',end-11*600,end+600)).fetchall()
        lookup={(r['bucket'],r['direction']):r['n'] for r in rows}
        return [{'at':b,'in':lookup.get((b,'in'),0),'out':lookup.get((b,'out'),0)} for b in range(end-11*600,end+1,600)]

    def update(self,tid,data):
        name=text_value(data.get('name'),40,'화장실 이름')
        stalls=integer(data.get('stalls'),1,100,'운영 칸 수')
        x=integer(data.get('x'),3,97,'지도 x'); y=integer(data.get('y'),3,97,'지도 y')
        with self.connect() as db:
            if not db.execute('UPDATE toilets SET name=?,stalls=?,x=?,y=? WHERE id=? AND active=1',(name,stalls,x,y,tid)).rowcount:
                raise Problem(404,'화장실을 찾을 수 없습니다')
        return {'saved':True}

    def simulate(self):
        if not self.demo:
            raise Problem(403,'시뮬레이션은 --demo에서만 사용할 수 있습니다')
        now=time.time()
        with self.connect() as db:
            for d in db.execute('SELECT d.* FROM devices d JOIN toilets t ON t.id=d.toilet_id WHERE t.active=1').fetchall():
                boot='demo-'+secrets.token_hex(8)
                n={1:2,2:5,3:12}.get(d['toilet_id'],4)
                # Synthetic histories are labelled as demo in every snapshot.
                for i in range(n):
                    db.execute('INSERT INTO events(device_id,boot_id,seq,direction,occurred_at,received_at) VALUES(?,?,?,?,?,?)',
                               (d['id'],boot,i+1,'in',now-(n-i)*12,now))
                db.execute("UPDATE devices SET last_seen=?,quality='good' WHERE id=?",(now,d['id']))
        return {'simulated':True}


class App(BaseHTTPRequestHandler):
    server_version='RestFlow/1.0'
    def log_message(self,fmt,*args):
        # Do not log request URLs, bodies or authentication headers.
        pass

    def send(self,status,body,kind='application/json; charset=utf-8',headers=None):
        if isinstance(body,(dict,list)):
            body=json.dumps(body,ensure_ascii=False).encode()
        if isinstance(body,str): body=body.encode()
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        for key,value in (headers or {}).items():self.send_header(key,value)
        self.end_headers();self.wfile.write(body)

    def token(self):
        auth=self.headers.get('Authorization','')
        return auth[7:] if auth.startswith('Bearer ') else ''

    def session_token(self):
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except CookieError:return ''
        return cookie['restflow_admin'].value if 'restflow_admin' in cookie else ''

    def session_cookie(self,token,clear=False):
        value=f'restflow_admin={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else 8*3600}'
        if self.headers.get('X-Forwarded-Proto')=='https':value+='; Secure'
        return {'Set-Cookie':value}

    def admin(self):
        if not self.server.store.session_valid(self.session_token()):
            raise Problem(401,'관리자 로그인이 필요합니다')

    def qr_url(self):
        with self.server.store.connect() as db:
            row=db.execute("SELECT value FROM settings WHERE key='visitor_url'").fetchone()
        return row['value'] if row else self.server.public_url

    def body(self):
        try: n=int(self.headers.get('Content-Length','0'))
        except ValueError: raise Problem(400,'잘못된 Content-Length')
        if not 0<n<=MAX_BODY: raise Problem(413,'요청 크기는 2.8MB 이하여야 합니다')
        if self.headers.get_content_type()!='application/json': raise Problem(415,'JSON 요청이 필요합니다')
        try: value=json.loads(self.rfile.read(n))
        except (ValueError,UnicodeError): raise Problem(400,'잘못된 JSON입니다')
        if not isinstance(value,dict): raise Problem(400,'JSON 객체가 필요합니다')
        return value

    def do_GET(self): self.handle_request('GET')
    def do_POST(self): self.handle_request('POST')
    def do_PUT(self): self.handle_request('PUT')
    def do_DELETE(self): self.handle_request('DELETE')

    def handle_request(self,method):
        try:
            route=urlparse(self.path);p=route.path;store=self.server.store
            if method=='GET':
                if p=='/api/status': return self.send(200,store.snapshot())
                if p=='/api/health':
                    with store.connect() as db: db.execute('SELECT 1').fetchone()
                    return self.send(200,{'ok':True,'demo':store.demo,'auth_mode':'password','api_version':2})
                if p=='/api/admin':
                    self.admin();return self.send(200,{'devices':store.all_devices(),'visitor_url':self.qr_url()})
                if p=='/api/history':
                    self.admin()
                    try: tid=int(parse_qs(route.query).get('toilet_id',['1'])[0])
                    except ValueError: raise Problem(400,'잘못된 화장실 ID')
                    return self.send(200,store.history(tid))
                if p=='/api/qr.svg':
                    import qrcode
                    import qrcode.image.svg
                    url=self.qr_url()
                    if not url: raise Problem(409,'관리자 화면에서 방문객 접속 주소를 입력하고 QR을 생성하세요')
                    img=qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage)
                    out=io.BytesIO();img.save(out)
                    return self.send(200,out.getvalue(),'image/svg+xml')
                allowed={'/':'index.html','/admin':'index.html','/app.js':'app.js','/style.css':'style.css','/map.svg':'map.svg'}
                if p in allowed:
                    f=ROOT/'web'/allowed[p]
                    types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}
                    return self.send(200,f.read_bytes(),types[f.suffix])
                raise Problem(404,'경로를 찾을 수 없습니다')
            data={} if method=='DELETE' else self.body()
            if method=='POST' and p=='/api/login':
                session=store.login(data.get('password'))
                return self.send(200,{'authenticated':True},headers=self.session_cookie(session))
            if method=='POST' and p in ('/api/events','/api/heartbeat'):
                return self.send(200,store.ingest(data,self.token(),p.endswith('heartbeat')))
            self.admin()
            if method=='POST' and p=='/api/logout':
                store.logout(self.session_token())
                return self.send(200,{'logged_out':True},headers=self.session_cookie('',True))
            if method=='PUT' and p=='/api/password':
                session=store.change_password(data.get('current_password'),data.get('new_password'))
                return self.send(200,{'changed':True},headers=self.session_cookie(session))
            if method=='POST' and p=='/api/toilets':return self.send(201,store.create(data))
            if method=='DELETE' and p.startswith('/api/toilets/'):
                try:tid=int(p.rsplit('/',1)[1])
                except ValueError:raise Problem(400,'잘못된 화장실 ID')
                return self.send(200,store.delete(tid))
            if method=='PUT' and p=='/api/visitor-url':
                url=visitor_url(data.get('url'))
                with store.connect() as db:
                    db.execute("INSERT INTO settings VALUES('visitor_url',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(url,))
                return self.send(200,{'saved':True,'url':url})
            if method=='POST' and p=='/api/devices':return self.send(201,store.register(data))
            if method=='POST' and p=='/api/demo':return self.send(200,store.simulate())
            if method=='PUT' and p.startswith('/api/toilets/'):
                try: tid=int(p.rsplit('/',1)[1])
                except ValueError: raise Problem(400,'잘못된 화장실 ID')
                return self.send(200,store.update(tid,data))
            if method=='POST' and p=='/api/reset':
                tid=integer(data.get('toilet_id'),1,2_147_483_647,'toilet_id')
                with store.connect() as db:
                    if not db.execute('UPDATE toilets SET reset_at=? WHERE id=? AND active=1',(time.time(),tid)).rowcount:
                        raise Problem(404,'화장실을 찾을 수 없습니다')
                    db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'window reset: {tid}'))
                return self.send(200,{'reset':True})
            if method=='PUT' and p=='/api/map':
                import base64
                image=data.get('image','')
                if not isinstance(image,str) or not image.startswith(('data:image/png;base64,','data:image/jpeg;base64,')):
                    raise Problem(400,'PNG 또는 JPEG 이미지만 지원합니다')
                try: raw=base64.b64decode(image.split(',',1)[1],validate=True)
                except ValueError: raise Problem(400,'이미지 인코딩 오류')
                if len(raw)>2_000_000:raise Problem(413,'이미지는 2MB 이하여야 합니다')
                if not ((image.startswith('data:image/png;') and raw.startswith(b'\x89PNG\r\n\x1a\n')) or (image.startswith('data:image/jpeg;') and raw.startswith(b'\xff\xd8\xff'))):
                    raise Problem(400,'이미지 형식이 일치하지 않습니다')
                with store.connect() as db:db.execute("INSERT INTO settings VALUES('map',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(image,))
                return self.send(200,{'saved':True})
            raise Problem(404,'경로를 찾을 수 없습니다')
        except Problem as e:self.send(e.status,{'error':e.message})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            self.send(500,{'error':'서버 오류가 발생했습니다. 서버 설정을 확인하세요'})


def make_server(host,port,store,public_url=''):
    server=ThreadingHTTPServer((host,port),App)
    server.store,server.public_url=store,public_url
    return server


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000)
    p.add_argument('--demo',action='store_true');p.add_argument('--db');args=p.parse_args()
    runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
    url=os.environ.get('PUBLIC_URL','').rstrip('/')
    if url and (urlparse(url).scheme not in ('http','https') or not urlparse(url).netloc):
        raise SystemExit('PUBLIC_URL은 실제 접속 가능한 http(s) URL이어야 합니다')
    store=Store(args.db or runtime/('demo.sqlite3' if args.demo else 'live.sqlite3'),args.demo)
    try:server=make_server(args.host,args.port,store,url)
    except OSError as error:
        raise SystemExit(f'서버를 시작하지 못했습니다 (포트 {args.port}). 이전 서버 창을 Ctrl+C로 종료한 뒤 다시 실행하세요. 오류 코드: {error.errno}')
    print(f'RestFlow listening on port {server.server_port}; mode={"DEMO" if args.demo else "LIVE"}',flush=True)
    print('관리자: /admin · 관리자 비밀번호로 로그인하세요.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
