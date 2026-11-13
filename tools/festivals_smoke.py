"""Full multi-festival browser flow using a disposable MariaDB and simulated TMAP/GPS.
Set RESTFLOW_TEST_DB_CONFIG (or RESTFLOW_DB_CONFIG), then run this script.
"""
import base64
import io
import json
import os
from pathlib import Path
import shutil
import sys
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import mariadb
from server import Store,make_server,load_db_config
from outdoor_smoke import SDK
from location_smoke import GEO
from playwright.sync_api import sync_playwright


def run():
    config=load_db_config(os.environ.get('RESTFLOW_TEST_DB_CONFIG'))
    config['database']+='_browser_test';config['demo_database']+='_browser_test'
    conn=mariadb.connect(**{k:config[k] for k in ('host','port','user','password')});conn.cursor().execute(f'CREATE DATABASE IF NOT EXISTS `{config["database"]}`');conn.commit();conn.close()
    store=Store(config,reset_schema=True)
    with store.connect() as db:db.execute('UPDATE toilets SET latitude=37.57+id*.001,longitude=126.98+id*.001')
    session=store.login('1234');server=make_server('127.0.0.1',0,store,'https://festival.example.org')
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
            context=browser.new_context(viewport={'width':1440,'height':1000},bypass_csp=True,has_touch=True)
            context.add_cookies([{'name':'restflow_admin','value':session,'domain':'127.0.0.1','path':'/'}]);context.add_init_script(GEO)
            context.route('https://apis.openapi.sk.com/**',lambda r:r.fulfill(body=SDK,content_type='application/javascript'))
            errors=[];admin=context.new_page();admin.on('pageerror',lambda e:errors.append(str(e)))
            base=f'http://127.0.0.1:{server.server_port}'
            admin.goto(base+'/admin');admin.locator('#add-festival').wait_for()
            def add_festival(name,mode):
                admin.locator('#add-festival').click();admin.locator('#festival-name').fill(name)
                admin.locator(f'input[name="festival-mode"][value="{mode}"]').check()
                with admin.expect_response(lambda r:'/api/festivals' in r.url and r.request.method=='POST') as created:
                    admin.locator('#create-festival').click()
                response=created.value
                assert response.status==201,response.text()
                fid=next(f['id'] for f in store.list_festivals() if f['name']==name)
                admin.wait_for_url('**/admin?festival_id='+str(fid))
                admin.wait_for_function('document.getElementById("festival-select").value==='+json.dumps(str(fid)))
                return int(admin.url.rsplit('=',1)[1])
            indoor_id=add_festival('별빛 실내 축제','indoor')
            assert store.snapshot(festival_id=indoor_id)['toilets']==[]
            admin.evaluate("window.openAdminView('facilities')")
            assert admin.locator('#map-surface').is_visible();assert not admin.locator('.outdoor-section').is_visible()
            assert admin.evaluate('testGeo.calls')==0
            admin.locator('#new-toilet-name').fill('실내 전용 화장실');admin.locator('#new-toilet-stalls').fill('5');admin.locator('#new-toilet-form button').click()
            admin.wait_for_function('document.getElementById("selected-toilet").options.length===1')
            png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6uoAAAAASUVORK5CYII=')
            admin.locator('#map-upload').set_input_files({'name':'layout.png','mimeType':'image/png','buffer':png})
            admin.wait_for_function('document.getElementById("event-map").src.startsWith("data:image/png")')
            marker=admin.locator('#markers .marker');r=marker.bounding_box();surface=admin.locator('#map-surface').bounding_box()
            admin.mouse.move(r['x']+r['width']/2,r['y']+r['height']/2);admin.mouse.down();admin.mouse.move(surface['x']+surface['width']*.7,surface['y']+surface['height']*.6,steps=6);admin.mouse.up()
            with admin.expect_response(lambda r:'/api/toilets/' in r.url and r.request.method=='PUT') as saved:
                admin.locator('#save-settings').click()
            assert saved.value.status==200,saved.value.text()
            admin.wait_for_function('!window.hasUnsavedDesignChanges()')
            admin.evaluate("window.openAdminView('devices')")
            tid=store.snapshot(festival_id=indoor_id)['toilets'][0]['id']
            admin.select_option('#device-toilet',str(tid));admin.locator('#device-id').fill('indoor-sensor')
            with admin.expect_response(lambda r:'/api/devices' in r.url and r.request.method=='POST') as registered:
                admin.locator('#device-form button').click()
            assert registered.value.status==201,registered.value.text()
            admin.locator('#device-result').wait_for()
            assert len(store.all_devices(festival_id=indoor_id))==1
            admin.evaluate("window.openAdminView('qr')");admin.locator('#qr-button').click();admin.locator('#qr-result').wait_for()
            indoor=store.festival(indoor_id);inside_url=admin.locator('#qr-destination').inner_text()
            assert inside_url=='https://festival.example.org/f/'+indoor['public_id']
            visitor=context.new_page();visitor.on('pageerror',lambda e:errors.append(str(e)));visitor.goto(base+'/f/'+indoor['public_id'])
            visitor.locator('#markers .marker').wait_for()
            assert visitor.locator('#subtitle').inner_text()=='별빛 실내 축제'
            assert visitor.locator('#cards').inner_text().find('실내 전용 화장실')>=0
            assert visitor.evaluate('testGeo.calls')==0
            assert not visitor.evaluate('Boolean(window.Tmapv2)')
            assert visitor.locator('a.brand').first.get_attribute('href')=='/f/'+indoor['public_id']
            admin.select_option('#festival-select','1');admin.wait_for_url('**/admin?festival_id=1')
            admin.wait_for_function('Boolean(window.openAdminView)');admin.wait_for_function('document.getElementById("festival-select").value==="1"')
            assert len(store.snapshot()['toilets'])==2
            assert admin.locator('#visitor-link').get_attribute('href')=='/f/'+store.festival()['public_id']
            admin.evaluate("window.openAdminView('qr')");admin.locator('#qr-button').click();admin.locator('#qr-result').wait_for()
            assert admin.locator('#qr-destination').inner_text()!=inside_url
            outdoor_id=add_festival('봄빛 야외 축제','outdoor')
            admin.evaluate("window.openAdminView('facilities')")
            admin.locator('#new-toilet-name').fill('야외 전용 화장실');admin.locator('#new-toilet-form button').click()
            admin.locator('.geo-pin.unplaced').wait_for()
            admin.evaluate("""()=>{const m=testMarkers.findLast(m=>!m.removed&&m.options.draggable);m.emit('dragstart');m.point=new Tmapv2.LatLng(37.58,126.99);m.emit('dragend');}""")
            admin.locator('#geo-save').click();admin.wait_for_function('!window.outdoor.hasDraft()')
            outdoor=store.festival(outdoor_id)
            outdoor_visitor=context.new_page();outdoor_visitor.on('pageerror',lambda e:errors.append(str(e)))
            outdoor_visitor.set_viewport_size({'width':390,'height':844});outdoor_visitor.goto(base+'/f/'+outdoor['public_id'])
            outdoor_visitor.locator('.geo-pin').wait_for();outdoor_visitor.wait_for_function('!document.getElementById("geo-route").disabled')
            pin=outdoor_visitor.locator('.geo-pin');pin.scroll_into_view_if_needed();r=pin.bounding_box();outdoor_visitor.touchscreen.tap(r['x']+r['width']/2,r['y']+r['height']/2)
            response={'features':[{'geometry':{'type':'Point'},'properties':{'totalDistance':120,'totalTime':90}},{'geometry':{'type':'LineString','coordinates':[[126.98,37.57],[126.99,37.58]]}}]}
            with patch('server._route_next',0),patch('server.urlopen',return_value=io.BytesIO(json.dumps(response).encode())) as tmap:
                outdoor_visitor.locator('#geo-route').click();outdoor_visitor.wait_for_function('document.getElementById("geo-route").textContent==="경로 지우기"')
                assert json.loads(tmap.call_args.args[0].data)['endX']==126.99
            outdoor_visitor.locator('#geo-route').click();assert outdoor_visitor.locator('#geo-route').inner_text()=='길찾기'
            assert outdoor_visitor.locator('.outdoor-tools button').count()==2
            assert visitor.locator('#subtitle').inner_text()=='별빛 실내 축제'
            visitor.reload();visitor.locator('#markers .marker').wait_for()
            assert visitor.locator('#cards').inner_text().find('실내 전용 화장실')>=0
            reloaded=Store(config)
            assert len(reloaded.list_festivals())==3
            assert reloaded.snapshot(festival_id=indoor_id)['settings']['map'].startswith('data:image/png')
            assert len(reloaded.all_devices(festival_id=outdoor_id))==0
            assert len(reloaded.snapshot(festival_id=outdoor_id)['toilets'])==1
            assert not errors,errors
            assert outdoor_visitor.evaluate('document.documentElement.scrollWidth<=innerWidth')
            print('PASS: create indoor/outdoor festivals, isolated toilets/maps/sensors, indoor drag save, per-festival QR generation, pinned visitors, outdoor marker tap/route toggle, restart persistence')
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()
        conn=mariadb.connect(**{k:config[k] for k in ('host','port','user','password')});conn.cursor().execute(f'DROP DATABASE `{config["database"]}`');conn.commit();conn.close()

if __name__=='__main__':
    with patch.dict(os.environ,{'RESTFLOW_TMAP_MAP_KEY':'test','RESTFLOW_TMAP_ROUTE_KEY':'test-route'}):run()
