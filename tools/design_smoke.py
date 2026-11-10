from playwright.sync_api import sync_playwright,expect
from pathlib import Path
import json,time,threading,http.server,functools,copy,io,sys,shutil
import qrcode,qrcode.image.svg
root=Path(__file__).resolve().parents[1]/'web';shots=Path(__file__).resolve().parents[1]/'work'/'design-check';shots.mkdir(parents=True,exist_ok=True)
class Handler(http.server.SimpleHTTPRequestHandler):
 def do_GET(self):
  if self.path=='/admin':self.path='/index.html'
  return super().do_GET()
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',8765),functools.partial(Handler,directory=str(root)))
threading.Thread(target=server.serve_forever,daemon=True).start()
now=time.time();toilets=[dict(id=i+1,name=n,stalls=4,x=x,y=y,level=l,online=True,quality='good',device_id=f'demo-{i+1}',last_seen=now) for i,(n,x,y,l) in enumerate([('동문 화장실',22,28,'quiet'),('화장실 B',78,46,'moderate'),('화장실 C',28,81,'busy')])]

for t,score in zip(toilets,[1.3,.4,2.8]):t.update(score=score,congestion_percent={1:55,2:20,3:85}[t['id']])
toilets[0]['level']='moderate';toilets[1]['level']='quiet'
snap=dict(toilets=toilets,updated_at=now,demo=True,settings={})
state={'auth':False};errors=[]
def route(r):
 path=r.request.url.split('/api/')[1].split('?')[0];method=r.request.method;body=r.request.post_data_json if method!='GET' and r.request.post_data else {}
 status=200;data={}
 if path=='health':data={'auth_mode':'password','demo':True,'ok':True}
 elif path=='admin':
  if not state['auth']:status=401;data={'error':'로그인 필요'}
  else:data={'automatic_visitor_url':'http://127.0.0.1:8765'}
 elif path=='login':state['auth']=True
 elif path=='logout':state['auth']=False
 elif path=='status':data=snap
 elif path=='history':data=[{'at':now-(11-i)*600,'in':(i*7)%23,'out':(i*5)%17} for i in range(12)]
 elif path.startswith('toilets/'):
  tid=int(path.split('/')[1]);t=next(t for t in toilets if t['id']==tid)
  if method=='DELETE':toilets.remove(t)
  else:t.update(body)
 elif path=='toilets':
  tid=max([t['id'] for t in toilets]+[0])+1;toilets.append(dict(id=tid,x=50,y=50,level='unknown',online=False,quality=None,device_id=None,last_seen=None,**body));data={'id':tid}
 elif path=='devices':data={'token':'test-device-token'}
 elif path=='qr':
  image=qrcode.make('http://127.0.0.1:8765/',image_factory=qrcode.image.svg.SvgPathImage);buf=io.BytesIO();image.save(buf);data={'url':'http://127.0.0.1:8765/','svg':buf.getvalue().decode()}
 elif path=='map':snap['settings']['map']=body['image']
 r.fulfill(status=status,json=data)
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=shutil.which('chromium') or p.chromium.executable_path,args=['--no-sandbox'])
 page=browser.new_page(viewport={'width':1440,'height':900});page.on('pageerror',lambda e:errors.append(str(e)));page.route('**/api/**',route)
 url='http://127.0.0.1:8765'
 def ids():return page.locator('.toilet-card').evaluate_all('(els)=>els.map(e=>Number(e.dataset.id))')
 def view(name):page.locator(f'.side-link[data-view="{name}"]').click();expect(page.locator(f'.admin-view[data-view="{name}"]')).to_be_visible()
 page.goto(url);expect(page.locator('.toilet-card')).to_have_count(3);assert ids()==[2,1,3],ids()
 expect(page.locator('.toilet-card[data-id="2"]')).to_contain_text('20%');expect(page.locator('.toilet-card[data-id="1"]')).to_contain_text('55%');expect(page.locator('.toilet-card[data-id="3"]')).to_contain_text('85%')
 assert page.get_by_role('button',name='확인 필요',exact=True).count()==0
 assert page.locator('.facility-detail').count()==0
 assert not page.locator('.live-summary').is_visible()
 assert page.locator('.marker small:visible').count()==3
 page.get_by_role('button',name='전체',exact=True).click();assert ids()==[1,2,3]
 page.get_by_role('button',name='추천순',exact=True).click();assert ids()==[2,1,3]
 page.screenshot(path=str(shots/'v4-visitor-desktop.png'),full_page=True)
 page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(shots/'v4-visitor-mobile.png'),full_page=True)
 page.set_viewport_size({'width':1440,'height':900});page.goto(url+'/admin');page.locator('#admin-password').fill('1234');page.locator('#login-form button').click();expect(page.locator('.admin-sidebar')).to_be_visible()
 chart=page.locator('.overview-bottom .panel h3').first
 expect(chart).to_have_text('동문 화장실 · 최근 2시간 통행 추이');page.locator('.toilet-card[data-id="2"]').click();expect(chart).to_have_text('화장실 B · 최근 2시간 통행 추이');expect(page.locator('.admin-view[data-view="overview"]')).to_be_visible()
 page.locator('#notice').evaluate('(e)=>e.hidden=true');page.screenshot(path=str(shots/'v4-admin-overview.png'),full_page=True)
 view('facilities');
 for width in [1280,1440,1840]:
  page.set_viewport_size({'width':width,'height':1000});page.wait_for_timeout(80);left=page.locator('.edit-map-slot .map-panel').bounding_box();right=page.locator('.form-stack').bounding_box();surface=page.locator('#map-surface').bounding_box();assert abs(surface['width']/surface['height']-1.7)<.01,(width,surface);assert abs(left['y']-right['y'])<2 and abs(left['y']+left['height']-right['y']-right['height'])<2,(width,left,right)
 page.set_viewport_size({'width':1440,'height':900});
 expect(page.locator('.map-panel>.upload-label')).to_be_visible();assert page.locator('.form-stack .upload-label').count()==0
 boxes=[page.locator('#'+i).bounding_box() for i in ['delete-toilet','cancel-edit','save-settings']];assert max(b['y'] for b in boxes)-min(b['y'] for b in boxes)<2,boxes
 assert boxes[0]['x']<boxes[1]['x']<boxes[2]['x'];assert not page.locator('#save-position').is_visible()
 page.locator('#toilet-name').fill('서쪽 화장실');page.locator('#stalls').fill('6');page.locator('#save-settings').click();expect(page.locator('#notice')).to_contain_text('저장했습니다');assert toilets[1]['name']=='서쪽 화장실'
 marker=page.locator('.marker[data-id="2"]');marker.press('ArrowRight');expect(page.locator('#undo-position')).to_be_enabled();page.locator('#save-settings').click();expect(page.locator('#undo-position')).to_be_disabled();assert toilets[1]['x']==79
 page.locator('#toilet-name').fill('취소');page.locator('#cancel-edit').click();expect(page.locator('#toilet-name')).to_have_value('서쪽 화장실')
 page.screenshot(path=str(shots/'v4-admin-editor.png'),full_page=True)
 page.locator('#new-toilet-name').fill('새 화장실');page.locator('#new-toilet-form button').click();expect(page.locator('#toilet-name')).to_have_value('새 화장실');page.once('dialog',lambda d:d.accept());page.locator('#delete-toilet').click();expect(page.locator('#selected-toilet option')).to_have_count(3)
 view('qr');qr=page.locator('.qr-section').bounding_box();main=page.locator('main').bounding_box();assert abs(qr['x']+qr['width']-(main['x']+main['width']-20))<3,(qr,main)
 page.locator('#qr-button').click();expect(page.locator('#qr-result')).to_be_visible()
 with page.expect_download() as download:page.locator('#qr-png-download').click()
 download.value.save_as(str(shots/'v4-qr-test.png'));assert (shots/'v4-qr-test.png').read_bytes().startswith(b'\x89PNG')
 page.screenshot(path=str(shots/'v4-admin-qr.png'),full_page=True)
 view('devices');expect(page.locator('.device-facility').first).to_have_text('동문 화장실');expect(page.locator('.device-facility').nth(1)).to_have_text('서쪽 화장실');page.screenshot(path=str(shots/'final-device-names.png'),full_page=True);page.locator('#device-toilet').select_option('3');page.locator('#device-id').fill('sensor-new');page.locator('#device-form button').click();expect(page.locator('#device-token')).to_have_value('test-device-token')
 view('settings');page.locator('#current-password').fill('1234');page.locator('#new-password').fill('abcde');page.locator('#confirm-password').fill('abcde');page.locator('#password-form button').click();expect(page.locator('#notice')).to_contain_text('비밀번호を変更' if False else '비밀번호를 변경했습니다')
 for name in ['overview','facilities','devices','qr','settings']:
  view(name);page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),name;page.set_viewport_size({'width':1440,'height':900})
 view('overview');before=page.locator('.map-panel').bounding_box()['height']
 for i in range(4,16):toilets.append(dict(id=i,name=f'추가 시설 {i}',stalls=4,x=10+(i*7)%80,y=25+(i*9)%65,level='unknown',online=False,quality=None,score=0,congestion_percent=None,device_id=None,last_seen=None))
 page.locator('.update-display').click();expect(page.locator('.toilet-card')).to_have_count(15);assert abs(page.locator('.map-panel').bounding_box()['height']-before)<2
 assert page.locator('#cards').evaluate('(e)=>e.scrollHeight>e.clientHeight');page.locator('#cards').evaluate('(e)=>e.scrollTop=e.scrollHeight');scroll=page.locator('#cards').evaluate('(e)=>e.scrollTop');page.locator('.update-display').click();page.wait_for_timeout(150);assert abs(page.locator('#cards').evaluate('(e)=>e.scrollTop')-scroll)<2
 page.goto(url);expect(page.locator('.toilet-card')).to_have_count(15);assert ids()[:3]==[2,1,3];assert page.locator('#cards').evaluate('(e)=>e.scrollHeight>e.clientHeight')
 for t in toilets:t.update(level='unknown',online=False,congestion_percent=None)
 page.locator('#refresh').click();expect(page.locator('.toilet-card').first).to_contain_text('안내 준비');assert page.locator('.recommend-badge').count()==0;assert page.locator('.traffic-progress:visible').count()==0;assert not page.locator('.traffic-percent').filter(has_text='%').count()
 page.route('**/api/status',lambda r:r.abort());page.locator('#refresh').click();expect(page.locator('#notice')).to_have_class('error');page.unroute('**/api/status')
 page.set_viewport_size({'width':390,'height':844});assert page.locator('#cards').evaluate('(e)=>getComputedStyle(e).overflowY')=='visible';assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.goto(url+'/admin');page.locator('#logout').click();expect(page.locator('#login-panel')).to_be_visible()
 assert not errors,errors
 browser.close()
server.shutdown();print('PASS: recommended sorting B/A/C, index20/55/85, unknown-last/no-percent, marker status text, compact/mobile layouts, editor actions baseline and upload under map, unified save/cancel, facility add/delete, full-width QR and PNG download, selected-facility chart, device/password/logout, 15-facility internal scroll and polling preservation; API mocked, actual DB not tested.')
