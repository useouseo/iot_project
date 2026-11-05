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
    server=make_server('127.0.0.1',0,Store(Path(folder)/'demo.sqlite3',True),'browser-smoke-test-token','https://event.example.org')
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=shutil.which("chromium") or p.chromium.executable_path,args=['--no-sandbox'])
            page=browser.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
            errors=[];page.on('pageerror',lambda err:errors.append(str(err)))
            url=f'http://127.0.0.1:{server.server_port}'
            page.goto(url);page.wait_for_selector('.toilet-card')
            assert page.locator('.toilet-card').count()==3
            assert page.locator('#banner').is_visible()
            assert page.locator('.status.quiet').count()==1
            assert page.locator('.status.moderate').count()==1
            assert page.locator('.status.busy').count()==1
            page.locator('.marker').nth(1).click();assert 'selected' in page.locator('.toilet-card').nth(1).get_attribute('class')
            page.screenshot(path=str(shots/'visitor-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(shots/'visitor-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.set_viewport_size({'width':1440,'height':1100});page.goto(url+'/admin')
            page.locator('#admin-token').fill('browser-smoke-test-token');page.locator('#login-form button').click()
            page.wait_for_selector('#admin-panel:not([hidden])')
            page.locator('#toilet-name').fill('동문 화장실');page.locator('#stalls').fill('6')
            page.locator('#toilet-form button').click();expect(page.locator('.card-name strong').first).to_have_text('동문 화장실')
            page.locator('#qr-button').click();page.wait_for_selector('#qr-image:not([hidden])')
            assert page.locator('#qr-image').get_attribute('src').startswith('data:image/svg+xml')
            page.screenshot(path=str(shots/'admin-desktop.png'),full_page=True)
            page.locator('#map-upload').set_input_files({'name':'tiny.png','mimeType':'image/png','buffer':__import__('base64').b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg==')})
            expect(page.locator('#event-map')).to_have_attribute('src',re.compile(r'^data:image/png'))
            page.locator('#logout').click();assert page.locator('#login-panel').is_visible()
            page.goto(url);page.wait_for_selector('.toilet-card')
            page.route('**/api/status',lambda route:route.abort())
            page.locator('#refresh').click();expect(page.locator('.status').first).to_have_text('갱신 실패')
            assert not errors,errors
            browser.close()
        print('Browser PASS: visitor, selection, mobile overflow, admin login/save/logout, map upload, QR, server failure; screenshots saved.')
    finally:
        server.shutdown();server.server_close();worker.join()
