'use strict';
const view = document.querySelector('#view');
const title = document.querySelector('#title');
const notice = document.querySelector('#notice');
const path = location.pathname;
const pid = path.split('/')[2];
const facility = path.startsWith('/facility/');
const facilityApi = '/api/facility/' + pid;
const kinds = [['women','여성'],['men','남성'],['shared','공용'],['women-accessible','여성 장애인'],['men-accessible','남성 장애인'],['shared-accessible','공용 장애인']];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const say = message => { notice.textContent = message; };
let password = '', map, draft, draftMarker, setup, adding = false;
async function api(url, method='GET', data) {
  const response = await fetch(url, {method, headers:{'Content-Type':'application/json',...(password ? {Authorization:'Bearer '+encodeURIComponent(password)} : {})},body:data ? JSON.stringify(data) : undefined});
  const result = await response.json().catch(()=>({}));
  if (!response.ok) throw Error(result.error || '요청을 완료하지 못했습니다.');
  return result;
}
const placePath = id => '/places/'+encodeURIComponent(id);
function markDraft(point) {
  draft = {lat:point.lat(),lon:point.lng()};
  if (draftMarker) draftMarker.setPosition(point);
  else {
    draftMarker = new Tmapv2.Marker({position:point,map,draggable:true,title:'새 장소 위치'});
    draftMarker.addListener('dragend',()=>markDraft(draftMarker.getPosition()));
  }
}
function toggleAdd(on) {
  adding = on;
  document.querySelector('#add-place').hidden = !on;
  if (on && map) markDraft(map.getCenter());
  if (!on) { draftMarker?.setMap(null); draftMarker=null; draft=null; }
}
function pinLabel(index) {
  let result='';
  for(let n=index+1;n;n=Math.floor((n-1)/26)) result=String.fromCharCode(65+(n-1)%26)+result;
  return result;
}
async function mapView() {
  title.textContent = '장소 지도';
  setup = await api('/api/setup');
  view.innerHTML = `<div class="bar map-tools"><form id="search" class="search"><label>장소 검색<input name="keyword" required placeholder="시청역"></label><button>검색</button></form><button data-action="add-place">+ 새 장소 추가</button></div>
    <div id="search-results"></div><div id="map" class="map map-large"></div>
    <form id="add-place" class="card" hidden><h2>새 장소 추가</h2><p class="hint">지도를 클릭하거나 마커를 옮겨 위치를 선택하세요.</p>
    <label>장소 이름<input name="name" required maxlength="100"></label><label>위치 안내<input name="address" required maxlength="100"></label>
    <button type="button" class="secondary" data-action="cancel-place">취소</button> <button>장소 저장</button></form>
    <section style="margin-top:14px"><h2>등록된 장소</h2>${setup.places.map((p,i)=>`<div class="row"><a href="${placePath(p.id)}"><b>${pinLabel(i)}</b> · ${esc(p.name)}</a><small>${esc(p.address)}</small></div>`).join('') || '<p class="hint">등록된 장소가 없습니다.</p>'}</section>`;
  try {
    map = new Tmapv2.Map('map',{center:new Tmapv2.LatLng(37.5655,126.977),width:'100%',height:'100%',zoom:16});
    const bounds = new Tmapv2.LatLngBounds();
    setup.places.forEach((place,i)=>{
      const point = new Tmapv2.LatLng(place.lat,place.lon);
      const pin = new Tmapv2.Marker({position:point,map,title:place.name,iconHTML:`<div class="label-pin"><b>${pinLabel(i)}</b>${esc(place.name)}</div>`});
      pin.addListener('click',()=>{if(!adding) location.assign(placePath(place.id));});
      bounds.extend(point);
    });
    if (setup.places.length===1) map.setCenter(new Tmapv2.LatLng(setup.places[0].lat,setup.places[0].lon));
    if (setup.places.length>1) map.fitBounds(bounds);
    map.addListener('click',({latLng})=>{if(adding) markDraft(latLng);});
  } catch {
    say(setup.map_key ? 'TMAP 지도를 열지 못했습니다. 장소 검색 결과로 등록할 수 있습니다.' : 'TMAP 키를 설정하면 지도가 표시됩니다.');
  }
}
async function installerPlace() {
  setup = await api('/api/setup');
  const place = setup.places.find(item=>item.id===pid);
  if (!place) throw Error('장소를 찾을 수 없습니다.');
  const status=await api(facilityApi+'/status');
  title.textContent=place.name;
  const qr='/facility/'+encodeURIComponent(pid)+'/qr.png';
  view.innerHTML=`<p><a class="button secondary" href="/">← 장소 지도</a></p><p>${esc(place.address)}</p>
  <section><div class="bar"><h2>등록된 모듈</h2><button data-action="add-zone">+ 모듈 추가</button></div>
  ${place.zones.map(z=>`<div class="row"><strong>${esc(z.name)}</strong><span>${esc(z.device)}</span><span>${z.open}/${z.total}칸${z.closed?' · 일시 사용 불가':''}</span><button class="danger" data-delete="${z.id}" data-name="${esc(z.name)}">삭제</button></div>`).join('') || '<p class="hint">등록된 모듈이 없습니다.</p>'}
  <form id="add-zone" hidden><fieldset><legend>구역 유형</legend><div class="types">${kinds.map(([v,t],i)=>`<label><input type="radio" name="kind" value="${v}" ${i===0?'checked':''}><span>${t}</span></label>`).join('')}</div></fieldset>
  <label>구역 이름 (선택)<input name="zone_name" maxlength="100"></label><label>전체 칸 수<input name="total" type="number" min="1" max="99" value="5" required></label>
  <label>장치 ID<input name="device" required maxlength="64" placeholder="RF-001"></label>
  <label><input type="checkbox" name="accessible"> 일반 구역 안에 장애인 이용 가능 칸 있음</label><button>모듈 등록</button></form></section>
  <section style="margin-top:14px"><h2>장소 관리자 QR</h2><img alt="장소 관리자 QR" src="${qr}">
  <div class="row-actions"><a class="button secondary" href="${qr}" download="RestFlow-장소관리.png">QR 저장</a><a class="button secondary" href="/facility/${encodeURIComponent(pid)}" target="_blank" rel="noopener">관리자 웹 열기</a>
  ${status.claimed?'':'<button data-action="claim-code">최초 인계 코드 발급</button>'}</div><div id="claim-result"></div></section>`;
}
async function loginView() {
  const status=await api(facilityApi+'/status');
  title.textContent=status.name;
  view.className='manager';
  view.innerHTML=`<p>${esc(status.address)}</p><form class="card" id="${status.claimed?'login':'claim'}"><h2>${status.claimed?'관리자 로그인':'관리자 비밀번호 설정'}</h2>
  ${status.claimed?'':'<label>1회용 인계 코드<input name="claim" required maxlength="64"></label>'}
  <label>비밀번호<input type="password" name="password" minlength="8" maxlength="128" required autocomplete="${status.claimed?'current-password':'new-password'}"></label>
  ${status.claimed?'':'<label>비밀번호 확인<input type="password" name="confirm" minlength="8" maxlength="128" required autocomplete="new-password"></label>'}<button>${status.claimed?'로그인':'설정 완료'}</button></form>`;
}
async function managerView() {
  const place=await api(facilityApi);
  view.innerHTML=`<p>${esc(place.address)}</p>${place.zones.map(z=>`<form class="card" data-zone="${z.id}"><h2>${esc(z.name)}</h2>
    <label>운영 칸 수 / 전체 ${z.total}칸<input name="open" type="number" min="0" max="${z.total}" value="${z.open}" required></label>
    <label><input name="closed" type="checkbox" ${z.closed?'checked':''}> 일시 사용 불가</label>
    <label>사유<input name="reason" maxlength="100" value="${esc(z.reason)}"></label><button>저장</button></form>`).join('') || '<p>등록된 구역이 없습니다.</p>'}
    <details class="card"><summary>비밀번호 변경</summary><form id="password"><label>현재 비밀번호<input name="current" type="password" required autocomplete="current-password"></label><label>새 비밀번호<input name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password"></label><label>새 비밀번호 확인<input name="confirm" type="password" required minlength="8" maxlength="128" autocomplete="new-password"></label><button>변경</button></form></details>`;
}
view.addEventListener('click',async event=>{
  const b=event.target.closest('button');
  if(!b) return;
  try {
    if(b.dataset.action==='add-place') toggleAdd(true);
    if(b.dataset.action==='cancel-place') toggleAdd(false);
    if(b.dataset.action==='add-zone') document.querySelector('#add-zone').hidden=false;
    if(b.dataset.lat){
      if(!adding) toggleAdd(true);
      if(map){
        const point=new Tmapv2.LatLng(Number(b.dataset.lat),Number(b.dataset.lon));
        markDraft(point); map.setCenter(point); map.setZoom(17);
      } else draft={lat:Number(b.dataset.lat),lon:Number(b.dataset.lon)};
    }
    if(b.dataset.delete && confirm(b.dataset.name+' 모듈을 삭제할까요?')){
      await api('/api/setup/places/'+pid+'/zones/'+b.dataset.delete,'DELETE');
      await installerPlace();
      say('모듈을 삭제했습니다.');
    }
    if(b.dataset.action==='claim-code'){
      const result=await api('/api/setup/places/'+pid+'/claim','POST',{});
      document.querySelector('#claim-result').innerHTML=`<p>1회용 인계 코드 <code>${esc(result.claim)}</code></p><p>관리 링크 <a href="${esc(result.url)}">${esc(result.url)}</a></p>`;
    }
  }catch(e){say(e.message);}
});
view.addEventListener('submit',async event=>{
  event.preventDefault();
  const form=event.target;
  const button=[...form.querySelectorAll('button')].find(b=>b.type==='submit');
  if(button) button.disabled=true;
  const data=Object.fromEntries(new FormData(form));
  try{
    if(form.id==='search'){
      const {results}=await api('/api/setup/search?q='+encodeURIComponent(data.keyword));
      document.querySelector('#search-results').innerHTML=results.map(p=>`<button class="secondary" data-lat="${p.lat}" data-lon="${p.lon}">${esc(p.name)}</button>`).join('') || '검색 결과가 없습니다.';
    }else if(form.id==='add-place'){
      if(!draft) throw Error('지도에서 위치를 선택하세요.');
      await api('/api/setup/places','POST',{...data,...draft});
      toggleAdd(false);
      location.reload();
    }else if(form.id==='add-zone'){
      await api('/api/setup/register','POST',{...data,place_id:pid,total:Number(data.total),accessible:data.accessible==='on'});
      await installerPlace();say('모듈을 등록했습니다.');
    }else if(form.id==='claim'||form.id==='login'){
      if(form.id==='claim'){
        if(data.password!==data.confirm) throw Error('비밀번호가 일치하지 않습니다.');
        await api(facilityApi+'/claim','POST',{claim:data.claim,password:data.password});
      }
      password=data.password;
      await managerView();say('');
    }else if(form.dataset.zone){
      await api(facilityApi+'/zones/'+form.dataset.zone,'PUT',{open:Number(data.open),closed:data.closed==='on',reason:data.reason});
      await managerView();say('저장했습니다.');
    }else if(form.id==='password'){
      if(data.current!==password||data.password!==data.confirm) throw Error('현재 비밀번호와 새 비밀번호 확인을 확인해 주세요.');
      await api(facilityApi+'/password','PUT',{password:data.password});
      password=data.password;await managerView();say('비밀번호를 변경했습니다.');
    }
  }catch(e){say(e.message);}
  finally{if(button) button.disabled=false;}
});
(facility?loginView():pid?installerPlace():mapView()).catch(error=>say(error.message));
