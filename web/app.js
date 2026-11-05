'use strict';
const $ = id => document.getElementById(id);
const adminPage = location.pathname === '/admin';
const labels = {quiet:'여유',moderate:'보통',busy:'혼잡',unknown:'확인 필요'};
let token = '', snapshot = null, selected = 1, dirty = false, refreshing = false;
const elem = (tag, text, cls) => { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e; };
const localTime = at => at ? new Date(at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '수신 기록 없음';
function notice(message, error=false) { $('notice').hidden=false; $('notice').textContent=message; $('notice').className=error?'error':''; }
async function api(path,method='GET',body) {
  const res=await fetch(path,{method,headers:{...(token?{Authorization:`Bearer ${token}`} : {}),...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(8000)});
  const data=await res.json(); if(!res.ok)throw new Error(data.error||`요청 실패 (${res.status})`); return data;
}
function current() { return snapshot?.toilets.find(t=>t.id===selected); }
function select(id, scroll=false) {
  if(dirty && id!==selected && !confirm('저장하지 않은 설정을 버리고 다른 화장실을 선택할까요?'))return;
  if(id!==selected) { selected=id;dirty=false; }
  render(); fillForm();
  if(adminPage&&token)loadHistory();
  if(scroll)$('cards').querySelector(`[data-id="${id}"]`)?.scrollIntoView({block:'nearest',behavior:'smooth'});
}
function render() {
  if(!snapshot)return;
  $('banner').hidden=!snapshot.demo;
  $('banner').textContent='시연 모드 · 모든 통행량과 장치 상태는 시뮬레이션 데이터입니다. 실제 현장 측정값이 아닙니다.';
  $('event-map').src=snapshot.settings.map||'/map.svg';
  document.querySelector('.badge').textContent=snapshot.settings.map?'등록된 배치도':'예시 배치도';
  document.querySelector('.map-stamp').hidden=Boolean(snapshot.settings.map);
  $('markers').replaceChildren();$('cards').replaceChildren();
  $('toilet-count').textContent=`총 ${snapshot.toilets.length}곳`;
  const online=snapshot.toilets.filter(t=>t.online).length;
  $('connection').textContent=`${online}/${snapshot.toilets.length}곳 센서 연결`;
  $('updated').textContent=`${localTime(snapshot.updated_at)} KST 갱신`;
  for(const t of snapshot.toilets) {
    const mark=elem('button',undefined,`marker ${t.level}${t.id===selected?' selected':''}`);
    mark.style.left=`${t.x}%`;mark.style.top=`${t.y}%`;
    mark.append(elem('span',String.fromCharCode(64+t.id)),elem('small',labels[t.level]));
    mark.setAttribute('aria-label',`${t.name}, ${labels[t.level]}`);mark.setAttribute('aria-pressed',String(t.id===selected));
    mark.addEventListener('click',e=>{e.stopPropagation();select(t.id,true);});$('markers').append(mark);
    const card=elem('button',undefined,`toilet-card${t.id===selected?' selected':''}`);card.dataset.id=t.id;
    card.setAttribute('aria-pressed',String(t.id===selected));
    const top=elem('div',undefined,'card-top'), name=elem('div',undefined,'card-name');
    name.append(elem('strong',t.name),elem('small',`운영 ${t.stalls}칸 · ${t.device_id?'센서 연결 시설':'장치 등록 대기'}`));
    top.append(elem('span',String.fromCharCode(64+t.id),'letter'),name,elem('span',labels[t.level],`status ${t.level}`));
    const bottom=elem('div',undefined,'card-bottom');
    bottom.append(elem('span',t.online?(t.quality==='good'?'● 정상 수신':'● 측정 신뢰도 확인 필요'):'○ 수신 대기 / 연결 끊김'),elem('span',`마지막 수신 ${localTime(t.last_seen)}`));
    card.append(top,bottom);card.addEventListener('click',()=>select(t.id));$('cards').append(card);
  }
  if(adminPage&&token) {
    const sel=$('selected-toilet'); const previous=sel.value;
    sel.replaceChildren(...snapshot.toilets.map(t=>{const o=elem('option',t.name);o.value=t.id;return o;}));sel.value=String(selected);
    $('simulate').hidden=!snapshot.demo;
    $('device-status').replaceChildren();
    for(const t of snapshot.toilets) {
      const line=elem('div',undefined,'device-line');
      line.append(elem('strong',t.name),elem('span',t.device_id||'미등록'),elem('span',t.online?'온라인':'오프라인'),elem('span',`품질: ${t.quality||'미확인'}`),elem('span',`마지막 수신 ${localTime(t.last_seen)}`));
      $('device-status').append(line);
    }
    if(!dirty)fillForm();
  }
}
function fillForm(){const t=current();if(!t)return;$('selected-toilet').value=t.id;$('toilet-name').value=t.name;$('stalls').value=t.stalls;$('map-x').value=t.x;$('map-y').value=t.y;}
async function refresh(){
  if(refreshing)return;refreshing=true;
  try {snapshot=await api('/api/status');render();if(adminPage&&token)await loadHistory();}
  catch(e){$('connection').textContent='서버 연결 확인 필요';$('updated').textContent='갱신 실패 · 이전 상태를 사용하지 마세요';notice(e.message,true);
    document.querySelectorAll('.status').forEach(el=>{el.className='status unknown';el.textContent='갱신 실패';});
    document.querySelectorAll('.marker').forEach(el=>{el.className='marker unknown';el.querySelector('small').textContent='수신 오류';});
  }finally{refreshing=false;}
}
async function loadHistory(){
  try{
    const rows=await api(`/api/history?toilet_id=${selected}`),max=Math.max(1,...rows.flatMap(r=>[r.in,r.out]));
    $('history').replaceChildren();
    for(const row of rows){const g=elem('div',undefined,'bar-group');g.setAttribute('aria-label',`${localTime(row.at)} 입장 ${row.in}, 퇴장 ${row.out}`);g.title=g.getAttribute('aria-label');
      const i=elem('div',undefined,'bar'),o=elem('div',undefined,'bar out');i.style.height=`${row.in/max*90}%`;o.style.height=`${row.out/max*90}%`;
      g.append(i,o,elem('small',new Date(row.at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false})));$('history').append(g);}
  }catch(e){notice(e.message,true);}
}
async function action(fn){try{await fn();}catch(e){notice(e.message,true);}}
$('visitor-link').classList.toggle('active',!adminPage);$('admin-link').classList.toggle('active',adminPage);
if(adminPage){$('title').textContent='현장의 흐름을, 한눈에.';$('subtitle').textContent='화장실 위치와 운영 정보, 센서 연결 상태를 관리하세요.';$('login-panel').hidden=false;$('workspace').hidden=true;}
$('login-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  token=$('admin-token').value.trim();
  try{await api('/api/admin');}catch(err){token='';throw err;}
  $('admin-token').value='';$('login-panel').hidden=true;$('workspace').hidden=false;$('admin-panel').hidden=false;
  notice('관리자 인증이 완료되었습니다.');await refresh();fillForm();
});});
$('logout').addEventListener('click',()=>{token='';$('admin-panel').hidden=true;$('workspace').hidden=true;$('login-panel').hidden=false;$('device-token').value='';$('device-result').hidden=true;notice('로그아웃했습니다.');});
$('refresh').addEventListener('click',refresh);
$('selected-toilet').addEventListener('change',()=>select(Number($('selected-toilet').value)));
$('toilet-form').addEventListener('input',()=>dirty=true);
$('map-surface').addEventListener('click',e=>{
  if(!adminPage||!token)return;
  const rect=$('map-surface').getBoundingClientRect();
  $('map-x').value=Math.min(97,Math.max(3,Math.round((e.clientX-rect.left)/rect.width*100)));
  $('map-y').value=Math.min(97,Math.max(3,Math.round((e.clientY-rect.top)/rect.height*100)));dirty=true;
  notice('좌표를 입력했습니다. 설정 저장을 누르면 위치가 반영됩니다.');
});
$('toilet-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  await api(`/api/toilets/${selected}`,'PUT',{name:$('toilet-name').value,stalls:Number($('stalls').value),x:Number($('map-x').value),y:Number($('map-y').value)});
  dirty=false;notice('화장실 설정을 저장했습니다.');await refresh();
});});
$('device-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  const data=await api('/api/devices','POST',{id:$('device-id').value,toilet_id:selected});
  $('device-token').value=data.token;$('device-result').hidden=false;$('device-id').value='';notice('장치를 등록했습니다. 발급된 토큰을 안전하게 보관하세요.');await refresh();
});});
$('dismiss-token').addEventListener('click',()=>{$('device-token').value='';$('device-result').hidden=true;});
$('map-upload').addEventListener('change',()=>action(async()=>{
  const f=$('map-upload').files[0];if(!f)return;
  if(f.size>2_000_000||!['image/png','image/jpeg'].includes(f.type))throw new Error('2MB 이하 PNG/JPEG 파일을 선택하세요.');
  const image=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(new Error('파일을 읽지 못했습니다'));r.readAsDataURL(f);});
  await api('/api/map','PUT',{image});notice('행사장 배치도를 저장했습니다.');await refresh();
}));
$('reset').addEventListener('click',()=>{if(confirm('선택한 화장실의 현재 혼잡도 계산 구간을 초기화할까요? 원본 통행 기록은 유지됩니다.'))action(async()=>{await api('/api/reset','POST',{toilet_id:selected});notice('계산 구간을 초기화했습니다.');await refresh();});});
$('simulate').addEventListener('click',()=>action(async()=>{await api('/api/demo','POST',{});notice('시연 통행 데이터를 추가했습니다.');await refresh();}));
$('qr-button').addEventListener('click',()=>action(async()=>{
  const response=await fetch('/api/qr.svg');if(!response.ok){const error=await response.json();throw new Error(error.error);}
  // CSP permits same-origin SVG via a data URI, avoiding an external QR service.
  const reader=new FileReader();reader.onload=()=>{$('qr-image').src=reader.result;$('qr-image').hidden=false;};reader.readAsDataURL(await response.blob());
}));
refresh();setInterval(refresh,5000);
