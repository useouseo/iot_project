from playwright.sync_api import sync_playwright,expect
from pathlib import Path
import json,time,threading,http.server,functools,copy,io,sys,shutil
import qrcode,qrcode.image.svg
root=Path(__file__).resolve().parents[1]/'web';shots=Path(__file__).resolve().parents[1]/'work'/'responsive-check';shots.mkdir(parents=True,exist_ok=True)
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
 browser=p.chromium.launch(executable_path=shutil.which('chromium') or p.chromium.executable_path,args=['--no-sandbox']);page=browser.new_page(viewport={'width':1200,'height':900});page.route('**/api/**',route)
 page.goto('http://127.0.0.1:8765/admin');page.locator('#admin-password').fill('1234');page.locator('#login-form button').click();page.locator('.side-link[data-view="facilities"]').click()
 problems=[]
 for width in [390,850,1000,1150,1151,1160,1180,1200,1240,1280,1366,1440,1600,1840]:
  page.set_viewport_size({'width':width,'height':900});page.wait_for_timeout(80)
  panel=page.locator('.form-stack>.panel').first.bounding_box()
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
  for id in ['delete-toilet','cancel-edit','save-settings']:
   b=page.locator('#'+id).bounding_box()
   if b['x']<panel['x'] or b['x']+b['width']>panel['x']+panel['width']+1 or b['y']+b['height']>panel['y']+panel['height']+1:problems.append((width,id))
 assert not problems,problems
 print('PASS: delete/cancel/save stay inside panels at all 14 widths, including previously failing 1151–1366px')
 page.set_viewport_size({'width':1200,'height':900});page.wait_for_timeout(100);page.screenshot(path=str(shots/'responsive-1200-fixed.png'),full_page=True)
 page.locator('.coordinate-details summary').click();page.wait_for_timeout(100)
 panel=page.locator('.form-stack>.panel').first.bounding_box()
 for id in ['delete-toilet','cancel-edit','save-settings']:
  b=page.locator('#'+id).bounding_box();assert b['x']>=panel['x'] and b['x']+b['width']<=panel['x']+panel['width']+1
 page.locator('#toilet-name').fill('중간 너비 저장');page.locator('#save-settings').click();expect(page.locator('#notice')).to_contain_text('저장했습니다')
 print('PASS: expanded coordinate section and form save at 1200px')
 browser.close()
server.shutdown()
