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

from server import Store, Problem, make_server

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

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.db=Store(Path(cls.temp.name)/'http.sqlite3')
        cls.server=make_server('127.0.0.1',0,cls.db,'integration-test-admin-token','https://event.example.org')
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def request(self,path,method='GET',body=None,token=None):
        headers={}
        if token:headers['Authorization']='Bearer '+token
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
    def test_traversal_not_served(self):self.assertEqual(self.request('/../server.py')[0],404)

if __name__=='__main__':unittest.main()
