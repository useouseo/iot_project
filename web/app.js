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
   byId('demo-chip').hidden=!data.demo;byId('demo-chip').title=byId('banner').textContent;byId('map-mode').value=data.settings.map_mode||'outdoor';
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
  const button=make('button','side-link',`<span aria-hidden="true">${icons(key)}</span>${title}`);button.type='button';button.dataset.view=key;(key==='settings'?sidebar.querySelector('.sidebar-bottom'):nav).append(button);button.addEventListener('click',()=>window.openAdminView(key));
 }
 byId('logout').innerHTML=icons('logout')+'로그아웃';sidebar.querySelector('.sidebar-bottom').append(byId('logout'));
 const header=document.querySelector('header');const event=make('div','event-context',`<label class="mode-control" for="map-mode">모드 선택<select id="map-mode" aria-label="모드 선택"><option value="outdoor">야외 페스티벌</option><option value="indoor">실내 페스티벌</option></select></label><span id="demo-chip" class="demo-chip" hidden><b></b>시연 모드</span>`);header.prepend(event);byId('visitor-link').innerHTML=icons('external')+'방문객 화면';
 const metrics=make('div','metrics');['등록 화장실','센서 연결','혼잡 시설','확인 필요'].forEach((title,i)=>metrics.append(make('div','metric',`<i aria-hidden="true">${icons(['facilities','wifi','users','alert'][i])}</i><div><span>${title}</span><strong>—</strong></div>`)));views.overview.append(metrics);
 const layout=document.querySelector('.layout');
 const workspaceHeading=document.querySelector('#workspace > .section-heading');workspaceHeading.remove();
 views.overview.append(layout);
 const mapPanel=document.querySelector('.map-panel');
 const mapTitle=make('div','map-heading','<h2>행사장 지도 <span class="badge">예시 배치도</span></h2><button type="button" class="secondary" id="edit-map-link">지도 편집</button>');mapPanel.prepend(mapTitle);
 byId('edit-map-link').innerHTML=icons('pencil')+'지도 편집';
 const addFacility=make('button','primary add-facility',icons('plus')+'시설 추가');addFacility.type='button';document.querySelector('.aside-title').append(addFacility);addFacility.addEventListener('click',()=>{window.openAdminView('facilities');byId('new-toilet-name').scrollIntoView({block:'center'});byId('new-toilet-name').focus();});
 byId('edit-map-link').addEventListener('click',()=>window.openAdminView('facilities'));
 const overviewBottom=make('div','overview-bottom');views.overview.append(overviewBottom);
 const deviceStatusPanel=make('section','panel','<h3>장치 연결 상태</h3>');deviceStatusPanel.append(byId('device-status'));overviewBottom.append(historyPanel,deviceStatusPanel);
 historyPanel.classList.remove('wide');
 const chartNote=make('span','chart-note',icons('info')+'차트는 시뮬레이션 데이터입니다.');historyPanel.querySelector('.aside-title').append(chartNote);
 const plot=make('div','chart-plot','<div class="chart-axis" aria-hidden="true"></div>');byId('history').before(plot);plot.append(byId('history'));
 const chartLabels=make('div','chart-key','<span>통행량 · 입장+퇴장</span>');historyPanel.querySelector('.aside-title').append(chartLabels);
 const facilitiesGrid=make('div','facilities-grid');views.facilities.append(facilitiesGrid);
 const mapSlot=make('div','edit-map-slot');facilitiesGrid.append(mapSlot);
 const formStack=make('div','form-stack');facilitiesGrid.append(formStack);formStack.append(editPanel,addPanel);
 const upload=document.querySelector('.upload-label');mapPanel.insertBefore(upload,byId('map-editor'));upload.firstChild.textContent='행사장 배치도 변경 ';
 editPanel.querySelector('h3').textContent='화장실 정보 및 위치';
 byId('toilet-form').querySelector('button').textContent='변경사항 저장';
 byId('save-position').textContent='변경사항 저장';byId('save-position').hidden=true;byId('undo-position').textContent='위치 되돌리기';
 const cancel=make('button','secondary','수정 취소');cancel.type='button';cancel.id='cancel-edit';byId('toilet-form').append(cancel);
 const form=byId('toilet-form'), fields=byId('toilet-fields'), save=form.querySelector('.primary');save.id='save-settings';
 const actions=make('div','facility-actions'),rightActions=make('div','facility-actions-right');byId('delete-toilet').textContent='삭제';byId('delete-toilet').type='button';actions.append(byId('delete-toilet'),rightActions);rightActions.append(cancel,save);form.append(actions);
 const identity=make('div','facility-identity');const nameLabel=byId('toilet-name').closest('label'),stallsLabel=byId('stalls').closest('label'),oldRow=stallsLabel.parentElement;nameLabel.before(identity);identity.append(nameLabel,stallsLabel);oldRow.remove();
 byId('reset').textContent='혼잡도 계산 구간 초기화';
 addPanel.classList.remove('wide');addPanel.querySelector('h3').textContent='새 화장실 추가';
 const deviceGrid=make('div','device-grid');views.devices.append(deviceGrid);
 const deviceList=make('section','panel','<h3>장치 연결 상태</h3><div id="device-list-slot"></div>');
 deviceGrid.append(deviceList,mixedPanel);mixedPanel.querySelector('h3').textContent='장치 등록';
 const deviceSelect=make('label','','연결할 화장실<select id="device-toilet"></select>');byId('device-fields').prepend(deviceSelect);
 byId('device-fields').querySelector('.hint').innerHTML='선택한 시설: <strong id="device-facility-label"></strong><br>화장실당 장치 한 대를 등록할 수 있습니다.';
 byId('device-toilet').addEventListener('change',()=>{byId('selected-toilet').value=byId('device-toilet').value;byId('selected-toilet').dispatchEvent(new Event('change'));});
 const qr=document.querySelector('.qr-section');qr.classList.add('panel');views.qr.append(qr);qr.querySelector('h4').textContent='방문객 접속 주소 및 QR';
 views.settings.append(settingsPanel);settingsPanel.classList.remove('wide');
 adminPanel.querySelector('.section-heading').remove();adminPanel.remove();
 // Keep the authenticated container ID used by existing authentication code.
 viewHost.id='admin-panel';
 const summaries=document.querySelector('.intro');
 const introTitle=byId('title');introTitle.textContent='운영 현황';
 const caption=make('p','view-caption','시설과 센서 상태를 한눈에 확인하세요.');introTitle.after(caption);
 const updateDisplay=make('button','update-display',icons('refresh')+'<span id="dashboard-updated">업데이트 중</span>');updateDisplay.type='button';updateDisplay.addEventListener('click',()=>byId('refresh').click());document.querySelector('.intro').append(updateDisplay);
 let currentView='overview';
 window.openAdminView=key=>{
  if(!views[key])key='overview';
  if(currentView!==key&&window.hasUnsavedDesignChanges?.()&&!confirm('저장하지 않은 변경사항이 있습니다. 화면을 이동할까요?'))return;
  currentView=key;
  Object.entries(views).forEach(([name,view])=>view.hidden=name!==key);
  sidebar.querySelectorAll('.side-link').forEach(b=>{b.classList.toggle('active',b.dataset.view===key);if(b.dataset.view===key)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  introTitle.textContent=titles[key];caption.textContent={overview:'시설과 센서 상태를 한눈에 확인하세요.',facilities:'화장실 정보와 지도 위치를 함께 수정하세요.',devices:'장치를 등록하고 시설별 연결 상태를 확인하세요.',qr:'자동 연결 주소로 방문객 안내 QR을 생성하세요.',settings:'관리자 계정의 비밀번호를 변경하세요.'}[key];
  if(key==='facilities'){mapSlot.append(mapPanel);mapPanel.append(byId('map-editor'));}
  else{layout.prepend(mapPanel);}
  const editing=key==='facilities';document.body.classList.toggle('editing-facilities',editing);byId('map-editor').hidden=!editing;byId('map-surface').classList.toggle('map-editable',editing);
  if(key==='devices')byId('device-list-slot').append(byId('device-status'));else deviceStatusPanel.append(byId('device-status'));
  window.designEditing=editing;
  window.rerenderRestflow?.();requestAnimationFrame(sizeFacilityPane);
 };
 window.openAdminView('overview');
 // Authentication toggles the shell; no sidebar is shown on the login screen.
 new MutationObserver(()=>{document.body.classList.toggle('signed-in',!byId('workspace').hidden);if(!byId('workspace').hidden)window.openAdminView(currentView);}).observe(byId('workspace'),{attributes:true,attributeFilter:['hidden']});
})();

'use strict';
const $ = id => document.getElementById(id);
const adminPage = location.pathname === '/admin';
const labels = {quiet:'여유',moderate:'보통',busy:'혼잡',unknown:adminPage?'확인 필요':'안내 준비'};
window.trafficPercent=t=>{if(!t||t.level==='unknown'||!t.online||t.quality!=='good')return null;if(Number.isFinite(t.congestion_percent))return Math.max(0,Math.min(100,Math.round(t.congestion_percent)));const s=t.score;if(!Number.isFinite(s))return null;return Math.min(100,Math.floor((s<.8?Math.max(0,s)*50:s<2?40+(s-.8)*35/1.2:75+(s-2)*12.5)+.5));};
let authenticated = false, snapshot = null, selected = 1, dirty = false, refreshing = false;
let positionDraft = null, drag = null, suppressMapClickUntil = 0, renderedMode = null;
const elem = (tag, text, cls) => { const e=document.createElement(tag); if(text!==undefined)e.textContent=text; if(cls)e.className=cls; return e; };
const localTime = at => at ? new Date(at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '수신 기록 없음';
let noticeTimer;
function notice(message, error=false) { clearTimeout(noticeTimer); if(!error)noticeTimer=setTimeout(()=>{$('notice').hidden=true;},6000); $('notice').hidden=false; $('notice').textContent=message; $('notice').className=error?'error':''; }
async function api(path,method='GET',body) {
  const res=await fetch(path,{method,headers:{...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(8000)});
  const data=await res.json();
  if(!res.ok){if(res.status===401&&adminPage&&authenticated&&path!=='/api/password')loggedOut('로그인이 만료되었습니다. 다시 로그인하세요.');throw new Error(data.error||`요청 실패 (${res.status})`);}
  return data;
}
function markerLabel(index) { return index<26 ? String.fromCharCode(65+index) : String(index+1); }

function current() { return snapshot?.toilets.find(t=>t.id===selected); }
function select(id, scroll=false) {
  if((dirty||window.outdoor?.hasDraft()) && id!==selected && !confirm('저장하지 않은 설정을 버리고 다른 화장실을 선택할까요?')) {
    $('selected-toilet').value=selected; return false;
  }
  if(id!==selected) { selected=id;dirty=false;positionDraft=null; }
  render(); if(!dirty)fillForm();
  if(adminPage&&authenticated)loadHistory();
  if(scroll){const list=$('cards'),card=list.querySelector(`[data-id="${id}"]`);if(card){const a=list.getBoundingClientRect(),b=card.getBoundingClientRect();if(b.bottom>a.bottom)list.scrollBy({top:b.bottom-a.bottom,behavior:'smooth'});else if(b.top<a.top)list.scrollBy({top:b.top-a.top,behavior:'smooth'});}}
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
  $('placement-state').textContent=changed?'위치 변경됨 · 오른쪽 변경사항 저장을 누르면 방문객 지도에도 반영됩니다.':'마커를 드래그하거나 지도를 클릭하세요. 마커에서 방향키로도 이동할 수 있습니다.';
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
  if(!adminPage||!authenticated||!window.designEditing||!event.isPrimary||event.button!==0)return;
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
  if(finished.moved&&!cancelled)notice('마커를 옮겼습니다. 변경사항 저장을 눌러주세요.');
  updatePlacement();
}
function render() {
  if(!snapshot||drag)return;
  const mode=snapshot.settings.map_mode||'outdoor';
  if(renderedMode!==null&&renderedMode!==mode){
    if(window.hasUnsavedDesignChanges?.()){notice('다른 관리자에서 모드가 변경됐습니다. 편집 내용을 저장하거나 취소한 뒤 새로고침하세요.',true);return;}
    else{location.reload();return;}
  }
  renderedMode=mode;document.body.classList.toggle('mode-indoor',mode==='indoor');document.body.classList.toggle('mode-outdoor',mode==='outdoor');
  const formHint=$('toilet-form').querySelector('.hint');
  formHint.textContent=mode==='indoor'?'배치도 마커를 드래그한 뒤 변경사항 저장을 누르세요.':'화장실 이름과 칸 수는 여기서 저장합니다. 입구 위치는 지도 아래에서 별도로 저장하세요.';
  if(!snapshot.toilets.some(t=>t.id===selected)){selected=snapshot.toilets[0]?.id??null;dirty=false;positionDraft=null;}
  $('banner').hidden=!snapshot.demo;
  $('banner').textContent='시연 모드 · 모든 통행량과 장치 상태는 시뮬레이션 데이터입니다. 실제 현장 측정값이 아닙니다.';
  $('event-map').src=snapshot.settings.map||'/map.svg';
  document.querySelector('.badge').textContent=snapshot.settings.map?'등록된 배치도':'예시 배치도';
  document.querySelector('.map-stamp').hidden=Boolean(snapshot.settings.map);
  const cardScroll=$('cards').scrollTop;
  $('markers').replaceChildren();$('cards').replaceChildren();
  $('toilet-count').textContent=`총 ${snapshot.toilets.length}곳`;
  if(!snapshot.toilets.length)$('cards').append(elem('p','아직 등록된 화장실이 없습니다. 행사장 현장 안내를 확인해 주세요.','empty'));
  const online=snapshot.toilets.filter(t=>t.online).length;
  $('connection').textContent=`${online}/${snapshot.toilets.length}곳 센서 연결`;
  $('updated').textContent=`${localTime(snapshot.updated_at)} KST 갱신`;
  const recommendation=snapshot.toilets.filter(x=>window.trafficPercent(x)!==null).sort((a,b)=>(a.score-b.score)||a.id-b.id)[0]?.id;
  for(const t of snapshot.toilets) {
    const mark=elem('button',undefined,`marker ${t.level}${t.id===selected?' selected':''}`);
    const pos=mapPosition(t);mark.style.left=`${pos.x}%`;mark.style.top=`${pos.y}%`;mark.dataset.id=t.id;
    mark.append(elem('span',markerLabel(snapshot.toilets.indexOf(t))),elem('small',labels[t.level]));
    mark.setAttribute('aria-label',`${t.name}, ${labels[t.level]}`);mark.setAttribute('aria-pressed',String(t.id===selected));
    mark.addEventListener('click',e=>{e.stopPropagation();if(performance.now()<suppressMapClickUntil)return;select(t.id,true);});
    if(adminPage&&authenticated&&window.designEditing){
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
    const card=elem('button',undefined,`toilet-card level-${t.level}${t.id===selected?' selected':''}`);card.dataset.id=t.id;
    card.setAttribute('aria-pressed',String(t.id===selected));
    const top=elem('div',undefined,'card-top'), name=elem('div',undefined,'card-name');
    const details=elem('small',`운영 ${t.stalls}칸`);if(adminPage)details.insertAdjacentHTML('afterbegin',window.restflowIcon('door'));
    name.append(elem('strong',t.name),details);
    top.append(elem('span',markerLabel(snapshot.toilets.indexOf(t)),'letter'),name,elem('span',labels[t.level],`status ${t.level}`));
    const bottom=elem('div',undefined,'card-bottom');
    bottom.append(elem('span',t.online?(t.quality==='good'?'● 정상 수신':'● 측정 신뢰도 확인 필요'):'○ 수신 대기 / 연결 끊김'),elem('span',`마지막 수신 ${localTime(t.last_seen)}`));
    {top.append(elem('span',undefined,'card-chevron'));top.lastChild.innerHTML=window.restflowIcon('chevron');}
    card.append(top,bottom);
    if(!adminPage){
      const percent=window.trafficPercent(t),meta=elem('div',undefined,'traffic-meta'),value=elem('span',percent===null?'안내 준비 중':`추정 혼잡도 ${percent}%`,'traffic-percent');meta.append(value,elem('span',`운영 ${t.stalls}칸`));
      name.querySelector('small').remove();name.append(meta);
      const progress=elem('div',undefined,`traffic-progress ${t.level}`);progress.setAttribute('aria-label',percent===null?'혼잡도 안내 준비 중':`추정 혼잡도 ${percent}%`);progress.hidden=percent===null;const fill=elem('span');fill.style.width=`${percent??0}%`;progress.append(fill);card.append(progress);
      if(t.id===recommendation){const badge=elem('span','추천','recommend-badge');name.prepend(badge);}
    }card.addEventListener('click',()=>select(t.id));$('cards').append(card);
  }
  $('map-editor').hidden=!(adminPage&&authenticated&&window.designEditing);
  $('map-surface').classList.toggle('map-editable',Boolean(adminPage&&authenticated&&window.designEditing));
  if(adminPage&&authenticated) {
    $('facility-total').textContent=`등록 ${snapshot.toilets.length}곳`;
    const empty=!snapshot.toilets.length;
    $('toilet-fields').disabled=empty;$('save-settings').disabled=empty;$('device-fields').disabled=empty;$('delete-toilet').disabled=empty;$('reset').disabled=empty;
    const sel=$('selected-toilet');
    sel.replaceChildren(...snapshot.toilets.map(t=>{const o=elem('option',t.name);o.value=t.id;return o;}));sel.value=String(selected);
    $('simulate').hidden=!snapshot.demo;
    $('device-status').replaceChildren();
    for(const t of snapshot.toilets) {
      const line=elem('div',undefined,'device-line');
      const deviceName=elem('strong',t.device_id||'미등록','device-name');deviceName.title=t.name;const deviceIcon=elem('span',undefined,'device-icon');deviceIcon.innerHTML=window.restflowIcon('devices');
      const state=elem('span',t.online?'온라인':'오프라인',`device-state${t.online?' online':''}`);const seen=elem('span',`최종 수신 ${t.last_seen?new Date(t.last_seen*1000).toLocaleTimeString('en-GB',{timeZone:'Asia/Seoul',hour12:false}):'없음'}`,'device-last-seen');const facility=elem('span',t.name,'device-facility');const identity=elem('div',undefined,'device-identity');identity.append(deviceName,facility);line.append(deviceIcon,identity,state,seen);
      $('device-status').append(line);
    }
    if(!dirty)fillForm();
    updatePlacement();
  }
  window.selectedFacilityId=selected;window.syncDesign?.(snapshot);window.outdoor?.update(snapshot,selected,Boolean(adminPage&&authenticated&&window.designEditing));$('cards').scrollTop=cardScroll;
}
function fillForm(){const t=current();if(!t){$('toilet-name').value='';$('stalls').value=4;$('map-x').value=50;$('map-y').value=50;return;}$('selected-toilet').value=t.id;$('toilet-name').value=t.name;$('stalls').value=t.stalls;$('map-x').value=t.x;$('map-y').value=t.y;}
async function refresh(){
  if(refreshing||drag)return;refreshing=true;
  try {snapshot=await api('/api/status');render();if(adminPage&&authenticated)await loadHistory();}
  catch(e){$('connection').textContent='서버 연결 확인 필요';$('updated').textContent='갱신 실패 · 이전 상태를 사용하지 마세요';notice(e.message,true);
    document.querySelectorAll('.summary-item strong,.metric strong').forEach(el=>el.textContent='—');
    if($('dashboard-updated'))$('dashboard-updated').textContent='갱신 실패 · 연결 확인';
    window.designUnavailable?.();
    document.querySelectorAll('.device-state').forEach(el=>{el.className='device-state';el.textContent='확인 필요';});
    document.querySelectorAll('.status').forEach(el=>{el.className='status unknown';el.textContent='갱신 실패';});
    document.querySelectorAll('.marker').forEach(el=>{el.className='marker unknown';el.querySelector('small').textContent=adminPage?'수신 오류':'안내 준비';});
  }finally{refreshing=false;}
}
let historyRequest=0;
async function loadHistory(){
  const request=++historyRequest,facilityId=selected;const chartTitle=document.querySelector('.overview-bottom .panel h3');if(chartTitle)chartTitle.textContent=current()?`${current().name} · 최근 2시간 통행 추이`:'최근 2시간 통행 추이';
  if(selected===null){$('history').replaceChildren(elem('p','화장실을 추가하면 통행 추이를 확인할 수 있습니다.','empty'));return;}
  try{
    const rows=await api(`/api/history?toilet_id=${facilityId}`),max=Math.max(4,Math.ceil(Math.max(0,...rows.map(r=>r.in+r.out))/4)*4);
    if(request!==historyRequest||selected!==facilityId||!authenticated)return;
    $('history').replaceChildren();
    const axis=document.querySelector('.chart-axis');if(axis){const scale=max;axis.replaceChildren(...Array.from({length:5},(_,i)=>elem('span',String(scale*(4-i)/4))));}
    $('history').style.setProperty('--chart-max',max);
    for(const row of rows){const g=elem('div',undefined,'bar-group');g.setAttribute('aria-label',`${localTime(row.at)} 입장 ${row.in}, 퇴장 ${row.out}`);g.title=g.getAttribute('aria-label');
      const i=elem('div',undefined,'bar'),o=elem('div',undefined,'bar out');i.style.height=`${(row.in+row.out)/max*100}%`;o.hidden=true;
      g.append(i,o,elem('small',new Date(row.at*1000).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit',hour12:false})));$('history').append(g);}
  }catch(e){notice(e.message,true);}
}
async function action(fn){try{await fn();}catch(e){notice(e.message,true);}}
$('visitor-link').classList.toggle('active',!adminPage);$('admin-link').hidden=!adminPage;$('admin-link').classList.toggle('active',adminPage);
if(adminPage){$('title').textContent='관리자 로그인';$('subtitle').textContent='';$('login-panel').hidden=false;$('workspace').hidden=true;}
function loggedOut(message='로그아웃했습니다.') {
  window.outdoor?.discard();
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
  if(window.hasUnsavedDesignChanges?.()&&!confirm('저장하지 않은 설정을 버리고 새 화장실을 추가할까요?'))return;
  const result=await api('/api/toilets','POST',{name:$('new-toilet-name').value,stalls:Number($('new-toilet-stalls').value)});
  selected=result.id;dirty=false;positionDraft=null;$('new-toilet-form').reset();await refresh();notice(snapshot.settings.map_mode==='indoor'?'화장실을 추가했습니다. 배치도에서 마커를 드래그한 뒤 저장하세요.':'화장실을 추가했습니다. 실제 지도에서 입구 위치를 지정해 저장하세요.');
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

window.hasUnsavedDesignChanges=()=>dirty||Boolean(window.outdoor?.hasDraft());
$('cancel-edit')?.addEventListener('click',()=>{window.outdoor?.discard();dirty=false;positionDraft=null;fillForm();render();notice('수정을 취소했습니다.');});
window.addEventListener('beforeunload',e=>{if(dirty||window.outdoor?.hasDraft()){e.preventDefault();e.returnValue='';}});

window.rerenderRestflow=render;

window.chooseOutdoorFacility=id=>select(id,true);

$('map-mode')?.addEventListener('change',async event=>{
  const selector=event.target,previous=snapshot?.settings.map_mode||'outdoor',next=selector.value;
  if(next===previous)return;
  if(window.hasUnsavedDesignChanges?.()&&!confirm('저장하지 않은 변경사항을 버리고 모드를 바꿀까요?')){selector.value=previous;return;}
  if(!confirm(`${next==='indoor'?'실내':'야외'} 페스티벌 모드로 바꿀까요? 방문객 화면에도 적용됩니다. 기존 배치도와 위치는 보존됩니다.`)){selector.value=previous;return;}
  selector.disabled=true;
  try{
    await api('/api/map-mode','PUT',{map_mode:next});
    dirty=false;positionDraft=null;window.outdoor?.discard();
    location.reload();
  }catch(error){selector.value=previous;selector.disabled=false;notice(error.message,true);}
});

const buildLabel=elem('small','화면 버전: marker-v2','app-build');document.querySelector('.map-panel').append(buildLabel);
fetch('/api/version').then(async response=>{
  const version=await response.json();
  if(!response.ok||version.build!=='2026-11-13-marker-v2')throw new Error('서버 파일도 함께 업데이트해야 합니다. 실행 창을 종료하고 같은 폴더의 server.py와 web 폴더를 교체한 뒤 다시 실행하세요.');
  buildLabel.textContent='화면·서버 버전: marker-v2';
}).catch(error=>{buildLabel.textContent='실행 버전 확인 필요';notice(error.message,true);});
