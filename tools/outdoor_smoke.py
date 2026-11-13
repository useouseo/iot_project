"""Browser regression checks with a test double for TMAP (no API key required).
Run: python tools/outdoor_smoke.py. Requires Playwright and Chromium.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import make_server
from playwright.sync_api import sync_playwright

SDK = r'''
window.testMarkers=[];
class Point {constructor(lat,lng){this.a=lat;this.b=lng;}lat(){return this.a;}lng(){return this.b;}}
class Events {constructor(){this.events={};}addListener(name,fn){this.events[name]=fn;}emit(name,e){this.events[name]?.(e);}}
class TestMap extends Events {
 constructor(id,options){super();this.center=options.center;this.container=document.getElementById(id);this.container.style.position='relative';window.testMap=this;}
 getCenter(){return this.center;}setCenter(p){this.center=p;}setZoom(){}resize(){}fitBounds(){}
}
class Marker extends Events {
 constructor(options){super();this.options=options;this.point=options.position;this.node=document.createElement('div');this.node.innerHTML=options.iconHTML;this.node.style.cssText='position:absolute;left:'+(100+testMarkers.length*90)+'px;top:130px';options.map.container.append(this.node);testMarkers.push(this);}
 getPosition(){return this.point;}setMap(map){if(!map){this.node.remove();this.removed=true;}}
}
class Overlay {constructor(){}setMap(){}extend(){}}
window.Tmapv2={Map:TestMap,Marker,LatLng:Point,Size:class{},Circle:Overlay,Polyline:Overlay,LatLngBounds:Overlay};
'''

def run():
    toilets=[dict(id=i,name=f'화장실 {chr(64+i)}',stalls=4,x=50,y=50,latitude=37.57+i*.001 if i<3 else None,longitude=126.98 if i<3 else None,level=['quiet','moderate','busy'][i-1],online=True,quality='good',score=.2,congestion_percent=10,last_seen=time.time(),device_id=f'demo-{i}') for i in range(1,4)]
    state=dict(demo=True,settings={},updated_at=time.time(),toilets=toilets)
    store=Mock();store.snapshot.side_effect=lambda:copy.deepcopy(state)
    server=make_server('127.0.0.1',0,store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    saved=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'),args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1000},bypass_csp=True)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.route('https://apis.openapi.sk.com/**',lambda r:r.fulfill(body=SDK,content_type='application/javascript'))
            page.route('**/api/map-config',lambda r:r.fulfill(json=dict(map_key='test',routing=True)))
            page.route('**/api/admin',lambda r:r.fulfill(json=dict(devices=[],visitor_url='',automatic_visitor_url='')))
            page.route('**/api/health',lambda r:r.fulfill(json=dict(ok=True,auth_mode='password')))
            page.route('**/api/history?*',lambda r:r.fulfill(json=[]))
            def save(route):
                values=route.request.post_data_json
                tid=int(route.request.url.rsplit('/',1)[1]);saved.append((tid,values))
                next(t for t in state['toilets'] if t['id']==tid).update(values)
                route.fulfill(json={'saved':True})
            page.route('**/api/coordinates/*',save)
            page.goto(f'http://127.0.0.1:{server.server_port}/admin')
            page.wait_for_function('Boolean(window.outdoor && window.testMap && window.openAdminView)')
            page.evaluate("window.openAdminView('facilities')")
            page.locator('.geo-pin.selected').wait_for()
            assert page.locator('.geo-pin.selected .geo-letter').inner_text()=='A'
            def drag(lat,lng):
                page.evaluate('''([lat,lng])=>{const marker=testMarkers.findLast(m=>!m.removed&&m.options.draggable);marker.emit('dragstart');window.rerenderRestflow();if(marker.removed)throw Error('Refresh removed a dragging marker');marker.point=new Tmapv2.LatLng(lat,lng);marker.emit('dragend');}''',[lat,lng])
                page.wait_for_function('window.outdoor.hasDraft()')
            drag(37.58,126.99)
            # A periodic refresh must not replace the dragged draft with persisted coordinates.
            page.evaluate('window.rerenderRestflow()')
            assert page.locator('#geo-lat').input_value()=='37.58'
            assert not saved
            page.locator('#geo-undo').click()
            assert not page.evaluate('window.outdoor.hasDraft()')
            assert abs(float(page.locator('#geo-lat').input_value())-37.571)<1e-8
            drag(37.582,126.992)
            page.locator('#geo-save').click()
            page.wait_for_function('!window.outdoor.hasDraft()')
            assert saved==[(1,dict(latitude=37.582,longitude=126.992))],saved
            # A new facility gets an unplaced marker without implicitly persisting map center.
            page.evaluate('window.chooseOutdoorFacility(3)')
            assert page.locator('.geo-pin.selected.unplaced .geo-letter').inner_text()=='C'
            assert not page.evaluate('window.outdoor.hasDraft()')
            drag(37.59,127.0)
            page.once('dialog',lambda d:d.dismiss())
            assert page.evaluate('window.chooseOutdoorFacility(2)') is False
            assert page.locator('.geo-pin.selected .geo-letter').inner_text()=='C'
            page.locator('#geo-save').click();page.wait_for_function('!window.outdoor.hasDraft()')
            assert saved[-1]==(3,dict(latitude=37.59,longitude=127.0))
            page.reload();page.wait_for_function('Boolean(window.outdoor && window.testMap && window.openAdminView)')
            page.evaluate("window.openAdminView('facilities');window.chooseOutdoorFacility(3)")
            assert page.locator('#geo-lat').input_value()=='37.59'
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.wait_for_function('window.testMap && window.testMarkers.length>=3')
            assert page.locator('.geo-pin').count()==3
            assert not page.evaluate('testMarkers.some(m=>!m.removed&&m.options.draggable)')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert not errors,errors
            print('PASS: pin labels, drag draft, refresh persistence, undo, save, unplaced marker, selection guard, reload persistence, visitor read-only markers, mobile layout')
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    with patch.dict(os.environ,{'RESTFLOW_TMAP_MAP_KEY':'test'}):run()
