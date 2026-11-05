"""Real Chromium checks against a disposable demo DB and HTTP server."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import tempfile
import shutil
import re
import threading
from playwright.sync_api import sync_playwright, expect
from server import Store,make_server

root=Path(__file__).resolve().parents[1]
shots=root/'docs'/'screenshots';shots.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as folder:
    server=make_server('127.0.0.1',0,Store(Path(folder)/'demo.sqlite3',True))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=shutil.which("chromium") or p.chromium.executable_path,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            url=f'http://127.0.0.1:{server.server_port}'
            page.goto(url);page.wait_for_selector('.toilet-card')
            assert page.locator('.toilet-card').count()==3
            assert not page.locator('#admin-link').is_visible()
            assert page.locator('#banner').is_visible()
            assert page.locator('.status.quiet').count()==1
            assert page.locator('.status.moderate').count()==1
            assert page.locator('.status.busy').count()==1
            page.locator('.marker').nth(1).click();assert 'selected' in page.locator('.toilet-card').nth(1).get_attribute('class')
            page.screenshot(path=str(shots/'visitor-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(shots/'visitor-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.set_viewport_size({'width':1440,'height':1100});page.goto(url+'/admin')
            assert '1234' not in page.locator('#login-panel').inner_text()
            page.route('**/api/health',lambda route:route.fulfill(json={'ok':True,'demo':True}))
            page.locator('#admin-password').fill('1234');page.locator('#login-form button').click()
            expect(page.locator('#notice')).to_contain_text('이전 서버가 실행 중입니다')
            assert page.locator('#login-panel').is_visible()
            page.unroute('**/api/health')
            page.locator('#login-form button').click()
            page.wait_for_selector('#admin-panel:not([hidden])')
            def drag_marker(dx,dy):
                marker=page.locator('.marker[data-id="1"]');marker.scroll_into_view_if_needed();box=marker.bounding_box()
                x=box['x']+box['width']/2;y=box['y']+box['height']/2
                page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+dx,y+dy,steps=8);page.mouse.up()
            drag_marker(90,40)
            draft=(int(page.locator('#map-x').input_value()),int(page.locator('#map-y').input_value()))
            assert draft!=(22,28)
            assert server.store.snapshot()['toilets'][0]['x']==22 # not saved yet
            page.locator('#refresh').click()
            expect(page.locator('#map-x')).to_have_value(str(draft[0]))
            page.locator('#undo-position').click();expect(page.locator('#map-x')).to_have_value('22')
            drag_marker(60,20)
            page.locator('.marker[data-id="1"]').press('ArrowRight')
            saved=(int(page.locator('#map-x').input_value()),int(page.locator('#map-y').input_value()))
            page.locator('#save-position').click();expect(page.locator('#save-position')).to_be_disabled()
            assert (server.store.snapshot()['toilets'][0]['x'],server.store.snapshot()['toilets'][0]['y'])==saved
            # Cancelling a gesture restores the previous position without saving.
            marker=page.locator('.marker[data-id="1"]');marker.scroll_into_view_if_needed();box=marker.bounding_box()
            page.mouse.move(box['x']+10,box['y']+10);page.mouse.down();page.mouse.move(box['x']+70,box['y']+35,steps=4)
            page.locator('#map-surface').dispatch_event('pointercancel',{'pointerId':1,'isPrimary':True})
            page.mouse.up();expect(page.locator('#map-x')).to_have_value(str(saved[0]));expect(page.locator('#save-position')).to_be_disabled()
            page.locator('#toilet-name').fill('동문 화장실');page.locator('#stalls').fill('6')
            page.locator('#toilet-form button').click();expect(page.locator('.card-name strong').first).to_have_text('동문 화장실')
            expect(page.locator('#visitor-url')).to_have_value(url)
            page.locator('#visitor-url').fill('https://festival.example.org/guide')
            page.locator('#qr-button').click();page.wait_for_selector('#qr-image:not([hidden])')
            assert page.locator('#qr-image').get_attribute('src').startswith('data:image/svg+xml')
            with page.expect_download() as result:page.locator('#qr-png-download').click()
            png=result.value;png.save_as(str(Path(folder)/'qr.png'));assert (Path(folder)/'qr.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            with page.expect_download() as result:page.locator('#qr-svg-download').click()
            svg=result.value;svg.save_as(str(Path(folder)/'qr.svg'));assert b'<svg' in (Path(folder)/'qr.svg').read_bytes()
            page.screenshot(path=str(shots/'admin-desktop.png'),full_page=True)
            page.locator('#map-upload').set_input_files({'name':'tiny.png','mimeType':'image/png','buffer':__import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==')})
            expect(page.locator('#event-map')).to_have_attribute('src',re.compile(r'^data:image/png'))
            # Facilities can be added and deleted without a fixed count.
            page.locator('#new-toilet-name').fill('서문 화장실');page.locator('#new-toilet-stalls').fill('5');page.locator('#new-toilet-form button').click()
            expect(page.locator('.toilet-card')).to_have_count(4)
            expect(page.locator('#toilet-name')).to_have_value('서문 화장실')
            page.once('dialog',lambda dialog:dialog.accept());page.locator('#delete-toilet').click()
            expect(page.locator('.toilet-card')).to_have_count(3)
            page.locator('#current-password').fill('1234');page.locator('#new-password').fill('changed-5678');page.locator('#confirm-password').fill('changed-5678')
            page.locator('#password-form button').click();expect(page.locator('#notice')).to_contain_text('비밀번호를 변경했습니다')
            page.reload();page.wait_for_selector('#admin-panel:not([hidden])') # cookie survives reload
            page.locator('#logout').click();expect(page.locator('#login-panel')).to_be_visible()
            page.locator('#admin-password').fill('1234');page.locator('#login-form button').click();expect(page.locator('#notice')).to_contain_text('올바르지')
            page.locator('#admin-password').fill('changed-5678');page.locator('#login-form button').click();page.wait_for_selector('#admin-panel:not([hidden])')
            page.locator('#logout').click();expect(page.locator('#login-panel')).to_be_visible()
            page.goto(url);page.wait_for_selector('.toilet-card')
            page.route('**/api/status',lambda route:route.abort())
            page.locator('#refresh').click();expect(page.locator('.status').first).to_have_text('갱신 실패')
            # Touch gestures use Chromium's real input pipeline on a mobile viewport.
            context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            mobile=context.new_page();mobile.on('pageerror',lambda err:errors.append(str(err)))
            mobile.goto(url+'/admin');mobile.locator('#admin-password').fill('changed-5678');mobile.locator('#login-form button').click()
            mobile.wait_for_selector('#admin-panel:not([hidden])');mobile.locator('.marker[data-id="1"]').scroll_into_view_if_needed()
            expect(mobile.locator('#map-x')).to_have_value(str(saved[0]))
            marker=mobile.locator('.marker[data-id="1"]').bounding_box();x=marker['x']+marker['width']/2;y=marker['y']+marker['height']/2
            cdp=context.new_cdp_session(mobile)
            cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0}]})
            for step in range(1,6):cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+step*7,'y':y+step*3,'id':0}]})
            cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            expect(mobile.locator('#save-position')).to_be_enabled()
            touch_x=int(mobile.locator('#map-x').input_value());assert touch_x!=saved[0]
            mobile.locator('#save-position').click();expect(mobile.locator('#save-position')).to_be_disabled()
            assert server.store.snapshot()['toilets'][0]['x']==touch_x
            assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
            # Deleting every facility leaves a usable empty state on mobile.
            for remaining in (2,1,0):
                mobile.once('dialog',lambda dialog:dialog.accept());mobile.locator('#delete-toilet').click()
                expect(mobile.locator('.toilet-card')).to_have_count(remaining)
            expect(mobile.locator('#toilet-name')).to_be_disabled()
            mobile.locator('#new-toilet-name').fill('다시 추가한 화장실');mobile.locator('#new-toilet-form button').click()
            expect(mobile.locator('.toilet-card')).to_have_count(1)
            expect(mobile.locator('#toilet-name')).to_have_value('다시 추가한 화장실')
            context.close()
            assert not errors,errors
            browser.close()
        print('Browser PASS: visitor, selection, mobile overflow, password login/change/logout, facility add/delete/empty/re-add, drag/undo/keyboard/cancel/polling, touch drag, map upload, QR PNG/SVG downloads, server failure; screenshots saved.')
    finally:
        server.shutdown();server.server_close();worker.join()
