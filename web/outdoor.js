/* TMAP outdoor map. Coordinates and routes use WGS84. Location stays in memory. */
(() => {
  'use strict';
  const panel=document.querySelector('.map-panel');
  const box=document.createElement('section');box.className='outdoor-section';
  box.innerHTML='<div id="outdoor-map" aria-label="야외 화장실 지도"></div><div class="outdoor-tools"><button id="geo-locate" class="secondary">내 위치 확인</button><button id="geo-route" class="primary" disabled>길찾기</button></div><p id="outdoor-message" role="status">지도를 준비하고 있습니다.</p><div id="outdoor-detail"></div><form id="geo-editor" hidden><strong id="geo-editor-title">선택한 화장실 입구 위치</strong><p>마커를 누른 채 끌어서 입구에 놓고 위치 저장을 누르세요. 새 화장실은 지도 중앙의 반투명 마커를 옮기면 됩니다.</p><details class="geo-coordinate-fields"><summary>좌표 직접 입력 (선택)</summary><label>위도<input id="geo-lat" type="number" step="any" min="-90" max="90" required></label><label>경도<input id="geo-lng" type="number" step="any" min="-180" max="180" required></label></details><button id="geo-save" class="primary">위치 저장</button><button id="geo-undo" class="secondary" type="button" disabled>위치 되돌리기</button><p id="geo-draft-state" role="status"></p></form>';
  const heading=panel.querySelector('.map-heading');
  if(heading)heading.after(box);else panel.prepend(box);
  const $=id=>document.getElementById(id);
  const labels={quiet:'여유',moderate:'보통',busy:'혼잡',unknown:'확인 필요'};
  let routePending=false, map, sdk, data, selected, editing=false, markers=[], routeLines=[], routeController, sequence=0, position, locationMarker, accuracyCircle, watch, selectedBefore, fitted=false, routing=false;
  let draft=null, draggingMarker=false, markerSignature='', suppressMapClickUntil=0;
  const message=s=>{$('outdoor-message').textContent=s;};
  let pointerTap=null, lastActivation=null;
  const current=()=>data?.toilets.find(t=>t.id===selected);
  const located=t=>Number.isFinite(t?.latitude)&&Number.isFinite(t?.longitude);
  async function request(path,method='GET',body,signal){
    const response=await fetch(window.festivalApiPath(path),{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:signal||AbortSignal.timeout(15000)});
    const result=await response.json();if(!response.ok)throw Error(result.error||'요청에 실패했습니다');return result;
  }
  function clearRoute(){sequence++;routeController?.abort();routeLines.forEach(l=>l.setMap(null));routeLines=[];routePending=false;$('geo-route').textContent='길찾기';}
  function update(snapshot,id,isEditing){
    data=snapshot;selected=id;editing=isEditing;
    if((snapshot.settings.map_mode||'outdoor')==='indoor'){clearRoute();if(watch!==undefined)navigator.geolocation.clearWatch(watch);watch=undefined;draft=null;return;}
    if(selectedBefore!==selected||!editing){draft=null;draggingMarker=false;}
    if(selectedBefore!==selected){clearRoute();selectedBefore=selected;$('geo-editor').reset();}
    $('geo-editor').hidden=!editing;
    document.querySelectorAll('.badge').forEach(n=>n.textContent='야외 지도');
    const t=current();
    $('geo-editor-title').textContent=t?`${t.name} · 입구 위치`:'화장실을 먼저 추가하세요';
    $('outdoor-detail').replaceChildren();
    if(t){const title=document.createElement('strong');title.textContent=t.name;const p=document.createElement('p');p.textContent=`${labels[t.level]} · ${located(t)?'입구 위치 등록됨':'입구 위치 미등록 — 관리자 등록 후 길찾기 가능'}`;$('outdoor-detail').append(title,p);}
    $('geo-route').textContent=routeLines.length?'경로 지우기':routePending?'경로 찾는 중…':'길찾기';
    $('geo-route').disabled=routePending||(!routeLines.length&&(Boolean(draft)||!map||!routing||!located(t)||!position));
    $('geo-save').disabled=!t||!draft; $('geo-undo').disabled=!draft;
    $('geo-draft-state').textContent=draft?'위치를 변경했습니다. 아직 저장되지 않았습니다.':located(t)?'저장된 입구 위치입니다. 마커를 드래그해 수정하세요.':'입구 위치가 없습니다. 지도 중앙의 마커를 옮겨 저장하세요.';
    if(editing&&document.activeElement?.closest('#geo-editor')===null&&!$('geo-lat').value&&located(t)){$('geo-lat').value=t.latitude;$('geo-lng').value=t.longitude;}
    if(!map)return;
    if(!fitted){const t=data.toilets.find(located);if(t){map.setCenter(new sdk.LatLng(t.latitude,t.longitude));map.setZoom(16);fitted=true;}}
    drawMarkers();
  }
  function drawMarkers(){
    if(!map||draggingMarker)return;
    const signature=JSON.stringify([selected,editing,draft,data.toilets.map(t=>[t.id,t.name,t.level,t.latitude,t.longitude])]);
    if(signature===markerSignature)return;
    markerSignature=signature;
    markers.forEach(m=>m.setMap(null));markers=[];
    data.toilets.forEach((facility,index)=>{
      const isSelected=facility.id===selected;
      const unplaced=!located(facility)&&!(draft?.id===facility.id);
      if(unplaced&&!(editing&&isSelected))return;
      const point=draft?.id===facility.id?new sdk.LatLng(draft.latitude,draft.longitude):located(facility)?new sdk.LatLng(facility.latitude,facility.longitude):map.getCenter();
      const pin=document.createElement('button');
      pin.className=`geo-pin ${facility.level}${isSelected?' selected':''}${unplaced?' unplaced':''}`;
      pin.dataset.facilityId=facility.id;pin.type='button';pin.setAttribute('aria-pressed',String(isSelected));pin.setAttribute('aria-label',`${facility.name}, ${labels[facility.level]}${editing?' · 드래그하여 입구 위치 지정':''}`);
      pin.title=facility.name+(editing?' · 드래그하여 위치 이동':'');
      const letter=document.createElement('span');letter.className='geo-letter';letter.textContent=index<26?String.fromCharCode(65+index):String(index+1);
      const status=document.createElement('small');status.textContent=unplaced?'미등록':labels[facility.level];pin.append(letter,status);
      const wrapper=document.createElement('div');wrapper.className='geo-facility-marker';wrapper.append(pin);
      const marker=new sdk.Marker({position:point,map,iconHTML:wrapper.outerHTML,iconSize:new sdk.Size(52,70),draggable:editing&&isSelected,title:facility.name});
      marker.addListener('click',()=>activateFacility(facility.id));
      if(editing){
        marker.addListener('dragstart',()=>{
          draggingMarker=true;
          const start=marker.getPosition();setDraft(start,false);
        });
        marker.addListener('dragend',()=>{
          const point=marker.getPosition();draggingMarker=false;suppressMapClickUntil=performance.now()+500;
          setDraft(point,false); // Keep this marker alive until the SDK finishes its drag event.
          requestAnimationFrame(()=>{if(data)update(data,selected,editing);});
        });
      }
      markers.push(marker);
    });
  }
  function setDraft(point,redraw=true){
    if(!editing||!current())return;
    draft={id:selected,latitude:point.lat(),longitude:point.lng()};
    $('geo-lat').value=draft.latitude;$('geo-lng').value=draft.longitude;
    clearRoute();message('마커를 옮겼습니다. 위치 저장을 눌러주세요.');
    $('geo-save').disabled=false;$('geo-undo').disabled=false;
    $('geo-draft-state').textContent='위치를 변경했습니다. 아직 저장되지 않았습니다.';
    if(redraw)update(data,selected,editing);
  }
  function discard(){draft=null;draggingMarker=false;markerSignature='';$('geo-editor').reset();const t=current();if(located(t)){$('geo-lat').value=t.latitude;$('geo-lng').value=t.longitude;}if(data)update(data,selected,editing);}
  window.outdoor={update,hasDraft:()=>Boolean(draft),discard};
  function activateFacility(id){
    if(draggingMarker||performance.now()<suppressMapClickUntil||!data?.toilets.some(t=>t.id===id))return;
    if(lastActivation?.id===id&&performance.now()-lastActivation.at<350)return;
    lastActivation={id,at:performance.now()};
    window.chooseOutdoorFacility(id);
  }
  function pinAt(event){
    const target=event.target?.closest?.('[data-facility-id]');
    if(target&&$('outdoor-map').contains(target))return target;
    // SDK map/polygon layers can be the event target even when a visible HTML pin is tapped.
    // Hit-test visible pins in screen coordinates before the SDK consumes the event.
    const pins=[...$('outdoor-map').querySelectorAll('[data-facility-id]')].reverse();
    return pins.find(pin=>{
      const rect=pin.getBoundingClientRect();
      return rect.width>0&&rect.height>0&&event.clientX>=rect.left&&event.clientX<=rect.right&&event.clientY>=rect.top&&event.clientY<=rect.bottom;
    });
  }
  const mapElement=$('outdoor-map');
  mapElement.addEventListener('click',event=>{
    const pin=pinAt(event);if(!pin)return;
    if(draggingMarker||performance.now()<suppressMapClickUntil)return;
    event.preventDefault();event.stopPropagation();activateFacility(Number(pin.dataset.facilityId));
  },true);
  mapElement.addEventListener('pointerdown',event=>{
    if(editing||event.isPrimary===false||(event.pointerType==='mouse'&&event.button!==0))return;
    const pin=pinAt(event);
    pointerTap=pin?{id:Number(pin.dataset.facilityId),pointer:event.pointerId,x:event.clientX,y:event.clientY,moved:false}:null;
  },true);
  document.addEventListener('pointermove',event=>{
    if(pointerTap&&event.pointerId===pointerTap.pointer&&Math.hypot(event.clientX-pointerTap.x,event.clientY-pointerTap.y)>12)pointerTap.moved=true;
  },true);
  document.addEventListener('pointerup',event=>{
    if(!pointerTap||event.pointerId!==pointerTap.pointer)return;
    const tap=pointerTap;pointerTap=null;
    if(editing||tap.moved||Math.hypot(event.clientX-tap.x,event.clientY-tap.y)>12)return;
    event.preventDefault();event.stopPropagation();activateFacility(tap.id);
  },true);
  document.addEventListener('pointercancel',()=>{pointerTap=null;},true);
  $('geo-undo').onclick=()=>{discard();message('저장된 위치로 되돌렸습니다.');};
  $('geo-editor').addEventListener('input',()=>{
    const lat=$('geo-lat'),lng=$('geo-lng');
    if(lat.value!==''&&lng.value!==''&&lat.validity.valid&&lng.validity.valid)setDraft({lat:()=>Number(lat.value),lng:()=>Number(lng.value)});
  });
  new ResizeObserver(()=>{if(map&&map.resize)map.resize();}).observe($('outdoor-map'));
  $('geo-editor').onsubmit=async e=>{
    e.preventDefault();if(!current())return;
    const tid=selected,latitude=Number($('geo-lat').value),longitude=Number($('geo-lng').value);
    try{await request(`/api/coordinates/${tid}`,'PUT',{latitude,longitude});if(selected===tid){draft=null;markerSignature='';}clearRoute();message('화장실 입구 위치를 저장했습니다.');const fresh=await request('/api/status');update(fresh,selected,editing);}catch(e){message(e.message);}
  };
  function acceptLocation(result,recenter=false){
    const first=!position;
    position={latitude:result.coords.latitude,longitude:result.coords.longitude,accuracy:result.coords.accuracy,timestamp:result.timestamp};
    if(map){
      locationMarker?.setMap(null);accuracyCircle?.setMap(null);
      const point=new sdk.LatLng(position.latitude,position.longitude);
      locationMarker=new sdk.Marker({position:point,map,iconHTML:'<div class="geo-user-marker"><span></span><strong>내 위치</strong></div>'});
      accuracyCircle=new sdk.Circle({center:point,radius:position.accuracy,map,strokeColor:'#287bdb',fillColor:'#287bdb',fillOpacity:.12,strokeWeight:1});
      if(first||recenter)map.setCenter(point);
    }
    if(recenter||(!routePending&&!routeLines.length))message(`현재 위치 오차 약 ${Math.round(position.accuracy)}m${position.accuracy>100?' · 위치 오차가 큽니다. 길찾기 전 출발 위치를 확인하세요.':''}`);
    if(data)update(data,selected,editing);
  }
  function locationFailure(error){
    if(error.code===1){
      position=undefined;locationMarker?.setMap(null);accuracyCircle?.setMap(null);clearRoute();
      if(watch!==undefined)navigator.geolocation.clearWatch(watch);watch=undefined;
    }
    if(data)update(data,selected,editing);
    return error.code===1?'위치 권한이 꺼져 있습니다. 브라우저 설정에서 허용한 뒤 다시 눌러주세요.':position?'새 위치를 확인하지 못했습니다. 마지막 위치는 지도에 유지됩니다.':'위치를 확인하지 못했습니다. 야외에서 다시 시도하세요.';
  }
  function freshLocation(recenter=false){
    return new Promise((resolve,reject)=>navigator.geolocation.getCurrentPosition(result=>{acceptLocation(result,recenter);resolve(result);},reject,{enableHighAccuracy:true,timeout:12000,maximumAge:0}));
  }
  async function locate(){
    if(!window.isSecureContext){message('위치 확인은 HTTPS 주소 또는 localhost에서 가능합니다.');return;}
    if(!navigator.geolocation){message('이 브라우저에서는 위치 확인을 지원하지 않습니다.');return;}
    if($('geo-locate').disabled)return;
    $('geo-locate').disabled=true;message('휴대폰 위치를 새로 확인하고 있습니다.');
    if(watch===undefined){
      watch=navigator.geolocation.watchPosition(result=>acceptLocation(result),error=>{
        const warning=locationFailure(error);if(!routePending&&!routeLines.length)message(warning);
      },{enableHighAccuracy:true,timeout:15000,maximumAge:10000});
    }
    try{await freshLocation(true);}catch(error){message(locationFailure(error));}
    finally{$('geo-locate').disabled=false;}
  }
  $('geo-locate').onclick=locate;
  $('geo-route').onclick=async()=>{
    if(routeLines.length){clearRoute();message('경로를 지웠습니다. 다른 화장실을 선택하거나 길찾기를 다시 누르세요.');if(data)update(data,selected,editing);return;}
    if(!position||!located(current()))return;
    clearRoute();routePending=true;const token=sequence;routeController=new AbortController();let timer;$('geo-route').disabled=true;message('도보 경로를 찾고 있습니다.');
    try{
      if(Date.now()-position.timestamp>60000){
        message('길찾기 전에 현재 위치를 새로 확인하고 있습니다.');
        try{await freshLocation();}catch(error){
          const warning=locationFailure(error);
          if(!position){message(warning);return;}
        }
      }
      if(token!==sequence)return;
      const warnings=[];
      if(Date.now()-position.timestamp>60000)warnings.push('최신 위치를 받지 못해 마지막으로 확인한 위치를 사용합니다.');
      if(position.accuracy>100)warnings.push(`현재 위치 오차가 약 ${Math.round(position.accuracy)}m입니다.`);
      if(warnings.length&&!confirm(warnings.join('\n')+'\n지도에서 출발 위치를 확인하셨나요? 이 위치로 길찾기를 계속할까요?')){message('길찾기를 취소했습니다. 내 위치 확인 후 다시 시도할 수 있습니다.');return;}
      message('도보 경로를 찾고 있습니다.');
      timer=setTimeout(()=>routeController?.abort(),15000);
      const result=await request('/api/route','POST',{latitude:position.latitude,longitude:position.longitude,toilet_id:selected},routeController.signal);
      if(token!==sequence)return;
      for(const line of result.lines)routeLines.push(new sdk.Polyline({path:line.map(([lng,lat])=>new sdk.LatLng(lat,lng)),strokeColor:'#1469d5',strokeWeight:6,map}));
      const bounds=new sdk.LatLngBounds();result.lines.flat().forEach(([lng,lat])=>bounds.extend(new sdk.LatLng(lat,lng)));map.fitBounds(bounds);
      message(`${warnings.length?'위치 오차에 따라 출발점이 다를 수 있습니다. ':''}도보 ${Number.isFinite(result.distance)?Math.round(result.distance)+'m':''} · ${Number.isFinite(result.seconds)?'약 '+Math.ceil(result.seconds/60)+'분':''}. 임시 통로·통제 구간은 현장 안내를 확인하세요. 이동 후 경로를 다시 조회할 수 있습니다.`);
    }catch(e){if(token===sequence)message(e.name==='AbortError'?'길찾기 시간이 초과되었습니다. 다시 시도하세요.':e.message);}
    finally{clearTimeout(timer);if(token===sequence){routePending=false;if(data)update(data,selected,editing);}}
  };
  async function init(){
    try{
      const config=await request('/api/map-config');routing=config.routing;
      if(config.map_mode==='indoor')return;
      if(!config.map_key){message('TMAP 지도 설정이 필요합니다. 관리자가 지도 API 키를 설정하면 표시됩니다.');return;}

      sdk=window.Tmapv2;if(!sdk)throw Error('TMAP 지도 인증을 확인하세요.');
      map=new sdk.Map('outdoor-map',{center:new sdk.LatLng(37.5665,126.978),width:'100%',height:getComputedStyle($('outdoor-map')).height,zoom:15});
      map.addListener('click',event=>{if(event.originalEvent?.target?.closest?.('[data-facility-id]'))return;if(!editing||!current()||draggingMarker||performance.now()<suppressMapClickUntil)return;setDraft(event.latLng);});
      message(routing?'화장실을 선택해 도보 경로를 확인하세요.':'지도는 준비되었습니다. 도보 길찾기 API 설정이 필요합니다.');if(data)update(data,selected,editing);
      if(location.pathname!=='/admin')locate();
    }catch(e){message(e.message);}
  }
  window.addEventListener('pagehide',()=>{if(watch!==undefined)navigator.geolocation.clearWatch(watch);clearRoute();});
  init();
})();
