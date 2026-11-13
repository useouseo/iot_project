"""Browser tests for persisted festival modes and the single route toggle button."""
import copy
import base64
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
from location_smoke import GEO
from playwright.sync_api import sync_playwright

def run():
    state=dict(settings={'map_mode':'outdoor'},demo=True,updated_at=time.time(),toilets=[dict(id=i,name=f'화장실 {chr(64+i)}',stalls=4,x=20+i*20,y=30+i*10,latitude=37.57+i*.001,longitude=126.98+i*.001,level='quiet',online=True,quality='good',score=.2,congestion_percent=10,last_seen=time.time(),device_id=f'demo-{i}') for i in range(1,3)])
    store=Mock();store.snapshot.side_effect=lambda:copy.deepcopy(state);store.map_mode.side_effect=lambda:state['settings']['map_mode']
    store.session_valid.return_value=True
    def setmode(mode):state['settings']['map_mode']=mode;return {'saved':True,'map_mode':mode}
    store.set_map_mode.side_effect=setmode
    server=make_server('127.0.0.1',0,store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':390,'height':844},bypass_csp=True,has_touch=True)
            context.add_init_script(GEO)
            context.route('https://apis.openapi.sk.com/**',lambda r:r.fulfill(body=SDK,content_type='application/javascript'))
            context.route('**/api/admin',lambda r:r.fulfill(json=dict(devices=[],visitor_url='',automatic_visitor_url='')))
            context.route('**/api/health',lambda r:r.fulfill(json=dict(ok=True,auth_mode='password')))
            context.route('**/api/history?*',lambda r:r.fulfill(json=[]))
            def upload(r):
                state['settings']['map']=r.request.post_data_json['image'];r.fulfill(json={'saved':True})
            context.route('**/api/map',upload)
            def save_indoor(r):
                tid=int(r.request.url.rsplit('/',1)[1]);next(t for t in state['toilets'] if t['id']==tid).update(r.request.post_data_json);r.fulfill(json={'saved':True})
            context.route('**/api/toilets/*',save_indoor)
            routes=[]
            def route(r):routes.append(r.request.post_data_json);r.fulfill(json=dict(lines=[[[126.98,37.57],[126.99,37.58]]],distance=120,seconds=90))
            context.route('**/api/route',route)
            visitor=context.new_page();errors=[];visitor.on('pageerror',lambda e:errors.append(str(e)))
            base=f'http://127.0.0.1:{server.server_port}'
            visitor.goto(base)
            visitor.wait_for_function('!document.getElementById("geo-route").disabled')
            assert visitor.locator('.outdoor-tools button').count()==2
            # Real DOM click, independent of the SDK listener, selects a map marker.
            visitor.locator('.geo-pin[data-facility-id="2"]').click()
            assert visitor.locator('.geo-pin.selected').get_attribute('data-facility-id')=='2'
            # Simulate an SDK overlay that consumes clicks and pointer events above visible pins.
            visitor.evaluate("""()=>{const layer=document.createElement('div');layer.id='sdk-touch-layer';layer.style.cssText='position:absolute;inset:0;z-index:999;background:transparent';for(const type of ['click','pointerup'])layer.addEventListener(type,e=>e.stopImmediatePropagation());document.getElementById('outdoor-map').append(layer);}""")
            for tid in ('1','2'):
                pin=visitor.locator(f'.geo-pin[data-facility-id="{tid}"]')
                pin.scroll_into_view_if_needed();rect=pin.bounding_box()
                visitor.touchscreen.tap(rect['x']+rect['width']/2,rect['y']+rect['height']/2)
                assert visitor.locator('.geo-pin.selected').get_attribute('data-facility-id')==tid
                assert f'화장실 {chr(64+int(tid))}' in visitor.locator('#outdoor-detail').inner_text()
            # A pan starting on a marker must not change the selected destination.
            visitor.evaluate("""()=>{const pin=document.querySelector('.geo-pin[data-facility-id="1"]'),rect=pin.getBoundingClientRect(),layer=document.getElementById('sdk-touch-layer');layer.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:101,isPrimary:true,clientX:rect.x+10,clientY:rect.y+10}));layer.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,pointerId:101,isPrimary:true,clientX:rect.x+60,clientY:rect.y+10}));}""")
            assert visitor.locator('.geo-pin.selected').get_attribute('data-facility-id')=='2'
            visitor.evaluate("document.getElementById('sdk-touch-layer').remove()")

            visitor.locator('#geo-route').click()
            visitor.wait_for_function('document.getElementById("geo-route").textContent==="경로 지우기"')
            assert routes[-1]['toilet_id']==2
            assert visitor.locator('.outdoor-tools button').count()==2
            buttons=visitor.locator('.outdoor-tools button');a,b=buttons.nth(0).bounding_box(),buttons.nth(1).bounding_box()
            assert abs(a['y']-b['y'])<1 and abs(a['height']-b['height'])<1
            visitor.locator('#geo-route').click();assert visitor.locator('#geo-route').inner_text()=='길찾기'
            assert len(routes)==1
            visitor.locator('#geo-route').click();visitor.wait_for_function('document.getElementById("geo-route").textContent==="경로 지우기"')
            visitor.locator('.geo-pin[data-facility-id="1"]').click()
            assert visitor.locator('#geo-route').inner_text()=='길찾기'
            admin=context.new_page();admin.on('pageerror',lambda e:errors.append(str(e)))
            admin.goto(base+'/admin');admin.locator('#map-mode').wait_for()
            assert '작은 흐름' not in admin.locator('.event-context').inner_text()
            # Cancellation keeps outdoor mode.
            admin.once('dialog',lambda d:d.dismiss());admin.select_option('#map-mode','indoor')
            assert state['settings']['map_mode']=='outdoor'
            admin.once('dialog',lambda d:d.accept());admin.select_option('#map-mode','indoor')
            admin.wait_for_function('document.body.classList.contains("mode-indoor")')
            admin.evaluate("window.openAdminView('facilities')")
            assert admin.locator('#map-surface').is_visible()
            assert admin.locator('.upload-label').is_visible()
            assert not admin.locator('.outdoor-section').is_visible()
            assert admin.evaluate('testGeo.calls')==0
            assert not admin.evaluate('Boolean(window.Tmapv2)')
            png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6uoAAAAASUVORK5CYII=')
            admin.locator('#map-upload').set_input_files({'name':'layout.png','mimeType':'image/png','buffer':png})
            admin.wait_for_function('document.getElementById("event-map").src.startsWith("data:image/png")')
            # Current visitor polls the new mode and reloads into the indoor layout.
            visitor.evaluate('window.rerenderRestflow()')
            visitor.reload();visitor.wait_for_function('document.body.classList.contains("mode-indoor")')
            assert visitor.locator('#map-surface').is_visible()
            assert not visitor.locator('.outdoor-tools').is_visible()
            assert visitor.evaluate('testGeo.calls')==0
            # Indoor markers remain selectable and draggable by admins.
            visitor.locator('#markers [data-id="2"]').click()
            assert visitor.locator('#markers [data-id="2"]').get_attribute('aria-pressed')=='true'
            before=copy.deepcopy(state['toilets'])
            marker=admin.locator('#markers [data-id="1"]');rect=marker.bounding_box();surface=admin.locator('#map-surface').bounding_box()
            admin.mouse.move(rect['x']+rect['width']/2,rect['y']+rect['height']/2);admin.mouse.down();admin.mouse.move(surface['x']+surface['width']*.7,surface['y']+surface['height']*.6,steps=6);admin.mouse.up()
            assert admin.evaluate('window.hasUnsavedDesignChanges()')
            admin.locator('#save-settings').click()
            admin.wait_for_function('!window.hasUnsavedDesignChanges()')
            assert state['toilets'][0]['x']!=before[0]['x']
            assert state['toilets'][0]['latitude']==before[0]['latitude']
            saved_indoor=copy.deepcopy(state['toilets'])
            admin.once('dialog',lambda d:d.accept());admin.select_option('#map-mode','outdoor')
            admin.wait_for_function('document.body.classList.contains("mode-outdoor")')
            assert admin.locator('#outdoor-map').is_visible()
            assert state['toilets']==saved_indoor
            assert state['settings']['map'].startswith('data:image/png')
            assert not errors,errors
            assert visitor.evaluate('document.documentElement.scrollWidth<=innerWidth')
            print('PASS: DOM selection and mobile taps through SDK overlay, pan exclusion, route toggle, destination change, two mobile buttons, mode cancel/save, indoor upload/selection/drag, no indoor GPS/SDK, coordinate preservation')
            browser.close()
    finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    with patch.dict(os.environ,{'RESTFLOW_TMAP_MAP_KEY':'test','RESTFLOW_TMAP_ROUTE_KEY':'test-route'}):run()
