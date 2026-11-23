import React, {useEffect, useMemo, useRef, useState} from 'react';
import {ActivityIndicator, StyleSheet, Text, View} from 'react-native';
import {WebView} from 'react-native-webview';

const TMAP_API = 'https://apis.openapi.sk.com/tmap';

export const demoOrigin = {lat: 37.56475, lon: 126.9781, label: '서울시청 시연 위치'};

function apiError(status, body, fallback) {
  const message = body?.error?.message || body?.errorMessage || body?.message;
  if (status === 401 || status === 403) return new Error('TMAP 앱 키 또는 사용 상품 권한을 확인해 주세요.');
  if (status === 429) return new Error('TMAP API의 일일 호출 한도에 도달했습니다.');
  return new Error(message || `${fallback} (${status})`);
}

async function parseJson(response) {
  const text = await response.text();
  if (!text) return null;
  try { return JSON.parse(text); } catch { return null; }
}

export function distanceMeters(a, b) {
  const rad = value => value * Math.PI / 180;
  const earth = 6371000;
  const dLat = rad(b.lat - a.lat);
  const dLon = rad(b.lon - a.lon);
  const lat1 = rad(a.lat);
  const lat2 = rad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return Math.round(earth * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h)));
}

export async function searchTmapPlaces(appKey, keyword, origin, signal) {
  const params = new URLSearchParams({
    version: '1', format: 'json', searchKeyword: keyword,
    reqCoordType: 'WGS84GEO', resCoordType: 'WGS84GEO',
    centerLat: String(origin.lat), centerLon: String(origin.lon),
    radius: '10', count: '20', searchType: 'all',
  });
  const response = await fetch(`${TMAP_API}/pois?${params}`, {
    headers: {appKey, Accept: 'application/json'}, signal,
  });
  const body = await parseJson(response);
  if (response.status === 204) return [];
  if (!response.ok) throw apiError(response.status, body, 'TMAP 장소 검색에 실패했습니다.');
  const rows = body?.searchPoiInfo?.pois?.poi ?? [];
  return rows.map((row, index) => {
    const lat = Number(row.pnsLat || row.frontLat || row.noorLat);
    const lon = Number(row.pnsLon || row.frontLon || row.noorLon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    const address = [row.upperAddrName, row.middleAddrName, row.lowerAddrName, row.detailAddrName]
      .filter(Boolean).join(' ');
    const place = {
      id: `tmap-${row.id || index}`, name: row.name || keyword,
      where: address || row.newAddressList?.newAddress?.[0]?.fullAddressRoad || '주소 정보 없음',
      lat, lon, source: 'tmap', access: /장애인|무장애/.test(`${row.name || ''} ${row.bizCatName || ''}`),
      status: 'unknown', category: row.bizCatName || 'TMAP 장소',
    };
    place.distance = distanceMeters(origin, place);
    return place;
  }).filter(Boolean).sort((a, b) => a.distance - b.distance);
}

export async function getWalkingRoute(appKey, origin, destination, signal) {
  const response = await fetch(`${TMAP_API}/routes/pedestrian?version=1`, {
    method: 'POST',
    headers: {appKey, 'Content-Type': 'application/json', Accept: 'application/json'},
    body: JSON.stringify({
      startX: origin.lon, startY: origin.lat, endX: destination.lon, endY: destination.lat,
      startName: origin.label || '현재 위치', endName: destination.name,
      reqCoordType: 'WGS84GEO', resCoordType: 'WGS84GEO', searchOption: '10',
    }),
    signal,
  });
  const body = await parseJson(response);
  if (!response.ok) throw apiError(response.status, body, 'TMAP 보행 경로를 불러오지 못했습니다.');
  const features = body?.features ?? [];
  const lines = features.filter(item => item.geometry?.type === 'LineString')
    .map(item => item.geometry.coordinates).filter(line => line.length > 1);
  const summary = features.map(item => item.properties)
    .find(item => Number.isFinite(Number(item?.totalTime)) && Number.isFinite(Number(item?.totalDistance)));
  if (!lines.length || !summary) throw new Error('선택한 위치까지의 보행 경로를 찾지 못했습니다.');
  return {lines, seconds: Number(summary.totalTime), meters: Number(summary.totalDistance)};
}

function safeJson(value) {
  return JSON.stringify(value).replace(/</g, '\\u003c').replace(/-->/g, '--\\>');
}

function mapHtml(appKey, initialCenter) {
  const key = encodeURIComponent(appKey);
  const initial = safeJson(initialCenter);
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
  <style>html,body,#map{margin:0;width:100%;height:100%;overflow:hidden;background:#eef3f1}
  .person{width:18px;height:18px;border:3px solid white;border-radius:50%;background:#187bf8;box-shadow:0 1px 5px #0006}
  .pin{min-width:28px;height:28px;padding:0 6px;border:3px solid white;border-radius:16px;display:flex;align-items:center;justify-content:center;color:white;font:700 12px sans-serif;box-shadow:0 1px 5px #0006}
  .free{background:#357245}.normal{background:#895c00}.busy,.closed{background:#b22835}.unknown{background:#5d7086}.selected{outline:3px solid #15263d}</style></head>
  <body><div id="map"></div><script>
  const send=(data)=>window.ReactNativeWebView?.postMessage(JSON.stringify(data));
  window.onerror=(message,source,line)=>send({type:'error',message:String(message),line});
  let map=null,layers=[],places=[];
  document.getElementById('map').addEventListener('click', event=>{
    const order=event.target.closest('button[data-order]')?.dataset.order;
    const place=places[Number(order)-1];
    if(place){event.stopPropagation();send({type:'select',id:place.id});}
  },true);
  const center=${initial};
  const point=(lat,lon)=>new Tmapv2.LatLng(Number(lat),Number(lon));
  function clear(){layers.forEach(layer=>{try{layer.setMap(null)}catch(_){}});layers=[]}
  function markerHtml(item){const state=['busy','normal','free','closed'].includes(item.status)?item.status:'unknown';const selected=item.selected?' selected':'';return '<button type="button" data-order="'+item.order+'" class="pin '+state+selected+'">'+String(item.order)+'</button>'}
  window.drawRestFlow=function(data){
    if(!map)return;clear();places=data.points;const bounds=new Tmapv2.LatLngBounds();
    const here=point(data.origin.lat,data.origin.lon);bounds.extend(here);
    if(Number.isFinite(data.origin.accuracy)){
      layers.push(new Tmapv2.Circle({center:here,radius:data.origin.accuracy,map,strokeColor:'#187bf8',fillColor:'#187bf8',fillOpacity:.12,strokeWeight:1}));
    }
    const me=new Tmapv2.Marker({position:here,iconHTML:'<div class="person"></div>',map});layers.push(me);
    data.points.forEach((item,index)=>{const pos=point(item.lat,item.lon);bounds.extend(pos);
      const marker=new Tmapv2.Marker({position:pos,title:item.name,iconHTML:markerHtml({...item,order:index+1}),map});
      layers.push(marker)});
    if(data.lines.length){data.lines.forEach(line=>{const path=line.map(([lon,lat])=>point(lat,lon));path.forEach(p=>bounds.extend(p));layers.push(new Tmapv2.Polyline({path,strokeColor:'#007f7e',strokeWeight:7,map}))});}
    if(data.points.length||data.lines.length){map.fitBounds(bounds);setTimeout(()=>{if(map.getZoom()>18)map.setZoom(18)},120)}
    else {map.setCenter(here);map.setZoom(16)}
  };
  function boot(){
    try{map=new Tmapv2.Map('map',{center:point(center.lat,center.lon),width:'100%',height:'100%',zoom:16});document.body.dataset.status='ready';send({type:'ready'})}
    catch(error){document.body.dataset.status='error';send({type:'error',message:error?.message||'TMAP 지도 초기화 실패'})}
  }
  let attempts=0;(function waitForSdk(){if(window.Tmapv2?.Map)return boot();if(++attempts>120)return send({type:'error',message:'TMAP SDK 로드 시간 초과'});setTimeout(waitForSdk,100)})();
  </script><script src="https://apis.openapi.sk.com/tmap/jsv2?version=1&amp;appKey=${key}" onerror="send({type:'error',message:'TMAP SDK 요청 실패'})"></script></body></html>`;
}

export function Tmap({appKey, origin, points, route, selectedId, onSelect, onStatus}) {
  const web = useRef(null);
  const source = useMemo(() => ({html: mapHtml(appKey, origin), baseUrl: 'http://localhost/'}), [appKey]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!ready) return;
    const payload = safeJson({
      points: points.map(({id, name, lat, lon, status}) => ({id, name, lat, lon, status, selected: id === selectedId})),
      origin, lines: route?.lines ?? [],
    });
    web.current?.injectJavaScript(`window.drawRestFlow(${payload});true;`);
  }, [ready, origin, points, route, selectedId]);

  useEffect(() => {
    onStatus?.(error ? {state: 'error', message: error} : ready ? {state: 'ready'} : {state: 'loading'});
  }, [ready, error, onStatus]);

  return <View style={StyleSheet.absoluteFill}>
    <WebView
      ref={web}
      source={source}
      originWhitelist={['http://*', 'https://*', 'about:blank']}
      javaScriptEnabled
      domStorageEnabled
      cacheEnabled
      mixedContentMode="always"
      thirdPartyCookiesEnabled
      sharedCookiesEnabled
      allowFileAccess={false}
      setSupportMultipleWindows={false}
      androidLayerType="hardware"
      onError={({nativeEvent}) => setError(nativeEvent.description || '웹뷰 네트워크 오류')}
      onHttpError={({nativeEvent}) => setError(`TMAP HTTP 오류 ${nativeEvent.statusCode}`)}
      onMessage={({nativeEvent}) => {
        let event;
        try { event = JSON.parse(nativeEvent.data); } catch { return; }
        if (event.type === 'ready') { setReady(true); setError(''); }
        if (event.type === 'error') setError(event.message || 'TMAP 지도를 초기화하지 못했습니다.');
        if (event.type === 'select') onSelect?.(event.id);
      }}
    />
    {(!ready || error) && <View pointerEvents="none" style={styles.cover}>
      {!error && <ActivityIndicator color="#007f7e" size="large"/>}
      <Text style={styles.coverTitle}>{error ? 'TMAP 연결 실패' : 'TMAP 지도 연결 중'}</Text>
      <Text style={styles.coverText}>{error || '지도 SDK를 불러오고 있습니다.'}</Text>
    </View>}
  </View>;
}

const styles = StyleSheet.create({
  cover: {position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, justifyContent: 'center', alignItems: 'center', padding: 24, backgroundColor: '#eef5f3'},
  coverTitle: {marginTop: 10, color: '#10243b', fontWeight: '800', fontSize: 16},
  coverText: {marginTop: 5, color: '#526174', textAlign: 'center', fontSize: 12},
});
