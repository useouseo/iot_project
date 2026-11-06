import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from deploy.configure import configure
from server import environment_secret, load_db_config


class DeploymentPreparationTests(unittest.TestCase):
    def test_configuration_preserves_credentials_and_keeps_them_out_of_env(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertTrue(configure(root,'restflow.example.com','ops@example.com','chosen-admin-password'))
            before={p.name:p.read_bytes() for p in (root/'.secrets').iterdir()}
            self.assertFalse(configure(root,'new.example.com','ops@example.com','replacement-password'))
            self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'.secrets').iterdir()})
            env=(root/'.env').read_text()
            for value in before.values():self.assertNotIn(value.decode().strip(),env)
            self.assertEqual((root/'.secrets').stat().st_mode & 0o777,0o700)
            self.assertIn('RESTFLOW_DOMAIN=new.example.com',env)

    def test_invalid_domain_or_email_creates_no_configuration(self):
        for domain,email in [('https://example.com','ops@example.com'),('127.0.0.1','ops@example.com'),
                             ('localhost','ops@example.com'),('example.com','bad\nEMAIL=x')]:
            with self.subTest(domain=domain),tempfile.TemporaryDirectory() as folder:
                with self.assertRaises(ValueError):configure(folder,domain,email,'valid-admin-password')
                self.assertFalse((Path(folder)/'.secrets').exists())

    def test_partial_credentials_are_not_silently_regenerated(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.secrets').mkdir()
            existing=root/'.secrets/db_password';existing.write_text('do-not-replace')
            with self.assertRaises(ValueError):configure(root,'example.com','ops@example.com','password-123')
            self.assertEqual(existing.read_text(),'do-not-replace')

    def test_secret_file_takes_precedence_without_leaking_to_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);secret=root/'password';secret.write_text('file-password\n')
            config=root/'db.json';config.write_text(json.dumps(dict(host='localhost',user='app',database='live',demo_database='demo')))
            with patch.dict(os.environ,{'RESTFLOW_DB_PASSWORD':'old-password','RESTFLOW_DB_PASSWORD_FILE':str(secret)},clear=True):
                self.assertEqual(load_db_config(config)['password'],'file-password')
                secret.unlink()
                with self.assertRaises(SystemExit) as error:environment_secret('RESTFLOW_DB_PASSWORD')
                self.assertNotIn('old-password',str(error.exception))
