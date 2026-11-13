import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError
from server import geo_coordinate, pedestrian_route, Problem

class OutdoorTests(unittest.TestCase):
    def setUp(self):
        self.store=Mock();self.store.festival.return_value=dict(id=1,name='테스트 축제',mode='outdoor',public_id='test-outdoor',map=None);self.store.map_mode.return_value='outdoor'
        self.store.snapshot.return_value={'toilets':[dict(id=1,latitude=37.57,longitude=126.98)]}
        self.data=dict(latitude=37.56,longitude=126.97,toilet_id=1)
        self.env=patch.dict(os.environ,{'RESTFLOW_TMAP_ROUTE_KEY':'test-server-key'},clear=True)
        self.env.start();self.addCleanup(self.env.stop)
        self.clock=patch('server._route_next',0);self.clock.start();self.addCleanup(self.clock.stop)
    def test_invalid_coordinates(self):
        for value in (True,None,'37',float('nan'),float('inf'),91):
            with self.subTest(value=value), self.assertRaises(Problem):geo_coordinate(value,-90,90)
    def test_missing_key(self):
        with patch.dict(os.environ,{},clear=True), self.assertRaises(Problem) as error:pedestrian_route(self.store,self.data)
        self.assertEqual(error.exception.status,503)
    def test_unregistered_destination(self):
        self.store.snapshot.return_value['toilets'][0]['latitude']=None
        with self.assertRaises(Problem) as error:pedestrian_route(self.store,self.data)
        self.assertEqual(error.exception.status,409)
    def test_tmap_coordinates_and_summary(self):
        response={'features':[{'geometry':{'type':'Point'},'properties':{'totalDistance':120,'totalTime':90}}, {'geometry':{'type':'LineString','coordinates':[[126.97,37.56],[126.98,37.57]]}}]}
        with patch('server.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as fetch:
            result=pedestrian_route(self.store,self.data)
        body=json.loads(fetch.call_args.args[0].data)
        self.assertEqual((body['startX'],body['startY']),(126.97,37.56))
        self.assertEqual((body['endX'],body['endY']),(126.98,37.57))
        self.assertEqual((result['distance'],result['seconds']),(120,90))
        self.assertNotIn('test-server-key',json.dumps(result))
    def test_provider_failure_is_sanitized(self):
        with patch('server.urlopen',side_effect=URLError('test-server-key')), self.assertRaises(Problem) as error:pedestrian_route(self.store,self.data)
        self.assertEqual(error.exception.status,502)
        self.assertNotIn('test-server-key',error.exception.message)
    def test_rate_limit(self):
        with patch('server._route_next',float('inf')),self.assertRaises(Problem) as error:pedestrian_route(self.store,self.data)
        self.assertEqual(error.exception.status,429)

    def test_browser_policy_upgrades_http_map_tiles(self):
        import threading
        from urllib.request import urlopen
        from server import make_server
        server=make_server('127.0.0.1',0,self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with urlopen(f'http://127.0.0.1:{server.server_port}/api/map-config') as response:
                policy=response.headers['Content-Security-Policy']
                self.assertIn('upgrade-insecure-requests',policy)
                self.assertIn('https://*.tmap.co.kr',policy)
                self.assertNotIn('test-server-key',response.read().decode())
        finally:
            server.shutdown();server.server_close();thread.join()
