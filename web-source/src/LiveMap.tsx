import type {Availability} from './availability';
import {useEffect, useRef} from 'react';

export type Point = {lat:number; lon:number};
type Marker = Point & {id:string;name:string;state?:Availability};
export default function LiveMap({markers, draft, onDraft, onSelect, center, onError, controls, selectedId, searchPoint, currentPosition, route}: {
  markers:Marker[]; draft:Point|null; center?:Point; onDraft?:(point:Point)=>void;
  onSelect:(id:string)=>void; onError:(message:string)=>void; controls?:boolean; selectedId?:string; searchPoint?:Point|null; currentPosition?:(Point & {accuracy:number}); route?:{lines:[number,number][][]};
}) {
  const root=useRef<HTMLDivElement>(null);
  const engine=useRef<any>(null);
  const callbacks=useRef({onDraft,onSelect,onError});
  callbacks.current={onDraft,onSelect,onError};
  const lastTouch=useRef<{id:string;time:number} | null>(null);
  function pinId(target:EventTarget | null){
    return target instanceof Element ? target.closest<HTMLButtonElement>('button[data-place-id]')?.dataset.placeId : undefined;
  }
  function selectPin(event: React.MouseEvent) {
    const id=pinId(event.target);
    if(!id) return;
    event.stopPropagation();
    if(lastTouch.current?.id===id && event.detail!==0 && performance.now()-lastTouch.current.time<800) return;
    callbacks.current.onSelect(id);
  }
  useEffect(()=>{
    const container=root.current;
    if(!container) return;
    let start:{id:string;x:number;y:number;finger:number} | undefined;
    const touchStart=(event:TouchEvent)=>{
      start=undefined;
      const id=pinId(event.target);
      const touch=event.touches[0];
      if(id && touch && event.touches.length===1) start={id,x:touch.clientX,y:touch.clientY,finger:touch.identifier};
    };
    const touchMove=(event:TouchEvent)=>{
      if(!start) return;
      const touch=event.touches[0];
      if(event.touches.length!==1 || Math.hypot(touch.clientX-start.x,touch.clientY-start.y)>10) start=undefined;
    };
    const touchEnd=(event:TouchEvent)=>{
      const tap=start;
      start=undefined;
      if(!tap || event.touches.length) return;
      const touch=Array.from(event.changedTouches).find(item=>item.identifier===tap.finger);
      if(!touch || Math.hypot(touch.clientX-tap.x,touch.clientY-tap.y)>10) return;
      if(event.cancelable) event.preventDefault();
      lastTouch.current={id:tap.id,time:performance.now()};
      callbacks.current.onSelect(tap.id);
    };
    const touchCancel=()=>{start=undefined;};
    container.addEventListener('touchstart',touchStart,{capture:true,passive:true});
    container.addEventListener('touchmove',touchMove,{capture:true,passive:true});
    container.addEventListener('touchend',touchEnd,{capture:true,passive:false});
    container.addEventListener('touchcancel',touchCancel,true);
    return ()=>{
      container.removeEventListener('touchstart',touchStart,true);
      container.removeEventListener('touchmove',touchMove,true);
      container.removeEventListener('touchend',touchEnd,true);
      container.removeEventListener('touchcancel',touchCancel,true);
    };
  },[]);
  const draftPin=useRef<any>(null);
  useEffect(()=>{
    const sdk=(window as any).Tmapv2;
    if(!sdk?.Map){callbacks.current.onError('TMAP 지도를 열지 못했습니다. 지도 키와 연결을 확인하세요.');return;}
    try {
      const map=new sdk.Map(root.current,{center:new sdk.LatLng(37.5655,126.977),width:'100%',height:'100%',zoom:16});
      engine.current=map;
      map.addListener('click',({latLng}:any)=>{
        if(latLng) callbacks.current.onDraft?.({lat:latLng.lat(),lon:latLng.lng()});
      });
      return ()=>{engine.current=null;map.destroy?.();};
    } catch { callbacks.current.onError('TMAP 지도 초기화에 실패했습니다.'); }
  },[]);
  const focus=center ?? markers[0];
  useEffect(()=>{
    const sdk=(window as any).Tmapv2,map=engine.current;
    if(!map || !focus) return;
    map.setCenter(new sdk.LatLng(focus.lat,focus.lon));
  },[focus?.lat,focus?.lon]);
  useEffect(()=>{
    const sdk=(window as any).Tmapv2,map=engine.current;
    if(!map) return;
    const pins=markers.map(place=>{
      const active=place.id===selectedId;
      const pin=document.createElement('button');
      pin.type='button';
      pin.dataset.placeId=place.id;
      pin.setAttribute('aria-label',place.name);
      pin.setAttribute('aria-pressed',String(active));
      pin.className='map-pin rf-tmap-pin'+(active?' active':'')+(place.state?' rf-state-'+place.state:'');
      const icon=document.createElement('span');
      icon.innerHTML='<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="currentColor"><circle cx="6.5" cy="4" r="1.8"/><path d="M5 7h3l2.5 7H8.7v7H4.3v-7H2.5L5 7Z"/><path d="M12 2v20" stroke="currentColor" stroke-width="1.6"/><circle cx="17.5" cy="4" r="1.8"/><path d="M14.5 7h6v7h-1.2v7h-3.6v-7h-1.2V7Z"/></svg>';
      const label=document.createElement('b');
      label.textContent=place.name;
      pin.append(icon,label);
      const marker=new sdk.Marker({position:new sdk.LatLng(place.lat,place.lon),map,title:place.name,iconHTML:pin.outerHTML,offset:new sdk.Point(17,17),zIndex:active?21:20});
      return marker;
    });
    return ()=>pins.forEach(pin=>pin.setMap(null));
  },[markers,selectedId]);
  useEffect(()=>{
    const sdk=(window as any).Tmapv2,map=engine.current;
    if(!map) return;
    if(!draft){draftPin.current?.setMap(null);draftPin.current=null;return;}
    const position=new sdk.LatLng(draft.lat,draft.lon);
    if(draftPin.current){draftPin.current.setPosition(position);return;}
    const pin=new sdk.Marker({position,map,draggable:true,title:'새 장소'});
    draftPin.current=pin;
    pin.addListener('dragend',()=>{
      const p=pin.getPosition();
      callbacks.current.onDraft?.({lat:p.lat(),lon:p.lng()});
    });
  },[draft]);
  useEffect(()=>{
    const sdk=(window as any).Tmapv2,map=engine.current;
    if(!map || !searchPoint) return;
    const marker=new sdk.Marker({position:new sdk.LatLng(searchPoint.lat,searchPoint.lon),map,title:"검색한 위치"});
    return ()=>marker.setMap(null);
  },[searchPoint]);
  useEffect(()=>{
    const sdk=(window as any).Tmapv2,map=engine.current;
    if(!map || !currentPosition) return;
    const point=new sdk.LatLng(currentPosition.lat,currentPosition.lon);
    const circle=new sdk.Circle({center:point,radius:currentPosition.accuracy,map,strokeColor:'#176ac9',strokeWeight:1,fillColor:'#176ac9',fillOpacity:.12});
    const marker=new sdk.Marker({position:point,map,title:'현재 위치',iconHTML:'<div class="rf-current-pin"></div>'});
    return ()=>{marker.setMap(null);circle.setMap(null);};
  },[currentPosition]);
  useEffect(()=>{
    const sdk=(window as any).Tmapv2,map=engine.current;
    if(!map || !route) return;
    const bounds=new sdk.LatLngBounds();
    const lines=route.lines.map(line=>{
      const path=line.map(([lon,lat])=>new sdk.LatLng(lat,lon));
      path.forEach(point=>bounds.extend(point));
      return new sdk.Polyline({path,strokeColor:'#176ac9',strokeWeight:6,map});
    });
    map.fitBounds(bounds);
    return ()=>lines.forEach(line=>line.setMap(null));
  },[route]);
  function zoom(step:number) {
    const map=engine.current;
    if(map)map.setZoom(Math.max(6,Math.min(19,map.getZoom()+step)));
  }
  return <>
    <div className="rf-live-map" ref={root} onClickCapture={selectPin}/>
    {controls&&<div className="map-tools"><div>
      <button aria-label="확대" type="button" onClick={()=>zoom(1)}>+</button>
      <button aria-label="축소" type="button" onClick={()=>zoom(-1)}><span className="minus">−</span></button>
    </div></div>}
  </>;
}
