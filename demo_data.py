"""Fictional facilities for the RestFlow demonstration near Seoul City Hall."""

DEMO_PLACES = [
    ('station', '시청역 시연 화장실', '시청역 · 지하 1층', 37.56515, 126.97765, [
        ('여성 화장실', 'women', 4, 5),
        ('남성 화장실', 'men', 5, 5),
        ('공용 장애인 화장실', 'shared-accessible', 1, 1),
    ]),
    ('palace', '덕수궁 돌담길 시연 화장실', '덕수궁 돌담길 · 정동 입구', 37.56555, 126.9746, [
        ('공용 화장실', 'shared', 2, 3),
    ]),
    ('library', '서울도서관 시연 화장실', '서울도서관 · 1층', 37.56639, 126.97794, [
        ('여성 화장실', 'women', 5, 5),
    ]),
    ('plaza', '서울광장 시연 화장실', '서울광장 · 남쪽 안내소', 37.56505, 126.9786, [
        ('공용 장애인 화장실', 'shared-accessible', 0, 1),
    ]),
    ('hall', '시민청 시연 화장실', '시민청 · 지하 2층', 37.56712, 126.97825, [
        ('여성 화장실', 'women', 2, 5),
        ('남성 화장실', 'men', 3, 4),
    ]),
]


def seed_demo(connection):
    with connection:
        if connection.execute('SELECT 1 FROM places LIMIT 1').fetchone():
            return
        for key, name, address, lat, lon, zones in DEMO_PLACES:
            place_id = f'demo-{key}'
            connection.execute('INSERT INTO places(id,name,address,lat,lon) VALUES(?,?,?,?,?)',
                               (place_id, name, address, lat, lon))
            for index, (zone, kind, opened, total) in enumerate(zones, 1):
                device = f'{place_id}-{index}'
                result = connection.execute(
                    'INSERT INTO zones(place_id,name,device,total,open,closed,reason,`accessible`) VALUES(?,?,?,?,?,?,?,?)',
                    (place_id, zone, device, total, opened, int(not opened),
                     '청소 중 (시연)' if not opened else '', int(kind.endswith('-accessible'))))
                connection.execute('INSERT INTO module_access(zone_id,slug,kind) VALUES(?,?,?)',
                                   (result.lastrowid, device, kind))


def start_telemetry(app, db, provision_equipment):
    """Feed fictional traffic and fan reports into the same code used by devices."""
    import secrets
    import threading
    import time

    from telemetry import digest

    scenarios = {
        'demo-station-1': (6, 65), 'demo-station-2': (3, 42), 'demo-station-3': (2, 53),
        'demo-palace-1': (5, 81), 'demo-hall-1': (5, 49), 'demo-hall-2': (3, 56),
    }
    sources = []
    with app.app_context(), db() as connection:
        for device, (count, humidity) in scenarios.items():
            zone = connection.execute('SELECT * FROM zones WHERE device=?',(device,)).fetchone()
            if not zone:
                continue
            link = connection.execute('SELECT toilet_id FROM sensor_links WHERE zone_id=?',(zone['id'],)).fetchone()
            sensor_key, fan_key = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            if link:
                current = connection.execute('SELECT id FROM devices WHERE toilet_id=?',(link['toilet_id'],)).fetchone()
                if current['id'] != device:
                    continue
                connection.execute('UPDATE devices SET token_hash=?,fan_token_hash=? WHERE id=?',
                                   (digest(sensor_key),digest(fan_key),device))
            else:
                provision_equipment(connection,zone['place_id'],zone['id'],device,zone['name'],sensor_key,fan_key)
            sources.append((device,sensor_key,fan_key,count,humidity))
    service = app.config['TELEMETRY']
    boot = 'simulation-' + secrets.token_hex(6)
    sequences = {}
    last_traffic = {}

    def tick():
        now = time.time()
        for device,sensor_key,fan_key,count,humidity in sources:
            payload = {'device_id':device,'boot_id':boot,'quality':'good'}
            try:
                service.ingest(payload,sensor_key,heartbeat=True)
                with service.connect() as connection:
                    previous = connection.execute("SELECT MAX(occurred_at) AS recent FROM events WHERE device_id=? AND direction='in'",
                                                  (device,)).fetchone()['recent']
                if now - (last_traffic.get(device) or previous or 0) >= 600:
                    for direction in ('in','out'):
                        for _ in range(count):
                            seq = sequences.get(device,0) + 1
                            service.ingest(dict(payload,seq=seq,direction=direction,occurred_at=now),sensor_key)
                            sequences[device] = seq
                    last_traffic[device] = now
                service.ingest_environment(dict(payload,temperature_c=24,humidity_pct=humidity,occurred_at=now),sensor_key)
                command = service.fan_command(device,fan_key)
                service.ingest_fan_status(dict(device_id=device,applied_percent=command['pwm_percent'],
                                               ok=True,mode=command['mode']),fan_key)
            except Exception:
                app.logger.exception('Demo telemetry tick failed for %s', device)

    tick()

    def simulate():
        while sources:
            time.sleep(5)
            tick()

    threading.Thread(target=simulate, daemon=True, name='restflow-demo').start()
