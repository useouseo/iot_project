"""RestFlow: window-based congestion, MariaDB storage, visitor/admin HTTP API."""
import argparse
import hashlib
import hmac
import io
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import threading

import mariadb

ROOT = Path(__file__).resolve().parent
APP_BUILD = '2026-11-13-festivals-v3'

def congestion_percent(score, healthy=True):
    """Relative traffic index, not stall occupancy. 0/.8/2/4 -> 0/40/75/100."""
    if not healthy or not isinstance(score, (int, float)) or not math.isfinite(score):
        return None
    score = max(0, score)
    if score < .8:
        value = score * 50
    elif score < 2:
        value = 40 + (score - .8) * 35 / 1.2
    else:
        value = 75 + (score - 2) * 12.5
    return min(100, int(value + .5))

WINDOW = 600
OFFLINE = 120
MAX_BODY = 2_800_000
DB_CONFIG_PATH = ROOT/'db_config.json'
DB_ENV = {
    'host':'RESTFLOW_DB_HOST',
    'port':'RESTFLOW_DB_PORT',
    'user':'RESTFLOW_DB_USER',
    'password':'RESTFLOW_DB_PASSWORD',
    'database':'RESTFLOW_DB_DATABASE',
    'demo_database':'RESTFLOW_DB_DEMO_DATABASE',
}


def environment_secret(name):
    path=os.environ.get(name+'_FILE')
    if path:
        try:return Path(path).read_text(encoding='utf-8').rstrip('\r\n')
        except OSError:raise SystemExit(name+'_FILE 설정 파일을 읽지 못했습니다')
    return os.environ.get(name)


def database_name(value, field='database'):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,64}',value):
        raise ValueError(f'{field}는 영문, 숫자, 밑줄로 된 1~64자 이름이어야 합니다')
    return value


def load_db_config(path=None):
    """Load non-secret defaults from JSON and allow environment overrides."""
    path=Path(path or os.environ.get('RESTFLOW_DB_CONFIG',DB_CONFIG_PATH))
    config={}
    if path.exists():
        try:
            value=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError) as error:
            raise SystemExit(f'MariaDB 설정 파일을 읽을 수 없습니다: {error}')
        if not isinstance(value,dict):
            raise SystemExit('MariaDB 설정 파일은 JSON 객체여야 합니다')
        config.update(value)
    for key,env_name in DB_ENV.items():
        if env_name in os.environ:config[key]=os.environ[env_name]
    secret=environment_secret('RESTFLOW_DB_PASSWORD')
    if secret is not None:config['password']=secret
    missing=[key for key in ('host','user','database','demo_database') if not config.get(key)]
    if missing:
        raise SystemExit('MariaDB 설정이 없습니다. 먼저 setup_mariadb.py를 실행하세요. 누락: '+', '.join(missing))
    try:
        config['port']=int(config.get('port',3306))
        if not 1<=config['port']<=65535:raise ValueError()
        database_name(config['database']);database_name(config['demo_database'],'demo_database')
    except (TypeError,ValueError) as error:
        raise SystemExit(f'MariaDB 설정이 올바르지 않습니다: {error}')
    config['password']=str(config.get('password',''))
    return {key:config[key] for key in ('host','port','user','password','database','demo_database')}


class Database:
    """Small DB-API wrapper that commits/rolls back and always closes MariaDB handles."""
    def __init__(self,config,database):
        self.config,self.database=config,database
        self.connection=None
        self.cursors=[]

    def __enter__(self):
        params={key:self.config[key] for key in ('host','port','user','password')}
        params['database']=self.database
        self.connection=mariadb.connect(**params)
        return self

    def cursor(self):
        cursor=self.connection.cursor(dictionary=True)
        self.cursors.append(cursor)
        return cursor

    def execute(self,sql,params=()):
        cursor=self.cursor();cursor.execute(sql,params);return cursor

    def executemany(self,sql,params):
        cursor=self.cursor();cursor.executemany(sql,params);return cursor

    def __exit__(self,kind,error,traceback):
        try:
            if self.connection:
                self.connection.rollback() if error else self.connection.commit()
        finally:
            for cursor in reversed(self.cursors):
                try:cursor.close()
                except mariadb.Error:pass
            if self.connection:
                try:self.connection.close()
                except mariadb.Error:pass
        return False

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


def automatic_qr_url(value):
    value=visitor_url(value)
    host=urlparse(value).hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost','.local')):
        raise Problem(409,'외부 접속 실행(start_public.bat)으로 실행한 관리자 화면에서 QR을 생성하세요')
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        address=None
    if address is not None and not address.is_global:
        raise Problem(409,'현재 주소는 외부에서 접속할 수 없습니다. start_public.bat로 실행하세요')
    return value


def qr_svg(url):
    import qrcode
    import qrcode.image.svg
    img=qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage)
    out=io.BytesIO();img.save(out)
    return out.getvalue()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),200_000).hex()


def password_value(value):
    if not isinstance(value,str) or not 4<=len(value)<=128:
        raise Problem(400,'비밀번호는 4~128자로 입력하세요')
    return value


def geo_coordinate(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise Problem(400, '유효한 위도·경도를 입력하세요')
    return float(value)

_route_slots = threading.BoundedSemaphore(4)
_route_lock = threading.Lock()
_route_next = 0.0

def pedestrian_route(store, data):
    key = environment_secret('RESTFLOW_TMAP_ROUTE_KEY')
    if not key:
        raise Problem(503, '도보 길찾기 API 설정이 필요합니다')
    lat = geo_coordinate(data.get('latitude'), -90, 90)
    lng = geo_coordinate(data.get('longitude'), -180, 180)
    tid = integer(data.get('toilet_id'), 1, 2147483647, '화장실 ID')
    snapshot=store.snapshot()
    if snapshot.get('settings',{}).get('map_mode','outdoor')=='indoor':
        raise Problem(409, '실내 모드에서는 도보 길찾기를 사용하지 않습니다')
    target = next((t for t in snapshot['toilets'] if t['id'] == tid), None)
    if not target:
        raise Problem(404, '화장실을 찾을 수 없습니다')
    if target['latitude'] is None or target['longitude'] is None:
        raise Problem(409, '화장실 입구 위치가 아직 등록되지 않았습니다')
    body = dict(startX=lng, startY=lat, endX=target['longitude'], endY=target['latitude'],
                reqCoordType='WGS84GEO', resCoordType='WGS84GEO', startName='출발지', endName='화장실 입구')
    if not _route_slots.acquire(blocking=False):
        raise Problem(429, '길찾기 요청이 많습니다. 잠시 후 다시 시도하세요')
    global _route_next
    try:
        with _route_lock:
            if time.monotonic() < _route_next:
                raise Problem(429, '길찾기는 잠시 후 다시 시도하세요')
            _route_next = time.monotonic() + 1
        request = Request('https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1',
                          data=json.dumps(body).encode(), headers={'Content-Type':'application/json', 'appKey':key})
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read(2000000))
        features = result.get('features', [])
        lines = [f['geometry']['coordinates'] for f in features if f.get('geometry', {}).get('type') == 'LineString']
        properties = next((f.get('properties', {}) for f in features if 'totalDistance' in f.get('properties', {})), {})
        if not lines:
            raise Problem(502, '이 구간의 도보 경로를 찾지 못했습니다')
        return dict(lines=lines, distance=properties.get('totalDistance'), seconds=properties.get('totalTime'))
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
        raise Problem(502, '길찾기 서비스에 연결하지 못했습니다. 잠시 후 다시 시도하세요')
    finally:
        _route_slots.release()


class Store:
    TABLES=('events','sessions','admin_sessions','devices','settings','audit','admin_credentials','toilets','festivals')
    def __init__(self, config, demo=False, reset_schema=False):
        self.config,self.demo=config.copy(),demo
        self.database=config['demo_database'] if demo else config['database']
        with self.connect() as db:
            if reset_schema:
                for table in self.TABLES:db.execute(f'DROP TABLE IF EXISTS `{table}`')
            statements=('''CREATE TABLE IF NOT EXISTS festivals(
              id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(80) NOT NULL,
              mode VARCHAR(8) NOT NULL, public_id VARCHAR(64) UNIQUE NOT NULL,
              map LONGTEXT NULL)
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS toilets(
              id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(40) NOT NULL,
              stalls INT NOT NULL, x INT NOT NULL, y INT NOT NULL,
              reset_at DOUBLE NOT NULL DEFAULT 0, active TINYINT(1) NOT NULL DEFAULT 1)
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS devices(
              id VARCHAR(64) PRIMARY KEY, toilet_id INT UNIQUE NOT NULL,
              token_hash CHAR(64) NOT NULL, last_seen DOUBLE NULL,
              quality VARCHAR(16) NOT NULL DEFAULT 'unknown',
              CONSTRAINT fk_devices_toilet FOREIGN KEY(toilet_id) REFERENCES toilets(id))
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS sessions(
              device_id VARCHAR(64) NOT NULL, boot_id VARCHAR(64) NOT NULL,
              last_seq INT NOT NULL, PRIMARY KEY(device_id,boot_id),
              CONSTRAINT fk_sessions_device FOREIGN KEY(device_id) REFERENCES devices(id))
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS events(
              id BIGINT PRIMARY KEY AUTO_INCREMENT, device_id VARCHAR(64) NOT NULL,
              boot_id VARCHAR(64) NOT NULL, seq INT NOT NULL,
              direction VARCHAR(8) NOT NULL, occurred_at DOUBLE NOT NULL,
              received_at DOUBLE NOT NULL,
              CONSTRAINT fk_events_device FOREIGN KEY(device_id) REFERENCES devices(id),
              UNIQUE KEY uq_event(device_id,boot_id,seq), KEY event_time(occurred_at))
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS settings(
              `key` VARCHAR(64) PRIMARY KEY, `value` LONGTEXT NOT NULL)
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS audit(
              id BIGINT PRIMARY KEY AUTO_INCREMENT, at DOUBLE NOT NULL, action VARCHAR(255) NOT NULL)
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS admin_credentials(
              id TINYINT PRIMARY KEY, salt CHAR(32) NOT NULL, password_hash CHAR(64) NOT NULL)
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
            '''CREATE TABLE IF NOT EXISTS admin_sessions(
              token_hash CHAR(64) PRIMARY KEY, expires_at DOUBLE NOT NULL)
              ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''')
            for statement in statements:db.execute(statement)
            db.execute("ALTER TABLE festivals ADD COLUMN IF NOT EXISTS active TINYINT(1) NOT NULL DEFAULT 1")
            # One-time, additive migration: preserve all legacy facilities, devices and settings.
            if not db.execute('SELECT 1 FROM festivals WHERE id=1').fetchone():
                legacy={r['key']:r['value'] for r in db.execute("SELECT * FROM settings WHERE `key` IN ('map','map_mode')")}
                mode=legacy.get('map_mode','outdoor')
                if mode not in ('indoor','outdoor'):mode='outdoor'
                db.execute('INSERT IGNORE INTO festivals(id,name,mode,public_id,map) VALUES(1,?,?,?,?)',('기존 축제',mode,secrets.token_urlsafe(12),legacy.get('map')))
            db.execute("ALTER TABLE toilets ADD COLUMN IF NOT EXISTS festival_id INT NOT NULL DEFAULT 1")
            db.execute("ALTER TABLE toilets ADD INDEX IF NOT EXISTS idx_toilets_festival (festival_id)")
            if not db.execute("SELECT 1 FROM information_schema.TABLE_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=DATABASE() AND TABLE_NAME='toilets' AND CONSTRAINT_NAME='fk_toilets_festival'").fetchone():
                db.execute('ALTER TABLE toilets ADD CONSTRAINT fk_toilets_festival FOREIGN KEY(festival_id) REFERENCES festivals(id)')
            db.execute("ALTER TABLE toilets ADD COLUMN IF NOT EXISTS latitude DOUBLE NULL")
            db.execute("ALTER TABLE toilets ADD COLUMN IF NOT EXISTS longitude DOUBLE NULL")
            if not db.execute('SELECT 1 FROM admin_credentials WHERE id=1').fetchone():
                salt=secrets.token_hex(16)
                db.execute('INSERT INTO admin_credentials VALUES(1,?,?)',(salt,password_hash('1234',salt)))
            if not db.execute('SELECT count(*) AS n FROM toilets').fetchone()['n']:
                db.executemany('INSERT INTO toilets(id,name,stalls,x,y) VALUES(?,?,?,?,?)', [
                    (1,'화장실 A',4,22,28), (2,'화장실 B',4,78,48)])
                if demo:
                    db.execute('INSERT INTO toilets(id,name,stalls,x,y) VALUES(3,?,?,?,?)',('화장실 C',3,28,78))
        if demo:
            first=self.list_festivals()[0]['id']
            if not self.all_devices(first):
                for t in self.snapshot(festival_id=first)['toilets']:
                    self.register({'id':f'demo-{t["id"]}', 'toilet_id':t['id']},first)
                self.simulate(first)

    def connect(self):
        return Database(self.config,self.database)

    def all_devices(self,festival_id=1):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT d.id,d.toilet_id,d.last_seen,d.quality FROM devices d JOIN toilets t ON t.id=d.toilet_id WHERE t.active=1 AND t.festival_id=?',(festival_id,))]

    def login(self, password):
        password=password_value(password)
        with self.connect() as db:
            row=db.execute('SELECT * FROM admin_credentials WHERE id=1 FOR UPDATE').fetchone()
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
            row=db.execute('SELECT * FROM admin_credentials WHERE id=1 FOR UPDATE').fetchone()
            if not hmac.compare_digest(row['password_hash'],password_hash(current,row['salt'])):
                raise Problem(401,'현재 비밀번호가 올바르지 않습니다')
            salt=secrets.token_hex(16)
            db.execute('UPDATE admin_credentials SET salt=?,password_hash=? WHERE id=1',(salt,password_hash(new,salt)))
            db.execute('DELETE FROM admin_sessions')
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),'admin password changed'))
            return self.new_session(db)

    def create(self,data,festival_id=1):
        self.festival(festival_id)
        name=text_value(data.get('name'),40,'화장실 이름')
        stalls=integer(data.get('stalls'),1,100,'운영 칸 수')
        x=integer(data.get('x',50),3,97,'지도 x');y=integer(data.get('y',50),3,97,'지도 y')
        with self.connect() as db:
            tid=db.execute('INSERT INTO toilets(name,stalls,x,y,festival_id) VALUES(?,?,?,?,?)',(name,stalls,x,y,festival_id)).lastrowid
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'toilet created: {tid}'))
        if self.demo:self.register({'id':f'demo-{tid}','toilet_id':tid},festival_id)
        return {'id':tid,'created':True}

    def delete(self,tid,festival_id=1):
        with self.connect() as db:
            if not db.execute('UPDATE toilets SET active=0 WHERE id=? AND active=1 AND festival_id=?',(tid,festival_id)).rowcount:
                raise Problem(404,'화장실을 찾을 수 없습니다')
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'toilet removed: {tid}'))
        return {'deleted':True}

    def register(self, data,festival_id=1):
        device = text_value(data.get('id'),64,'장치 ID')
        if not device.isascii() or not all(c.isalnum() or c in '-_' for c in device):
            raise Problem(400, '장치 ID는 영문·숫자·하이픈·밑줄을 사용하세요')
        toilet = integer(data.get('toilet_id'),1,2_147_483_647,'화장실 ID')
        token = secrets.token_urlsafe(32)
        try:
            with self.connect() as db:
                if not db.execute('SELECT 1 FROM toilets WHERE id=? AND active=1 AND festival_id=?',(toilet,festival_id)).fetchone():
                    raise Problem(404,'화장실을 찾을 수 없습니다')
                db.execute('INSERT INTO devices(id,toilet_id,token_hash) VALUES(?,?,?)',(device,toilet,digest(token)))
                db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'device registered: {device}'))
        except mariadb.IntegrityError:
            raise Problem(409,'화장실이 없거나 이미 등록된 장치/화장실입니다')
        return {'id':device,'token':token}

    def authenticate_device(self, device, token, db, lock=False):
        suffix=' FOR UPDATE' if lock else ''
        row = db.execute('SELECT d.* FROM devices d JOIN toilets t ON t.id=d.toilet_id JOIN festivals f ON f.id=t.festival_id WHERE d.id=? AND t.active=1 AND f.active=1'+suffix,(device,)).fetchone()
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
            self.authenticate_device(device,token,db,True)
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
            db.execute('INSERT INTO sessions VALUES(?,?,?) ON DUPLICATE KEY UPDATE last_seq=VALUES(last_seq)',(device,boot,seq))
            db.execute('UPDATE devices SET last_seen=?,quality=? WHERE id=?',(now,quality,device))
            return {'accepted':True,'duplicate':False}

    def snapshot(self, now=None,festival_id=1):
        festival=self.festival(festival_id)
        now = time.time() if now is None else now
        with self.connect() as db:
            rows = db.execute('SELECT t.*,d.id device_id,d.last_seen,d.quality FROM toilets t LEFT JOIN devices d ON d.toilet_id=t.id WHERE t.active=1 AND t.festival_id=? ORDER BY t.id',(festival_id,)).fetchall()
            result=[]
            for row in rows:
                t=dict(row)
                counts = db.execute('''SELECT direction,count(*) n FROM events WHERE device_id=?
                  AND occurred_at>=? AND occurred_at<=? GROUP BY direction''',
                  (t['device_id'],max(now-WINDOW,t['reset_at']),now)).fetchall()
                counts={r['direction']:r['n'] for r in counts}
                prev=db.execute("SELECT count(*) AS n FROM events WHERE device_id=? AND direction='in' AND occurred_at>=? AND occurred_at<?",(t['device_id'],max(now-2*WINDOW,t['reset_at']),now-WINDOW)).fetchone()['n']
                ins,outs=counts.get('in',0),counts.get('out',0)
                score=(.6*ins+.4*max(0,ins-outs)+.2*max(0,ins-prev))/t['stalls']
                online = t['last_seen'] is not None and now-t['last_seen'] <= OFFLINE
                healthy=online and t['quality']=='good'
                level = ('busy' if score>=2 else 'moderate' if score>=.8 else 'quiet') if healthy else 'unknown'
                t.update(level=level,online=online,congestion_percent=congestion_percent(score,healthy),score=round(score,2),entries=ins,exits=outs,previous_entries=prev)
                result.append(t)
            settings={r['key']:r['value'] for r in db.execute("SELECT * FROM settings WHERE `key` IN ('map','visitor_url','map_mode')")}
        settings['map_mode']=festival['mode']
        settings.pop('map',None)
        if festival['map']:settings['map']=festival['map']
        festival={k:v for k,v in festival.items() if k!='map'}
        return {'festival':festival,'toilets':result,'updated_at':now,'window_seconds':WINDOW,'demo':self.demo,'settings':settings}

    def festival(self,festival_id=1):
        festival_id=integer(festival_id,1,2147483647,'축제 ID')
        with self.connect() as db:
            row=db.execute('SELECT * FROM festivals WHERE id=?',(festival_id,)).fetchone()
        if not row:raise Problem(404,'축제를 찾을 수 없습니다')
        if not row['active']:raise Problem(410,'운영이 종료된 축제입니다')
        return dict(row)

    def festival_by_public_id(self,public_id):
        with self.connect() as db:
            row=db.execute('SELECT * FROM festivals WHERE public_id=?',(public_id,)).fetchone()
        if not row:raise Problem(404,'축제를 찾을 수 없습니다. QR 주소를 확인하세요')
        if not row['active']:raise Problem(410,'운영이 종료된 축제입니다')
        return dict(row)

    def list_festivals(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT id,name,mode,public_id FROM festivals WHERE active=1 ORDER BY id')]

    def delete_festival(self,festival_id,confirm_name):
        festival_id=integer(festival_id,1,2147483647,'축제 ID')
        with self.connect() as db:
            # Lock active rows in a consistent order so concurrent deletions cannot remove the last festival.
            rows=db.execute('SELECT id,name FROM festivals WHERE active=1 ORDER BY id FOR UPDATE').fetchall()
            target=next((r for r in rows if r['id']==festival_id),None)
            if not target:raise Problem(404,'삭제할 축제를 찾을 수 없습니다')
            if not isinstance(confirm_name,str) or confirm_name.strip()!=target['name']:
                raise Problem(400,'삭제할 축제 이름을 정확히 입력하세요')
            if len(rows)<=1:raise Problem(409,'마지막 축제는 삭제할 수 없습니다. 새 축제를 먼저 추가하세요')
            db.execute('UPDATE festivals SET active=0 WHERE id=?',(festival_id,))
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(time.time(),f'festival archived: {festival_id}'))
            return {'deleted':True,'next_festival_id':next(r['id'] for r in rows if r['id']!=festival_id)}

    def create_festival(self,data):
        name=text_value(data.get('name'),80,'축제 이름')
        mode=data.get('mode')
        if mode not in ('indoor','outdoor'):raise Problem(400,'실내 또는 야외를 선택하세요')
        with self.connect() as db:
            fid=db.execute('INSERT INTO festivals(name,mode,public_id) VALUES(?,?,?)',(name,mode,secrets.token_urlsafe(12))).lastrowid
        return {k:v for k,v in self.festival(fid).items() if k!='map'}

    def map_mode(self,festival_id=1):
        return self.festival(festival_id)['mode']

    def set_map_mode(self,mode,festival_id=1):
        raise Problem(409,'운영 유형은 축제 생성 시 정합니다. 다른 유형은 새 축제로 추가하세요')

    def history(self,toilet_id,now=None,festival_id=1):
        self.require_toilet(toilet_id,festival_id)
        now=time.time() if now is None else now
        end=int(now//600)*600
        with self.connect() as db:
            device=db.execute('SELECT id FROM devices WHERE toilet_id=?',(toilet_id,)).fetchone()
            rows=db.execute('''SELECT FLOOR(occurred_at/600)*600 bucket,direction,count(*) n FROM events
              WHERE device_id=? AND occurred_at>=? AND occurred_at<? GROUP BY bucket,direction''',
              (device['id'] if device else '',end-11*600,end+600)).fetchall()
        lookup={(r['bucket'],r['direction']):r['n'] for r in rows}
        return [{'at':b,'in':lookup.get((b,'in'),0),'out':lookup.get((b,'out'),0)} for b in range(end-11*600,end+1,600)]

    def update(self,tid,data,festival_id=1):
        self.require_toilet(tid,festival_id)
        name=text_value(data.get('name'),40,'화장실 이름')
        stalls=integer(data.get('stalls'),1,100,'운영 칸 수')
        x=integer(data.get('x'),3,97,'지도 x'); y=integer(data.get('y'),3,97,'지도 y')
        with self.connect() as db:
            if not db.execute('UPDATE toilets SET name=?,stalls=?,x=?,y=? WHERE id=? AND active=1 AND festival_id=?',(name,stalls,x,y,tid,festival_id)).rowcount:
                raise Problem(404,'화장실을 찾을 수 없습니다')
        return {'saved':True}

    def update_info(self,tid,data,festival_id=1):
        name=text_value(data.get('name'),40,'화장실 이름')
        stalls=integer(data.get('stalls'),1,100,'운영 칸 수')
        self.require_toilet(tid,festival_id)
        with self.connect() as db:
            db.execute('UPDATE toilets SET name=?,stalls=? WHERE id=? AND festival_id=? AND active=1',(name,stalls,tid,festival_id))
        return {'saved':True}

    def update_layout_position(self,tid,data,festival_id=1):
        x=integer(data.get('x'),3,97,'지도 X');y=integer(data.get('y'),3,97,'지도 Y')
        self.require_toilet(tid,festival_id)
        with self.connect() as db:
            db.execute('UPDATE toilets SET x=?,y=? WHERE id=? AND festival_id=? AND active=1',(x,y,tid,festival_id))
        return {'saved':True}

    def require_toilet(self,tid,festival_id=1):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM toilets WHERE id=? AND festival_id=? AND active=1',(tid,festival_id)).fetchone():
                raise Problem(404,'이 축제의 화장실을 찾을 수 없습니다')

    def simulate(self,festival_id=1):
        if not self.demo:
            raise Problem(403,'시뮬레이션은 --demo에서만 사용할 수 있습니다')
        now=time.time()
        with self.connect() as db:
            for d in db.execute('SELECT d.* FROM devices d JOIN toilets t ON t.id=d.toilet_id WHERE t.active=1 AND t.festival_id=?',(festival_id,)).fetchall():
                boot='demo-'+secrets.token_hex(8)
                n={1:2,2:5,3:12}.get(d['toilet_id'],4)
                # Synthetic histories are labelled as demo in every snapshot.
                for i in range(n):
                    db.execute('INSERT INTO events(device_id,boot_id,seq,direction,occurred_at,received_at) VALUES(?,?,?,?,?,?)',
                               (d['id'],boot,i+1,'in',now-(n-i)*12,now))
                db.execute("UPDATE devices SET last_seen=?,quality='good' WHERE id=?",(now,d['id']))
        return {'simulated':True}


class FestivalScope:
    SCOPED={'snapshot','all_devices','map_mode','set_map_mode','create','delete','register','history','update','simulate','require_toilet','update_info','update_layout_position'}
    def __init__(self,store,festival_id):
        self.root,self.festival_id=store,festival_id
        self.festival_info=store.festival(festival_id)
    def __getattr__(self,name):
        method=getattr(self.root,name)
        if name in self.SCOPED:return lambda *args,**kwargs:method(*args,festival_id=self.festival_id,**kwargs)
        return method


def festival_url(base,festival):
    if not base:return ''
    return urlparse(base)._replace(path='/f/'+festival['public_id'],query='',fragment='').geturl()


class App(BaseHTTPRequestHandler):
    server_version='RestFlow/3.0'
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
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: blob: https://*.sk.com https://*.tmap.co.kr https://*.sktmap.com; style-src 'self' 'unsafe-inline'; script-src 'self' https://*.sk.com https://*.tmap.co.kr https://*.sktmap.com; connect-src 'self' https://*.sk.com https://*.tmap.co.kr https://*.sktmap.com; worker-src blob:; upgrade-insecure-requests; frame-ancestors 'none'; base-uri 'none'")
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

    def qr_url(self,store):
        with store.connect() as db:
            row=db.execute("SELECT value FROM settings WHERE `key`='visitor_url'").fetchone()
        return festival_url(row['value'] if row else self.server.public_url,store.festival_info)

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
            route=urlparse(self.path);p=route.path;root_store=self.server.store
            query=parse_qs(route.query)
            assets={'/app.js':'app.js','/outdoor.js':'outdoor.js','/style.css':'style.css','/outdoor.css':'outdoor.css','/map.svg':'map.svg','/pretendard.woff2':'pretendard.woff2'}
            if method=='GET' and p in assets:
                file=ROOT/'web'/assets[p]
                types={'.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.woff2':'font/woff2'}
                return self.send(200,file.read_bytes(),types[file.suffix])
            if method=='GET' and p=='/api/version':return self.send(200,{'build':APP_BUILD,'files':{name:hashlib.sha256((ROOT/'web'/name).read_bytes()).hexdigest()[:12] for name in ('app.js','outdoor.js','outdoor.css')}})
            if method=='GET' and p=='/api/health':
                with root_store.connect() as db:db.execute('SELECT 1').fetchone()
                return self.send(200,{'ok':True,'demo':root_store.demo,'auth_mode':'password','api_version':2})
            if p=='/api/festivals' and method in ('GET','POST'):
                self.admin()
                return self.send(200,root_store.list_festivals()) if method=='GET' else self.send(201,root_store.create_festival(self.body()))
            if method=='DELETE' and re.fullmatch(r'/api/festivals/[0-9]+',p):
                self.admin();data=self.body()
                return self.send(200,root_store.delete_festival(int(p.rsplit('/',1)[1]),data.get('confirm_name')))
            if method=='POST' and p=='/api/login':
                session=root_store.login(self.body().get('password'))
                return self.send(200,{'authenticated':True},headers=self.session_cookie(session))
            if method=='POST' and p in ('/api/events','/api/heartbeat'):
                return self.send(200,root_store.ingest(self.body(),self.token(),p.endswith('heartbeat')))
            if method=='POST' and p=='/api/logout':
                self.admin();root_store.logout(self.session_token())
                return self.send(200,{'logged_out':True},headers=self.session_cookie('',True))
            if p.startswith('/f/'):
                festival=root_store.festival_by_public_id(p[3:])
                fid=festival['id'];p='/'
            else:
                try:fid=int(query.get('festival_id',[str(root_store.list_festivals()[0]['id']) if p=='/admin' else '1'])[0])
                except ValueError:raise Problem(400,'잘못된 축제 ID')
            store=FestivalScope(root_store,fid)
            if method=='GET':
                if p=='/api/map-config': return self.send(200,{'map_key':environment_secret('RESTFLOW_TMAP_MAP_KEY') or '', 'routing':bool(environment_secret('RESTFLOW_TMAP_ROUTE_KEY')), 'map_mode':store.map_mode()})
                if p=='/api/status': return self.send(200,store.snapshot())
                if p=='/api/admin':
                    self.admin();return self.send(200,{'devices':store.all_devices(),'visitor_url':self.qr_url(store),'automatic_visitor_url':festival_url(self.server.public_url,store.festival_info)})
                if p=='/api/history':
                    self.admin()
                    try: tid=int(parse_qs(route.query).get('toilet_id',['1'])[0])
                    except ValueError: raise Problem(400,'잘못된 화장실 ID')
                    return self.send(200,store.history(tid))
                if p=='/api/qr.svg':
                    url=self.qr_url(store)
                    if not url:raise Problem(409,'start_public.bat 실행 후 관리자 화면에서 QR을 생성하세요')
                    return self.send(200,qr_svg(url),'image/svg+xml')
                allowed={'/':'index.html','/admin':'index.html'}
                if p in allowed:
                    f=ROOT/'web'/allowed[p]
                    types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.woff2':'font/woff2'}
                    body=f.read_bytes()
                    if f.name=='index.html':
                        mode=store.map_mode()
                        key=(environment_secret('RESTFLOW_TMAP_MAP_KEY') or '') if mode=='outdoor' else ''
                        from html import escape
                        info=store.festival_info
                        body=body.replace(b'<body>',f'<body class="mode-{mode}" data-festival-id="{fid}" data-festival-name="{escape(info["name"],quote=True)}" data-festival-public-id="{escape(info["public_id"],quote=True)}">'.encode())
                        sdk=('<script src="https://apis.openapi.sk.com/tmap/jsv2?version=1&amp;appKey='+quote(key,safe='')+'"></script>') if key else ''
                        body=body.replace(b'<!--TMAP_SDK-->',sdk.encode('utf-8'))
                        body=body.replace(b'?v=responsive9',('?v='+APP_BUILD).encode()).replace(b'/outdoor.js"',('/outdoor.js?v='+APP_BUILD+'"').encode()).replace(b'/outdoor.css"',('/outdoor.css?v='+APP_BUILD+'"').encode())
                    return self.send(200,body,types[f.suffix])
                raise Problem(404,'경로를 찾을 수 없습니다')
            data={} if method=='DELETE' else self.body()
            if method=='POST' and p=='/api/route':return self.send(200,pedestrian_route(store,data))
            self.admin()
            if method=='PUT' and p=='/api/map-mode':return self.send(200,store.set_map_mode(data.get('map_mode')))
            if method=='POST' and p=='/api/qr':
                url=festival_url(automatic_qr_url(self.server.public_url or data.get('url')),store.festival_info)
                return self.send(200,{'url':url,'svg':qr_svg(url).decode('utf-8')})
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
                    db.execute("INSERT INTO settings VALUES('visitor_url',?) ON DUPLICATE KEY UPDATE `value`=VALUES(`value`)",(url,))
                return self.send(200,{'saved':True,'url':url})
            if method=='POST' and p=='/api/devices':return self.send(201,store.register(data))
            if method=='POST' and p=='/api/demo':return self.send(200,store.simulate())
            if method=='PUT' and re.fullmatch(r'/api/coordinates/[0-9]+',p):
                tid=int(p.rsplit('/',1)[1])
                lat=geo_coordinate(data.get('latitude'),-90,90)
                lng=geo_coordinate(data.get('longitude'),-180,180)
                with store.connect() as db:
                    if not db.execute('SELECT 1 FROM toilets WHERE id=? AND active=1 AND festival_id=?',(tid,fid)).fetchone():
                        raise Problem(404,'화장실을 찾을 수 없습니다')
                    db.execute('UPDATE toilets SET latitude=?,longitude=? WHERE id=? AND festival_id=?',(lat,lng,tid,fid))
                return self.send(200,{'saved':True})
            if method=='PUT' and re.fullmatch(r'/api/(layout-position|toilet-info)/[0-9]+',p):
                tid=int(p.rsplit('/',1)[1])
                method_fn=store.update_layout_position if p.startswith('/api/layout-position/') else store.update_info
                return self.send(200,method_fn(tid,data))
            if method=='PUT' and p.startswith('/api/toilets/'):


                try: tid=int(p.rsplit('/',1)[1])
                except ValueError: raise Problem(400,'잘못된 화장실 ID')
                return self.send(200,store.update(tid,data))
            if method=='POST' and p=='/api/reset':
                tid=integer(data.get('toilet_id'),1,2_147_483_647,'toilet_id')
                with store.connect() as db:
                    if not db.execute('UPDATE toilets SET reset_at=? WHERE id=? AND active=1 AND festival_id=?',(time.time(),tid,fid)).rowcount:
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
                with store.connect() as db:db.execute('UPDATE festivals SET map=? WHERE id=?',(image,fid))
                return self.send(200,{'saved':True})
            raise Problem(404,'경로를 찾을 수 없습니다')
        except Problem as e:
            if e.status==410 and method=='GET' and (urlparse(self.path).path=='/' or urlparse(self.path).path.startswith('/f/')):
                return self.send(410,'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>축제 운영 종료 · RestFlow</title><link rel="stylesheet" href="/outdoor.css"><main class="festival-ended"><h1>운영이 종료된 축제입니다</h1><p>이 QR의 화장실 안내는 종료되었습니다. 현장 안내를 확인해 주세요.</p></main></html>','text/html; charset=utf-8')
            if e.status==410 and method=='GET' and urlparse(self.path).path=='/admin':
                return self.send(303,'',headers={'Location':'/admin'})
            self.send(e.status,{'error':e.message})
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:
            self.send(500,{'error':'서버 오류가 발생했습니다. 서버 설정을 확인하세요'})


def make_server(host,port,store,public_url=''):
    server=ThreadingHTTPServer((host,port),App)
    server.store,server.public_url=store,public_url
    return server


def bootstrap_admin(store):
    password=environment_secret('RESTFLOW_INITIAL_ADMIN_PASSWORD')
    if password is None:return
    if not 8<=len(password)<=128 or password=='1234':
        raise SystemExit('초기 관리자 비밀번호는 8~128자로 설정하세요')
    with store.connect() as db:
        row=db.execute('SELECT * FROM admin_credentials WHERE id=1').fetchone()
    if hmac.compare_digest(row['password_hash'],password_hash('1234',row['salt'])):
        store.logout(store.change_password('1234',password))


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8000)
    p.add_argument('--demo',action='store_true');p.add_argument('--db-config',default=os.environ.get('RESTFLOW_DB_CONFIG',str(DB_CONFIG_PATH)));args=p.parse_args()
    url=os.environ.get('PUBLIC_URL',os.environ.get('RENDER_EXTERNAL_URL','')).rstrip('/')
    if url and (urlparse(url).scheme not in ('http','https') or not urlparse(url).netloc):
        raise SystemExit('PUBLIC_URL은 실제 접속 가능한 http(s) URL이어야 합니다')
    config=load_db_config(args.db_config)
    try:store=Store(config,args.demo)
    except mariadb.Error as error:
        raise SystemExit(f'MariaDB에 연결하지 못했습니다: {error}. MariaDB 서비스와 db_config.json을 확인하세요.')
    bootstrap_admin(store)
    try:server=make_server(args.host,args.port,store,url)
    except OSError as error:
        raise SystemExit(f'서버를 시작하지 못했습니다 (포트 {args.port}). 이전 서버 창을 Ctrl+C로 종료한 뒤 다시 실행하세요. 오류 코드: {error.errno}')
    print(f'RestFlow listening on port {server.server_port}; mode={"DEMO" if args.demo else "LIVE"}',flush=True)
    print('관리자: /admin · 관리자 비밀번호로 로그인하세요.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
