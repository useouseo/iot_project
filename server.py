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


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


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
            return [dict(r) for r in db.execute('SELECT id,toilet_id,last_seen,quality FROM devices')]

    def register(self, data):
        device = text_value(data.get('id'),64,'장치 ID')
        if not device.isascii() or not all(c.isalnum() or c in '-_' for c in device):
            raise Problem(400, '장치 ID는 영문·숫자·하이픈·밑줄을 사용하세요')
        toilet = integer(data.get('toilet_id'),1,9999,'화장실 ID')
        token = secrets.token_urlsafe(32)
        try:
            with self.connect() as db:
                db.execute('INSERT INTO devices(id,toilet_id,token_hash) VALUES(?,?,?)',(device,toilet,digest(token)))
                db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'device registered: {device}'))
        except sqlite3.IntegrityError:
            raise Problem(409,'화장실이 없거나 이미 등록된 장치/화장실입니다')
        return {'id':device,'token':token}

    def authenticate_device(self, device, token, db):
        row = db.execute('SELECT * FROM devices WHERE id=?',(device,)).fetchone()
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
            rows = db.execute('SELECT t.*,d.id device_id,d.last_seen,d.quality FROM toilets t LEFT JOIN devices d ON d.toilet_id=t.id ORDER BY t.id').fetchall()
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
            settings={r['key']:r['value'] for r in db.execute('SELECT * FROM settings')}
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
            if not db.execute('UPDATE toilets SET name=?,stalls=?,x=?,y=? WHERE id=?',(name,stalls,x,y,tid)).rowcount:
                raise Problem(404,'화장실을 찾을 수 없습니다')
        return {'saved':True}

    def simulate(self):
        if not self.demo:
            raise Problem(403,'시뮬레이션은 --demo에서만 사용할 수 있습니다')
        now=time.time()
        with self.connect() as db:
            for d in db.execute('SELECT * FROM devices').fetchall():
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

    def send(self,status,body,kind='application/json; charset=utf-8'):
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
        self.end_headers();self.wfile.write(body)

    def token(self):
        auth=self.headers.get('Authorization','')
        return auth[7:] if auth.startswith('Bearer ') else ''

    def admin(self):
        if not hmac.compare_digest(self.token(),self.server.admin_token):
            raise Problem(401,'관리자 토큰을 확인하세요')

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

    def handle_request(self,method):
        try:
            route=urlparse(self.path);p=route.path;store=self.server.store
            if method=='GET':
                if p=='/api/status': return self.send(200,store.snapshot())
                if p=='/api/health':
                    with store.connect() as db: db.execute('SELECT 1').fetchone()
                    return self.send(200,{'ok':True,'demo':store.demo})
                if p=='/api/admin':
                    self.admin();return self.send(200,{'devices':store.all_devices()})
                if p=='/api/history':
                    self.admin()
                    try: tid=int(parse_qs(route.query).get('toilet_id',['1'])[0])
                    except ValueError: raise Problem(400,'잘못된 화장실 ID')
                    return self.send(200,store.history(tid))
                if p=='/api/qr.svg':
                    import qrcode
                    import qrcode.image.svg
                    url=self.server.public_url
                    if not url: raise Problem(409,'서버 PUBLIC_URL 설정 후 QR을 생성하세요')
                    img=qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage)
                    out=io.BytesIO();img.save(out)
                    return self.send(200,out.getvalue(),'image/svg+xml')
                allowed={'/':'index.html','/admin':'index.html','/app.js':'app.js','/style.css':'style.css','/map.svg':'map.svg'}
                if p in allowed:
                    f=ROOT/'web'/allowed[p]
                    types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml'}
                    return self.send(200,f.read_bytes(),types[f.suffix])
                raise Problem(404,'경로를 찾을 수 없습니다')
            data=self.body()
            if method=='POST' and p in ('/api/events','/api/heartbeat'):
                return self.send(200,store.ingest(data,self.token(),p.endswith('heartbeat')))
            self.admin()
            if method=='POST' and p=='/api/devices':return self.send(201,store.register(data))
            if method=='POST' and p=='/api/demo':return self.send(200,store.simulate())
            if method=='PUT' and p.startswith('/api/toilets/'):
                try: tid=int(p.rsplit('/',1)[1])
                except ValueError: raise Problem(400,'잘못된 화장실 ID')
                return self.send(200,store.update(tid,data))
            if method=='POST' and p=='/api/reset':
                tid=integer(data.get('toilet_id'),1,9999,'toilet_id')
                with store.connect() as db:
                    if not db.execute('UPDATE toilets SET reset_at=? WHERE id=?',(time.time(),tid)).rowcount:
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


def make_server(host,port,store,token,public_url=''):
    server=ThreadingHTTPServer((host,port),App)
    server.store,server.admin_token,server.public_url=store,token,public_url
    return server


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000)
    p.add_argument('--demo',action='store_true');p.add_argument('--db');args=p.parse_args()
    runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
    token=os.environ.get('ADMIN_TOKEN')
    if not token:
        f=runtime/'admin-token'
        if not f.exists():
            fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as out:out.write(secrets.token_urlsafe(32))
        token=f.read_text().strip()
    if len(token)<16:raise SystemExit('ADMIN_TOKEN은 16자 이상이어야 합니다')
    url=os.environ.get('PUBLIC_URL','').rstrip('/')
    if url and (urlparse(url).scheme not in ('http','https') or not urlparse(url).netloc):
        raise SystemExit('PUBLIC_URL은 실제 접속 가능한 http(s) URL이어야 합니다')
    store=Store(args.db or runtime/('demo.sqlite3' if args.demo else 'live.sqlite3'),args.demo)
    server=make_server(args.host,args.port,store,token,url)
    print(f'RestFlow listening on port {server.server_port}; mode={"DEMO" if args.demo else "LIVE"}',flush=True)
    print('Admin token: ADMIN_TOKEN 환경변수 또는 .runtime/admin-token 파일을 사용하세요 (값은 출력하지 않습니다).',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
