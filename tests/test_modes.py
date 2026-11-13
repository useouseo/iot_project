"""Settings persistence and HTTP contracts; SQLite is a settings-only test adapter."""
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from server import Store,make_server

class Connection:
    def __init__(self,path):
        self.db=sqlite3.connect(path);self.db.row_factory=sqlite3.Row
    def __enter__(self):return self
    def __exit__(self,*args):self.db.commit();self.db.close()
    def execute(self,sql,args=()):
        sql=sql.replace('ON DUPLICATE KEY UPDATE `value`=VALUES(`value`)','ON CONFLICT(`key`) DO UPDATE SET `value`=excluded.`value`')
        return self.db.execute(sql,args)

class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        path=Path(self.temp.name)/'settings.db'
        with Connection(path) as db:
            db.execute('CREATE TABLE settings (`key` TEXT PRIMARY KEY, value TEXT)')
            db.execute("INSERT INTO settings VALUES ('map','data:image/png;base64,saved-layout')")
            db.execute('CREATE TABLE toilets (id INT,x INT,y INT,latitude REAL,longitude REAL)')
            db.execute('INSERT INTO toilets VALUES (1,22,28,37.57,126.98)')
        self.store=Store.__new__(Store);self.store.demo=False;self.store.connect=lambda:Connection(path)
        self.store.session_valid=lambda token:token=='test-admin'
        def snapshot():
            with self.store.connect() as db:
                return {'settings':{r['key']:r['value'] for r in db.execute('SELECT * FROM settings')},'toilets':[dict(r) for r in db.execute('SELECT * FROM toilets')]}
        self.store.snapshot=snapshot
        self.server=make_server('127.0.0.1',0,self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        env=patch.dict(os.environ,{'RESTFLOW_TMAP_MAP_KEY':'test-map-key','RESTFLOW_TMAP_ROUTE_KEY':'test-route-key'},clear=True);env.start();self.addCleanup(env.stop)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,method='GET',body=None,admin=True):
        req=Request(f'http://127.0.0.1:{self.server.server_port}'+path,method=method,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'Cookie':'restflow_admin=test-admin'} if admin else {})})
        try:
            with urlopen(req) as response:return response.status,response.read().decode()
        except HTTPError as e:return e.code,e.read().decode()
    def test_default_and_html_sdk(self):
        self.assertEqual(self.store.map_mode(),'outdoor')
        code,html=self.request('/')
        self.assertEqual(code,200);self.assertIn('tmap/jsv2',html)
        self.assertIn('mode-outdoor',html);self.assertIn('modes-v1',html)
    def test_authorization_and_invalid_mode(self):
        self.assertEqual(self.request('/api/map-mode','PUT',{'map_mode':'indoor'},False)[0],401)
        self.assertEqual(self.request('/api/map-mode','PUT',{'map_mode':'wrong'})[0],400)
        self.assertEqual(self.store.map_mode(),'outdoor')
    def test_switch_preserves_layout_and_both_coordinates(self):
        before=self.store.snapshot()
        self.assertEqual(self.request('/api/map-mode','PUT',{'map_mode':'indoor'})[0],200)
        self.assertEqual(self.store.map_mode(),'indoor')
        code,html=self.request('/')
        self.assertEqual(code,200);self.assertIn('mode-indoor',html);self.assertNotIn('tmap/jsv2',html)
        self.assertEqual(json.loads(self.request('/api/map-config')[1])['map_mode'],'indoor')
        self.assertEqual(self.request('/api/route','POST',{'latitude':37.56,'longitude':126.97,'toilet_id':1})[0],409)
        self.assertEqual(self.request('/api/map-mode','PUT',{'map_mode':'outdoor'})[0],200)
        after=self.store.snapshot()
        self.assertEqual(before['toilets'],after['toilets'])
        self.assertEqual(before['settings']['map'],after['settings']['map'])
        # Read from a second Store against the same persisted settings file.
        other=Store.__new__(Store);other.connect=self.store.connect
        self.assertEqual(other.map_mode(),'outdoor')
    def test_version_endpoint_identifies_assets_without_keys(self):
        status,body=self.request('/api/version')
        self.assertEqual(status,200);self.assertIn('modes-v1',body)
        self.assertNotIn('test-map-key',body);self.assertNotIn('test-route-key',body)
