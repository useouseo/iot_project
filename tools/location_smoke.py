"""Location retry and route regression checks, using browser geolocation/TMAP doubles."""
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import make_server
from outdoor_smoke import SDK
from playwright.sync_api import sync_playwright

GEO=r'''
window.testGeo={calls:0,latitude:37.57,longitude:126.98,accuracy:15,timestamp:Date.now(),fail:0};
window.emitLocation=()=>({coords:{latitude:testGeo.latitude,longitude:testGeo.longitude,accuracy:testGeo.accuracy},timestamp:testGeo.timestamp});
Object.defineProperty(navigator,'geolocation',{value:{
 getCurrentPosition(ok,fail,options){testGeo.calls++;testGeo.options=options;queueMicrotask(()=>testGeo.fail?fail({code:testGeo.fail}):ok(emitLocation()));},
 watchPosition(ok){window.testWatchSuccess=ok;queueMicrotask(()=>ok(emitLocation()));return 1;},
 clearWatch(){}
}});
'''

def run():
    store=Mock();store.festival.return_value=dict(id=1,name='테스트 축제',mode='outdoor',public_id='test-outdoor',map=None);store.list_festivals.return_value=[dict(id=1,name='테스트 축제',mode='outdoor',public_id='test-outdoor')];store.map_mode.return_value='outdoor';store.snapshot.return_value=dict(settings={},demo=True,updated_at=time.time(),toilets=[dict(id=1,name='화장실 A',stalls=4,x=50,y=50,latitude=37.58,longitude=126.99,level='quiet',online=True,quality='good',score=.2,congestion_percent=10,last_seen=time.time(),device_id='demo-1')])
    server=make_server('127.0.0.1',0,store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
            page=browser.new_page(bypass_csp=True)
            page.add_init_script(GEO)
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.route('https://apis.openapi.sk.com/**',lambda r:r.fulfill(body=SDK,content_type='application/javascript'))
            page.route('**/api/map-config*',lambda r:r.fulfill(json=dict(map_key='test',routing=True)))
            routes=[]
            def route(r):
                routes.append(r.request.post_data_json)
                r.fulfill(json=dict(lines=[[[126.98,37.57],[126.99,37.58]]],distance=120,seconds=90))
            page.route('**/api/route*',route)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function('testGeo.calls===1 && !document.getElementById("geo-route").disabled')
            page.evaluate('testGeo.latitude=37.571;testGeo.timestamp=Date.now()')
            page.locator('#geo-locate').click()
            page.wait_for_function('testGeo.calls===2 && !document.getElementById("geo-locate").disabled')
            assert page.evaluate('testGeo.options.maximumAge')==0
            # An old position refreshes before routing, without stopping at the old 60s cutoff.
            page.evaluate('testGeo.timestamp=Date.now()-120000;testWatchSuccess(emitLocation());testGeo.latitude=37.572;testGeo.timestamp=Date.now()')
            page.locator('#geo-route').click()
            page.wait_for_function('document.getElementById("outdoor-message").textContent.includes("120m")')
            assert page.evaluate('testGeo.calls')==3
            assert routes[-1]['latitude']==37.572
            page.locator('#geo-route').click()
            # A large error can be declined or explicitly accepted.
            page.evaluate('testGeo.accuracy=500;testGeo.timestamp=Date.now();testWatchSuccess(emitLocation())')
            page.once('dialog',lambda d:d.dismiss());page.locator('#geo-route').click()
            page.wait_for_function('!document.getElementById("geo-route").disabled')
            assert len(routes)==1
            page.once('dialog',lambda d:d.accept());page.locator('#geo-route').click()
            page.wait_for_function('document.getElementById("outdoor-message").textContent.includes("120m")')
            assert len(routes)==2
            page.locator('#geo-route').click()
            # A timeout retains the last fix and permits using it with explicit confirmation.
            page.evaluate('testGeo.timestamp=Date.now()-120000;testWatchSuccess(emitLocation());testGeo.fail=3')
            page.locator('#geo-locate').click()
            page.wait_for_function('!document.getElementById("geo-locate").disabled')
            assert not page.locator('#geo-route').is_disabled()
            page.once('dialog',lambda d:d.accept());page.locator('#geo-route').click()
            page.wait_for_function('document.getElementById("outdoor-message").textContent.includes("120m")')
            assert len(routes)==3
            # Revoked permissions clear the stored position and prevent routing.
            page.evaluate('testGeo.fail=1')
            page.locator('#geo-locate').click()
            page.wait_for_function('document.getElementById("outdoor-message").textContent.includes("권한")')
            assert page.locator('#geo-route').is_disabled()
            assert not errors,errors
            print('PASS: fresh retry, uncached location, stale auto-refresh, accuracy confirmation, timeout fallback, permission denial')
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    with patch.dict(os.environ,{'RESTFLOW_TMAP_MAP_KEY':'test'}):run()
