"""RestFlow v5 sensor ingestion and ventilation control, scoped to installed equipment."""
import hashlib
import hmac
import math
import time

from database import Database

WINDOW = 600
OFFLINE = 120
ENVIRONMENT_MAX_AGE = 90
FAN_STATUS_MAX_AGE = 45
FAN_PWM_FREQUENCY_HZ = 1000
FAN_GPIO_BCM = 18

class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def integer(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise Problem(400, f'{name}: {lo}~{hi} 정수가 필요합니다')
    return value


def finite_number(value, lo, hi, name):
    if type(value) not in (int,float) or not math.isfinite(value) or not lo <= value <= hi:
        raise Problem(400,f'{name}: {lo}~{hi} 숫자가 필요합니다')
    return float(value)


def boolean(value,name):
    if type(value) is not bool:
        raise Problem(400,f'{name}: true 또는 false가 필요합니다')
    return value


def text_value(value, maximum, name):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Problem(400, f'{name}: 1~{maximum}자 문자열이 필요합니다')
    return value.strip()


def optional_text(value, maximum, name):
    if value in (None, ''):
        return None
    if not isinstance(value, str) or len(value.strip()) > maximum:
        raise Problem(400, f'{name}: {maximum}자 이하 문자열이 필요합니다')
    return value.strip() or None


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def init_telemetry(db):
    statements=('''CREATE TABLE IF NOT EXISTS toilets(
      id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100) NOT NULL
     
      )
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS devices(
      id VARCHAR(64) COLLATE utf8mb4_bin PRIMARY KEY, toilet_id INT UNIQUE NOT NULL,
      token_hash CHAR(64) NOT NULL, fan_token_hash CHAR(64) NOT NULL, last_seen DOUBLE NULL,
      quality VARCHAR(16) NOT NULL DEFAULT 'unknown',
      CONSTRAINT fk_devices_toilet FOREIGN KEY(toilet_id) REFERENCES toilets(id))
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS sessions(
      device_id VARCHAR(64) COLLATE utf8mb4_bin NOT NULL, boot_id VARCHAR(64) NOT NULL,
      last_seq INT NOT NULL, PRIMARY KEY(device_id,boot_id),
      CONSTRAINT fk_sessions_device FOREIGN KEY(device_id) REFERENCES devices(id))
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS events(
      id BIGINT PRIMARY KEY AUTO_INCREMENT, device_id VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
      boot_id VARCHAR(64) NOT NULL, seq INT NOT NULL,
      direction VARCHAR(8) NOT NULL, occurred_at DOUBLE NOT NULL,
      received_at DOUBLE NOT NULL,
      CONSTRAINT fk_events_device FOREIGN KEY(device_id) REFERENCES devices(id),
      UNIQUE KEY uq_event(device_id,boot_id,seq), KEY event_time(occurred_at))
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS environment_samples(
      id BIGINT PRIMARY KEY AUTO_INCREMENT, device_id VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
      temperature_c DECIMAL(5,2) NOT NULL, humidity_pct DECIMAL(5,2) NOT NULL,
      presence TINYINT(1) NOT NULL, idle_seconds INT NOT NULL,
      occurred_at DOUBLE NOT NULL, received_at DOUBLE NOT NULL,
      CONSTRAINT fk_environment_device FOREIGN KEY(device_id) REFERENCES devices(id),
      KEY environment_device_time(device_id,occurred_at), KEY environment_received(received_at))
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS occupancy_state(
      toilet_id INT PRIMARY KEY, estimate INT NOT NULL DEFAULT 0,
      confidence VARCHAR(16) NOT NULL DEFAULT 'unknown',
      reason VARCHAR(255) NOT NULL DEFAULT '초기 상태 미확인',
      last_event_at DOUBLE NULL, last_boot_id VARCHAR(64) NULL,
      initialized_at DOUBLE NULL, updated_at DOUBLE NOT NULL,
      CONSTRAINT fk_occupancy_toilet FOREIGN KEY(toilet_id) REFERENCES toilets(id))
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS control_profiles(
      toilet_id INT PRIMARY KEY, enabled TINYINT(1) NOT NULL DEFAULT 1,
      humidity_medium DECIMAL(5,2) NOT NULL DEFAULT 60,
      humidity_high DECIMAL(5,2) NOT NULL DEFAULT 70,
      idle_standby_seconds INT NOT NULL DEFAULT 300,
      idle_off_seconds INT NOT NULL DEFAULT 900,
      fan_quiet INT NOT NULL DEFAULT 30,
      fan_moderate INT NOT NULL DEFAULT 60,
      fan_busy INT NOT NULL DEFAULT 100,
      CONSTRAINT fk_control_toilet FOREIGN KEY(toilet_id) REFERENCES toilets(id))
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS fan_status(
      device_id VARCHAR(64) COLLATE utf8mb4_bin PRIMARY KEY, applied_percent INT NOT NULL DEFAULT 0,
      requested_percent INT NOT NULL DEFAULT 0, mode VARCHAR(32) NOT NULL DEFAULT 'unknown',
      ok TINYINT(1) NOT NULL DEFAULT 0, error_message VARCHAR(255) NULL,
      last_poll_at DOUBLE NULL, last_applied_at DOUBLE NULL,
      CONSTRAINT fk_fan_device FOREIGN KEY(device_id) REFERENCES devices(id))
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''',
    '''CREATE TABLE IF NOT EXISTS audit(
      id BIGINT PRIMARY KEY AUTO_INCREMENT, at DOUBLE NOT NULL, action VARCHAR(255) NOT NULL)
      ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci''')
    for statement in statements:
        db.execute(statement)

    db.execute("""ALTER TABLE control_profiles
        ADD COLUMN IF NOT EXISTS control_mode VARCHAR(8) NOT NULL DEFAULT 'auto',
        ADD COLUMN IF NOT EXISTS idle_saving TINYINT(1) NOT NULL DEFAULT 1,
        ADD COLUMN IF NOT EXISTS manual_percent INT NOT NULL DEFAULT 60""")

class Telemetry:
    def __init__(self, config, database):
        self.config = config
        self.database = database

    def connect(self):
        return Database(self.config, self.database)

    def authenticate_device(self, device, token, db, lock=False, fan=False):
        suffix=' FOR UPDATE' if lock else ''
        row = db.execute('SELECT d.* FROM devices d JOIN sensor_links l ON l.toilet_id=d.toilet_id WHERE d.id=?'+suffix,(device,)).fetchone()
        if not row or not hmac.compare_digest(row['fan_token_hash' if fan else 'token_hash'],digest(token)):
            raise Problem(401,'장치 인증에 실패했습니다')
        return row

    def ingest(self, data, token, heartbeat=False, now=None):
        now = time.time() if now is None else now
        device = text_value(data.get('device_id'),64,'device_id')
        quality = data.get('quality','good')
        if quality not in ('good','degraded','fault'):
            raise Problem(400,'quality 값이 올바르지 않습니다')
        with self.connect() as db:
            device_row=self.authenticate_device(device,token,db,True)
            state=db.execute('SELECT * FROM occupancy_state WHERE toilet_id=? FOR UPDATE',(device_row['toilet_id'],)).fetchone()
            if not state:
                db.execute('INSERT INTO occupancy_state(toilet_id,updated_at) VALUES(?,?)',(device_row['toilet_id'],now))
                state=db.execute('SELECT * FROM occupancy_state WHERE toilet_id=? FOR UPDATE',(device_row['toilet_id'],)).fetchone()
            interrupted = device_row['last_seen'] is None or now-device_row['last_seen'] > OFFLINE
            if interrupted and state['confidence'] == 'reliable':
                db.execute("UPDATE occupancy_state SET confidence='unknown',reason=? WHERE toilet_id=?",
                           ('센서 통신 공백',device_row['toilet_id']))
                state['confidence'] = 'unknown'
                state['reason'] = '센서 통신 공백'
            if heartbeat:
                boot = data.get('boot_id')
                if boot is not None:
                    boot = text_value(boot,64,'boot_id')
                if boot and state['last_boot_id'] and boot != state['last_boot_id']:
                    db.execute("UPDATE occupancy_state SET confidence='unknown',reason=? WHERE toilet_id=?",
                               ('장치 재부팅 감지',device_row['toilet_id']))
                if boot:
                    db.execute('UPDATE occupancy_state SET last_boot_id=? WHERE toilet_id=?',(boot,device_row['toilet_id']))
                db.execute('UPDATE devices SET last_seen=?,quality=? WHERE id=?',(now,quality,device))
                if quality!='good':
                    db.execute('''UPDATE occupancy_state SET confidence='unknown',reason=?,updated_at=?
                                  WHERE toilet_id=?''',(f'장치 품질 {quality}',now,device_row['toilet_id']))
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
            sequence_gap=(session is not None and seq>session['last_seq']+1) or (session is None and seq!=1)
            boot_changed=bool(state['last_boot_id'] and state['last_boot_id']!=boot)
            estimate=int(state['estimate'])
            confidence=state['confidence']
            reasons=[]
            if not state['initialized_at'] or at > state['initialized_at']:
                if direction=='in':
                    estimate+=1
                elif estimate>0:
                    estimate-=1
                else:
                    reasons.append('대응하는 입장 기록 없는 퇴장 감지')
            if boot_changed:reasons.append('장치 재부팅 감지')
            if sequence_gap:reasons.append('이벤트 순서 누락 감지')
            if quality!='good':reasons.append(f'장치 품질 {quality}')
            if reasons:confidence='unknown'
            db.execute('INSERT INTO events(device_id,boot_id,seq,direction,occurred_at,received_at) VALUES(?,?,?,?,?,?)',
                       (device,boot,seq,direction,at,now))
            db.execute('INSERT INTO sessions VALUES(?,?,?) ON DUPLICATE KEY UPDATE last_seq=VALUES(last_seq)',(device,boot,seq))
            effective_quality='degraded' if sequence_gap or quality=='degraded' else quality
            db.execute('UPDATE devices SET last_seen=?,quality=? WHERE id=?',(now,effective_quality,device))
            db.execute('''UPDATE occupancy_state SET estimate=?,confidence=?,reason=?,last_event_at=?,
                          last_boot_id=?,updated_at=? WHERE toilet_id=?''',
                       (estimate,confidence,' · '.join(reasons) if reasons else ('정상 통행 추적' if confidence=='reliable' else state['reason']),
                        max(float(state['last_event_at'] or 0),float(at)),boot,now,device_row['toilet_id']))
            return {'accepted':True,'duplicate':False,'occupancy_confidence':confidence}

    def ingest_environment(self,data,token,now=None):
        now=time.time() if now is None else now
        device=text_value(data.get('device_id'),64,'device_id')
        temperature=finite_number(data.get('temperature_c'),-20,80,'temperature_c')
        humidity=finite_number(data.get('humidity_pct'),0,100,'humidity_pct')
        quality=data.get('quality','good')
        if quality not in ('good','degraded','fault'):
            raise Problem(400,'quality 값이 올바르지 않습니다')
        occurred_at=data.get('occurred_at')
        if type(occurred_at) not in (int,float) or not math.isfinite(occurred_at) or not now-300<=occurred_at<=now+30:
            raise Problem(400,'occurred_at은 최근 5분 이내 UTC Unix 초여야 합니다')
        with self.connect() as db:
            row=self.authenticate_device(device,token,db,True)
            occupancy=db.execute('SELECT * FROM occupancy_state WHERE toilet_id=?',(row['toilet_id'],)).fetchone()
            boot = data.get('boot_id')
            if boot is not None:
                boot = text_value(boot,64,'boot_id')
            reboot = bool(boot and occupancy and occupancy['last_boot_id'] and occupancy['last_boot_id'] != boot)
            if reboot or row['last_seen'] is None or now-row['last_seen'] > OFFLINE:
                db.execute("UPDATE occupancy_state SET confidence='unknown',reason=? WHERE toilet_id=?",
                           ('장치 재부팅 감지' if reboot else '센서 통신 공백',row['toilet_id']))
                if occupancy:
                    occupancy['confidence'] = 'unknown'
            presence=bool(occupancy and occupancy['confidence']=='reliable' and occupancy['estimate']>0)
            reference=(occupancy['last_event_at'] or occupancy['initialized_at']) if occupancy else None
            idle_seconds=0 if presence or reference is None else min(86400,max(0,int(now-reference)))
            db.execute('''INSERT INTO environment_samples
              (device_id,temperature_c,humidity_pct,presence,idle_seconds,occurred_at,received_at)
              VALUES(?,?,?,?,?,?,?)''',(device,temperature,humidity,int(presence),idle_seconds,occurred_at,now))
            db.execute('UPDATE devices SET last_seen=?,quality=? WHERE id=?',(now,quality,device))
            if boot and occupancy:
                db.execute('UPDATE occupancy_state SET last_boot_id=? WHERE toilet_id=?',(boot,row['toilet_id']))
            if quality!='good':
                db.execute('''UPDATE occupancy_state SET confidence='unknown',reason=?,updated_at=?
                              WHERE toilet_id=?''',(f'환경 센서 품질 {quality}',now,row['toilet_id']))
            db.execute('DELETE FROM environment_samples WHERE received_at<?',(now-7*86400,))
            toilet_id=row['toilet_id']
        return {'accepted':True,'control':self.control_status(toilet_id,now)['control']}

    def control_status(self,toilet_id,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            row=db.execute('''SELECT t.*, d.id device_id,
              (SELECT COALESCE(SUM(CASE WHEN z.closed=0 THEN z.open ELSE 0 END),0) FROM zones z
               WHERE z.place_id=l.place_id AND (l.zone_id IS NULL OR z.id=l.zone_id)) operating,d.last_seen,d.quality,(d.fan_token_hash <> '') fan_enabled,p.enabled,p.humidity_medium,
              p.humidity_high,p.control_mode,p.idle_saving,p.manual_percent,p.idle_standby_seconds,p.idle_off_seconds,p.fan_quiet,p.fan_moderate,p.fan_busy
              FROM toilets t LEFT JOIN devices d ON d.toilet_id=t.id
              JOIN control_profiles p ON p.toilet_id=t.id
              JOIN sensor_links l ON l.toilet_id=t.id WHERE t.id=?''',(toilet_id,)).fetchone()
            if not row:raise Problem(404,'시설을 찾을 수 없습니다')
            latest=db.execute('''SELECT * FROM environment_samples WHERE device_id=?
                                 ORDER BY occurred_at DESC,id DESC LIMIT 1''',(row['device_id'] or '',)).fetchone()
            occupancy=db.execute('SELECT * FROM occupancy_state WHERE toilet_id=?',(toilet_id,)).fetchone()
            fan_row=db.execute('SELECT * FROM fan_status WHERE device_id=?',(row['device_id'] or '',)).fetchone()
            counts=db.execute('''SELECT direction,count(*) n FROM events WHERE device_id=?
              AND occurred_at>=? AND occurred_at<=? GROUP BY direction''',
              (row['device_id'] or '',now-WINDOW,now)).fetchall()
        counts={r['direction']:r['n'] for r in counts}
        row=dict(row)
        profile={key:row[key] for key in ('enabled','humidity_medium','humidity_high','control_mode','idle_saving','manual_percent','idle_standby_seconds','idle_off_seconds','fan_quiet','fan_moderate','fan_busy')}
        ins=counts.get('in',0)
        operating=int(row['operating'])
        score=ins/operating if operating else 0
        level='busy' if score>=2 else 'moderate' if score>=1 else 'quiet'
        online=row['last_seen'] is not None and now-row['last_seen']<=OFFLINE
        healthy=online and row['quality']=='good'
        estimate=int(occupancy['estimate']) if occupancy else 0
        confidence=occupancy['confidence'] if occupancy else 'unknown'
        occupancy_reason=occupancy['reason'] if occupancy else '재실 상태가 초기화되지 않음'
        if not online:
            occupancy_mode='unknown';occupancy_reason='출입 센서 오프라인'
        elif not healthy:
            occupancy_mode='unknown';occupancy_reason='센서 품질 확인 필요'
        elif confidence!='reliable':
            occupancy_mode='unknown'
        else:
            occupancy_mode='occupied' if estimate>0 else 'unoccupied'
        reference=None
        if occupancy:
            reference=occupancy['last_event_at'] or occupancy['initialized_at']
        idle=0 if occupancy_mode=='occupied' or reference is None else max(0,int(now-reference))
        occupancy_result={'state':occupancy_mode,'estimate':estimate,'confidence':confidence,
                          'reason':occupancy_reason,'last_event_at':occupancy['last_event_at'] if occupancy else None,
                          'idle_seconds':idle,'updated_at':occupancy['updated_at'] if occupancy else None}
        environment=None
        if latest:
            environment={'temperature_c':float(latest['temperature_c']),'humidity_pct':float(latest['humidity_pct']),
                         'occurred_at':latest['occurred_at'],'received_at':latest['received_at'],
                         'fresh':now-min(latest['received_at'],latest['occurred_at'])<=ENVIRONMENT_MAX_AGE}
        safe_fan=int(profile['fan_moderate'])
        control={'automatic':profile['enabled'],'mode':'sensor_fault','fan_pwm_percent':safe_fan,
                 'fan_pwm_raw':round(safe_fan*255/100),'reason':'온습도 데이터 수신 대기 · 보수 출력 유지','updated_at':now,
                 'pwm_frequency_hz':FAN_PWM_FREQUENCY_HZ,'gpio_bcm':FAN_GPIO_BCM}
        if profile['control_mode']=='manual':
            fan = int(profile['manual_percent'])
            control.update(automatic=False,mode='manual',fan_pwm_percent=fan,
                           fan_pwm_raw=round(fan*255/100),reason='관리자가 지정한 수동 출력')
        elif not profile['enabled']:
            control.update(mode='disabled',fan_pwm_percent=0,fan_pwm_raw=0,reason='관리자가 자동제어를 사용 중지함')
        elif environment and environment['fresh'] and (healthy or environment['humidity_pct']>=profile['humidity_high']):
            humidity=environment['humidity_pct']
            base={'quiet':profile['fan_quiet'],'moderate':profile['fan_moderate'],'busy':profile['fan_busy']}[level]
            fan=base;mode='active';reasons=[f"혼잡도 { {'quiet':'여유','moderate':'보통','busy':'혼잡'}[level] } 기준 환기"]
            if humidity>=profile['humidity_high']:
                fan=100;mode='drying';reasons.append('고습도 강제 환기')
            elif humidity>=profile['humidity_medium']:
                fan=max(fan,profile['fan_moderate']);mode='drying';reasons.append('목표 습도 이상으로 환기 강화')
            elif occupancy_mode=='unknown':
                fan=max(fan,profile['fan_moderate']);mode='uncertain';reasons=[f'재실 불확실: {occupancy_reason}','자동 정지 금지']
            elif occupancy_mode=='occupied':
                reasons.append(f'재실 추정 {estimate}명')
            elif profile['idle_saving'] and idle>=profile['idle_off_seconds']:
                fan=0;mode='off';reasons=['장시간 무인으로 자동 정지']
            elif profile['idle_saving'] and idle>=profile['idle_standby_seconds']:
                fan=int(profile['fan_quiet']);mode='standby';reasons=['무인시간 기준을 넘어 절전 대기']
            elif profile['idle_saving']:
                mode='cooldown';reasons.append(f'무인 확인 후 {idle}초 경과')
            raw=round(fan*255/100)
            control.update(mode=mode,fan_pwm_percent=int(fan),fan_pwm_raw=raw,reason=' · '.join(reasons))
        elif environment and not environment['fresh']:
            control['reason']='환경 데이터가 90초 이상 갱신되지 않음'
        elif not healthy:
            control['reason']='출입 센서가 오프라인이거나 측정 품질 확인 필요'
        fan_status=None
        if fan_row:
            fan_status=dict(fan_row)
            fan_status['ok']=bool(fan_status['ok'])
            fan_status['online']=fan_status['last_poll_at'] is not None and now-fan_status['last_poll_at']<=FAN_STATUS_MAX_AGE
            fan_status['applied_fresh']=fan_status['last_applied_at'] is not None and now-fan_status['last_applied_at']<=FAN_STATUS_MAX_AGE
        return {'toilet_id':toilet_id,'name':row['name'],'device_id':row['device_id'],'level':level,'score':round(score,2),'online':online,
                'fan_enabled':bool(row['fan_enabled']),
                'settings':{'mode':profile['control_mode'],'idle_saving':bool(profile['idle_saving']),
                            'manual_percent':profile['manual_percent'],'target_humidity':float(profile['humidity_medium']),
                            'high_humidity':float(profile['humidity_high'])},
                'quality':row['quality'] or 'unknown','entries':ins,'operating':operating,'environment':environment,
                'occupancy':occupancy_result,'control':control,'fan_status':fan_status}

    def fan_command(self,device,token,now=None):
        now=time.time() if now is None else now
        device=text_value(device,64,'device_id')
        with self.connect() as db:
            row=self.authenticate_device(device,token,db,fan=True)
            toilet_id=row['toilet_id']
        status=self.control_status(toilet_id,now)
        control=status['control']
        with self.connect() as db:
            db.execute('''INSERT INTO fan_status(device_id,requested_percent,mode,last_poll_at)
              VALUES(?,?,?,?) ON DUPLICATE KEY UPDATE requested_percent=VALUES(requested_percent),
              mode=VALUES(mode),last_poll_at=VALUES(last_poll_at)''',
              (device,control['fan_pwm_percent'],control['mode'],now))
        return {'device_id':device,'toilet_id':toilet_id,'command_id':int(now*1000),
                'pwm_percent':control['fan_pwm_percent'],'pwm_frequency_hz':FAN_PWM_FREQUENCY_HZ,
                'gpio_bcm':FAN_GPIO_BCM,'mode':control['mode'],'reason':control['reason'],
                'kickstart_ms':500,'expires_in_seconds':20}

    def ingest_fan_status(self,data,token,now=None):
        now=time.time() if now is None else now
        device=text_value(data.get('device_id'),64,'device_id')
        applied=integer(data.get('applied_percent'),0,100,'applied_percent')
        ok=boolean(data.get('ok'),'ok')
        error=optional_text(data.get('error_message'),255,'error_message')
        mode=optional_text(data.get('mode'),32,'mode') or 'unknown'
        with self.connect() as db:
            row=self.authenticate_device(device,token,db,fan=True)
            toilet_id=row['toilet_id']
        current=self.control_status(toilet_id,now)['control']
        with self.connect() as db:
            db.execute('''INSERT INTO fan_status
              (device_id,applied_percent,requested_percent,mode,ok,error_message,last_poll_at,last_applied_at)
              VALUES(?,?,?,?,?,?,?,?) ON DUPLICATE KEY UPDATE applied_percent=VALUES(applied_percent),
              requested_percent=VALUES(requested_percent),mode=VALUES(mode),ok=VALUES(ok),
              error_message=VALUES(error_message),last_poll_at=VALUES(last_poll_at),last_applied_at=VALUES(last_applied_at)''',
              (device,applied,current['fan_pwm_percent'],mode,int(ok),error,now,now))
        return {'accepted':True}

    def reset_occupancy(self,toilet_id,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM sensor_links WHERE toilet_id=? FOR UPDATE',(toilet_id,)).fetchone():
                raise Problem(404,'화장실을 찾을 수 없습니다')
            db.execute('''INSERT INTO occupancy_state
              (toilet_id,estimate,confidence,reason,last_event_at,initialized_at,updated_at)
              VALUES(?,0,'reliable','관리자 수동 초기화',?,?,?)
              ON DUPLICATE KEY UPDATE estimate=0,confidence='reliable',reason='관리자 수동 초기화',
              last_event_at=VALUES(last_event_at),initialized_at=VALUES(initialized_at),updated_at=VALUES(updated_at)''',
              (toilet_id,now,now,now))
            db.execute('INSERT INTO audit(at,action) VALUES(?,?)',(now,f'occupancy reset: {toilet_id}'))
        return {'reset':True,'occupancy':self.control_status(toilet_id,now)['occupancy']}

