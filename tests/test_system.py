import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import Store, Problem, make_server, visitor_url

class SystemTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Store(Path(self.temp.name)/'test.sqlite3')
        self.device=self.db.register({'id':'atom-a','toilet_id':1})
        self.token=self.device['token']
        self.now=time.time()
    def tearDown(self):self.temp.cleanup()
    def event(self,seq=1,direction='in',at=None,boot='boot-1'):
        return dict(device_id='atom-a',boot_id=boot,seq=seq,direction=direction,occurred_at=self.now if at is None else at)
    def send(self,e=None,token=None):return self.db.ingest(e or self.event(),self.token if token is None else token,now=self.now)
    def row(self,now=None):return self.db.snapshot(self.now if now is None else now)['toilets'][0]
    def test_unknown_until_device_heartbeat(self):
        self.assertEqual(self.row()['level'],'unknown')
        self.db.ingest({'device_id':'atom-a'},self.token,True,self.now)
        self.assertEqual(self.row()['level'],'quiet')
    def test_auth_rejects(self):
        with self.assertRaises(Problem) as err:self.send(token='wrong')
        self.assertEqual(err.exception.status,401)
        self.assertEqual(self.row()['entries'],0)
    def test_duplicate_exactly_once(self):
        self.assertTrue(self.send()['accepted']);self.assertTrue(self.send()['duplicate'])
        self.assertEqual(self.row()['entries'],1)
    def test_duplicate_payload_conflict(self):
        self.send()
        with self.assertRaises(Problem) as err:self.send(self.event(direction='out'))
        self.assertEqual(err.exception.status,409)
    def test_out_of_order(self):
        self.send(self.event(seq=2))
        with self.assertRaises(Problem):self.send(self.event(seq=1))
    def test_reboot_sequence_namespace(self):
        self.send();self.send(self.event(boot='boot-2'))
        self.assertEqual(self.row()['entries'],2)
    def test_old_replay_not_current_and_expires(self):
        self.send(self.event(at=self.now-601));self.assertEqual(self.row()['entries'],0)
        self.send(self.event(seq=2,at=self.now-599));self.assertEqual(self.row()['entries'],1)
        self.assertEqual(self.row(self.now+2)['entries'],0)
    def test_future_and_expired_and_nonfinite_timestamps(self):
        for value in (self.now+31,self.now-86401,float('nan'),float('inf'),'bad',True):
            with self.subTest(value=value),self.assertRaises(Problem):self.send(self.event(at=value))
    def test_sequence_and_direction_validation(self):
        for value in (True,0,-1,1.2,'1'):
            with self.subTest(value=value),self.assertRaises(Problem):self.send(self.event(seq=value))
        with self.assertRaises(Problem):self.send(self.event(direction='sideways'))
    def test_offline_and_degraded_override_congestion(self):
        self.send();self.assertEqual(self.row(self.now+121)['level'],'unknown')
        self.db.ingest({'device_id':'atom-a','quality':'degraded'},self.token,True,self.now)
        self.assertEqual(self.row()['level'],'unknown')
    def test_all_three_levels(self):
        self.send();self.assertEqual(self.row()['level'],'quiet')
        for seq in range(2,5):self.send(self.event(seq=seq))
        self.assertEqual(self.row()['level'],'moderate')
        for seq in range(5,10):self.send(self.event(seq=seq))
        self.assertEqual(self.row()['level'],'busy')
    def test_exits_cannot_make_negative_score(self):
        for seq in range(1,6):self.send(self.event(seq=seq,direction='out'))
        self.assertEqual(self.row()['score'],0)
    def test_reset_keeps_history_but_excludes_old_window(self):
        self.send()
        with self.db.connect() as db:db.execute('UPDATE toilets SET reset_at=? WHERE id=1',(self.now+1,))
        self.assertEqual(self.row(self.now+2)['entries'],0)
        self.assertEqual(sum(r['in'] for r in self.db.history(1,self.now+2)),1)
    def test_config_persistence(self):
        self.db.update(1,dict(name='동문 화장실',stalls=6,x=30,y=50))
        reloaded=Store(self.db.path)
        self.assertEqual(reloaded.snapshot()['toilets'][0]['stalls'],6)
    def test_settings_validation(self):
        for bad in ({'stalls':0},{'x':101},{'name':''},{'y':False}):
            with self.subTest(bad=bad),self.assertRaises(Problem):
                self.db.update(1,dict(name='A',stalls=4,x=20,y=20)|bad)
    def test_device_unique_per_toilet(self):
        with self.assertRaises(Problem):self.db.register(dict(id='new',toilet_id=1))
    def test_concurrent_delivery_is_idempotent(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda _:self.send(),range(12)))
        self.assertEqual(sum(r['accepted'] for r in results),1)
    def test_live_simulation_disabled(self):
        with self.assertRaises(Problem):self.db.simulate()
    def test_tokens_not_in_public_or_device_list(self):
        for value in (self.db.snapshot(),self.db.all_devices()):
            self.assertNotIn(self.token,json.dumps(value));self.assertNotIn('token_hash',json.dumps(value))

class FacilityLifecycleTests(unittest.TestCase):
    def test_delete_all_stays_empty_after_restart_and_can_add(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.sqlite3';db=Store(path,True)
            for t in db.snapshot()['toilets']:db.delete(t['id'])
            reloaded=Store(path,True)
            self.assertEqual(reloaded.snapshot()['toilets'],[])
            new=reloaded.create({'name':'새 출입구','stalls':5})
            self.assertGreater(new['id'],3)
            self.assertEqual(len(reloaded.snapshot()['toilets']),1)
            self.assertEqual(len(reloaded.all_devices()),1)
    def test_more_than_three_facilities_and_preserved_records(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Store(Path(folder)/'state.sqlite3',True)
            for i in range(30):db.create({'name':f'화장실 {i+4}','stalls':4})
            self.assertEqual(len(db.snapshot()['toilets']),33)
            with db.connect() as conn:before=conn.execute('SELECT count(*) FROM events').fetchone()[0]
            db.delete(1)
            with db.connect() as conn:self.assertEqual(conn.execute('SELECT count(*) FROM events').fetchone()[0],before)
    def test_existing_database_schema_is_migrated_without_losing_settings(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'old.sqlite3'
            with sqlite3.connect(path) as conn:
                conn.executescript("CREATE TABLE toilets(id INTEGER PRIMARY KEY,name TEXT NOT NULL,stalls INTEGER NOT NULL,x INTEGER NOT NULL,y INTEGER NOT NULL,reset_at REAL NOT NULL DEFAULT 0);INSERT INTO toilets VALUES(9,'기존 시설',7,40,50,0);CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);INSERT INTO settings VALUES('visitor_url','https://old.example.org');")
            db=Store(path)
            self.assertEqual(db.snapshot()['toilets'][0]['name'],'기존 시설')
            self.assertEqual(db.snapshot()['settings']['visitor_url'],'https://old.example.org')
            self.assertTrue(db.session_valid(db.login('1234')))

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.db=Store(Path(cls.temp.name)/'http.sqlite3')
        cls.server=make_server('127.0.0.1',0,cls.db,'https://event.example.org')
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def setUp(self):
        status,body,headers=self.request('/api/login','POST',{'password':'1234'})
        self.assertEqual(status,200)
        self.cookie=headers['Set-Cookie'].split(';',1)[0]
    def request(self,path,method='GET',body=None,token=None,cookie=None):
        headers={}
        if token=='integration-test-admin-token':headers['Cookie']=self.cookie
        elif token:headers['Authorization']='Bearer '+token
        if cookie:headers['Cookie']=cookie
        if body is not None:headers['Content-Type']='application/json'
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try:
            with urlopen(req) as r:return r.status,r.read(),r.headers
        except HTTPError as e:return e.code,e.read(),e.headers
    def test_pages_and_security_headers(self):
        for path in ('/','/admin','/app.js','/style.css','/map.svg'):
            status,body,headers=self.request(path);self.assertEqual(status,200);self.assertGreater(len(body),30)
            self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
    def test_health_and_admin_auth(self):
        self.assertEqual(self.request('/api/health')[0],200)
        self.assertEqual(self.request('/api/admin')[0],401)
        self.assertEqual(self.request('/api/admin',token='integration-test-admin-token')[0],200)
    def test_full_api_event_roundtrip(self):
        code,body,_=self.request('/api/devices','POST',dict(id='http-device',toilet_id=1),'integration-test-admin-token')
        self.assertEqual(code,201);token=json.loads(body)['token']
        event=dict(device_id='http-device',boot_id='one',seq=1,direction='in',occurred_at=time.time())
        self.assertEqual(self.request('/api/events','POST',event,token)[0],200)
        self.assertTrue(json.loads(self.request('/api/events','POST',event,token)[1])['duplicate'])
        status=json.loads(self.request('/api/status')[1]);self.assertEqual(status['toilets'][0]['entries'],1)
    def test_simulator_cli_and_persistent_state(self):
        code,body,_=self.request('/api/devices','POST',dict(id='sim-device',toilet_id=2),'integration-test-admin-token')
        self.assertEqual(code,201)
        token=json.loads(body)['token']
        path=Path(self.temp.name)/'sim.json'
        cmd=[sys.executable,str(Path(__file__).resolve().parents[1]/'tools/simulate.py'),'--url',self.base,'--device','sim-device','--state',str(path)]
        env=dict(os.environ,DEVICE_TOKEN=token)
        for extra in (['--count','3'],['--direction','out']):
            run=subprocess.run(cmd+extra,env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertNotIn(token,run.stdout+run.stderr)
        state=json.loads(path.read_text());self.assertEqual(state['seq'],4);self.assertEqual(state['queue'],[])
        row=self.db.snapshot()['toilets'][1];self.assertEqual((row['entries'],row['exits']),(3,1))
    def test_admin_write_requires_auth(self):
        self.assertEqual(self.request('/api/toilets/1','PUT',dict(name='bad',stalls=4,x=10,y=10))[0],401)
    def test_image_svg_rejected(self):
        self.assertEqual(self.request('/api/map','PUT',{'image':'data:image/svg+xml;base64,PHN2Zz4='},'integration-test-admin-token')[0],400)
    def test_qr_generated_locally(self):
        status,body,headers=self.request('/api/qr.svg');self.assertEqual(status,200)
        self.assertIn(b'<svg',body);self.assertIn('image/svg+xml',headers['Content-Type'])
    def test_visitor_url_requires_admin(self):
        self.assertEqual(self.request('/api/visitor-url','PUT',{'url':'https://event.example.org'})[0],401)
    def test_visitor_url_saved_and_used_for_qr(self):
        target='https://festival.example.org/guide?event=4'
        status,body,_=self.request('/api/visitor-url','PUT',{'url':target},'integration-test-admin-token')
        self.assertEqual(status,200)
        self.assertEqual(json.loads(self.request('/api/admin',token='integration-test-admin-token')[1])['visitor_url'],target)
        with self.db.connect() as db:self.assertEqual(db.execute("SELECT value FROM settings WHERE key='visitor_url'").fetchone()[0],target)
        status,svg,_=self.request('/api/qr.svg');self.assertEqual(status,200);self.assertIn(b'<svg',svg)
    def test_visitor_url_rejects_invalid_or_embedded_credentials(self):
        for target in ('javascript:alert(1)','file:///tmp/secret','https://user:password@example.org','https://','http://host:bad','https://example.org/has space','https://example.org/\nsecret'):
            with self.subTest(target=target):
                self.assertEqual(self.request('/api/visitor-url','PUT',{'url':target},'integration-test-admin-token')[0],400)
    def test_password_login_and_cookie_flags(self):
        status,body,headers=self.request('/api/login','POST',{'password':'1234'})
        self.assertEqual(status,200)
        self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertNotIn('1234',body.decode())
        self.assertEqual(self.request('/api/login','POST',{'password':'wrong'})[0],401)
        self.assertEqual(self.request('/api/admin',token='old-admin-token-is-not-a-session')[0],401)
    def test_logout_revokes_session(self):
        self.assertEqual(self.request('/api/logout','POST',{},cookie=self.cookie)[0],200)
        self.assertEqual(self.request('/api/admin',cookie=self.cookie)[0],401)
    def test_password_change_persists_and_revokes_other_sessions(self):
        status,body,headers=self.request('/api/login','POST',{'password':'1234'})
        other=headers['Set-Cookie'].split(';',1)[0]
        try:
            status,body,headers=self.request('/api/password','PUT',{'current_password':'1234','new_password':'new-pass-5678'},cookie=self.cookie)
            self.assertEqual(status,200)
            new_cookie=headers['Set-Cookie'].split(';',1)[0]
            self.assertEqual(self.request('/api/admin',cookie=other)[0],401)
            self.assertEqual(self.request('/api/admin',cookie=self.cookie)[0],401)
            self.assertEqual(self.request('/api/admin',cookie=new_cookie)[0],200)
            self.assertEqual(self.request('/api/login','POST',{'password':'1234'})[0],401)
            restored=Store(self.db.path)
            self.assertTrue(restored.session_valid(restored.login('new-pass-5678')))
            public=self.request('/api/status')[1].decode()
            self.assertNotIn('new-pass-5678',public);self.assertNotIn('password_hash',public);self.assertNotIn('salt',public)
        finally:self.db.change_password('new-pass-5678','1234')
    def test_password_change_validates_current_password_and_length(self):
        for data in ({'current_password':'wrong','new_password':'5678'},{'current_password':'1234','new_password':'abc'}):
            self.assertIn(self.request('/api/password','PUT',data,cookie=self.cookie)[0],(400,401))
        self.assertEqual(self.request('/api/admin',cookie=self.cookie)[0],200)
    def test_toilet_add_delete_and_revoked_device(self):
        status,body,_=self.request('/api/toilets','POST',{'name':'새 화장실','stalls':6},cookie=self.cookie)
        self.assertEqual(status,201);tid=json.loads(body)['id']
        status,body,_=self.request('/api/devices','POST',{'id':'new-physical-device','toilet_id':tid},cookie=self.cookie)
        self.assertEqual(status,201);device_token=json.loads(body)['token']
        heartbeat={'device_id':'new-physical-device','quality':'good'}
        self.assertEqual(self.request('/api/heartbeat','POST',heartbeat,device_token)[0],200)
        self.assertEqual(self.request(f'/api/toilets/{tid}','DELETE',cookie=self.cookie)[0],200)
        self.assertNotIn(tid,[r['id'] for r in self.db.snapshot()['toilets']])
        self.assertEqual(self.request('/api/heartbeat','POST',heartbeat,device_token)[0],401)
        self.assertEqual(self.request(f'/api/toilets/{tid}','DELETE',cookie=self.cookie)[0],404)
    def test_toilet_creation_requires_login(self):
        self.assertEqual(self.request('/api/toilets','POST',{'name':'No','stalls':4})[0],401)
    def test_expired_session_is_rejected(self):
        with self.db.connect() as db:db.execute('UPDATE admin_sessions SET expires_at=0')
        self.assertEqual(self.request('/api/admin',cookie=self.cookie)[0],401)
    def test_traversal_not_served(self):self.assertEqual(self.request('/../server.py')[0],404)

if __name__=='__main__':unittest.main()
