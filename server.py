import argparse
import functools
import io
import ipaddress
import json
import socket
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen
import math
import os
import secrets
import pymysql
import re

from database import Database, load_config
from telemetry import Problem, Telemetry, digest, init_telemetry
from pathlib import Path

import qrcode
from flask import Flask, Response, abort, g, jsonify, request, send_file, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 8192

DEMO_MODE = False
INSTALLER_KEY = os.environ.get('RESTFLOW_INSTALLER_KEY') or secrets.token_urlsafe(18)


def db():
    if 'db' not in g:
        g.db = Database(app.config['DB_CONFIG'], app.config['DB_NAME'], close_on_exit=False)
    return g.db


@app.teardown_appcontext
def close_db(_error):
    connection = g.pop('db', None)
    if connection:
        connection.close()


def init_db(config=None, demo=False):
    global DEMO_MODE
    DEMO_MODE = demo
    config = config or load_config()
    name = config['demo_database' if demo else 'database']
    app.config.update(DB_CONFIG=config, DB_NAME=name, TELEMETRY=Telemetry(config, name))
    with app.app_context(), db() as connection:
        schema = """
        CREATE TABLE IF NOT EXISTS places (
          id VARCHAR(128) PRIMARY KEY, name VARCHAR(100) NOT NULL, address VARCHAR(300) NOT NULL,
          lat DOUBLE NOT NULL, lon DOUBLE NOT NULL, manager_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS zones (
          id BIGINT PRIMARY KEY AUTO_INCREMENT, place_id VARCHAR(128) NOT NULL REFERENCES places(id),
          name VARCHAR(100) NOT NULL, device VARCHAR(100) NOT NULL UNIQUE,
          total INTEGER NOT NULL CHECK(total BETWEEN 1 AND 99),
          open INTEGER NOT NULL CHECK(open BETWEEN 0 AND total),
          closed INTEGER NOT NULL DEFAULT 0, reason VARCHAR(100) NOT NULL DEFAULT '',
          `accessible` INTEGER NOT NULL DEFAULT 0, UNIQUE(place_id, name)
        );
        CREATE TABLE IF NOT EXISTS site_access (
          place_id VARCHAR(128) PRIMARY KEY REFERENCES places(id), claim_hash TEXT, password_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS module_access (
          zone_id BIGINT PRIMARY KEY REFERENCES zones(id), slug VARCHAR(128) NOT NULL UNIQUE,
          claim_hash TEXT, password_hash TEXT, kind VARCHAR(32)
        );
        """

        options = ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin'
        for statement in schema.split(';'):
            if statement.strip():
                connection.execute(statement + options)
        init_telemetry(connection)
        connection.execute("""CREATE TABLE IF NOT EXISTS sensor_links (
            toilet_id INT PRIMARY KEY REFERENCES toilets(id),
            place_id VARCHAR(128) NOT NULL,
            zone_id BIGINT NULL,
            scope_id BIGINT AS (COALESCE(zone_id, 0)) PERSISTENT,
            UNIQUE(place_id, scope_id),
            FOREIGN KEY(place_id) REFERENCES places(id) ON DELETE CASCADE,
            FOREIGN KEY(zone_id) REFERENCES zones(id) ON DELETE CASCADE
        )""" + options)


def telemetry():
    return app.config['TELEMETRY']


@app.errorhandler(Problem)
def telemetry_error(error):
    return jsonify(error=error.message), error.status


def body():
    data = request.get_json()
    if not isinstance(data, dict):
        abort(400, '입력 형식을 확인해 주세요.')
    return data


def value(data, key, limit=100, optional=False):
    raw = data.get(key, '')
    if not isinstance(raw, str) or len(raw.strip()) > limit or (not raw.strip() and not optional):
        abort(400, f'{key} 입력값을 확인해 주세요.')
    return raw.strip()


def number(data, key, low, high):
    raw = data.get(key)
    if type(raw) not in (int, float) or not math.isfinite(raw) or not low <= raw <= high:
        abort(400, f'{key} 범위를 확인해 주세요.')
    return raw


def whole(data, key, low, high):
    raw = number(data, key, low, high)
    if type(raw) is not int:
        abort(400, f'{key}에는 정수를 입력해 주세요.')
    return raw


def credential():
    return request.headers.get('Authorization', '').removeprefix('Bearer ')


def installer(view):
    @functools.wraps(view)
    def authorized(*args, **kwargs):
        if not secrets.compare_digest(credential().encode(), INSTALLER_KEY.encode()):
            abort(401, '설치팀 접속 코드를 확인해 주세요.')
        return view(*args, **kwargs)
    return authorized


def place_row(place_id):
    row = db().execute('SELECT * FROM places WHERE id=?', (place_id,)).fetchone()
    if row is None:
        abort(404, '장소를 찾을 수 없습니다.')
    return row


def manager(place_id):
    row = place_row(place_id)
    code = credential()
    if not row['manager_hash'] or not code or not check_password_hash(row['manager_hash'], code):
        abort(401, '이 장소의 관리자 코드를 확인해 주세요.')


def place_detail(row, include_devices=False, legacy_only=False):
    place = {key: row[key] for key in ('id', 'name', 'address', 'lat', 'lon')}
    columns = 'id,name,total,open,closed,reason,`accessible`,(SELECT kind FROM module_access WHERE zone_id=zones.id) AS kind'
    if include_devices:
        columns += ',device'
    scope = ' AND id NOT IN (SELECT zone_id FROM module_access)' if legacy_only else ''
    place['zones'] = [dict(zone) for zone in db().execute(
        f'SELECT {columns} FROM zones WHERE place_id=?{scope} ORDER BY id', (row['id'],)
    )]
    signals = sensor_status(row['id'], private=include_devices)
    place['sensor'] = signals.get(None)
    for zone in place['zones']:
        zone['sensor'] = signals.get(zone['id'])
    return place


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(404)
@app.errorhandler(409)
@app.errorhandler(502)
@app.errorhandler(503)
def api_error(error):
    return jsonify(error=error.description), error.code


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.get('/')
@app.get('/manage/<place_id>')
@app.get('/module/<place_id>')
def web(place_id=None):
    if request.path == '/':
        require_local()
        return redesign()
    page = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
    sdk = '<script src="/api/setup/map-sdk.js"></script>' if request.path == '/' and tmap_key() else ''
    return Response(page.replace('<!--TMAP_SDK-->', sdk), mimetype='text/html')


@app.get('/ui.js')
@app.get('/legacy.js')
def script():
    return send_from_directory(ROOT / 'web', 'legacy.js' if request.path == '/legacy.js' else 'ui.js')


@app.get('/api/places')
def public_places():
    rows = db().execute('SELECT * FROM places WHERE manager_hash IS NOT NULL OR EXISTS (SELECT 1 FROM site_access sa WHERE sa.place_id=places.id AND sa.password_hash IS NOT NULL) OR EXISTS (SELECT 1 FROM zones JOIN module_access ON module_access.zone_id=zones.id WHERE zones.place_id=places.id) ORDER BY name,id')
    return jsonify(places=[place_detail(row) for row in rows])


@app.get('/api/install')
@installer
def install_list():
    return jsonify(places=[place_detail(row, True) for row in db().execute('SELECT * FROM places ORDER BY name,id')])


@app.post('/api/install')
@installer
def add_place():
    data = body()
    fields = (secrets.token_urlsafe(9), value(data, 'name'), value(data, 'address'),
              number(data, 'lat', -90, 90), number(data, 'lon', -180, 180))
    with db() as connection:
        connection.execute('INSERT INTO places(id,name,address,lat,lon) VALUES(?,?,?,?,?)', fields)
    return jsonify(id=fields[0]), 201


@app.post('/api/install/<place_id>/zones')
@installer
def add_zone(place_id):
    place_row(place_id)
    data = body()
    total = whole(data, 'total', 1, 99)
    try:
        with db() as connection:
            connection.execute('INSERT INTO zones(place_id,name,device,total,open,`accessible`) VALUES(?,?,?,?,?,?)',
                (place_id, value(data, 'name'), value(data, 'device', 64), total, total, int(data.get('accessible') is True)))
    except pymysql.err.IntegrityError:
        abort(409, '이미 사용 중인 장치 ID 또는 구역명입니다.')
    return jsonify(ok=True), 201


@app.post('/api/install/<place_id>/handoff')
@installer
def handoff(place_id):
    place_row(place_id)
    if not db().execute('SELECT 1 FROM zones WHERE place_id=?', (place_id,)).fetchone():
        abort(409, '구역을 하나 이상 등록해 주세요.')
    code = secrets.token_urlsafe(12)
    with db() as connection:
        connection.execute('UPDATE places SET manager_hash=? WHERE id=?', (generate_password_hash(code), place_id))
    return jsonify(code=code, path=f'/manage/{place_id}')


@app.get('/manage/<place_id>/qr.png')
def qr(place_id):
    place_row(place_id)
    base = os.environ.get('RESTFLOW_PUBLIC_URL', request.host_url).rstrip('/')
    image = qrcode.make(f'{base}/manage/{place_id}')
    output = io.BytesIO()
    image.save(output, format='PNG')
    output.seek(0)
    return send_file(output, mimetype='image/png')


@app.get('/api/manage/<place_id>')
def detail(place_id):
    manager(place_id)
    return jsonify(place_detail(place_row(place_id), True, legacy_only=True))


@app.put('/api/manage/<place_id>/zones/<int:zone_id>')
def update_zone(place_id, zone_id):
    manager(place_id)
    data = body()
    zone = db().execute('SELECT total FROM zones WHERE id=? AND place_id=? AND id NOT IN (SELECT zone_id FROM module_access)', (zone_id, place_id)).fetchone()
    if zone is None:
        abort(404, '구역을 찾을 수 없습니다.')
    count = whole(data, 'open', 0, zone['total'])
    closed = data.get('closed') is True or count == 0
    reason = value(data, 'reason', optional=True) if closed else ''
    with db() as connection:
        connection.execute('UPDATE zones SET open=?,closed=?,reason=? WHERE id=? AND place_id=?',
                           (count, int(closed), reason, zone_id, place_id))
    return jsonify(ok=True)


KINDS = {
    'women':'여성 화장실', 'men':'남성 화장실', 'shared':'공용 화장실',
    'women-accessible':'여성 장애인 화장실', 'men-accessible':'남성 장애인 화장실',
    'shared-accessible':'공용 장애인 화장실',
}


def require_local():
    if not ipaddress.ip_address(request.remote_addr).is_loopback:
        abort(403, '설치 화면은 서버 PC에서 열어 주세요.')
    if request.host.split(':')[0] not in ('localhost', '127.0.0.1'):
        abort(403, '서버 PC에서 http://127.0.0.1:8080 으로 열어 주세요.')


def tmap_key():
    key = os.environ.get('RESTFLOW_TMAP_MAP_KEY', '').strip()
    if key:
        return key
    path = ROOT / 'mobile' / '.env.local'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            name, sep, val = line.partition('=')
            if sep and name.strip() in ('EXPO_PUBLIC_TMAP_APP_KEY', 'EXPO_PUBLIC_TMAP_MAP_KEY') and val.strip():
                return val.strip().strip('"').strip("'")
    return ''


def manager_base():
    address = os.environ.get('RESTFLOW_PUBLIC_URL', '').rstrip('/')
    if address:
        return address
    # Use the address of the LAN interface, since the installer runs on loopback.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        try:
            route.connect(('192.0.2.1', 80))
            host = route.getsockname()[0]
        except OSError:
            host = '127.0.0.1'
    return f'http://{host}:{request.environ.get("SERVER_PORT", 8080)}'


@app.get('/api/setup')
def setup_info():
    require_local()
    rows = db().execute('SELECT * FROM places ORDER BY name,id')
    places = [place_detail(row, True) for row in rows]
    modules = [dict(row) for row in db().execute(
        """SELECT ma.slug,z.id,z.name,z.device,z.place_id FROM module_access ma
        JOIN zones z ON z.id=ma.zone_id ORDER BY z.id""")]
    return jsonify(places=places, modules=modules, map_key=tmap_key(), manager_base=manager_base())


@app.get('/api/setup/map-sdk.js')
def setup_map_sdk():
    key = tmap_key()
    if not key:
        abort(400, 'TMAP 지도 키가 설정되지 않았습니다.')
    upstream = 'https://apis.openapi.sk.com/tmap/jsv2?' + urlencode(dict(version=1, appKey=key))
    try:
        with urlopen(Request(upstream, headers={'Referer': request.host_url}), timeout=12) as script:
            payload = script.read(6_000_001)
    except OSError:
        abort(400, '서버에서도 TMAP 지도 SDK에 접속하지 못했습니다.')
    if len(payload) > 6_000_000 or b'Tmapv2' not in payload:
        abort(400, 'TMAP 지도 SDK 응답을 확인해 주세요.')
    return Response(payload, mimetype='text/javascript')


@app.post('/api/setup/address')
def setup_address():
    require_local()
    data = body()
    lat, lon = number(data, 'lat', -90, 90), number(data, 'lon', -180, 180)
    key = tmap_key()
    if not key:
        abort(400, 'TMAP 지도 키가 설정되지 않았습니다.')
    query = urlencode(dict(version=1, lat=lat, lon=lon, coordType='WGS84GEO', addressType='A10'))
    upstream = 'https://apis.openapi.sk.com/tmap/geo/reversegeocoding?' + query
    try:
        with urlopen(Request(upstream, headers={'appKey':key}), timeout=8) as response:
            info = json.load(response).get('addressInfo') or {}
    except (OSError, ValueError):
        abort(400, 'TMAP 주소를 조회하지 못했습니다.')
    if info.get('roadName') and info.get('buildingIndex'):
        address = ' '.join(str(info[k]).strip() for k in ('city_do','gu_gun','eup_myun','roadName','buildingIndex') if info.get(k))
    else:
        candidates = [part.strip() for part in str(info.get('fullAddress') or '').split(',') if part.strip()]
        address = next((part for part in reversed(candidates) if any(char.isdigit() for char in part)), '') or (candidates[-1] if candidates else '')
    if not address:
        abort(404, '선택한 위치의 주소를 찾지 못했습니다.')
    return jsonify(address=address)


@app.post('/api/walking-route')
def walking_route():
    payload = request.get_json()
    if not isinstance(payload, dict) or not isinstance(payload.get('origin'), dict):
        abort(400, '출발 위치를 확인해 주세요.')
    origin = payload['origin']
    try:
        lat, lon = float(origin['lat']), float(origin['lon'])
    except (KeyError, TypeError, ValueError):
        abort(400, '출발 위치를 확인해 주세요.')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        abort(400, '출발 위치를 확인해 주세요.')
    place_id = payload.get('place_id')
    if not isinstance(place_id, str):
        abort(400, '도착 장소를 선택해 주세요.')
    destination = db().execute('SELECT name,lat,lon FROM places WHERE id=?', (place_id,)).fetchone()
    if not destination:
        abort(404, '등록된 장소를 찾을 수 없습니다.')
    key = os.environ.get('RESTFLOW_TMAP_ROUTE_KEY', '').strip() or tmap_key()
    if not key:
        abort(503, 'TMAP 경로 서비스 키를 설정해 주세요.')
    body = json.dumps({
        'startX': lon, 'startY': lat, 'endX': destination['lon'], 'endY': destination['lat'],
        'startName': '현재 위치', 'endName': destination['name'],
        'reqCoordType': 'WGS84GEO', 'resCoordType': 'WGS84GEO', 'searchOption': '10',
    }).encode()
    upstream = Request('https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1',
                       data=body, headers={'appKey': key, 'Content-Type': 'application/json'})
    try:
        with urlopen(upstream, timeout=12) as response:
            features = json.load(response).get('features', [])
    except (OSError, ValueError):
        abort(502, 'TMAP 보행 경로를 불러오지 못했습니다.')
    lines = [f['geometry']['coordinates'] for f in features
             if f.get('geometry', {}).get('type') == 'LineString' and len(f['geometry'].get('coordinates', [])) > 1]
    summary = next((f['properties'] for f in features if 'totalTime' in (f.get('properties') or {})
                    and 'totalDistance' in f['properties']), None)
    if not lines or summary is None:
        abort(404, '선택한 장소까지의 도보 경로를 찾지 못했습니다.')
    return jsonify(lines=lines, seconds=summary['totalTime'], meters=summary['totalDistance'])


@app.get('/api/setup/search')
def setup_search():
    require_local()
    keyword = request.args.get('q', '').strip()[:80]
    if not keyword or not tmap_key():
        abort(400, '검색어나 TMAP 지도 설정을 확인해 주세요.')
    query = urlencode(dict(version=1, searchKeyword=keyword, count=8, reqCoordType='WGS84GEO', resCoordType='WGS84GEO'))
    try:
        with urlopen(Request('https://apis.openapi.sk.com/tmap/pois?' + query, headers={'appKey': tmap_key()}), timeout=8) as data:
            rows = json.load(data).get('searchPoiInfo', {}).get('pois', {}).get('poi', [])
    except (OSError, ValueError):
        abort(400, 'TMAP 장소 검색을 완료하지 못했습니다. 지도 키의 장소 검색 권한을 확인해 주세요.')
    results = []
    for row in rows:
        try:
            lat, lon = float(row.get('pnsLat') or row.get('frontLat') or row.get('noorLat')), float(row.get('pnsLon') or row.get('frontLon') or row.get('noorLon'))
        except (ValueError, TypeError):
            continue
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            results.append(dict(name=row.get('name', keyword), lat=lat, lon=lon))
    return jsonify(results=results)


@app.post('/api/setup/register')
def register_module():
    require_local()
    data = body()
    kind = value(data, 'kind', 24)
    if kind not in KINDS:
        abort(400, '구역 유형을 선택해 주세요.')
    total = whole(data, 'total', 1, 99)
    device = value(data, 'device', 64)
    keys = {}
    if 'fan_enabled' in data:
        if type(data['fan_enabled']) is not bool:
            abort(400, '환기 제어 사용 여부를 확인해 주세요.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', device):
            abort(400, '장치 ID는 영문·숫자·하이픈·밑줄만 입력해 주세요.')
        keys = {'device_id':device,'sensor_token':secrets.token_urlsafe(32)}
        if data['fan_enabled']:
            keys['fan_token'] = secrets.token_urlsafe(32)
    place_id = value(data, 'place_id', 64, optional=True)
    slug, claim = secrets.token_urlsafe(12), secrets.token_urlsafe(10)
    digest = generate_password_hash(claim)
    name = value(data, 'zone_name', optional=True) or KINDS[kind]
    try:
        with db() as connection:
            if place_id:
                place_row(place_id)
            else:
                place_id = secrets.token_urlsafe(9)
                connection.execute('INSERT INTO places(id,name,address,lat,lon) VALUES(?,?,?,?,?)',
                    (place_id, value(data, 'name'), value(data, 'address'),
                     number(data, 'lat', -90, 90), number(data, 'lon', -180, 180)))
            zone = connection.execute('INSERT INTO zones(place_id,name,device,total,open,`accessible`) VALUES(?,?,?,?,?,?)',
                (place_id,name,device,total,total,int(kind.endswith('-accessible') or data.get('accessible') is True)))
            zone_id = zone.lastrowid
            connection.execute('INSERT INTO module_access(zone_id,slug,claim_hash,kind) VALUES(?,?,?,?)',
                (zone_id,slug,digest,kind))
            if keys:
                provision_equipment(connection,place_id,zone_id,device,name,keys['sensor_token'],keys.get('fan_token'))
    except pymysql.err.IntegrityError:
        abort(409, '이미 등록된 장치 ID 또는 해당 장소의 구역명입니다.')
    return jsonify(place_id=place_id,zone_id=zone_id,slug=slug,claim=claim,url=f'{manager_base()}/module/{slug}',**keys), 201


def module_row(slug):
    row = db().execute("""SELECT ma.*, z.name,z.device,z.total,z.open,z.closed,z.reason,p.name AS place
        FROM module_access ma JOIN zones z ON ma.zone_id=z.id JOIN places p ON p.id=z.place_id
        WHERE ma.slug=?""", (slug,)).fetchone()
    if row is None:
        abort(404, '등록된 모듈을 찾을 수 없습니다.')
    return row


@app.post('/api/setup/modules/<slug>/claim')
def reissue_claim(slug):
    require_local()
    row = module_row(slug)
    claim = secrets.token_urlsafe(10)
    with db() as connection:
        updated = connection.execute('UPDATE module_access SET claim_hash=? WHERE zone_id=? AND password_hash IS NULL',
                                     (generate_password_hash(claim), row['zone_id']))
        if not updated.rowcount:
            abort(409, '담당자가 이미 비밀번호를 설정했습니다.')
    return jsonify(claim=claim,url=f'{manager_base()}/module/{slug}')


@app.get('/module/<slug>/qr.png')
def module_qr(slug):
    require_local()
    module_row(slug)
    image = qrcode.make(f'{manager_base()}/module/{slug}')
    output = io.BytesIO()
    image.save(output, format='PNG')
    output.seek(0)
    return send_file(output, mimetype='image/png')


@app.get('/api/module/<slug>/status')
def module_status(slug):
    row = module_row(slug)
    return jsonify(name=row['name'], place=row['place'], claimed=bool(row['password_hash']))


def new_password(data):
    password = data.get('password')
    if not isinstance(password, str) or not 8 <= len(password) <= 128 or not password.strip():
        abort(400, '비밀번호를 8자 이상 입력해 주세요.')
    return password


def authenticate_module(row):
    supplied = unquote(credential())
    if not row['password_hash'] or not 8 <= len(supplied) <= 128 or not check_password_hash(row['password_hash'], supplied):
        abort(401, '이 모듈의 비밀번호를 확인해 주세요.')


@app.post('/api/module/<slug>/claim')
def claim_module(slug):
    row = module_row(slug)
    data = body()
    password = new_password(data)
    if not row['claim_hash'] or not check_password_hash(row['claim_hash'], value(data, 'claim', 64)):
        abort(401, '인계 코드를 확인해 주세요.')
    with db() as connection:
        updated = connection.execute("""UPDATE module_access SET password_hash=?,claim_hash=NULL
            WHERE zone_id=? AND claim_hash=? AND password_hash IS NULL""",
            (generate_password_hash(password), row['zone_id'], row['claim_hash']))
        if not updated.rowcount:
            abort(409, '이미 비밀번호가 설정되었거나 인계 코드가 바뀌었습니다.')
    return jsonify(ok=True)


@app.get('/api/module/<slug>')
def module_details(slug):
    row = module_row(slug)
    authenticate_module(row)
    return jsonify({k:row[k] for k in ('place','name','device','total','open','closed','reason')})


@app.put('/api/module/<slug>')
def module_update(slug):
    row = module_row(slug)
    authenticate_module(row)
    data = body()
    count = whole(data, 'open', 0, row['total'])
    closed = count == 0 or data.get('closed') is True
    reason = value(data, 'reason', optional=True) if closed else ''
    with db() as connection:
        result = connection.execute("""UPDATE zones SET open=?,closed=?,reason=? WHERE id=?
            AND EXISTS (SELECT 1 FROM module_access WHERE zone_id=zones.id AND password_hash=?)""",
            (count,int(closed),reason,row['zone_id'],row['password_hash']))
        if not result.rowcount:
            abort(401, '비밀번호가 변경되었습니다. 다시 접속해 주세요.')
    return jsonify(ok=True)


@app.put('/api/module/<slug>/password')
def module_password(slug):
    row = module_row(slug)
    authenticate_module(row)
    password = new_password(body())
    with db() as connection:
        updated = connection.execute('UPDATE module_access SET password_hash=? WHERE zone_id=? AND password_hash=?',
                                     (generate_password_hash(password),row['zone_id'],row['password_hash']))
        if not updated.rowcount:
            abort(401, '다시 접속해 주세요.')
    return jsonify(ok=True)


def redesign():
    page = (ROOT / 'web' / 'redesign' / 'index.html').read_text(encoding='utf-8')
    sdk = '<script src="/api/setup/map-sdk.js"></script>' if request.path in ('/', '/user') and tmap_key() else ''
    if DEMO_MODE:
        sdk = '<meta name="restflow-demo" content="true">' + sdk
    return Response(page.replace('</head>', sdk + '</head>'), mimetype='text/html')


@app.get('/assets/<path:asset>')
def frontend_asset(asset):
    return send_from_directory(ROOT / 'web' / 'redesign' / 'assets', asset)


@app.get('/favicon.png')
def frontend_icon():
    return send_from_directory(ROOT / 'web' / 'redesign', 'favicon.png')


@app.get('/user')
def user_page():
    return redesign()


@app.get('/places/<pid>')
@app.get('/facility/<pid>')
def place_page(pid):
    if request.path.startswith('/places/'):
        require_local()
    place_row(pid)
    return redesign()


@app.get('/places.js')
def places_script():
    return send_from_directory(ROOT / 'web', 'places.js')


@app.post('/api/setup/places')
def create_site_place():
    require_local()
    data = body()
    pid = secrets.token_urlsafe(9)
    with db() as connection:
        connection.execute('INSERT INTO places(id,name,address,lat,lon) VALUES(?,?,?,?,?)',
            (pid, value(data,'name'), value(data,'address'), number(data,'lat',-90,90), number(data,'lon',-180,180)))
    return jsonify(id=pid), 201


@app.delete('/api/setup/places/<pid>/zones/<int:zid>')
def remove_site_zone(pid, zid):
    require_local()
    with db() as connection:
        if not connection.execute('SELECT 1 FROM zones WHERE id=? AND place_id=?',(zid,pid)).fetchone():
            abort(404, '이 장소에 해당 구역이 없습니다.')
        connection.execute('DELETE FROM module_access WHERE zone_id=?',(zid,))
        connection.execute('DELETE FROM zones WHERE id=? AND place_id=?',(zid,pid))
    return jsonify(ok=True)


def site_access(pid):
    place_row(pid)
    return db().execute('SELECT * FROM site_access WHERE place_id=?',(pid,)).fetchone()


@app.post('/api/setup/places/<pid>/claim')
def issue_site_claim(pid):
    require_local()
    place_row(pid)
    claim = secrets.token_urlsafe(10)
    with db() as connection:
        connection.execute('SELECT id FROM places WHERE id=? FOR UPDATE', (pid,))
        current = connection.execute('SELECT password_hash FROM site_access WHERE place_id=? FOR UPDATE', (pid,)).fetchone()
        if current and current['password_hash']:
            abort(409, '이 장소의 관리자 비밀번호가 이미 설정되었습니다.')
        connection.execute("""INSERT INTO site_access(place_id,claim_hash) VALUES(?,?)
            ON DUPLICATE KEY UPDATE claim_hash=VALUES(claim_hash)""", (pid,generate_password_hash(claim)))
    return jsonify(claim=claim,url=f'{manager_base()}/facility/{pid}')


@app.get('/facility/<pid>/qr.png')
def site_qr(pid):
    require_local()
    place_row(pid)
    code = qrcode.QRCode()
    code.add_data(f'{manager_base()}/facility/{pid}')
    image = code.make_image(fill_color='#355940', back_color='#ffffff')
    data = io.BytesIO()
    image.save(data,format='PNG')
    data.seek(0)
    return send_file(data,mimetype='image/png')


@app.get('/api/facility/<pid>/status')
def facility_status(pid):
    row = place_row(pid)
    access = site_access(pid)
    return jsonify(name=row['name'], address=row['address'], claimed=bool(access and access['password_hash']))


@app.post('/api/facility/<pid>/claim')
def facility_claim(pid):
    access = site_access(pid)
    data = body()
    password = new_password(data)
    claim = value(data,'claim',64)
    if not access or not access['claim_hash'] or not check_password_hash(access['claim_hash'], claim):
        abort(401, '인계 코드를 확인해 주세요.')
    with db() as connection:
        change = connection.execute("""UPDATE site_access SET password_hash=?,claim_hash=NULL
            WHERE place_id=? AND claim_hash=? AND password_hash IS NULL""",
            (generate_password_hash(password),pid,access['claim_hash']))
        if not change.rowcount:
            abort(409, '인계 코드가 변경되었거나 이미 사용되었습니다.')
    return jsonify(ok=True)


def facility_auth(pid):
    access = site_access(pid)
    if not access:
        abort(401, '먼저 인계 코드로 비밀번호를 설정해 주세요.')
    authenticate_module(access)
    return access['password_hash']


@app.get('/api/facility/<pid>')
def facility_get(pid):
    facility_auth(pid)
    return jsonify(place_detail(place_row(pid), True))


@app.put('/api/facility/<pid>/zones/<int:zid>')
def facility_update(pid,zid):
    digest = facility_auth(pid)
    data = body()
    row = db().execute('SELECT total FROM zones WHERE id=? AND place_id=?',(zid,pid)).fetchone()
    if not row:
        abort(404, '이 장소에 해당 구역이 없습니다.')
    count = whole(data,'open',0,row['total'])
    closed = count == 0 or data.get('closed') is True
    reason = value(data,'reason',optional=True) if closed else ''
    with db() as connection:
        change = connection.execute("""UPDATE zones SET open=?,closed=?,reason=? WHERE id=? AND place_id=?
            AND EXISTS (SELECT 1 FROM site_access WHERE place_id=? AND password_hash=?)""",
            (count,int(closed),reason,zid,pid,pid,digest))
        if not change.rowcount:
            abort(409, '구역 또는 접근 권한이 변경됐습니다. 다시 열어 주세요.')
    return jsonify(ok=True)


@app.put('/api/facility/<pid>/password')
def facility_password(pid):
    digest = facility_auth(pid)
    password = new_password(body())
    with db() as connection:
        change = connection.execute('UPDATE site_access SET password_hash=? WHERE place_id=? AND password_hash=?',
                                    (generate_password_hash(password),pid,digest))
        if not change.rowcount:
            abort(409, '비밀번호가 변경됐습니다. 다시 로그인해 주세요.')
    return jsonify(ok=True)


@app.delete('/api/setup/places/<pid>')
def remove_place(pid):
    require_local()
    place_row(pid)
    with db() as connection:
        connection.execute('DELETE FROM module_access WHERE zone_id IN (SELECT id FROM zones WHERE place_id=?)',(pid,))
        connection.execute('DELETE FROM zones WHERE place_id=?',(pid,))
        connection.execute('DELETE FROM site_access WHERE place_id=?',(pid,))
        connection.execute('DELETE FROM places WHERE id=?',(pid,))
    return jsonify(ok=True)


@app.put('/api/facility/<pid>/zones')
def facility_update_batch(pid):
    digest = facility_auth(pid)
    updates = body().get('zones')
    if not isinstance(updates,list) or not updates or len(updates)>200:
        abort(400,'변경할 구역을 확인해 주세요.')
    with db() as connection:
        current = connection.execute('SELECT password_hash FROM site_access WHERE place_id=? FOR UPDATE', (pid,)).fetchone()
        if not current or current['password_hash'] != digest:
            abort(401,'비밀번호가 변경됐습니다. 다시 로그인해 주세요.')
        for item in updates:
            if not isinstance(item,dict):
                abort(400,'구역 형식을 확인해 주세요.')
            zid=whole(item,'id',1,2**53-1)
            zone=connection.execute('SELECT total FROM zones WHERE id=? AND place_id=?',(zid,pid)).fetchone()
            if not zone:
                abort(404,'이 장소에 해당 구역이 없습니다.')
            count=whole(item,'open',0,zone['total'])
            closed=count==0 or item.get('closed') is True
            reason=value(item,'reason',optional=True) if closed else ''
            connection.execute('UPDATE zones SET open=?,closed=?,reason=? WHERE id=? AND place_id=?',
                               (count,int(closed),reason,zid,pid))
    return jsonify(ok=True)


def sensor_status(pid, private=False):
    links = db().execute('SELECT zone_id,toilet_id FROM sensor_links WHERE place_id=?', (pid,))
    result = {}
    for link in links:
        try:
            status = telemetry().control_status(link['toilet_id'])
        except Problem as error:
            if error.status == 404:
                continue
            raise
        healthy = status['online'] and status['quality'] == 'good'
        state = {'quiet':'free', 'moderate':'normal', 'busy':'busy'}[status['level']]
        public = {'state': 'closed' if not status['operating'] else state if healthy else 'unknown',
                  'online': status['online'], 'entries': status['entries'] if healthy else None}
        result[link['zone_id']] = {**status, **public} if private else public
    return result


def provision_equipment(connection, pid, zid, device, name, sensor_key, fan_key):
    identity = connection.execute('INSERT INTO toilets(name) VALUES(?)', (name[:100],)).lastrowid
    connection.execute('INSERT INTO control_profiles(toilet_id) VALUES(?)', (identity,))
    connection.execute('INSERT INTO sensor_links(toilet_id,place_id,zone_id) VALUES(?,?,?)', (identity,pid,zid))
    connection.execute('INSERT INTO devices(id,toilet_id,token_hash,fan_token_hash) VALUES(?,?,?,?)',
                       (device,identity,digest(sensor_key),digest(fan_key) if fan_key else ""))


@app.post('/api/setup/places/<pid>/equipment')
def setup_equipment(pid):
    require_local()
    data = body()
    zid = data.get('zone_id')
    if zid is not None:
        zid = whole(data, 'zone_id', 1, 2**53-1)
    device = value(data, 'device_id', 64)
    if not re.fullmatch(r'[A-Za-z0-9_-]+', device):
        abort(400, '장치 ID는 영문·숫자·하이픈·밑줄만 입력해 주세요.')
    fan_enabled = data.get('fan_enabled', True)
    if type(fan_enabled) is not bool:
        abort(400, '환기 제어 사용 여부를 확인해 주세요.')
    sensor_key, fan_key = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    try:
        with db() as connection:
            place = connection.execute('SELECT name FROM places WHERE id=? FOR UPDATE', (pid,)).fetchone()
            if not place:
                abort(404, '장소를 찾을 수 없습니다.')
            name = place['name']
            if zid is not None:
                zone = connection.execute('SELECT name FROM zones WHERE id=? AND place_id=? FOR UPDATE', (zid,pid)).fetchone()
                if not zone:
                    abort(404, '구역을 찾을 수 없습니다.')
                name = zone['name']
            linked = connection.execute("""SELECT l.toilet_id,d.id,d.fan_token_hash FROM sensor_links l
                 JOIN devices d ON d.toilet_id=l.toilet_id WHERE l.place_id=? AND l.zone_id <=> ? FOR UPDATE""",
                 (pid,zid)).fetchone()
            if linked:
                if data.get('enable_fan') is True:
                    if linked['id'] != device or linked['fan_token_hash']:
                        abort(409, '환기를 추가할 수 있는 모듈을 선택해 주세요.')
                    connection.execute('UPDATE devices SET fan_token_hash=? WHERE toilet_id=?',
                                       (digest(fan_key),linked['toilet_id']))
                    return jsonify(device_id=device,fan_token=fan_key)
                if data.get('reissue') is False:
                    abort(409, '이미 연결된 범위입니다. 장비 목록에서 키를 재발급해 주세요.')
                if linked['id'] != device:
                    abort(409, '이미 연결된 장치 ID로 키를 재발급해 주세요.')
                if not linked['fan_token_hash']:
                    fan_key = None
                connection.execute("""UPDATE devices SET token_hash=?,fan_token_hash=?,last_seen=NULL,quality='unknown'
                    WHERE toilet_id=?""", (digest(sensor_key),digest(fan_key) if fan_key else '',linked['toilet_id']))
                connection.execute('DELETE FROM fan_status WHERE device_id=?', (device,))
                connection.execute("UPDATE occupancy_state SET confidence='unknown',reason='장치 키 재발급' WHERE toilet_id=?", (linked['toilet_id'],))
            else:
                if data.get('reissue') is True or data.get('enable_fan') is True:
                    abort(404, '재발급할 장비가 없습니다.')
                fan_key = fan_key if fan_enabled else None
                provision_equipment(connection,pid,zid,device,name,sensor_key,fan_key)
    except pymysql.err.IntegrityError:
        abort(409, '이미 사용 중인 장치 ID입니다.')
    return jsonify(device_id=device,sensor_token=sensor_key,**({"fan_token":fan_key} if fan_key else {}))


@app.get('/api/facility/<pid>/equipment')
def facility_equipment(pid):
    facility_auth(pid)
    return jsonify(equipment=[{'zone_id': zone, **status} for zone, status in sensor_status(pid, private=True).items()])


@app.put('/api/facility/<pid>/equipment/settings')
def facility_equipment_settings(pid):
    password_hash = facility_auth(pid)
    data = body()
    zid = None if data.get('zone_id') is None else whole(data, 'zone_id', 1, 2**53-1)
    mode = data.get('mode')
    if mode not in ('auto','manual'):
        abort(400, '자동 또는 수동 모드를 선택해 주세요.')
    with db() as connection:
        access = connection.execute('SELECT password_hash FROM site_access WHERE place_id=? FOR UPDATE', (pid,)).fetchone()
        if not access or access['password_hash'] != password_hash:
            abort(401, '관리자 비밀번호가 변경되었습니다.')
        link = connection.execute('SELECT l.toilet_id,d.fan_token_hash FROM sensor_links l JOIN devices d ON d.toilet_id=l.toilet_id WHERE l.place_id=? AND l.zone_id <=> ? FOR UPDATE',
                                  (pid,zid)).fetchone()
        if not link:
            abort(404, '연결된 장비가 없습니다.')
        if not link['fan_token_hash']:
            abort(409, '환기 미사용 모듈입니다.')
        identity = link['toilet_id']
        if mode == 'manual':
            percent = whole(data, 'manual_percent', 0, 100)
            connection.execute("UPDATE control_profiles SET control_mode='manual',manual_percent=? WHERE toilet_id=?",
                               (percent,identity))
        else:
            target = round(number(data, 'target_humidity', 1, 99), 2)
            idle_saving = data.get('idle_saving')
            if type(idle_saving) is not bool:
                abort(400, '무인 자동 절전 설정을 확인해 주세요.')
            connection.execute("""UPDATE control_profiles SET enabled=1,control_mode='auto',
                humidity_medium=?,humidity_high=?,idle_saving=? WHERE toilet_id=?""",
                (target,min(100,target+10),int(idle_saving),identity))
    return jsonify({'zone_id':zid, **telemetry().control_status(identity)})


@app.post('/api/facility/<pid>/equipment/reset')
def facility_equipment_reset(pid):
    facility_auth(pid)
    data = body()
    if data.get('confirmed_empty') is not True:
        abort(400, '현장에서 비어 있는지 확인해 주세요.')
    zid = data.get('zone_id')
    if zid is not None:
        zid = whole(data, 'zone_id', 1, 2**53-1)
    link = db().execute('SELECT toilet_id FROM sensor_links WHERE place_id=? AND zone_id <=> ?', (pid,zid)).fetchone()
    if not link:
        abort(404, '연결된 장비가 없습니다.')
    return jsonify(telemetry().reset_occupancy(link['toilet_id']))


@app.post('/api/events')
@app.post('/api/heartbeat')
def device_event():
    return jsonify(telemetry().ingest(body(), credential(), heartbeat=request.path == '/api/heartbeat'))


@app.post('/api/environment')
def device_environment():
    return jsonify(telemetry().ingest_environment(body(), credential()))


@app.get('/api/fan-command')
def fan_command():
    return jsonify(telemetry().fan_command(request.args.get('device_id'), credential()))


@app.post('/api/fan-status')
def fan_status():
    return jsonify(telemetry().ingest_fan_status(body(), credential()))


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--port', type=int, default=8080)
    cli.add_argument('--demo', action='store_true', help='Run with an isolated fictional demo database')
    args = cli.parse_args()
    init_db(demo=args.demo)
    if DEMO_MODE:
        from demo_data import seed_demo, start_telemetry

        with app.app_context():
            seed_demo(db())
        start_telemetry(app, db, provision_equipment)
        print(f'Demo user web: http://127.0.0.1:{args.port}/user', flush=True)
    print(f'Installer web: http://127.0.0.1:{args.port}', flush=True)
    app.run(host='0.0.0.0', port=args.port)
