'use strict';
const $ = id => document.getElementById(id);
const adminPage = location.pathname === '/admin';
const labels = {quiet:'여유',moderate:'보통',busy:'혼잡',unknown:'확인 필요'};
let authenticated = false, snapshot = null, selected = 1, dirty = false, refreshing = false;
let positionDraft = null, drag = null, suppressMapClickUntil = 0;
const elem = (tag, text, cls) => { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e; };
const localTime = at => at ? new Date(at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '수신 기록 없음';
function notice(message, error=false) { $('notice').hidden=false; $('notice').textContent=message; $('notice').className=error?'error':''; }
async function api(path,method='GET',body) {
  const res=await fetch(path,{method,headers:{...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(8000)});
  const data=await res.json();
  if(!res.ok){if(res.status===401&&adminPage&&authenticated&&path!=='/api/password')loggedOut('로그인이 만료되었습니다. 다시 로그인하세요.');throw new Error(data.error||`요청 실패 (${res.status})`);}
  return data;
}
function markerLabel(index) { return String(index+1); }

function current() { return snapshot?.toilets.find(t=>t.id===selected); }
function select(id, scroll=false) {
  if(dirty && id!==selected && !confirm('저장하지 않은 설정을 버리고 다른 화장실을 선택할까요?')) {
    $('selected-toilet').value=selected; return false;
  }
  if(id!==selected) { selected=id;dirty=false;positionDraft=null; }
  render(); if(!dirty)fillForm();
  if(adminPage&&authenticated)loadHistory();
  if(scroll)$('cards').querySelector(`[data-id="${id}"]`)?.scrollIntoView({block:'nearest',behavior:'smooth'});
  return true;
}
function mapPosition(t) { return positionDraft?.id===t.id ? positionDraft : t; }
function formChanged() {
  const t=current();return t && ($('toilet-name').value!==t.name || Number($('stalls').value)!==t.stalls || Number($('map-x').value)!==t.x || Number($('map-y').value)!==t.y);
}
function updatePlacement() {
  const t=current();if(!t){$('placement-title').textContent='화장실을 추가해 주세요';$('placement-state').textContent='추가한 화장실은 드래그해서 위치를 정할 수 있습니다.';$('save-position').disabled=true;$('undo-position').disabled=true;return;}
  const changed=positionDraft?.id===t.id && (positionDraft.x!==t.x || positionDraft.y!==t.y);
  $('placement-title').textContent=`${t.name} · 위치 설정`;
  $('placement-state').textContent=changed?'위치 변경됨 · 위치 저장을 누르면 방문객 지도에도 반영됩니다.':'마커를 드래그하거나 지도를 클릭하세요. 마커에서 방향키로도 이동할 수 있습니다.';
  $('save-position').disabled=!changed; $('undo-position').disabled=!changed;
}
function setPosition(x,y) {
  const t=current();if(!t)return;
  x=Math.min(97,Math.max(3,Math.round(x)));y=Math.min(97,Math.max(3,Math.round(y)));
  positionDraft={id:selected,x,y};$('map-x').value=x;$('map-y').value=y;dirty=Boolean(formChanged());
  const mark=$('markers').querySelector(`[data-id="${selected}"]`);
  if(mark){mark.style.left=`${x}%`;mark.style.top=`${y}%`;}
  updatePlacement();
}
function beginDrag(event,id) {
  if(!adminPage||!authenticated||!event.isPrimary||event.button!==0)return;
  event.preventDefault();event.stopPropagation();
  if(!select(id)){suppressMapClickUntil=performance.now()+400;return;}
  const surface=$('map-surface'),rect=surface.getBoundingClientRect(),pos=mapPosition(current());
  drag={pointer:event.pointerId,id,startX:event.clientX,startY:event.clientY,
    offsetX:event.clientX-rect.left-pos.x/100*rect.width,offsetY:event.clientY-rect.top-pos.y/100*rect.height,
    previous:positionDraft?{...positionDraft}:null,previousDirty:dirty,moved:false};
  surface.setPointerCapture(event.pointerId);
}
function finishDrag(event,cancelled=false) {
  if(!drag||event.pointerId!==drag.pointer)return;
  const finished=drag;drag=null;
  const surface=$('map-surface');
  if(surface.hasPointerCapture(event.pointerId))surface.releasePointerCapture(event.pointerId);
  if(cancelled){positionDraft=finished.previous;dirty=finished.previousDirty;render();if(!dirty)fillForm();else{
    const pos=mapPosition(current());$('map-x').value=pos.x;$('map-y').value=pos.y;
  }}
  $('markers').querySelector('.dragging')?.classList.remove('dragging');
  suppressMapClickUntil=performance.now()+400;
  if(finished.moved&&!cancelled)notice('마커를 옮겼습니다. 지도 아래의 위치 저장을 눌러주세요.');
  updatePlacement();
}
function render() {
  if(!snapshot||drag)return;
  if(!snapshot.toilets.some(t=>t.id===selected)){selected=snapshot.toilets[0]?.id??null;dirty=false;positionDraft=null;}
  $('banner').hidden=!snapshot.demo;
  $('banner').textContent='시연 모드 · 모든 통행량과 장치 상태는 시뮬레이션 데이터입니다. 실제 현장 측정값이 아닙니다.';
  $('event-map').src=snapshot.settings.map||'/map.svg';
  document.querySelector('.badge').textContent=snapshot.settings.map?'등록된 배치도':'예시 배치도';
  document.querySelector('.map-stamp').hidden=Boolean(snapshot.settings.map);
  $('markers').replaceChildren();$('cards').replaceChildren();
  $('toilet-count').textContent=`총 ${snapshot.toilets.length}곳`;
  if(!snapshot.toilets.length)$('cards').append(elem('p','아직 등록된 화장실이 없습니다. 행사장 현장 안내를 확인해 주세요.','empty'));
  const online=snapshot.toilets.filter(t=>t.online).length;
  $('connection').textContent=`${online}/${snapshot.toilets.length}곳 센서 연결`;
  $('updated').textContent=`${localTime(snapshot.updated_at)} KST 갱신`;
  for(const t of snapshot.toilets) {
    const mark=elem('button',undefined,`marker ${t.level}${t.id===selected?' selected':''}`);
    const pos=mapPosition(t);mark.style.left=`${pos.x}%`;mark.style.top=`${pos.y}%`;mark.dataset.id=t.id;
    mark.append(elem('span',markerLabel(snapshot.toilets.indexOf(t))),elem('small',labels[t.level]));
    mark.setAttribute('aria-label',`${t.name}, ${labels[t.level]}`);mark.setAttribute('aria-pressed',String(t.id===selected));
    mark.addEventListener('click',e=>{e.stopPropagation();if(performance.now()<suppressMapClickUntil)return;select(t.id,true);});
    if(adminPage&&authenticated){
      mark.title='드래그하여 위치 이동 · 방향키 미세 조정';
      mark.setAttribute('aria-describedby','placement-state');
      mark.addEventListener('pointerdown',e=>beginDrag(e,t.id));
      mark.addEventListener('keydown',e=>{
        const direction={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[e.key];
        if(!direction)return;e.preventDefault();if(!select(t.id))return;
        const pos=mapPosition(current()),step=e.shiftKey?5:1;setPosition(pos.x+direction[0]*step,pos.y+direction[1]*step);
        $('markers').querySelector(`[data-id="${t.id}"]`)?.focus();
      });
    }
    $('markers').append(mark);
    const card=elem('button',undefined,`toilet-card${t.id===selected?' selected':''}`);card.dataset.id=t.id;
    card.setAttribute('aria-pressed',String(t.id===selected));
    const top=elem('div',undefined,'card-top'), name=elem('div',undefined,'card-name');
    name.append(elem('strong',t.name),elem('small',`운영 ${t.stalls}칸 · ${t.device_id?'센서 연결 시설':'장치 등록 대기'}`));
    top.append(elem('span',markerLabel(snapshot.toilets.indexOf(t)),'letter'),name,elem('span',labels[t.level],`status ${t.level}`));
    const bottom=elem('div',undefined,'card-bottom');
    bottom.append(elem('span',t.online?(t.quality==='good'?'● 정상 수신':'● 측정 신뢰도 확인 필요'):'○ 수신 대기 / 연결 끊김'),elem('span',`마지막 수신 ${localTime(t.last_seen)}`));
    card.append(top,bottom);card.addEventListener('click',()=>select(t.id));$('cards').append(card);
  }
  $('map-editor').hidden=!(adminPage&&authenticated);
  $('map-surface').classList.toggle('map-editable',Boolean(adminPage&&authenticated));
  if(adminPage&&authenticated) {
    $('facility-total').textContent=`등록 ${snapshot.toilets.length}곳`;
    const empty=!snapshot.toilets.length;
    $('toilet-fields').disabled=empty;$('device-fields').disabled=empty;$('delete-toilet').disabled=empty;$('reset').disabled=empty;
    const sel=$('selected-toilet');
    sel.replaceChildren(...snapshot.toilets.map(t=>{const o=elem('option',t.name);o.value=t.id;return o;}));sel.value=String(selected);
    $('simulate').hidden=!snapshot.demo;
    $('device-status').replaceChildren();
    for(const t of snapshot.toilets) {
      const line=elem('div',undefined,'device-line');
      line.append(elem('strong',t.name),elem('span',t.device_id||'미등록'),elem('span',t.online?'온라인':'오프라인'),elem('span',`품질: ${t.quality||'미확인'}`),elem('span',`마지막 수신 ${localTime(t.last_seen)}`));
      $('device-status').append(line);
    }
    if(!dirty)fillForm();
    updatePlacement();
  }
}
function fillForm(){const t=current();if(!t){$('toilet-name').value='';$('stalls').value=4;$('map-x').value=50;$('map-y').value=50;return;}$('selected-toilet').value=t.id;$('toilet-name').value=t.name;$('stalls').value=t.stalls;$('map-x').value=t.x;$('map-y').value=t.y;}
async function refresh(){
  if(refreshing||drag)return;refreshing=true;
  try {snapshot=await api('/api/status');render();if(adminPage&&authenticated)await loadHistory();}
  catch(e){$('connection').textContent='서버 연결 확인 필요';$('updated').textContent='갱신 실패 · 이전 상태를 사용하지 마세요';notice(e.message,true);
    document.querySelectorAll('.status').forEach(el=>{el.className='status unknown';el.textContent='갱신 실패';});
    document.querySelectorAll('.marker').forEach(el=>{el.className='marker unknown';el.querySelector('small').textContent='수신 오류';});
  }finally{refreshing=false;}
}
async function loadHistory(){
  if(selected===null){$('history').replaceChildren(elem('p','화장실을 추가하면 통행 추이를 확인할 수 있습니다.','empty'));return;}
  try{
    const rows=await api(`/api/history?toilet_id=${selected}`),max=Math.max(1,...rows.flatMap(r=>[r.in,r.out]));
    $('history').replaceChildren();
    for(const row of rows){const g=elem('div',undefined,'bar-group');g.setAttribute('aria-label',`${localTime(row.at)} 입장 ${row.in}, 퇴장 ${row.out}`);g.title=g.getAttribute('aria-label');
      const i=elem('div',undefined,'bar'),o=elem('div',undefined,'bar out');i.style.height=`${row.in/max*90}%`;o.style.height=`${row.out/max*90}%`;
      g.append(i,o,elem('small',new Date(row.at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false})));$('history').append(g);}
  }catch(e){notice(e.message,true);}
}
async function action(fn){try{await fn();}catch(e){notice(e.message,true);}}
$('visitor-link').classList.toggle('active',!adminPage);$('admin-link').hidden=!adminPage;$('admin-link').classList.toggle('active',adminPage);
if(adminPage){$('title').textContent='현장의 흐름을, 한눈에.';$('subtitle').textContent='PC와 휴대폰에서 화장실과 센서 운영을 관리하세요.';$('login-panel').hidden=false;$('workspace').hidden=true;}
function loggedOut(message='로그아웃했습니다.') {
  if(drag)finishDrag({pointerId:drag.pointer},true);
  authenticated=false;dirty=false;positionDraft=null;$('map-editor').hidden=true;$('map-surface').classList.remove('map-editable');
  $('admin-panel').hidden=true;$('workspace').hidden=true;$('login-panel').hidden=false;$('device-token').value='';$('device-result').hidden=true;
  $('password-form').reset();notice(message);
}
async function checkBackend(){
  const health=await api('/api/health');
  if(health.auth_mode!=='password')throw new Error('이전 서버가 실행 중입니다. 기존 서버 창에서 Ctrl+C로 종료한 뒤, 수정한 폴더의 start_demo.bat를 다시 실행하고 브라우저에서 Ctrl+F5를 누르세요.');
}
async function showAdmin(){
  await checkBackend();
  const settings=await api('/api/admin');authenticated=true;
  $('visitor-url').value=settings.automatic_visitor_url||location.origin;updateQrHint();
  $('admin-password').value='';$('login-panel').hidden=true;$('workspace').hidden=false;$('admin-panel').hidden=false;
  await refresh();fillForm();
}
$('login-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  await checkBackend();
  await api('/api/login','POST',{password:$('admin-password').value});await showAdmin();notice('로그인했습니다.');
});});
$('logout').addEventListener('click',()=>action(async()=>{await api('/api/logout','POST',{});loggedOut();}));
$('password-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  if($('new-password').value!==$('confirm-password').value)throw new Error('새 비밀번호와 확인 입력이 일치하지 않습니다.');
  await api('/api/password','PUT',{current_password:$('current-password').value,new_password:$('new-password').value});
  $('password-form').reset();notice('비밀번호를 변경했습니다. 다음 로그인부터 새 비밀번호를 사용하세요.');
});});
$('new-toilet-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  if(dirty&&!confirm('저장하지 않은 설정을 버리고 새 화장실을 추가할까요?'))return;
  const result=await api('/api/toilets','POST',{name:$('new-toilet-name').value,stalls:Number($('new-toilet-stalls').value)});
  selected=result.id;dirty=false;positionDraft=null;$('new-toilet-form').reset();await refresh();notice('화장실을 추가했습니다. 지도에서 마커를 드래그해 배치하세요.');
});});
$('delete-toilet').addEventListener('click',()=>action(async()=>{
  const t=current();if(!t)return;
  if(!confirm(`${t.name}을(를) 삭제할까요? 지도와 목록에서 제거하고 연결된 장치의 수신을 중지합니다. 기존 통행 기록은 보존합니다.`))return;
  await api(`/api/toilets/${selected}`,'DELETE');dirty=false;positionDraft=null;selected=null;await refresh();notice('화장실을 삭제했습니다.');
}));
$('refresh').addEventListener('click',refresh);
$('selected-toilet').addEventListener('change',()=>select(Number($('selected-toilet').value)));
$('toilet-form').addEventListener('input',e=>{
  dirty=Boolean(formChanged());
  if(['map-x','map-y'].includes(e.target.id) && $('map-x').validity.valid && $('map-y').validity.valid)setPosition(Number($('map-x').value),Number($('map-y').value));
});
$('map-surface').addEventListener('pointermove',e=>{
  if(!drag||e.pointerId!==drag.pointer)return;
  if(!drag.moved&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<4)return;
  drag.moved=true;e.preventDefault();
  $('markers').querySelector(`[data-id="${drag.id}"]`)?.classList.add('dragging');
  const rect=$('map-surface').getBoundingClientRect();
  setPosition((e.clientX-drag.offsetX-rect.left)/rect.width*100,(e.clientY-drag.offsetY-rect.top)/rect.height*100);
});
$('map-surface').addEventListener('pointerup',e=>finishDrag(e));
$('map-surface').addEventListener('pointercancel',e=>finishDrag(e,true));
$('map-surface').addEventListener('lostpointercapture',e=>{if(drag)finishDrag(e,true);});
$('map-surface').addEventListener('click',e=>{
  if(!adminPage||!authenticated||performance.now()<suppressMapClickUntil)return;
  const rect=$('map-surface').getBoundingClientRect();
  setPosition((e.clientX-rect.left)/rect.width*100,(e.clientY-rect.top)/rect.height*100);
});
$('save-position').addEventListener('click',()=>$('toilet-form').requestSubmit());
$('undo-position').addEventListener('click',()=>{
  const t=current();if(!t)return;positionDraft=null;$('map-x').value=t.x;$('map-y').value=t.y;dirty=Boolean(formChanged());render();
});
$('toilet-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  await api(`/api/toilets/${selected}`,'PUT',{name:$('toilet-name').value,stalls:Number($('stalls').value),x:Number($('map-x').value),y:Number($('map-y').value)});
  dirty=false;positionDraft=null;notice('화장실 설정과 지도 위치를 저장했습니다.');await refresh();
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
function updateQrHint() {
  $('qr-url-hint').textContent='공개 접속 주소를 자동으로 사용합니다. PC와 외부 접속 실행 창을 켜두면 Wi-Fi·LTE·5G에서 사용할 수 있습니다.';
}
function dataUrl(blob) {
  return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('QR 이미지를 읽지 못했습니다'));reader.readAsDataURL(blob);});
}
$('qr-form').addEventListener('submit',e=>{e.preventDefault();action(async()=>{
  const button=$('qr-button');button.disabled=true;$('qr-result').hidden=true;
  try{
    const saved=await api('/api/qr','POST',{url:location.origin+'/'});
    const svg=await dataUrl(new Blob([saved.svg],{type:'image/svg+xml'})),image=new Image();image.src=svg;await image.decode();
    const canvas=document.createElement('canvas');canvas.width=canvas.height=1024;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,1024,1024);ctx.drawImage(image,0,0,1024,1024);
    $('qr-image').src=svg;$('qr-destination').textContent=saved.url;
    $('qr-svg-download').href=svg;$('qr-png-download').href=canvas.toDataURL('image/png');$('qr-result').hidden=false;
    notice('QR을 생성했습니다. PNG 또는 SVG 다운로드를 누르면 파일로 저장됩니다.');
  }finally{button.disabled=false;}
});});
if(adminPage)showAdmin().catch(e=>{if(e.message.includes('이전 서버'))notice(e.message,true);});else refresh();
setInterval(()=>{if(!adminPage||authenticated)refresh();},5000);
