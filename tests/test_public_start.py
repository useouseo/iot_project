"""Exercise the launcher with real MariaDB/HTTP and a simulated tunnel process."""
import contextlib
import io
import json
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import URLError

import mariadb
from server import Store, load_db_config, database_name
from tools import public_start


class PublicLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=load_db_config()
        cls.config['database']+='_launcher_test'
        cls.config['demo_database']+='_launcher_test'
        for key in ('database','demo_database'):database_name(cls.config[key])
        db=mariadb.connect(**{key:cls.config[key] for key in ('host','port','user','password')})
        try:
            cur=db.cursor()
            for key in ('database','demo_database'):
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{cls.config[key]}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            db.commit();cur.close()
        finally:db.close()

    @classmethod
    def tearDownClass(cls):
        db=mariadb.connect(**{key:cls.config[key] for key in ('host','port','user','password')})
        try:
            cur=db.cursor()
            for key in ('database','demo_database'):cur.execute(f"DROP DATABASE IF EXISTS `{cls.config[key]}`")
            db.commit();cur.close()
        finally:db.close()

    def test_url_parser_accepts_only_expected_tunnel_hostname(self):
        self.assertEqual(public_start.tunnel_url('Visit https://clear-river-123.trycloudflare.com now'),
                         'https://clear-river-123.trycloudflare.com')
        self.assertIsNone(public_start.tunnel_url('https://evil.example/trycloudflare.com'))

    def exercise(self, demo):
        config=self.config.copy()
        store=Store(config,demo,reset_schema=True)
        changed=store.change_password('1234','existing-password-123')
        store.logout(changed)
        public='https://clear-river-123.trycloudflare.com'
        class Tunnel:
            stdout=io.StringIO('Tunnel created: '+public+'\n')
            stopped=False
            def poll(self):return 0 if self.stopped else None
            def terminate(self):self.stopped=True
            def wait(self,timeout=None):return 0
            def kill(self):self.stopped=True
        tunnel=Tunnel()
        with socket.socket() as probe:
            probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        args=public_start.parser().parse_args((['--demo'] if demo else [])+['--port',str(port)])
        base=f'http://127.0.0.1:{port}'
        def opened(url):
            self.assertEqual(url,base+'/admin')
            with urlopen(base+'/api/health') as response:
                self.assertEqual(json.load(response)['demo'],demo)
            req=Request(base+'/api/login',data=json.dumps({'password':'existing-password-123'}).encode(),
                        headers={'Content-Type':'application/json'})
            with urlopen(req) as response:
                cookie=response.headers['Set-Cookie'].split(';')[0]
            req=Request(base+'/api/qr',data=json.dumps({'url':base}).encode(),
                        headers={'Content-Type':'application/json','Cookie':cookie})
            with urlopen(req) as response:
                result=json.load(response)
            self.assertEqual(result['url'],public)
            self.assertIn('<svg',result['svg'])
            raise KeyboardInterrupt()
        with patch.object(public_start,'sys',SimpleNamespace(platform='win32',executable=sys.executable)), \
             patch.object(public_start,'load_or_setup',return_value=config), \
             patch.object(public_start,'download_tunnel',return_value='unused.exe'), \
             patch.object(public_start.subprocess,'Popen',return_value=tunnel), \
             patch.object(public_start.getpass,'getpass',side_effect=AssertionError('Existing password must be kept')), \
             patch.object(public_start.webbrowser,'open',side_effect=opened), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):public_start.run(args)
        self.assertTrue(tunnel.stopped)
        with self.assertRaises((URLError,OSError)):
            urlopen(base+'/api/health',timeout=1)
        reloaded=Store(config,demo)
        session=reloaded.login('existing-password-123')
        self.assertTrue(reloaded.session_valid(session))
        reloaded.logout(session)

    def test_live_launch_qr_password_preservation_and_cleanup(self):self.exercise(False)
    def test_demo_launch_qr_password_preservation_and_cleanup(self):self.exercise(True)
