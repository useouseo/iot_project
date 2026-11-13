/* TMAP outdoor map. Coordinates and routes use WGS84. Location stays in memory. */
(() => {
  'use strict';
  const panel=document.querySelector('.map-panel');
  const box=document.createElement('section');
  box.innerHTML='<div id="outdoor-map" aria-label="야외 화장실 지도"></div><div class="outdoor-tools"><button id="geo-locate" class="secondary">내 위치 확인</button><button id="geo-route" class="primary" disabled>선택한 화장실 길찾기</button><button id="geo-clear" class="secondary" hidden>경로 지우기</button></div><p id="outdoor-message" role="status">지도를 준비하고 있습니다.</p><div id="outdoor-detail"></div><form id="geo-editor" hidden><strong>선택한 화장실 입구 위치</strong><p>지도를 눌러 입구를 지정한 뒤 저장하세요. 위도·경도 직접 입력도 가능합니다.</p><label>위도<input id="geo-lat" type="number" step="any" min="-90" max="90" required></label><label>경도<input id="geo-lng" type="number" step="any" min="-180" max="180" required></label><button class="primary">입구 위치 저장</button></form>';
  panel.prepend(box);
  const $=id=>document.getElementById(id);
  const labels={quiet:'여유',moderate:'보통',busy:'혼잡',unknown:'확인 필요'};
  let routePending=false, map, sdk, data, selected, editing=false, markers=[], routeLines=[], routeController, sequence=0, position, locationMarker, accuracyCircle, watch, selectedBefore, fitted=false, routing=false;
  const message=s=>{$('outdoor-message').textContent=s;};
  const current=()=>data?.toilets.find(t=>t.id===selected);
  const located=t=>Number.isFinite(t?.latitude)&&Number.isFinite(t?.longitude);
  async function request(path,method='GET',body,signal){
    const response=await fetch(path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(15000)});
    const result=await response.json();if(!response.ok)throw Error(result.error||'요청에 실패했습니다');return result;
  }
  function clearRoute(){sequence++;routeController?.abort();routeLines.forEach(l=>l.setMap(null));routeLines=[];$('geo-clear').hidden=true;}
  function update(snapshot,id,isEditing){
    data=snapshot;selected=id;editing=isEditing;
    if(selectedBefore!==selected){clearRoute();selectedBefore=selected;$('geo-editor').reset();}
    $('geo-editor').hidden=!editing;
    document.querySelectorAll('.badge').forEach(n=>n.textContent='야외 지도');
    const t=current();
    $('outdoor-detail').replaceChildren();
    if(t){const title=document.createElement('strong');title.textContent=t.name;const p=document.createElement('p');p.textContent=`${labels[t.level]} · ${located(t)?'입구 위치 등록됨':'입구 위치 미등록 — 관리자 등록 후 길찾기 가능'}`;$('outdoor-detail').append(title,p);}
    $('geo-route').disabled=routePending||!map||!routing||!located(t)||!position;
    if(editing&&document.activeElement?.closest('#geo-editor')===null&&!$('geo-lat').value&&located(t)){$('geo-lat').value=t.latitude;$('geo-lng').value=t.longitude;}
    if(!map)return;
    markers.forEach(m=>m.setMap(null));markers=[];
    for(const facility of data.toilets.filter(located)){
      const pin=document.createElement('button');pin.className=`geo-pin ${facility.level}${facility.id===selected?' selected':''}`;pin.type='button';pin.textContent=`${facility.name} · ${labels[facility.level]}`;
      const marker=new sdk.Marker({position:new sdk.LatLng(facility.latitude,facility.longitude),map,iconHTML:pin.outerHTML});
      marker.addListener('click',()=>window.chooseOutdoorFacility(facility.id));markers.push(marker);
    }
    if(!fitted){const t=data.toilets.find(located);if(t){map.setCenter(new sdk.LatLng(t.latitude,t.longitude));map.setZoom(16);fitted=true;}}
  }
  window.outdoor={update};
  new ResizeObserver(()=>{if(map&&map.resize)map.resize();}).observe($('outdoor-map'));
  $('geo-clear').onclick=()=>{clearRoute();message('경로를 지웠습니다.');};
  $('geo-editor').onsubmit=async e=>{
    e.preventDefault();if(!current())return;
    const tid=selected,latitude=Number($('geo-lat').value),longitude=Number($('geo-lng').value);
    try{await request(`/api/coordinates/${tid}`,'PUT',{latitude,longitude});clearRoute();message('화장실 입구 위치를 저장했습니다.');const fresh=await request('/api/status');update(fresh,selected,editing);}catch(e){message(e.message);}
  };
  function locate(){
    if(!window.isSecureContext){message('위치 확인은 HTTPS 주소 또는 localhost에서 가능합니다.');return;}
    if(!navigator.geolocation){message('이 브라우저에서는 위치 확인을 지원하지 않습니다.');return;}
    if(watch!==undefined){if(position&&map)map.setCenter(new sdk.LatLng(position.latitude,position.longitude));return;}
    message('휴대폰 위치를 확인하고 있습니다. 위치 권한을 허용해 주세요.');
    watch=navigator.geolocation.watchPosition(result=>{
      const first=!position;position={...result.coords,latitude:result.coords.latitude,longitude:result.coords.longitude,accuracy:result.coords.accuracy,timestamp:result.timestamp};
      if(map){locationMarker?.setMap(null);accuracyCircle?.setMap(null);const point=new sdk.LatLng(position.latitude,position.longitude);locationMarker=new sdk.Marker({position:point,map,iconHTML:'<div class="geo-pin">● 내 위치</div>'});accuracyCircle=new sdk.Circle({center:point,radius:position.accuracy,map,strokeColor:'#287bdb',fillColor:'#287bdb',fillOpacity:.12,strokeWeight:1});if(first)map.setCenter(point);}
      message(`현재 위치 오차 약 ${Math.round(position.accuracy)}m${position.accuracy>100?' · 위치가 부정확합니다. 야외에서 다시 확인해 주세요.':''}`);if(data)update(data,selected,editing);
    },error=>{navigator.geolocation.clearWatch(watch);watch=undefined;position=undefined;locationMarker?.setMap(null);accuracyCircle?.setMap(null);clearRoute();if(data)update(data,selected,editing);message(error.code===1?'위치 권한이 꺼져 있습니다. 브라우저 설정에서 허용한 뒤 다시 눌러주세요.':'위치를 확인하지 못했습니다. 야외에서 다시 시도하세요.');},{enableHighAccuracy:true,timeout:15000,maximumAge:10000});
  }
  $('geo-locate').onclick=locate;
  $('geo-route').onclick=async()=>{
    if(!position||!located(current()))return;
    if(Date.now()-position.timestamp>60000||position.accuracy>100){message('위치가 오래되었거나 오차가 큽니다. 야외에서 정확한 위치가 잡힌 후 다시 시도하세요.');return;}
    clearRoute();routePending=true;const token=sequence;routeController=new AbortController();const timer=setTimeout(()=>routeController?.abort(),15000);$('geo-route').disabled=true;message('도보 경로를 찾고 있습니다.');
    try{
      const result=await request('/api/route','POST',{latitude:position.latitude,longitude:position.longitude,toilet_id:selected},routeController.signal);
      if(token!==sequence)return;
      for(const line of result.lines)routeLines.push(new sdk.Polyline({path:line.map(([lng,lat])=>new sdk.LatLng(lat,lng)),strokeColor:'#1469d5',strokeWeight:6,map}));
      const bounds=new sdk.LatLngBounds();result.lines.flat().forEach(([lng,lat])=>bounds.extend(new sdk.LatLng(lat,lng)));map.fitBounds(bounds);
      message(`도보 ${Number.isFinite(result.distance)?Math.round(result.distance)+'m':''} · ${Number.isFinite(result.seconds)?'약 '+Math.ceil(result.seconds/60)+'분':''}. 임시 통로·통제 구간은 현장 안내를 확인하세요. 이동 후 경로를 다시 조회할 수 있습니다.`);$('geo-clear').hidden=false;
    }catch(e){if(token===sequence)message(e.name==='AbortError'?'길찾기 시간이 초과되었습니다. 다시 시도하세요.':e.message);}
    finally{routePending=false;clearTimeout(timer);if(data)update(data,selected,editing);}
  };
  async function init(){
    try{
      const config=await request('/api/map-config');routing=config.routing;
      if(!config.map_key){message('TMAP 지도 설정이 필요합니다. 관리자가 지도 API 키를 설정하면 표시됩니다.');return;}

      sdk=window.Tmapv2;if(!sdk)throw Error('TMAP 지도 인증을 확인하세요.');
      map=new sdk.Map('outdoor-map',{center:new sdk.LatLng(37.5665,126.978),width:'100%',height:getComputedStyle($('outdoor-map')).height,zoom:15});
      map.addListener('click',event=>{if(!editing||!current())return;$('geo-lat').value=event.latLng.lat();$('geo-lng').value=event.latLng.lng();message('입구 위치를 지정했습니다. 입구 위치 저장을 눌러주세요.');});
      message(routing?'화장실을 선택해 도보 경로를 확인하세요.':'지도는 준비되었습니다. 도보 길찾기 API 설정이 필요합니다.');if(data)update(data,selected,editing);
      if(location.pathname!=='/admin')locate();
    }catch(e){message(e.message);}
  }
  window.addEventListener('pagehide',()=>{if(watch!==undefined)navigator.geolocation.clearWatch(watch);clearRoute();});
  init();
})();
