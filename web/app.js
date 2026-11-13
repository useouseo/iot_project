'use strict';
window.restflowIcon = name => '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+({"overview": "<path d=\"M4 20V13m5 7V9m5 11V5m5 15V2\" stroke-width=\"3.5\"/>", "facilities": "<circle cx=\"8\" cy=\"4\" r=\"2\"/><circle cx=\"17\" cy=\"4\" r=\"2\"/><path d=\"M5 9h6v6H9v6H7v-6H5V9Zm9 0h6v6h-2v6h-2v-6h-2V9Z\"/>", "map": "<path d=\"M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z\"/><circle cx=\"12\" cy=\"10\" r=\"2.5\"/>", "devices": "<rect x=\"3\" y=\"11\" width=\"18\" height=\"10\" rx=\"2\"/><path d=\"M7 15h.01M11 15h.01M16 15h2M7 8a8 8 0 0 1 10 0M10 5a4 4 0 0 1 4 0M12 2v1\"/>", "qr": "<path d=\"M3 3h6v6H3zM15 3h6v6h-6zM3 15h6v6H3zM15 13v4h4v4M21 13v2M13 21h2M13 13h.01M21 21h.01\"/>", "settings": "<path d=\"m10 3 .6-1h2.8l.6 2 2 .9 2-.5 2 2-1 1.9.9 2 2 1v2.8l-2 1-.9 2 1 1.9-2 2-2-.5-2 .9-.6 2h-2.8l-.6-2-2-.9-2 .5-2-2 1-1.9-.9-2-2-1v-2.8l2-1 .9-2-1-1.9 2-2 2 .5Z\"/><circle cx=\"12\" cy=\"12\" r=\"3\"/>", "logout": "<path d=\"M9 3H4v18h5m6-15 6 6-6 6M8 12h13\"/>", "external": "<path d=\"M14 3h7v7m0-7L11 13M10 4H4v16h16v-6\"/>", "pencil": "<path d=\"m14 4 6 6M3 21l2-7L16 3a2 2 0 0 1 3 0l2 2a2 2 0 0 1 0 3L10 19l-7 2Z\"/>", "plus": "<path d=\"M12 4v16M4 12h16\"/>", "wifi": "<path d=\"M2 8a16 16 0 0 1 20 0M5 12a11 11 0 0 1 14 0M8 16a6 6 0 0 1 8 0\"/><circle cx=\"12\" cy=\"20\" r=\"1\"/>", "users": "<circle cx=\"12\" cy=\"6\" r=\"3\"/><path d=\"M6 21v-4a6 6 0 0 1 12 0v4M3 10a3 3 0 0 0 2 5M21 10a3 3 0 0 1-2 5M2 21v-3M22 21v-3\"/>", "alert": "<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 6v7m0 4h.01\"/>", "refresh": "<path d=\"M20 4v6h-6M20 10a8 8 0 1 0 .2 5\"/>", "door": "<path d=\"M5 3h14v18H5zM8 3v18M12 12h.01\"/>", "chevron": "<path d=\"m9 5 7 7-7 7\"/>", "down": "<path d=\"m6 9 6 6 6-6\"/>", "info": "<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 11v6m0-10h.01\"/>"})[name]+'</svg>';
'use strict';
// Organize the existing, server-backed controls without duplicating forms or IDs.
(() => {
 const byId=id=>document.getElementById(id);
 const make=(tag,cls,html='')=>{const node=document.createElement(tag);node.className=cls;node.innerHTML=html;return node;};
 const admin=location.pathname==='/admin';
 document.body.classList.add(admin?'admin-page':'visitor-page');
 document.querySelector('.brand-sub').remove();
 byId('title').textContent=admin?'운영 현황':'화장실 찾기';
 byId('subtitle').textContent='';
 document.querySelector('.intro .eyebrow').remove();
 document.querySelector('.how').remove();
 document.querySelector('#workspace > .section-heading .eyebrow').remove();
 const summary=make('div','summary-strip');
 byId('cards').before(summary);
 const filters=make('div','facility-filters','<button type="button" data-sort="all">전체</button><button type="button" class="active" data-sort="recommended">추천순</button>');
 summary.after(filters);
 let sort='recommended', latest=null;
 const trafficNote=make('p','traffic-note','통행량과 운영 칸 수를 반영한 추정치입니다. 실제 사용 중인 칸 수를 의미하지 않습니다.');byId('cards').after(trafficNote);
 function orderCards(){
  if(admin||!latest)return;
  const ordered=[...latest.toilets].sort((a,b)=>sort==='all'?a.id-b.id:((window.trafficPercent(a)===null)-(window.trafficPercent(b)===null))||((Number.isFinite(a.score)?a.score:Infinity)-(Number.isFinite(b.score)?b.score:Infinity))||a.id-b.id);
  const cards=byId('cards'),position=cards.scrollTop;for(const toilet of ordered){const node=cards.querySelector('[data-id="'+toilet.id+'"]');if(node)cards.append(node);}cards.scrollTop=position;
  filters.querySelectorAll('button').forEach(button=>{const active=button.dataset.sort===sort;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
 }
 filters.addEventListener('click',event=>{const button=event.target.closest('[data-sort]');if(!button)return;sort=button.dataset.sort;orderCards();byId('cards').scrollTop=0;});
 window.designUnavailable=()=>{document.querySelectorAll('.traffic-percent').forEach(node=>node.textContent='안내 준비 중');document.querySelectorAll('.traffic-progress').forEach(node=>node.hidden=true);document.querySelectorAll('.recommend-badge').forEach(node=>node.remove());};
 const mapPanelForSizing=document.querySelector('.map-panel'),layoutForSizing=document.querySelector('.layout');
 function sizeFacilityPane(){const height=mapPanelForSizing.getBoundingClientRect().height;if(height>0){layoutForSizing.style.setProperty('--facility-pane-height',height+'px');if(document.body.classList.contains('editing-facilities'))document.querySelector('.facilities-grid')?.style.setProperty('--editor-pane-height',height+'px');}}
 new ResizeObserver(sizeFacilityPane).observe(mapPanelForSizing);window.addEventListener('resize',sizeFacilityPane);window.sizeFacilityPane=sizeFacilityPane;
 byId('cards').tabIndex=0;byId('cards').setAttribute('role','region');byId('cards').setAttribute('aria-label','화장실 목록');
 window.syncDesign=data=>{
  latest=data;orderCards();requestAnimationFrame(sizeFacilityPane);
  if(admin){
   const values=[`${data.toilets.length}곳`,`${data.toilets.filter(t=>t.online).length} / ${data.toilets.length}`,`${data.toilets.filter(t=>t.level==='busy').length}곳`,`${data.toilets.filter(t=>!t.online||t.level==='unknown'||t.quality!=='good').length}곳`];
   byId('dashboard-updated').textContent=new Date(data.updated_at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})+' 업데이트';
   byId('demo-chip').hidden=!data.demo;byId('demo-chip').title=byId('banner').textContent;document.querySelector('.event-name').firstChild.textContent=data.demo?'작은 흐름 페스티벌':'행사장';
   document.querySelector('.chart-note').hidden=!data.demo;
   document.querySelectorAll('.metric strong').forEach((node,index)=>node.textContent=values[index]);
   const selection=byId('device-toilet');selection.replaceChildren(...data.toilets.map(t=>{const o=document.createElement('option');o.value=t.id;o.textContent=t.name;return o;}));selection.value=byId('selected-toilet').value;
   byId('device-facility-label').textContent=data.toilets.find(t=>String(t.id)===selection.value)?.name||'화장실을 먼저 추가하세요';
  }
 };
 if(!admin)return;
 const adminPanel=byId('admin-panel');
 const panels=[...adminPanel.querySelectorAll('.admin-grid > .panel')];
 const addPanel=panels[0],editPanel=panels[1],mixedPanel=panels[2],settingsPanel=panels[3],historyPanel=panels[4];
 const sidebar=make('aside','admin-sidebar','<a class="brand" href="/admin"><span class="brand-mark">↗</span> RestFlow</a><span class="operator-tag">관리자</span><nav aria-label="관리 메뉴"></nav><div class="sidebar-bottom"></div>');
 document.body.prepend(sidebar);
 const nav=sidebar.querySelector('nav');
 const titles={overview:'운영 현황',facilities:'화장실·지도 관리',devices:'장치 관리',qr:'방문객 QR',settings:'설정'};
 const icons=window.restflowIcon;
 const views={};
 const viewHost=make('div','admin-views');byId('workspace').prepend(viewHost);
 for(const [key,title] of Object.entries(titles)){
  const view=make('section','admin-view');view.dataset.view=key;view.hidden=true;viewHost.append(view);views[key]=view;
  const button=make('button','side-link',`<span aria-hidden="true">${icons(key)}</span>${title}`);button.type='button';button.datas…5616 tokens truncated….in}, 퇴장 ${row.out}`);g.title=g.getAttribute('aria-label');
      const i=elem('div',undefined,'bar'),o=elem('div',undefined,'bar out');i.style.height=`${(row.in+row.out)/max*100}%`;o.hidden=true;
      g.append(i,o,elem('small',new Date(row.at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false})));$('history').append(g);}
  }catch(e){notice(e.message,true);}
}
async function action(fn){try{await fn();}catch(e){notice(e.message,true);}}
$('visitor-link').classList.toggle('active',!adminPage);$('admin-link').hidden=!adminPage;$('admin-link').classList.toggle('active',adminPage);
if(adminPage){$('title').textContent='관리자 로그인';$('subtitle').textContent='';$('login-panel').hidden=false;$('workspace').hidden=true;}
function loggedOut(message='로그아웃했습니다.') {
  if(drag)finishDrag({pointerId:drag.pointer},true);
  authenticated=false;dirty=false;positionDraft=null;$('title').textContent='관리자 로그인';$('map-editor').hidden=true;$('map-surface').classList.remove('map-editable');
  $('admin-panel').hidden=true;$('workspace').hidden=true;$('login-panel').hidden=false;$('device-token').value='';$('device-result').hidden=true;
  $('password-form').reset();notice(message);
}
async function checkBackend(){
  const health=await api('/api/health');
  if(health.auth_mode!=='password')throw new Error('이전 서버가 실행 중입니다. 기존 서버 창에서 Ctrl+C로 종료한 뒤, 수정한 폴더의 start_public.bat를 다시 실행하고 브라우저에서 Ctrl+F5를 누르세요.');
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
  selected=result.id;dirty=false;positionDraft=null;$('new-toilet-form').reset();await refresh();notice('화장실을 추가했습니다. 실제 지도에서 입구 위치를 지정해 저장하세요.');
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
  if(!adminPage||!authenticated||!window.designEditing||performance.now()<suppressMapClickUntil)return;
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

window.hasUnsavedDesignChanges=()=>dirty;
$('cancel-edit')?.addEventListener('click',()=>{dirty=false;positionDraft=null;fillForm();render();notice('수정을 취소했습니다.');});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});

window.rerenderRestflow=render;

window.chooseOutdoorFacility=id=>select(id,true);
