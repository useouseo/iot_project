"""Run against a dedicated MariaDB database configured with RESTFLOW_DB_*."""
import secrets
import time
import unittest

import server


class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.init_db()
        server.app.testing = True

    def test_sensor_fan_and_capacity(self):
        client = server.app.test_client()
        suffix = secrets.token_hex(4)

        def call(method, path, data=None, key=None, code=200):
            headers = {'Authorization': 'Bearer ' + key} if key else {}
            response = client.open(path, method=method, json=data, headers=headers)
            self.assertEqual(response.status_code, code, (path, response.get_data(as_text=True)))
            return response.get_json()

        pid = call('POST','/api/setup/places',
                   dict(name='통합검증',address='주소',lat=37.5,lon=127), code=201)['id']
        setup = f'/api/setup/places/{pid}'
        facility = f'/api/facility/{pid}'
        device = 'sensor-' + suffix
        try:
            call('POST','/api/setup/register',
                 dict(place_id=pid,kind='shared',zone_name='공용',device='module-'+suffix,total=5), code=201)
            zone = next(p for p in call('GET','/api/setup')['places'] if p['id']==pid)['zones'][0]['id']
            claim = call('POST',setup+'/claim',{})['claim']
            password = 'manager-test'
            call('POST',facility+'/claim',dict(claim=claim,password=password))
            call('POST',setup+'/claim',{},code=409)
            call('PUT',facility+'/zones',dict(zones=[dict(id=zone,open=4,closed=False)]),password)
            keys = call('POST',setup+'/equipment',dict(zone_id=zone,device_id=device))
            sensor, fan = keys['sensor_token'], keys['fan_token']
            now = time.time()
            for seq in range(1,7):
                event = dict(device_id=device,seq=seq,boot_id='A',direction='in',occurred_at=now)
                call('POST','/api/events',event,sensor)
            self.assertTrue(call('POST','/api/events',event,sensor)['duplicate'])
            command = f'/api/fan-command?device_id={device}'
            call('GET',command,key=sensor,code=401)
            self.assertGreaterEqual(call('GET',command,key=fan)['pwm_percent'],60)
            env = dict(device_id=device,temperature_c=25,humidity_pct=82,occurred_at=now)
            call('POST','/api/environment',env,sensor)
            self.assertEqual(call('GET',command,key=fan)['pwm_percent'],100)
            call('POST','/api/fan-status',dict(device_id=device,applied_percent=100,ok=True,mode='drying'),fan)

            def public():
                places = call('GET','/api/places')['places']
                return next(p for p in places if p['id']==pid)['zones'][0]['sensor']

            self.assertEqual(public(),dict(state='normal',online=True,entries=6))
            call('PUT',facility+'/zones',dict(zones=[dict(id=zone,open=2,closed=False)]),password)
            self.assertEqual(public()['state'],'busy')
            private = call('GET',facility+'/equipment',key=password)['equipment'][0]
            self.assertEqual(private['fan_status']['applied_percent'],100)
            call('GET',facility+'/equipment',code=401)
            call('POST',facility+'/equipment/reset',dict(zone_id=zone,confirmed_empty=True),password)
            control = server.app.config['TELEMETRY']
            env.update(humidity_pct=45)
            call('POST','/api/environment',env,sensor)
            with control.connect() as db:
                db.execute('UPDATE occupancy_state SET last_event_at=? WHERE toilet_id=?',
                           (now-400,private['toilet_id']))
            self.assertEqual(call('GET',command,key=fan)['mode'],'standby')
            self.assertEqual(call('GET',command,key=fan)['pwm_percent'],30)
            with control.connect() as db:
                db.execute('UPDATE occupancy_state SET last_event_at=? WHERE toilet_id=?',
                           (now-1000,private['toilet_id']))
            self.assertEqual(call('GET',command,key=fan)['pwm_percent'],0)
            settings_url = facility+'/equipment/settings'
            auto = dict(zone_id=zone,mode='auto',target_humidity=50,idle_saving=False)
            call('PUT',settings_url,auto,code=401)
            call('PUT',settings_url,dict(auto,target_humidity=100),password,code=400)
            updated = call('PUT',settings_url,auto,password)
            self.assertEqual(updated['settings']['high_humidity'],60)
            self.assertEqual(call('GET',command,key=fan)['pwm_percent'],100)
            with control.connect() as db:
                db.execute('UPDATE events SET occurred_at=? WHERE device_id=?',(now-601,device))
            self.assertEqual(call('GET',command,key=fan)['pwm_percent'],30)
            for humidity, expected in [(50,60),(59,60),(60,100)]:
                env.update(humidity_pct=humidity,occurred_at=time.time())
                call('POST','/api/environment',env,sensor)
                self.assertEqual(call('GET',command,key=fan)['pwm_percent'],expected)
            manual = dict(zone_id=zone,mode='manual',manual_percent=40)
            result = call('PUT',settings_url,manual,password)
            self.assertEqual(result['fan_status']['applied_percent'],100)
            self.assertEqual(call('GET',command,key=fan)['pwm_percent'],40)
            call('POST','/api/fan-status',dict(device_id=device,applied_percent=40,ok=True,mode='manual'),fan)
            result = call('GET',facility+'/equipment',key=password)['equipment'][0]
            self.assertEqual(result['fan_status']['applied_percent'],40)
            call('PUT',settings_url,dict(auto,idle_saving=True),password)
            env.update(humidity_pct=45,occurred_at=time.time())
            call('POST','/api/environment',env,sensor)
            self.assertEqual(call('GET',command,key=fan)['pwm_percent'],0)
            sensor_only = 'sensor-only-' + suffix
            scope = dict(zone_id=None,device_id=sensor_only)
            only = call('POST',setup+'/equipment',dict(scope,fan_enabled=False,reissue=False))
            self.assertNotIn('fan_token',only)
            sensor_only_key = only['sensor_token']
            payload = dict(device_id=sensor_only,boot_id='first')
            call('POST','/api/heartbeat',payload,sensor_only_key)
            sensor_only_command = f'/api/fan-command?device_id={sensor_only}'
            call('GET',sensor_only_command,key=sensor_only_key,code=401)
            call('PUT',settings_url,dict(manual,zone_id=None),password,code=409)
            status = call('GET',facility+'/equipment',key=password)['equipment']
            self.assertFalse(next(item for item in status if item['device_id']==sensor_only)['fan_enabled'])
            added = call('POST',setup+'/equipment',dict(scope,enable_fan=True))
            self.assertNotIn('sensor_token',added)
            call('POST','/api/heartbeat',payload,sensor_only_key)
            call('GET',sensor_only_command,key=added['fan_token'])
            call('POST',setup+'/equipment',dict(zone_id=zone,device_id=device,reissue=False),code=409)
            call('POST','/api/heartbeat',dict(device_id=device,boot_id='B'),sensor)
            self.assertGreaterEqual(call('GET',command,key=fan)['pwm_percent'],60)
        finally:
            call('DELETE',setup)
        call('GET',command,key=fan,code=401)


if __name__ == '__main__':
    unittest.main()
