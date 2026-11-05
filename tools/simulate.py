"""Exercise the real device HTTP contract. State persists for safe retries."""
import argparse
import json
import os
from pathlib import Path
import time
import uuid
from urllib.request import Request,urlopen

p=argparse.ArgumentParser()
p.add_argument('--url',default='http://127.0.0.1:8000')
p.add_argument('--device',required=True)
p.add_argument('--direction',choices=['in','out'],default='in')
p.add_argument('--count',type=int,default=1)
p.add_argument('--state',default='.runtime/simulator.json')
p.add_argument('--heartbeat',action='store_true')
a=p.parse_args()
token=os.environ.get('DEVICE_TOKEN')
if not token:raise SystemExit('발급된 장치 토큰을 DEVICE_TOKEN 환경변수에 설정하세요.')
if not 1<=a.count<=100:raise SystemExit('--count는 1~100입니다')
path=Path(a.state);path.parent.mkdir(parents=True,exist_ok=True)
state=json.loads(path.read_text()) if path.exists() else dict(device=a.device,boot=uuid.uuid4().hex,seq=0,queue=[])
if state['device']!=a.device:raise SystemExit('장치마다 다른 --state 파일을 사용하세요')
def save():
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.replace(path)
def send(route,data):
    r=Request(a.url.rstrip('/')+route,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
    with urlopen(r,timeout=10) as response:return json.load(response)
if not a.heartbeat:
    for _ in range(a.count):
        state['seq']+=1;state['queue'].append(dict(device_id=a.device,boot_id=state['boot'],seq=state['seq'],direction=a.direction,occurred_at=time.time(),quality='good'))
    save()
while state['queue']:
    send('/api/events',state['queue'][0]);state['queue'].pop(0);save()
send('/api/heartbeat',dict(device_id=a.device,quality='good'))
print('전송 완료 · 장치 토큰은 출력하지 않았습니다.')
