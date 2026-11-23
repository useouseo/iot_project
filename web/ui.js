'use strict';
const view = document.querySelector('#view');
const notice = document.querySelector('#notice');
const title = document.querySelector('#title');
const slug = location.pathname.match(/^\/module\/([\w-]+)$/)?.[1];
const kinds = [
  ['women','여성'],['men','남성'],['shared','공용'],
  ['women-accessible','여성 장애인'],['men-accessible','남성 장애인'],['shared-accessible','공용 장애인']
];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tell = message => { notice.textContent = message; };
let password = '';
let setup, map, marker, position;
const moduleApi = '/api/module/' + slug;

async function api(path, method='GET', data) {
  const response = await fetch(path, {
    method, headers:{'Content-Type':'application/json',...(password?{Authorization:'Bearer '+encodeURIComponent(password)}:{})},
    body:data ? JSON.stringify(data) : undefined,
  });
  if (response.ok) return response.json();
  const result = await response.json().catch(()=>({}));
  throw Error(result.error || '서버 요청을 완료하지 못했습니다.');
}

function setMarker(lat, lon) {
  position = {lat, lon};
  if (!map) {
    document.querySelector('#map-status').textContent = '검색 결과의 위치를 선택했습니다.';
    return;
  }
  const location = new Tmapv2.LatLng(lat, lon);
  if (marker) marker.setPosition(location);
  else {
    marker = new Tmapv2.Marker({position:location,map,draggable:true});
    marker.addListener('dragend', () => {
      const point = marker.getPosition();
      position = {lat:point.lat(),lon:point.lng()};
    });
  }
  document.querySelector('#map-status').textContent = '마커 위치가 선택됐습니다.';
}

async function installerView() {
  title.textContent = '현장 설치';
  setup = await api('/api/setup');
  view.innerHTML = `<div class="grid">
    <section><h2>설치 위치</h2><form class="search" id="search"><label>장소 검색<input name="keyword" placeholder="시청역" required></label><button>검색</button></form>
    <div id="search-results"></div><div id="map" class="map"></div>
    <p class="hint" id="map-status">지도에서 화장실 입구를 클릭하거나 마커를 옮기세요.</p></section>
    <section><h2>화장실 구역 등록</h2><form id="register">
    <label>작업 장소<select name="place_id"><option value="">새 장소</option>${setup.places.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('')}</select></label>
    <div id="new-place"><label>장소 이름<input name="name" placeholder="시청역 화장실" required maxlength="100"></label><label>주소·위치 안내<input name="address" placeholder="지하 1층 · 개찰구 밖" required maxlength="100"></label></div>
    <fieldset><legend>구역 유형</legend><div class="types">${kinds.map(([value, label], i)=>`<label><input type="radio" name="kind" value="${value}" ${i===0?'checked':''}><span>${label}</span></label>`).join('')}</div></fieldset>
    <label>구역 이름 (선택)<input name="zone_name" maxlength="100" placeholder="예: 지하 1층 여성 화장실"></label>
    <div class="fields"><label>전체 칸 수<input name="total" type="number" min="1" max="99" value="5" required></label><label>장치 ID<input name="device" placeholder="RF-001" maxlength="64" required></label></div>
    <label><input type="checkbox" name="accessible"> 일반 구역 안에 장애인 이용 가능 칸 있음</label>
    <button class="full">구역 등록 및 QR 발급</button></form>
    <div id="handoff"></div><h2 style="margin-top:22px">등록된 모듈</h2><div id="modules"></div></section></div>`;
  renderModules();
  if (!setup.map_key) {
    document.querySelector('#map-status').textContent = 'mobile/.env.local에 TMAP 지도 키를 설정하고 새로고침하세요.';
    return;
  }
  try {
    map = new Tmapv2.Map('map',{center:new Tmapv2.LatLng(37.5655,126.977),width:'100%',height:'100%',zoom:16});
    map.addListener('click', ({latLng}) => setMarker(latLng.lat(),latLng.lng()));
  } catch {
    document.querySelector('#map-status').textContent = 'TMAP 지도를 불러오지 못했습니다. 검색 결과를 선택해 등록할 수 있습니다.';
  }
}

function renderModules() {
  const modules = document.querySelector('#modules');
  modules.innerHTML = setup.modules.map(item=>{
    const place = setup.places.find(p=>p.id===item.place_id)?.name;
    const path = '/module/'+encodeURIComponent(item.slug);
    return `<div class="row"><strong>${esc(item.name)}</strong><small>${esc(place)} · ${esc(item.device)}</small>
      <a class="button secondary" download="RestFlow-${esc(item.device)}.png" href="${path}/qr.png">QR 저장</a>
      <button class="secondary" data-claim="${esc(item.slug)}">인계 코드 재발급</button></div>`;
  }).join('') || '<p class="hint">등록한 모듈이 여기에 표시됩니다.</p>';
}

function showHandoff(result) {
  const path = '/module/' + new URL(result.url).pathname.split('/').at(-1);
  document.querySelector('#handoff').innerHTML = `<div class="card"><h2>모듈 QR과 인계 코드</h2>
    <img alt="모듈 관리자 QR" src="${esc(path)}/qr.png">
    <a href="${esc(result.url)}" target="_blank" rel="noopener">관리자 웹 열기</a>
    <p>인계 코드 <code>${esc(result.claim)}</code></p>
    <p class="hint">QR은 모듈에 부착하고, 인계 코드는 담당자에게 따로 전달하세요.</p></div>`;
}

async function loginView() {
  const status = await api(moduleApi+'/status');
  title.textContent = status.name;
  view.className = 'manager';
  view.innerHTML = `<p>${esc(status.place)}</p><form id="${status.claimed?'login':'claim'}" class="card">
    <h2>${status.claimed?'관리자 로그인':'관리자 비밀번호 설정'}</h2>
    ${status.claimed?'':'<label>1회용 인계 코드<input name="claim" required maxlength="64"></label>'}
    <label>${status.claimed?'비밀번호':'새 비밀번호'}<input type="password" name="password" required minlength="8" maxlength="128" autocomplete="${status.claimed?'current-password':'new-password'}"></label>
    ${status.claimed?'':'<label>비밀번호 확인<input type="password" name="confirm" required minlength="8" maxlength="128" autocomplete="new-password"></label>'}
    <button class="full">${status.claimed?'로그인':'설정 완료'}</button></form>`;
}

async function managerView() {
  const room = await api(moduleApi);
  view.innerHTML = `<p>${esc(room.place)} · ${esc(room.device)}</p>
    <form class="card" id="manage"><h2>운영 칸 수</h2><div class="step">
    <button type="button" data-step="-1" aria-label="운영 칸 수 줄이기">−</button>
    <input aria-label="운영 칸 수" name="open" type="number" min="0" max="${room.total}" value="${room.open}" required>
    <span>/ ${room.total}</span><button type="button" data-step="1" aria-label="운영 칸 수 늘리기">+</button></div>
    <label><input type="checkbox" name="closed" ${room.closed?'checked':''}> 일시 사용 불가</label>
    <label>사유<input name="reason" maxlength="100" value="${esc(room.reason)}" placeholder="예: 청소 중"></label><button class="full">저장</button></form>
    <details class="card"><summary>비밀번호 변경</summary><form id="password">
    <label>현재 비밀번호<input type="password" name="current" required maxlength="128" autocomplete="current-password"></label>
    <label>새 비밀번호<input type="password" name="password" required minlength="8" maxlength="128" autocomplete="new-password"></label>
    <label>새 비밀번호 확인<input type="password" name="confirm" required minlength="8" maxlength="128" autocomplete="new-password"></label><button class="full">비밀번호 변경</button></form></details>`;
}

view.addEventListener('change', event=>{
  if (event.target.name !== 'place_id') return;
  const place=setup.places.find(p=>p.id===event.target.value);
  const fields=document.querySelector('#new-place');
  fields.hidden=Boolean(place);
  fields.querySelectorAll('input').forEach(input=>{input.required=!place;});
  if (place && map) {
    setMarker(place.lat,place.lon);
    map.setCenter(marker.getPosition());
  }
});

view.addEventListener('click', async event=>{
  const button=event.target.closest('button');
  if (!button) return;
  try {
    if (button.dataset.lat) {
      setMarker(Number(button.dataset.lat),Number(button.dataset.lon));
      if (map) {
        map.setCenter(marker.getPosition());
        map.setZoom(17);
      }
    }
    if (button.dataset.step) {
      const input=document.querySelector('#manage [name="open"]');
      input.value=Math.max(0,Math.min(Number(input.max), Number(input.value)+Number(button.dataset.step)));
    }
    if (button.dataset.claim) {
      showHandoff(await api('/api/setup/modules/'+button.dataset.claim+'/claim','POST',{}));
    }
  } catch (error) { tell(error.message); }
});

view.addEventListener('submit', async event=>{
  event.preventDefault();
  const form=event.target;
  const button=form.querySelector('button[type="submit"]') || [...form.querySelectorAll('button')].find(b=>b.type==='submit');
  if (button) button.disabled=true;
  const data=Object.fromEntries(new FormData(form));
  try {
    if (form.id==='search') {
      const {results}=await api('/api/setup/search?q='+encodeURIComponent(data.keyword));
      document.querySelector('#search-results').innerHTML=results.map(p=>`<button class="secondary" data-lat="${p.lat}" data-lon="${p.lon}">${esc(p.name)}</button>`).join('') || '검색 결과가 없습니다.';
    } else if (form.id==='register') {
      if (!data.place_id && !position) throw Error('지도에서 입구 위치를 선택하세요.');
      const result=await api('/api/setup/register','POST',{...data,...position,total:Number(data.total),accessible:data.accessible==='on'});
      setup=await api('/api/setup');
      form.elements.place_id.innerHTML='<option value="">새 장소</option>'+setup.places.map(p=>`<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
      form.elements.place_id.value=result.place_id;
      form.elements.place_id.dispatchEvent(new Event('change',{bubbles:true}));
      form.elements.device.value='';
      form.elements.zone_name.value='';
      renderModules();
      showHandoff(result);
      tell('구역과 모듈을 등록했습니다.');
    } else if (form.id==='claim') {
      if (data.password!==data.confirm) throw Error('비밀번호가 일치하지 않습니다.');
      await api(moduleApi+'/claim','POST',{claim:data.claim,password:data.password});
      password=data.password;
      await managerView();
      tell('비밀번호를 설정했습니다.');
    } else if (form.id==='login') {
      password=data.password;
      await managerView();
      tell('');
    } else if (form.id==='manage') {
      await api(moduleApi,'PUT',{open:Number(data.open),closed:data.closed==='on',reason:data.reason});
      await managerView();
      tell('저장했습니다. 이용자 앱의 다음 조회에서 반영됩니다.');
    } else if (form.id==='password') {
      if (data.password!==data.confirm) throw Error('새 비밀번호가 일치하지 않습니다.');
      if (data.current!==password) throw Error('현재 비밀번호를 확인해 주세요.');
      await api(moduleApi+'/password','PUT',{password:data.password});
      password=data.password;
      await managerView();
      tell('비밀번호를 변경했습니다. 기존 QR을 계속 사용할 수 있습니다.');
    }
  } catch (error) { tell(error.message); }
  finally { if (button) button.disabled=false; }
});

(slug ? loginView() : installerView()).catch(error=>tell(error.message));
