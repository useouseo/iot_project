'use strict';
const view = document.querySelector('#view');
const notice = document.querySelector('#notice');
const managerId = location.pathname.match(/^\/manage\/([\w-]+)$/)?.[1];
const title = document.querySelector('#title');
title.textContent = managerId ? '화장실 시설 관리' : '현장 설치';
let code = '';
let selected = '';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tell = s => { notice.textContent = s; };
async function api(path, method='GET', data) {
  const response = await fetch(path, {method, headers:{Authorization:'Bearer '+code,'Content-Type':'application/json'},body:data ? JSON.stringify(data) : undefined});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '서버 요청에 실패했습니다.');
  return result;
}
function login() {
  view.innerHTML = '<form class="card" id="login"><h2>접속 코드</h2><label>'+(managerId?'시설 관리자 코드':'서버에 표시된 설치팀 코드')+'<input name="code" type="password" required></label><button>접속</button></form>';
}
async function installerView() {
  const {places} = await api('/api/install');
  const place = places.find(p=>p.id===selected) || places[0];
  selected = place?.id || '';
  const device = new URLSearchParams(location.search).get('device') || '';
  view.innerHTML = '<div class="grid"><form class="card" id="place"><h2>장소 등록</h2><label>장소 이름<input name="name" placeholder="시청역 화장실" required maxlength="100"></label><label>주소·위치 안내<input name="address" placeholder="지하 1층 · 개찰구 밖" required maxlength="100"></label><label>위도<input name="lat" type="number" step="any" min="-90" max="90" value="37.5655" required></label><label>경도<input name="lon" type="number" step="any" min="-180" max="180" value="126.977" required></label><button>장소 저장</button></form>'+
    (place ? '<section><label>작업 장소<select id="place-select">'+places.map(p=>'<option value="'+p.id+'" '+(p.id===selected?'selected':'')+'>'+esc(p.name)+'</option>').join('')+'</select></label><h2>설치 구역</h2><ul>'+place.zones.map(z=>'<li>'+esc(z.name)+' · '+esc(z.device)+'</li>').join('')+'</ul><form id="zone"><label>구역명<input name="name" placeholder="여성 화장실" maxlength="100" required></label><label>모듈 ID<input name="device" value="'+esc(device)+'" placeholder="RF-001" maxlength="64" required></label><label>전체 칸 수<input name="total" type="number" min="1" max="99" value="5" required></label><label><input type="checkbox" name="accessible"> 휠체어 접근 확인</label><button>구역 저장</button></form><hr><form id="handoff"><button '+(!place.zones.length?'disabled':'')+'>관리자 코드 및 QR 발급</button></form><div id="handoff-result"></div></section>' : '<section><h2>설치 구역</h2><p>장소를 먼저 등록하세요.</p></section>')+'</div>';
}
async function managerView() {
  const place = await api('/api/manage/'+managerId);
  title.textContent = place.name+' 관리';
  view.innerHTML = '<p>'+esc(place.address)+'</p><div class="grid">'+place.zones.map(z=>'<form class="card" data-zone="'+z.id+'"><h2>'+esc(z.name)+'</h2><label>운영 칸 수 / 전체 '+z.total+'칸<input name="open" type="number" min="0" max="'+z.total+'" value="'+z.open+'" required></label><label><input name="closed" type="checkbox" '+(z.closed?'checked':'')+'> 일시 사용 불가</label><label>사유<input name="reason" value="'+esc(z.reason)+'" maxlength="100" placeholder="청소 중"></label><button>상태 저장</button></form>').join('')+'</div>';
}
view.addEventListener('change', async event=>{
  if(event.target.id==='place-select') {
    selected=event.target.value;
    try { await installerView(); } catch(error) { tell(error.message); }
  }
});
view.addEventListener('submit', async event=>{
  event.preventDefault();
  const form = event.target;
  const submit = form.querySelector('button');
  submit.disabled = true;
  const data = Object.fromEntries(new FormData(form));
  try {
    if(form.id==='login') {
      code=data.code;
      await (managerId ? managerView() : installerView());
      tell('');
    } else if(form.id==='place') {
      const created=await api('/api/install','POST',{...data,lat:Number(data.lat),lon:Number(data.lon)});
      selected=created.id;
      await installerView();
      tell('장소를 등록했습니다.');
    } else if(form.id==='zone') {
      await api('/api/install/'+selected+'/zones','POST',{...data,total:Number(data.total),accessible:data.accessible==='on'});
      await installerView();
      tell('구역과 모듈을 연결했습니다.');
    } else if(form.id==='handoff') {
      const handoff=await api('/api/install/'+selected+'/handoff','POST',{});
      const link=new URL(handoff.path,location.origin).href;
      document.querySelector('#handoff-result').innerHTML='<img alt="장소 관리자 QR" src="'+handoff.path+'/qr.png"><p><a href="'+handoff.path+'" target="_blank" rel="noopener">관리자 웹 열기</a></p><p>관리 링크 <code>'+esc(link)+'</code></p><p>관리자 코드 <code>'+esc(handoff.code)+'</code></p>';
      tell('관리 링크와 코드를 담당자에게 전달하세요. 새 코드 발급 시 이전 코드는 만료됩니다.');
    } else if(form.dataset.zone) {
      await api('/api/manage/'+managerId+'/zones/'+form.dataset.zone,'PUT',{...data,open:Number(data.open),closed:data.closed==='on'});
      await managerView();
      tell('저장했습니다. 이용자 앱에서 곧 확인할 수 있습니다.');
    }
  } catch(error) { tell(error.message); }
  finally { submit.disabled = false; }
});
login();
