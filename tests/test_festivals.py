"""Multi-festival integration tests against an explicitly configured disposable MariaDB."""
import concurrent.futures
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import mariadb
from server import Store,make_server,load_db_config,FestivalScope,Problem

CONFIG=load_db_config(os.environ.get('RESTFLOW_TEST_DB_CONFIG'))
CONFIG['database']+='_festivals_test';CONFIG['demo_database']+='_festivals_test'

def setup_databases():
    conn=mariadb.connect(**{k:CONFIG[k] for k in ('host','port','user','password')});cur=conn.cursor()
    for name in (CONFIG['database'],CONFIG['demo_database']):cur.execute(f'CREATE DATABASE IF NOT EXISTS `{name}`')
    conn.commit();conn.close()
setup_databases()

def tearDownModule():
    conn=mariadb.connect(**{k:CONFIG[k] for k in ('host','port','user','password')});cur=conn.cursor()
    for name in (CONFIG['database'],CONFIG['demo_database']):cur.execute(f'DROP DATABASE IF EXISTS `{name}`')
    conn.commit();conn.close()

class FestivalTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(CONFIG,reset_schema=True)
        self.session=self.store.login('1234')
        self.indoor=self.store.create_festival({'name':'실내 축제','mode':'indoor'})
        self.outdoor=self.store.create_festival({'name':'야외 축제','mode':'outdoor'})
        self.in_toilet=self.store.create({'name':'실내 A','stalls':3},self.indoor['id'])['id']
        self.out_toilet=self.store.create({'name':'야외 A','stalls':4},self.outdoor['id'])['id']
        self.server=make_server('127.0.0.1',0,self.store,'https://festival.example.org')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
        env=patch.dict(os.environ,{'RESTFLOW_TMAP_MAP_KEY':'test-map','RESTFLOW_TMAP_ROUTE_KEY':'test-route'},clear=True);env.start();self.addCleanup(env.stop)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,method='GET',body=None,festival=None,admin=True):
        if festival is not None:path+=('&' if '?' in path else '?')+'festival_id='+str(festival)
        req=Request(f'http://127.0.0.1:{self.server.server_port}'+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Cookie':'restflow_admin='+self.session} if admin else {})})
        try:
            with urlopen(req) as r:return r.status,r.read().decode()
        except HTTPError as e:return e.code,e.read().decode()
    def test_new_festivals_start_empty_and_type_is_fixed(self):
        new=self.store.create_festival({'name':'새 축제','mode':'indoor'})
        self.assertEqual(self.store.snapshot(festival_id=new['id'])['toilets'],[])
        self.assertNotIn('map',self.store.snapshot(festival_id=new['id'])['settings'])
        self.assertEqual(self.request('/api/map-mode','PUT',{'map_mode':'outdoor'},new['id'])[0],409)
        for data in ({'name':'','mode':'indoor'},{'name':'x','mode':'bad'}):self.assertEqual(self.request('/api/festivals','POST',data)[0],400)
    def test_creation_and_list_require_login(self):
        self.assertEqual(self.request('/api/festivals',admin=False)[0],401)
        self.assertEqual(self.request('/api/festivals','POST',{'name':'new','mode':'indoor'},admin=False)[0],401)
        status,body=self.request('/api/festivals');self.assertEqual(status,200);self.assertEqual(len(json.loads(body)),3)
    def test_lists_maps_devices_and_restart_are_isolated(self):
        inside=FestivalScope(self.store,self.indoor['id']);outside=FestivalScope(self.store,self.outdoor['id'])
        inside.register({'id':'inside-sensor','toilet_id':self.in_toilet})
        outside.register({'id':'outside-sensor','toilet_id':self.out_toilet})
        self.assertEqual([r['id'] for r in inside.all_devices()],['inside-sensor'])
        self.assertEqual([r['id'] for r in outside.all_devices()],['outside-sensor'])
        image='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6uoAAAAASUVORK5CYII='
        self.assertEqual(self.request('/api/map','PUT',{'image':image},self.indoor['id'])[0],200)
        self.assertNotIn('map',outside.snapshot()['settings'])
        reloaded=Store(CONFIG)
        self.assertEqual(reloaded.snapshot(festival_id=self.indoor['id'])['settings']['map'],image)
        self.assertEqual([t['id'] for t in reloaded.snapshot(festival_id=self.outdoor['id'])['toilets']],[self.out_toilet])
    def test_cross_festival_writes_and_history_are_rejected(self):
        fid=self.indoor['id'];tid=self.out_toilet
        attempts=[(f'/api/toilets/{tid}','PUT',{'name':'bad','stalls':1,'x':50,'y':50}),
          (f'/api/toilets/{tid}','DELETE',None),(f'/api/coordinates/{tid}','PUT',{'latitude':37.5,'longitude':127}),
          ('/api/reset','POST',{'toilet_id':tid}),('/api/devices','POST',{'id':'wrong','toilet_id':tid}),
          (f'/api/history?toilet_id={tid}','GET',None)]
        for path,method,body in attempts:
            with self.subTest(path=path):self.assertEqual(self.request(path,method,body,fid)[0],404)
        row=self.store.snapshot(festival_id=self.outdoor['id'])['toilets'][0]
        self.assertEqual(row['name'],'야외 A');self.assertEqual(row['latitude'],None)
    def test_festival_qr_and_public_pages_do_not_follow_admin_selection(self):
        urls=[]
        for festival in (self.indoor,self.outdoor):
            status,body=self.request('/api/qr','POST',{},festival['id']);self.assertEqual(status,200)
            url=json.loads(body)['url'];urls.append(url)
            self.assertEqual(url,'https://festival.example.org/f/'+festival['public_id'])
            page=self.request('/f/'+festival['public_id'])[1]
            self.assertIn(f'data-festival-id="{festival["id"]}"',page)
            self.assertEqual('tmap/jsv2' in page,festival['mode']=='outdoor')
        self.assertNotEqual(urls[0],urls[1])
        self.request('/admin',festival=self.outdoor['id'])
        page=self.request('/f/'+self.indoor['public_id'],festival=self.outdoor['id'])[1]
        self.assertIn('mode-indoor',page);self.assertIn('data-festival-id="2"',page)
        self.assertEqual(self.request('/f/not-existing')[0],404)
    def test_concurrent_requests_remain_scoped(self):
        fids=[self.indoor['id'],self.outdoor['id']]*8
        def get(fid):
            status,body=self.request('/api/status',festival=fid,admin=False)
            return fid,status,json.loads(body)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for fid,status,body in pool.map(get,fids):
                self.assertEqual(status,200);self.assertEqual(body['festival']['id'],fid)
                self.assertEqual({t['festival_id'] for t in body['toilets']},{fid})
    def test_route_uses_only_selected_festival_destination(self):
        self.assertEqual(self.request('/api/route','POST',{'latitude':37.5,'longitude':127,'toilet_id':self.out_toilet},self.indoor['id'])[0],409)
        self.assertEqual(self.request('/api/route','POST',{'latitude':37.5,'longitude':127,'toilet_id':self.in_toilet},self.outdoor['id'])[0],404)
        self.assertEqual(self.request(f'/api/coordinates/{self.out_toilet}','PUT',{'latitude':37.58,'longitude':126.99},self.outdoor['id'])[0],200)
        payload={'features':[{'geometry':{'type':'Point'},'properties':{'totalDistance':120,'totalTime':90}},{'geometry':{'type':'LineString','coordinates':[[127,37.5],[126.99,37.58]]}}]}
        with patch('server._route_next',0),patch('server.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())) as remote:
            code,_=self.request('/api/route','POST',{'latitude':37.5,'longitude':127,'toilet_id':self.out_toilet},self.outdoor['id'])
            self.assertEqual(code,200);self.assertEqual(json.loads(remote.call_args.args[0].data)['endX'],126.99)
    def test_legacy_migration_preserves_layout_devices_history_and_password(self):
        legacy=Store(CONFIG,reset_schema=True)
        token=legacy.register({'id':'legacy-sensor','toilet_id':1})['token']
        session=legacy.login('1234')
        import time
        now=time.time()
        legacy.ingest(dict(device_id='legacy-sensor',boot_id='migration',seq=1,direction='in',occurred_at=now),token)
        with legacy.connect() as db:
            db.execute("INSERT INTO settings VALUES('map_mode','indoor')")
            db.execute("INSERT INTO settings VALUES('map','data:image/png;base64,legacy-layout')")
            db.execute('UPDATE toilets SET x=31,y=46,latitude=37.57,longitude=126.98 WHERE id=1')
            # Recreate the previously shipped schema without festival ownership.
            db.execute('ALTER TABLE toilets DROP FOREIGN KEY fk_toilets_festival')
            db.execute('ALTER TABLE toilets DROP INDEX idx_toilets_festival')
            db.execute('ALTER TABLE toilets DROP COLUMN festival_id')
            db.execute('DROP TABLE festivals')
        migrated=Store(CONFIG)
        self.assertEqual(len(migrated.list_festivals()),1)
        self.assertEqual(migrated.festival()['name'],'기존 축제')
        self.assertEqual(migrated.map_mode(),'indoor')
        self.assertEqual(migrated.snapshot()['settings']['map'],'data:image/png;base64,legacy-layout')
        row=migrated.snapshot()['toilets'][0]
        self.assertEqual((row['x'],row['y'],row['latitude'],row['longitude']),(31,46,37.57,126.98))
        self.assertEqual(row['entries'],1)
        self.assertTrue(migrated.session_valid(session))
        self.assertTrue(migrated.ingest({'device_id':'legacy-sensor'},token,heartbeat=True)['accepted'])
        public_id=migrated.festival()['public_id']
        again=Store(CONFIG)
        self.assertEqual(again.festival()['public_id'],public_id)
        self.assertEqual(len(again.list_festivals()),1)
    def test_festival_delete_requires_name_and_retains_records(self):
        token=self.store.register({'id':'ending-sensor','toilet_id':self.out_toilet},self.outdoor['id'])['token']
        path='/api/festivals/'+str(self.outdoor['id'])
        self.assertEqual(self.request(path,'DELETE',{'confirm_name':self.outdoor['name']},admin=False)[0],401)
        self.assertEqual(self.request(path,'DELETE',{'confirm_name':'wrong'})[0],400)
        self.assertEqual(self.request(path,'DELETE',{'confirm_name':self.outdoor['name']})[0],200)
        self.assertNotIn(self.outdoor['id'],[f['id'] for f in self.store.list_festivals()])
        code,body=self.request('/f/'+self.outdoor['public_id'],admin=False)
        self.assertEqual(code,410);self.assertIn('운영이 종료된 축제입니다',body);self.assertNotIn('야외 A',body)
        self.assertEqual(self.request('/api/status',festival=self.outdoor['id'])[0],410)
        with self.assertRaises(Problem) as error:self.store.ingest({'device_id':'ending-sensor'},token,heartbeat=True)
        self.assertEqual(error.exception.status,401)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) n FROM toilets WHERE festival_id=?',(self.outdoor['id'],)).fetchone()['n'],1)
            self.assertEqual(db.execute("SELECT count(*) n FROM devices WHERE id='ending-sensor'").fetchone()['n'],1)
        self.assertEqual(len(self.store.snapshot(festival_id=self.indoor['id'])['toilets']),1)
    def test_deleting_legacy_festival_keeps_admin_creation_and_assets_working(self):
        legacy=self.store.festival()
        self.assertEqual(self.request('/api/festivals/1','DELETE',{'confirm_name':legacy['name']})[0],200)
        self.assertEqual(self.request('/')[0],410)
        self.assertEqual(self.request('/admin')[0],200)
        self.assertEqual(self.request('/api/festivals')[0],200)
        self.assertEqual(self.request('/api/health')[0],200)
        self.assertEqual(self.request('/api/version')[0],200)
        self.assertEqual(self.request('/app.js')[0],200)
        self.assertEqual(self.request('/api/festivals','POST',{'name':'삭제 후 새 축제','mode':'indoor'})[0],201)
        reloaded=Store(CONFIG)
        self.assertNotIn(1,[f['id'] for f in reloaded.list_festivals()])
        with self.assertRaises(Problem) as error:reloaded.festival(1)
        self.assertEqual(error.exception.status,410)
        # Demo initialization must also avoid reactivating the deleted legacy festival.
        demo_config=CONFIG.copy();demo_config['demo_database']=CONFIG['database']
        Store(demo_config,demo=True)
        self.assertNotIn(1,[f['id'] for f in reloaded.list_festivals()])
    def test_concurrent_delete_preserves_at_least_one_festival(self):
        self.store.delete_festival(self.outdoor['id'],self.outdoor['name'])
        candidates=self.store.list_festivals()
        def remove(f):return self.request('/api/festivals/'+str(f['id']),'DELETE',{'confirm_name':f['name']})[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses=list(pool.map(remove,candidates))
        self.assertEqual(sorted(statuses),[200,409])
        self.assertEqual(len(self.store.list_festivals()),1)
    def test_layout_position_and_metadata_save_independently(self):
        fid=self.indoor['id'];tid=self.in_toilet
        self.assertEqual(self.request(f'/api/layout-position/{tid}','PUT',{'x':65,'y':73},fid)[0],200)
        row=self.store.snapshot(festival_id=fid)['toilets'][0]
        self.assertEqual((row['x'],row['y'],row['name'],row['stalls']),(65,73,'실내 A',3))
        self.assertEqual(self.request(f'/api/toilet-info/{tid}','PUT',{'name':'실내 새 이름','stalls':5},fid)[0],200)
        row=self.store.snapshot(festival_id=fid)['toilets'][0]
        self.assertEqual((row['x'],row['y'],row['name'],row['stalls']),(65,73,'실내 새 이름',5))
        self.assertEqual(self.request(f'/api/layout-position/{tid}','PUT',{'x':20,'y':30},self.outdoor['id'])[0],404)
        self.assertEqual(self.request(f'/api/toilet-info/{tid}','PUT',{'name':'bad','stalls':2},self.outdoor['id'])[0],404)
        self.assertEqual(self.request(f'/api/layout-position/{tid}','PUT',{'x':True,'y':30},fid)[0],400)
        self.assertEqual(self.request(f'/api/toilet-info/{tid}','PUT',{'name':'bad','stalls':0},fid)[0],400)
