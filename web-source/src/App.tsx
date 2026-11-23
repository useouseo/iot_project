import {availabilityLabels, defaultPreferences, readPreferences, restroomLabels, score, summarize, type Preferences, type Sensor} from "./availability";
import LiveMap, {Point} from "./LiveMap";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type IconName =
  | "arrow"
  | "building"
  | "check"
  | "chevron"
  | "close"
  | "layers"
  | "pin"
  | "plus"
  | "search"
  | "trash"
  | "toilet"
  | "settings";

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    arrow: (
      <>
        <path d="m9 18 6-6-6-6" />
        <path d="M15 12H3" />
      </>
    ),
    building: (
      <>
        <path d="M4 21V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v16" />
        <path d="M9 21v-4h4v4M8 7h1m3 0h1M8 11h1m3 0h1M2 21h18" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    close: (
      <>
        <path d="m18 6-12 12M6 6l12 12" />
      </>
    ),
    layers: (
      <>
        <path d="m12 2 9 5-9 5-9-5 9-5Z" />
        <path d="m3 12 9 5 9-5M3 17l9 5 9-5" />
      </>
    ),
    pin: (
      <>
        <path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" />
        <circle cx="12" cy="10" r="2.5" />
      </>
    ),
    plus: (
      <>
        <path d="M12 5v14M5 12h14" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    trash: (
      <>
        <path d="M4 7h16M9 3h6l1 4H8l1-4Z" />
        <path d="m6 7 1 14h10l1-14M10 11v6m4-6v6" />
      </>
    ),
    settings: <><circle cx="12" cy="12" r="3"/><path d="m10 2 4 0 1 3 3 1 3 0 1 4-2 2v2l2 2-2 4-3-1-2 1-1 2h-4l-1-2-2-1-3 1-2-4 2-2v-2L2 10l1-4h3l3-1z"/></>,
    toilet: (
      <>
        <circle cx="6.5" cy="4" r="1.8" fill="currentColor" stroke="none" />
        <path d="M5 7h3l2.5 7H8.7v7H4.3v-7H2.5L5 7Z" fill="currentColor" stroke="none" />
        <path d="M12 2v20" />
        <circle cx="17.5" cy="4" r="1.8" fill="currentColor" stroke="none" />
        <path d="M14.5 7h6v7h-1.2v7h-3.6v-7h-1.2V7Z" fill="currentColor" stroke="none" />
      </>
    ),
  };

  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.8"
      viewBox="0 0 24 24"
      width={size}
    >
      {paths[name]}
    </svg>
  );
}

const types=[["women","여성"],["men","남성"],["shared","공용"],["women-accessible","여성 장애인"],["men-accessible","남성 장애인"],["shared-accessible","공용 장애인"]];
type FanSettings = {mode:"auto"|"manual"; target_humidity:number; high_humidity:number; idle_saving:boolean; manual_percent:number};
type Equipment = Sensor & {
  settings:FanSettings; fan_enabled:boolean;
  zone_id:number|null; device_id:string; name:string; quality:string;
  environment:{temperature_c:number;humidity_pct:number;fresh:boolean}|null;
  occupancy:{state:string;reason:string};
  control:{fan_pwm_percent:number;mode:string;reason:string};
  fan_status:{online:boolean;ok:boolean;applied_percent:number;applied_fresh:boolean;mode:string}|null;
};
function FanControl({item,busy,save,reset}:{item:Equipment;busy:boolean;save:(settings:FanSettings)=>Promise<boolean>;reset:()=>void}){
  const [draft,setDraft]=useState<FanSettings|null>(null);
  const settings=draft ?? item.settings;
  const change=(patch:Partial<FanSettings>)=>setDraft({...settings,...patch});
  const fan=item.fan_status;
  const applied=fan?.applied_fresh ? fan.applied_percent+"%" : "확인 필요";
  const pending=item.settings.mode==="manual" && fan?.online && fan.ok &&
    (!fan.applied_fresh || fan.mode!=="manual" || fan.applied_percent!==item.control.fan_pwm_percent);
  const connected=item.online && item.quality==="good" && fan?.online;
  return <div className="restflow-fan-card">
    <div className="restflow-fan-heading zone-head">
      <span aria-hidden="true"><Icon name="toilet" size={18}/></span>
      <div><h3>센서·환기 제어</h3></div>
      <b className={connected ? "rf-device-good" : "rf-device-check"}>{connected ? "연결 정상" : "연결 확인 필요"}</b>
    </div>
    <div className="restflow-fan-status">
      <span>현재 습도<strong>{item.environment?.fresh ? item.environment.humidity_pct+"%" : "확인 필요"}</strong></span>
      <span>혼잡도<strong>{availabilityLabels[item.state]}</strong></span>
      <span>재실<strong>{item.occupancy.state==="occupied" ? "감지됨" : item.occupancy.state==="unoccupied" ? "무인" : "불확실"}</strong></span>
      <span>팬 적용<strong>{applied}</strong></span>
    </div>
    <form onSubmit={async event=>{
      event.preventDefault();
      if(await save(settings))setDraft(null);
    }}>
      <fieldset className="restflow-fan-modes" aria-label="환기 제어 모드" disabled={busy}>
        <button type="button" aria-pressed={settings.mode==="auto"} onClick={()=>change({mode:"auto"})}>자동</button>
        <button type="button" aria-pressed={settings.mode==="manual"} onClick={()=>change({mode:"manual"})}>수동</button>
      </fieldset>
      <div className="restflow-fan-panels">
      <div className="restflow-fan-panel" inert={settings.mode!=="auto"}>
        <p className="restflow-fan-feedback" role="status">{draft && item.settings.mode!=="auto" ? "저장하면 자동 모드가 적용됩니다." : item.control.reason}</p>
        <label className="restflow-fan-setting">목표 습도
          <span><input type="number" required disabled={settings.mode!=="auto"} min="1" max="99" step="0.01"
            value={Number.isNaN(settings.target_humidity) ? "" : settings.target_humidity}
            onChange={event=>change({target_humidity:event.target.valueAsNumber})}/> %</span>
        </label>
        <p className="restflow-fan-help">목표 습도부터 환기를 강화합니다. {Number.isFinite(settings.target_humidity) && Math.min(100, Math.round((settings.target_humidity+10)*100)/100)+"%부터 최대 출력입니다."}</p>
        <label className="restflow-fan-setting">무인 자동 절전(팬)
          <span className="restflow-fan-switch"><input type="checkbox" role="switch" checked={settings.idle_saving} onChange={event=>change({idle_saving:event.target.checked})}/> {settings.idle_saving ? "켜짐" : "꺼짐"}</span>
        </label>
        <p className="restflow-fan-help">습도가 높으면 환기가 우선입니다. 무인 확인 후 5분에 저출력, 15분에 정지합니다.</p>
      </div>
      <div className="restflow-fan-panel" inert={settings.mode!=="manual"}>
      <label className="restflow-fan-slider">
        <span className="restflow-fan-slider-heading">팬 출력 설정 <strong aria-hidden="true">{settings.manual_percent}%</strong></span>
        <input type="range" style={{"--fan-percent":settings.manual_percent+"%"} as React.CSSProperties} min="0" max="100" step="1" value={settings.manual_percent}
          onChange={event=>change({manual_percent:event.target.valueAsNumber})}/>
        <span><small>0%</small><small>100%</small></span>
      </label>
      <p className="restflow-fan-feedback" role="status">
        {draft ? `설정값 ${settings.manual_percent}% · 저장 전` :
          `요청 ${item.control.fan_pwm_percent}% · ${pending ? "적용 대기" : !fan?.online || !fan.ok ? "장비 확인 필요" : "적용 완료"}`}
      </p>
      </div>
      </div>
      <button className="restflow-equipment-primary" disabled={busy || draft===null}>환기 설정 저장</button>
    </form>
    <button className="restflow-equipment-button" disabled={busy} onClick={reset}>무인 확인 후 초기화</button>
  </div>;
}
type ModuleItem={id:number;kind?:string;name:string;type:string;device:string;open:number;total:number;status:"online"|"attention";closed:boolean;reason:string;accessible:boolean;sensor?:Equipment|null};
type Place=Point & {id:string;name:string;address:string;detail:string;modules:number;zones:ModuleItem[];sensor?:Equipment|null};
type RawZone=Omit<ModuleItem,"type"|"status"|"closed"|"accessible"> & {kind?:string;closed:number;accessible:number};
type RawPlace=Omit<Place,"detail"|"modules"|"zones"> & {zones:RawZone[]};
function adapt(place:RawPlace):Place {
  return {...place,detail:"",modules:place.zones.length,zones:place.zones.map(z=>({...z,
    type:types.find(([value])=>value===z.kind)?.[1] || "등록 구역", status:z.closed?"attention":"online",
    closed:Boolean(z.closed),accessible:Boolean(z.accessible)}))};
}
async function api(url:string,method="GET",data?:unknown,password?:string){
  const response=await fetch(url,{method,headers:{"Content-Type":"application/json",...(password?{Authorization:"Bearer "+encodeURIComponent(password)}:{})},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json().catch(()=>({}));
  if(!response.ok) throw Error(result.error || "서버 요청을 완료하지 못했습니다.");
  return result;
}
type UserPlace=Place & {distance:number;siteAccessible:boolean} & ReturnType<typeof summarize>;
const city={lat:37.5655,lon:126.977};
function distance(a:Point,b:Point){
  const r=Math.PI/180,dLat=(b.lat-a.lat)*r,dLon=(b.lon-a.lon)*r;
  const h=Math.sin(dLat/2)**2+Math.cos(a.lat*r)*Math.cos(b.lat*r)*Math.sin(dLon/2)**2;
  return Math.round(6371000*2*Math.asin(Math.min(1,Math.sqrt(h))));
}

type LocationFix = Point & {accuracy: number; timestamp: number};
const demoMode=Boolean(document.querySelector('meta[name="restflow-demo"]'));
const preferenceKey=demoMode ? "restflow-demo-preferences" : "restflow-user-preferences";
const demoFix={...city,accuracy:0,timestamp:0};

function UserApp() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "open" | "accessible">("all");
  const [preferences,setPreferences]=useState(()=>readPreferences(preferenceKey));
  const [draftPreferences,setDraftPreferences]=useState<Preferences>(preferences ?? defaultPreferences);
  const [editingPreferences,setEditingPreferences]=useState(false);
  const [sort, setSort] = useState<"distance" | "recommended">(preferences ? "recommended" : "distance");
  const activePreferences=preferences ?? defaultPreferences;
  function savePreferences(next:Preferences){
    try{localStorage.setItem(preferenceKey,JSON.stringify(next));}
    catch{setUserError("기기의 저장소가 꺼져 있어 추천 설정을 이번 실행에만 적용합니다.");}
    setPreferences(next);
    setEditingPreferences(false);
    setSort("recommended");
  }
  const [selectedId,setSelectedId]=useState("");
  const [origin,setOrigin]=useState(city);
  const [position,setPosition]=useState<LocationFix | undefined>(demoMode ? demoFix : undefined);
  const latestFix=useRef<LocationFix | undefined>(undefined);
  const locationWatch=useRef<number | undefined>(undefined);
  const [locating,setLocating]=useState(false);
  const [focus,setFocus]=useState<Point>();
  const [route,setRoute]=useState<{lines:[number,number][][];seconds:number;meters:number}>();
  const [routing,setRouting]=useState(false);
  const [routeError,setRouteError]=useState("");
  const routeRequest=useRef<AbortController | null>(null);
  const [locationMessage,setLocationMessage]=useState(demoMode ? "시청 앞 시연 위치" : "서울시청 기준");
  const [userPlaces,setUserPlaces]=useState<Place[]>([]);
  const [userError,setUserError]=useState("");
  useEffect(()=>{
    let active=true,timer:number;
    async function refresh(){
      try{const {places}=await api("/api/places");if(active){setUserPlaces(places.map(adapt));setUserError("");}}
      catch(e){if(active){
        setUserError((e as Error).message);
        setUserPlaces(current=>current.map(place=>({...place,sensor:null,
          zones:place.zones.map(zone=>({...zone,sensor:null}))})));
      }}
      finally{if(active)timer=window.setTimeout(refresh,5000);}
    }
    refresh();return ()=>{active=false;window.clearTimeout(timer);};
  },[]);
  function rememberLocation({coords,timestamp}: GeolocationPosition):LocationFix {
    const point={lat:coords.latitude,lon:coords.longitude,accuracy:coords.accuracy,timestamp};
    latestFix.current=point;
    setOrigin(point);
    setPosition(point);
    setLocationMessage(`현재 위치 · 오차 약 ${Math.round(point.accuracy)}m`);
    return point;
  }
  function locationFailure(error: GeolocationPositionError){
    if(error.code===1){
      latestFix.current=undefined;
      setPosition(undefined);
      setOrigin(city);
      setLocationMessage("서울시청 기준");
      if(locationWatch.current!==undefined) navigator.geolocation.clearWatch(locationWatch.current);
      locationWatch.current=undefined;
      setRoute(undefined);
    }
    return Error(error.code===1?"브라우저에서 위치 권한을 허용해 주세요.":"현재 위치를 확인하지 못했습니다. 다시 시도해 주세요.");
  }
  function locate(): Promise<LocationFix> {
    if(demoMode) return Promise.resolve(demoFix);
    const nativeLocation=(window as Window & {restflowNativeLocation?:()=>Promise<GeolocationPosition>}).restflowNativeLocation;
    if(nativeLocation) return nativeLocation().then(rememberLocation);
    return new Promise((resolve,reject)=>{
      if(!navigator.geolocation || !window.isSecureContext){
        reject(Error("현재 위치를 확인하려면 HTTPS 또는 서버 PC의 localhost에서 열어 주세요."));
        return;
      }
      navigator.geolocation.getCurrentPosition(result=>{
        resolve(rememberLocation(result));
        if(locationWatch.current===undefined){
          locationWatch.current=navigator.geolocation.watchPosition(rememberLocation,error=>{
            if(error.code===1){
              const failure=locationFailure(error);
              routeRequest.current?.abort();
              setRouting(false);
              setRouteError(failure.message);
            }
          },{maximumAge:10000,enableHighAccuracy:true});
        }
      },error=>reject(locationFailure(error)),{timeout:12000,maximumAge:0,enableHighAccuracy:true});
    });
  }
  useEffect(()=>()=>{
    if(locationWatch.current!==undefined) navigator.geolocation.clearWatch(locationWatch.current);
  },[]);
  async function showLocation(){
    setRouteError("");
    setLocating(true);
    try{setFocus(await locate());}
    catch(error){setRouteError((error as Error).message);}
    finally{setLocating(false);}
  }
  const visiblePlaces=useMemo(()=>{
    const term=query.trim().toLowerCase();
    return userPlaces.map((p):UserPlace=>{
      const zones=p.zones.map(zone=>({...zone,kind:zone.kind ?? types.find(([,label])=>zone.name.includes(label))?.[0]}));
      return {...p,...summarize(zones,activePreferences.restroom,p.sensor),siteAccessible:zones.some(zone=>zone.accessible && !zone.closed && zone.open>0),distance:distance(origin,p)};
    }).filter(p=>(!term||[p.name,p.address,p.detail].some(value=>value.toLowerCase().includes(term)))
      && (filter==="all" || (filter==="open"?p.open>0:p.siteAccessible)))
      .sort((a,b)=>(sort==="recommended"?score(a,activePreferences.accessibleFirst)-score(b,activePreferences.accessibleFirst):0)||a.distance-b.distance);
  },[userPlaces,query,filter,sort,origin,activePreferences]);
  const selected=visiblePlaces.find(p=>p.id===selectedId) || visiblePlaces[0];
  const [mapError,setMapError]=useState("");

  const markers=visiblePlaces;
  useEffect(()=>{
    setRoute(undefined);
    setRouteError("");
    setRouting(false);
    return ()=>routeRequest.current?.abort();
  },[selected?.id]);
  function selectPlace(id:string){
    setSelectedId(id);
    setFocus(undefined);
  }
  const selectedCard=useRef<HTMLButtonElement>(null);
  function selectMapPlace(id:string){
    selectPlace(id);
    requestAnimationFrame(()=>{
      selectedCard.current?.scrollIntoView({block:"nearest",behavior:"smooth"});
    });
  }
  async function findRoute(){
    if(!selected) return;
    if(route){setRoute(undefined);setFocus(undefined);return;}
    setSelectedId(selected.id);
    routeRequest.current?.abort();
    const controller=new AbortController();
    routeRequest.current=controller;
    setRouteError("");
    setRoute(undefined);
    setRouting(true);
    let timer:number|undefined;
    try{
      const saved=latestFix.current;
      const from=saved && Date.now()-saved.timestamp<60000 ? saved : await locate();
      if(from.accuracy>100 && !window.confirm(`현재 위치 오차가 약 ${Math.round(from.accuracy)}m입니다. 이 위치에서 길찾기를 계속할까요?`)) return;
      timer=window.setTimeout(()=>controller.abort("timeout"),15000);
      if(controller.signal.aborted) return;
      const result=await fetch("/api/walking-route",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({origin:{lat:from.lat,lon:from.lon},place_id:selected.id}),signal:controller.signal,
      });
      const data=await result.json();
      if(!result.ok) throw Error(data.error || "도보 경로를 불러오지 못했습니다.");
      setRoute(data);
    }catch(error){
      if(controller.signal.reason==="timeout") setRouteError("길찾기 시간이 초과됐습니다. 다시 시도해 주세요.");
      else if(!controller.signal.aborted) setRouteError((error as Error).message);
    }finally{
      window.clearTimeout(timer);
      if(routeRequest.current===controller) setRouting(false);
    }
  }

  return (
    <div className="user-app">
      <header className="user-header">
        <a className="brand" href="#" aria-label="RestFlow 홈">
          <span className="brand-mark">
            <Icon name="toilet" size={22} />
          </span>
          <span>
            Rest<span>Flow</span>
          </span>
        </a>
        <div className="rf-user-header-actions"><button
          className="current-location"
          onClick={showLocation} disabled={locating || routing}
        >
          <Icon name="pin" size={16} />
          <span>
            <small>내 위치</small>
            <strong>{locationMessage}</strong>
          </span>
        </button>
        <button className="preference-button" type="button" aria-label="맞춤 추천 설정" onClick={()=>{setDraftPreferences(activePreferences);setEditingPreferences(true);}}><Icon name="settings" size={20}/></button>
        </div>
      </header>

      <main className="user-main">
        {demoMode && <p className="panel-tip rf-demo-notice"><strong>시연 모드</strong> · 화장실 상태와 출발 위치는 가상 데이터입니다.</p>}
        <section className="user-intro">
          <div>
            <p>가까운 화장실을 빠르게 찾아보세요</p>
            <h1>내 주변 화장실</h1>
          </div>
          <label className="user-search">
            <Icon name="search" size={19} />
            <input
              aria-label="주변 화장실 검색"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="장소명이나 위치를 검색하세요"
              value={query}
            />
            {query && (
              <button aria-label="검색어 지우기" onClick={() => setQuery("")}>
                <Icon name="close" size={15} />
              </button>
            )}
          </label>
        </section>

        <div className="user-filters" aria-label="화장실 필터">
          <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>
            전체
          </button>
          <button className={filter === "open" ? "active" : ""} onClick={() => setFilter("open")}>
            운영 중
          </button>
          <button
            className={filter === "accessible" ? "active" : ""}
            onClick={() => setFilter("accessible")}
          >
            장애인 이용 가능
          </button>
        </div>

        <section className="user-content">
          <div className="user-map">
            <LiveMap selectedId={selected?.id} markers={markers} draft={null} center={focus || selected || city} onSelect={selectMapPlace} currentPosition={position} route={route} onError={setMapError}/>
            <button aria-label="내 위치로 이동" className="locate-button" onClick={showLocation} disabled={locating || routing}><Icon name="pin" size={18}/></button>
            <div className="user-map-legend">{mapError || (["free","normal","busy","unknown"] as const).map(state=><span className={`rf-state-${state}`} key={state}>{availabilityLabels[state]}</span>)}</div>
          </div>

          <aside className="nearby-panel">
            <div className="nearby-heading">
              <div className="nearby-title">
                <h2>가까운 화장실</h2>
                <p>
                  {sort === "distance"
                    ? "현재 위치에서 가까운 순서예요."
                    : `${activePreferences.restroom === "any" ? "전체 화장실" : restroomLabels[activePreferences.restroom]+" 화장실"}의 거리와 혼잡도를 함께 계산했어요.`}
                </p>
              </div>
              <div className="sort-control" aria-label="목록 정렬">
                <button
                  className={sort === "distance" ? "active" : ""}
                  onClick={() => setSort("distance")}
                >
                  거리순
                </button>
                <button
                  className={sort === "recommended" ? "active" : ""}
                  onClick={() => setSort("recommended")}
                >
                  추천순
                </button>
              </div>
            </div>
            <div className="result-count">{userError || `검색 결과 ${visiblePlaces.length}곳 · 혼잡도는 최근 10분 입장 기준`}</div>
            <div className="user-place-list">
              {visiblePlaces.map((place) => (
                <button
                  className={`user-place-card ${selected?.id === place.id ? "selected" : ""}`}
                  key={place.id}
                  ref={selected?.id === place.id ? selectedCard : undefined}
                  onClick={() => selectPlace(place.id)}
                >
                  <span className={`user-place-icon rf-state-${place.state}`}>
                    <Icon name="toilet" size={18} />
                  </span>
                  <span className="user-place-copy">
                    <span>
                      <strong>{place.name}</strong>
                      <i className={`rf-crowd-badge rf-state-${place.state}`}>{availabilityLabels[place.state]}{place.crowdBasis!==place.basis && " · 시설 전체"}</i>
                    </span>
                    <small>{place.address}</small>
                    <span className="place-meta">
                      <b>{place.distance}m</b>
                      <span title="직선거리와 분당 75m 기준">도보 약 {Math.max(1,Math.ceil(place.distance / 75))}분</span>
                      {place.siteAccessible && <span>장애인 이용 가능</span>}
                    </span>
                  </span>
                  <span className={`availability rf-state-${place.state}`}>
                    {place.total ? <><strong>{place.open}</strong><small>/ {place.total}칸</small><em>{place.basis} 기준</em></> : <em>해당 구역 없음</em>}
                  </span>
                  {selected?.id===place.id && place.zones.length>0 && <span className="zone-breakdown">
                    <span className="zone-breakdown-title">구역별 운영·혼잡도</span>
                    {place.zones.map(zone=>{
                      const state=zone.closed || !zone.open ? "closed" : zone.sensor?.state ?? "unknown";
                      return <span className="user-zone-row" key={zone.id}><strong>{zone.name}</strong><span>{zone.closed?0:zone.open}/{zone.total}칸</span><i className={`rf-crowd-badge rf-state-${state}`}>{availabilityLabels[state]}</i>{zone.closed && zone.reason && <small>{zone.reason}</small>}</span>;
                    })}
                  </span>}
                </button>
              ))}
              {visiblePlaces.length === 0 && (
                <div className="user-empty">
                  <Icon name="search" size={23} />
                  <strong>검색 결과가 없습니다</strong>
                  <p>검색어나 필터를 변경해 보세요.</p>
                </div>
              )}
            </div>
            {selected && <div className="rf-route-actions">
              <button className="primary" onClick={findRoute} disabled={routing || locating || (!route && selected.state==="closed")}>{route ? "경로 지우기" : routing ? "경로 찾는 중…" : "현재 위치에서 도보 길찾기"}</button>
              {route && <p role="status">{demoMode ? "시연 출발점 기준 · " : ""}도보 약 {Math.max(1,Math.ceil(route.seconds/60))}분 · {Math.round(route.meters)}m</p>}
            </div>}
            {routeError && <p role="alert" className="rf-route-message">{routeError}</p>}
          </aside>
        </section>
      </main>
      {(!preferences || editingPreferences) && <div className="preference-backdrop">
        <section aria-labelledby="preference-title" aria-modal="true" role="dialog" className="preference-modal"
          onKeyDown={event=>{if(event.key==="Escape" && preferences) setEditingPreferences(false);}}>
          <div className="preference-heading"><span><Icon name="settings" size={22}/></span>
            <div><small>{preferences ? "추천 설정 변경" : "처음 오셨나요?"}</small><h2 id="preference-title">나에게 맞는 화장실 추천</h2></div>
            {preferences && <button type="button" aria-label="닫기" onClick={()=>setEditingPreferences(false)}><Icon name="close" size={19}/></button>}
          </div>
          <p className="preference-description">이용할 화장실 유형과 추천 설정을 이 기기에 저장합니다.</p>
          <fieldset className="preference-options"><legend>주로 이용할 화장실</legend><div>
            {(["women","men","shared","any"] as const).map(value=><button type="button" key={value}
              aria-pressed={draftPreferences.restroom===value} className={draftPreferences.restroom===value?"selected":""}
              onClick={()=>setDraftPreferences(current=>({...current,restroom:value}))}>{restroomLabels[value]}</button>)}
          </div></fieldset>
          <label className="accessibility-preference"><strong>장애인 화장실 우선 추천</strong>
            <input type="checkbox" checked={draftPreferences.accessibleFirst}
              onChange={event=>setDraftPreferences(current=>({...current,accessibleFirst:event.target.checked}))}/></label>
          <div className="preference-actions">
            {!preferences && <button className="secondary skip-preference" onClick={()=>savePreferences(defaultPreferences)}>기본 설정으로 시작</button>}
            <button className="primary" onClick={()=>savePreferences(draftPreferences)}>추천 설정 저장</button>
          </div>
        </section>
      </div>}
    </div>
  );
}

export default function App() {
  const path=location.pathname;
  const siteId=path.split("/")[2] || "";
  const [places,setPlaces]=useState<Place[]>([]);
  const [modules,setModules]=useState<ModuleItem[]>([]);
  const [page]=useState<"map"|"manage"|"admin"|"user">(path.startsWith("/facility/")?"admin":path.startsWith("/places/")?"manage":path==="/user"?"user":"map");
  const [query,setQuery]=useState("");
  const [selectedId,setSelectedId]=useState(siteId || new URLSearchParams(location.search).get("selected") || "");
  const [adding,setAdding]=useState(false);
  const [draft,setDraft]=useState<Point|null>(null);
  const [address,setAddress]=useState("");
  const [addressStatus,setAddressStatus]=useState("");
  const addressEdited=useRef(false);
  useEffect(()=>{
    if(!adding || !draft)return;
    let active=true;
    addressEdited.current=false;
    setAddress("");
    setAddressStatus("지도 위치에서 주소를 조회하는 중…");
    api("/api/setup/address","POST",draft).then(result=>{
      if(!active)return;
      if(!addressEdited.current)setAddress(result.address);
      setAddressStatus("주소를 확인하고 필요하면 수정하세요.");
    }).catch(()=>{
      if(active)setAddressStatus("주소를 자동으로 찾지 못했습니다. 직접 입력해 주세요.");
    });
    return ()=>{active=false;};
  },[adding,draft]);
  const [deleting,setDeleting]=useState(false);
  const [addingModule,setAddingModule]=useState(false);
  const [adminDirty,setAdminDirty]=useState(false);
  const [equipment,setEquipment]=useState<Equipment[]>([]);
  const [equipmentMessage,setEquipmentMessage]=useState("");
  const [keys,setKeys]=useState<{zone_id:number|null;device_id:string;sensor_token?:string;fan_token?:string}|null>(null);
  const [placing,setPlacing]=useState(false);
  const [toast,setToast]=useState("");
  const [auth,setAuth]=useState("");
  const [claimed,setClaimed]=useState<boolean|null>(null);
  const [claim,setClaim]=useState("");
  const [managerBase,setManagerBase]=useState("");
  const [busy,setBusy]=useState(false);
  const [lookup,setLookup]=useState<(Point & {name:string})[]>([]);
  const [mapCenter,setMapCenter]=useState<Point>();
  const [searchedPoint,setSearchedPoint]=useState<Point|null>(null);
  function searchMap(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    const keyword=String(new FormData(event.currentTarget).get("keyword") || "").trim();
    if(!keyword)return;
    setLookup([]);
    perform(async()=>{
      const {results}=await api("/api/setup/search?q="+encodeURIComponent(keyword));
      setLookup(results);
      if(!results.length)notify("장소 검색 결과가 없습니다.");
    });
  }
  const toastTimer=useRef<number>(0);
  const filteredPlaces=useMemo(()=>{
    const term=query.trim().toLowerCase();
    return places.filter(p=>!term||[p.name,p.address].some(value=>value.toLowerCase().includes(term)));
  },[places,query]);
  const selected=places.find(p=>p.id===selectedId);
  const selectedModules=modules;
  function notify(message:string){
    window.clearTimeout(toastTimer.current);setToast(message);
    toastTimer.current=window.setTimeout(()=>setToast(""),4500);
  }
  async function loadPlaces(){
    const result=await api("/api/setup");
    const next:Place[]=result.places.map(adapt);
    setManagerBase(result.manager_base);
    setPlaces(next);setModules(next.find(p=>p.id===siteId)?.zones || []);
    if(!siteId && next[0]) setSelectedId(old=>old || next[0].id);
  }
  const facility="/api/facility/"+siteId;
  async function loadFacility(password:string){
    const place=adapt(await api(facility,"GET",undefined,password));
    setPlaces([place]);setModules(place.zones);setAuth(password);setAdminDirty(false);
  }
  useEffect(()=>{
    if(page==="admin"){api(facility+"/status").then(result=>setClaimed(result.claimed)).catch(e=>notify(e.message));}
    else if(page!=="user") loadPlaces().catch(e=>notify(e.message));
  },[]);
  useEffect(()=>{
    if(page!=="admin" || !auth)return;
    let active=true,timer:number;
    async function refresh(){
      try {
        const result=await api(facility+"/equipment","GET",undefined,auth);
        if(active){setEquipment(result.equipment);setEquipmentMessage("");}
      } catch(error) {
        if(active){setEquipment([]);setEquipmentMessage((error as Error).message);}
      } finally {
        if(active)timer=window.setTimeout(refresh,5000);
      }
    }
    refresh();
    return ()=>{active=false;window.clearTimeout(timer);};
  },[page,facility,auth]);

  useEffect(()=>{
    if(page!=="manage")return;
    const timer=window.setInterval(()=>{loadPlaces().catch(()=>{});},5000);
    return ()=>window.clearInterval(timer);
  },[page,siteId]);

  function manageModuleKeys(zone_id:number|null, device_id:string, action:"register"|"reissue"|"add-fan"){
    if(action==="reissue" && !confirm("키를 재발급하면 연결된 장비에 새 키를 설정해야 합니다. 계속할까요?"))return;
    perform(async()=>{
      const issued=await api("/api/setup/places/"+siteId+"/equipment","POST",{
        zone_id,device_id,reissue:action==="reissue",enable_fan:action==="add-fan",fan_enabled:false,
      });
      setKeys({...issued,zone_id});
      await loadPlaces();
    });
  }

  function moduleConnection(zoneId:number|null, deviceId:string, item?:Equipment|null){
    return <div className="module-connection">
      {(!item || (item.online && item.quality==="good") || !item.fan_enabled || item.fan_status?.online) &&
        <div className="module-connection-status">
          {!item ? <span>센서 키 미발급</span> : item.online && item.quality==="good" && <span>센서 정상</span>}
          {!item?.fan_enabled ? <span>환기 미사용</span> : item.fan_status?.online && <span>환기 연결됨</span>}
        </div>}
      <div className="module-connection-actions">
        <button className="restflow-equipment-button" disabled={busy} onClick={()=>manageModuleKeys(zoneId,deviceId,item?"reissue":"register")}>{item?"키 재발급":"센서 키 발급"}</button>
        {item && !item.fan_enabled && <button className="restflow-equipment-button" disabled={busy} onClick={()=>manageModuleKeys(zoneId,deviceId,"add-fan")}>환기 추가</button>}
      </div>
      {keys?.zone_id===zoneId && <div className="restflow-keys">
        {([["ATOM Lite 키",keys.sensor_token],["Raspberry Pi 키",keys.fan_token]] as const).map(([label,key])=>key &&
          <p key={label}>{label} <code>{key}</code> <button className="restflow-equipment-button" aria-label={label+" 복사"}
            onClick={()=>navigator.clipboard.writeText(key).then(()=>notify("키를 복사했습니다.")).catch(()=>notify("키를 선택해 복사해 주세요."))}>복사</button></p>)}
        <button className="restflow-equipment-button" onClick={()=>setKeys(null)}>키 닫기</button>
      </div>}
    </div>;
  }

  function ventilationPanel(zoneId:number|null){
    const item=equipment.find(e=>e.zone_id===zoneId);
    if(!item)return <p className="restflow-vent-unavailable">{equipmentMessage || "연결된 모듈 없음"}</p>;
    if(!item.fan_enabled)return <p className="restflow-vent-unavailable">환기 미사용</p>;
    return <details className="restflow-vent" key={item.device_id}>
      <summary><Icon name="settings" size={14}/><span className="vent-open">환기 설정 열기</span>
        <span className="vent-close">환기 설정 접기</span><Icon name="chevron" size={14}/></summary>
      <FanControl item={item} busy={busy} save={settings=>saveFanSettings(zoneId,settings)} reset={()=>resetOccupancy(zoneId)}/>
    </details>;
  }

  async function saveFanSettings(zone_id:number|null, settings:FanSettings){
    let saved=false;
    await perform(async()=>{
      const updated=await api(facility+"/equipment/settings","PUT",{zone_id,...settings},auth);
      setEquipment(current=>current.map(item=>item.zone_id===zone_id ? {...item,...updated} : item));
      saved=true;
      notify("환기 설정을 저장했습니다.");
    });
    return saved;
  }

  function resetOccupancy(zone_id:number|null){
    if(!confirm("현장에서 해당 범위에 사람이 없는지 확인하셨나요?"))return;
    perform(async()=>{
      await api(facility+"/equipment/reset","POST",{zone_id,confirmed_empty:true},auth);
      const result=await api(facility+"/equipment","GET",undefined,auth);
      setEquipment(result.equipment);
      notify("재실 추정을 초기화했습니다.");
    });
  }

  async function perform(action:()=>Promise<void>){
    if(busy)return;
    setBusy(true);
    try{await action();}catch(e){notify((e as Error).message);}finally{setBusy(false);}
  }
  function savePlace(event:FormEvent<HTMLFormElement>){
    event.preventDefault();const form=new FormData(event.currentTarget);
    if(!draft){notify("지도에서 위치를 먼저 지정하세요.");return;}
    perform(async()=>{
      const {id}=await api("/api/setup/places","POST",{...draft,name:form.get("name"),address:[form.get("address"),form.get("detail")].filter(Boolean).join(" · ")});
      location.assign("/?selected="+encodeURIComponent(id));
    });
  }
  function beginPlacing(){setDraft(searchedPoint);setLookup([]);setPlacing(true);setAdding(false);}
  function deleteSelectedPlace(){
    if(!selected)return;
    perform(async()=>{await api("/api/setup/places/"+selected.id,"DELETE");location.assign("/");});
  }
  function saveModule(event:FormEvent<HTMLFormElement>){
    event.preventDefault();const form=new FormData(event.currentTarget);
    perform(async()=>{
      const issued=await api("/api/setup/register","POST",{
        place_id:siteId,kind:types.find(([,label])=>label===form.get("type"))?.[0],
        zone_name:form.get("name"),device:form.get("device"),total:Number(form.get("total")),
        fan_enabled:form.has("fan_enabled"),
      });
      setKeys(issued);
      setAddingModule(false);
      await loadPlaces();
      notify("새 모듈을 등록했습니다.");
    });
  }
  function deleteModule(module:ModuleItem){
    if(!confirm(module.name+" 모듈을 삭제할까요?"))return;
    perform(async()=>{await api("/api/setup/places/"+siteId+"/zones/"+module.id,"DELETE");await loadPlaces();notify("모듈을 삭제했습니다.");});
  }
  function updateModule(id:number,patch:Partial<ModuleItem>){
    setModules(current=>current.map(z=>z.id===id?{...z,...patch}:z));setAdminDirty(true);
  }
  function saveOperating(){
    perform(async()=>{await api(facility+"/zones","PUT",{zones:modules.map(({id,open,closed,reason})=>({id,open,closed,reason}))},auth);
      await loadFacility(auth);notify("운영 상태를 저장했습니다.");});
  }
  function login(event:FormEvent<HTMLFormElement>){
    event.preventDefault();const data=new FormData(event.currentTarget),password=String(data.get("password"));
    perform(async()=>{
      if(claimed===false){
        if(password!==data.get("confirm"))throw Error("비밀번호가 일치하지 않습니다.");
        await api(facility+"/claim","POST",{claim:data.get("claim"),password});
        setClaimed(true);
      }
      await loadFacility(password);
    });
  }

  if (page === "user") return <UserApp />;

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="RestFlow 홈">
          <span className="brand-mark">
            <Icon name="toilet" size={22} />
          </span>
          <span>
            Rest<span>Flow</span>
          </span>
        </a>
        <div className="topbar-actions">
          <a className="back-button" href="/user">이용자 화면</a>
          <div className="connection">
            <span />
            설치·운영 관리
          </div>
        </div>
      </header>

      <main>
        {page === "map" ? (
          <>
            <section className="page-heading">
              <div>
                <h1>설치 장소 관리</h1>
              </div>
              <button className="primary add-button" onClick={beginPlacing}>
                <Icon name="plus" size={19} />새 장소 추가
              </button>
            </section>

            <section className="workspace">
              <aside className="place-panel">
                <div className="panel-head">
                  <div>
                    <h2>등록된 장소</h2>
                    <span>총 {places.length}곳</span>
                  </div>
                  <label className="search-box">
                    <Icon name="search" size={18} />
                    <input
                      aria-label="장소 검색"
                      onChange={(event) => setQuery(event.target.value)}
                      placeholder="장소명 또는 주소 검색"
                      value={query}
                    />
                    {query && (
                      <button aria-label="검색어 지우기" onClick={() => setQuery("")}>
                        <Icon name="close" size={15} />
                      </button>
                    )}
                  </label>
                </div>

                <div className="place-list">
                  {filteredPlaces.map((place) => (
                    <button
                      className={`place-card ${selectedId === place.id ? "selected" : ""}`}
                      key={place.id}
                      onClick={() => {setSelectedId(place.id);setMapCenter(place);}}
                    >
                      <span className="place-letter">
                        <Icon name="toilet" size={16} />
                      </span>
                      <span className="place-copy">
                        <strong>{place.name}</strong>
                        <span>{place.address}</span>
                        <small>
                          <Icon name="layers" size={14} />
                          모듈 {place.modules}개 연결
                        </small>
                      </span>
                      <Icon name="chevron" size={18} />
                    </button>
                  ))}
                  {filteredPlaces.length === 0 && (
                    <div className="empty-state">
                      <span>
                        <Icon name="search" size={22} />
                      </span>
                      <strong>검색 결과가 없어요</strong>
                      <p>다른 장소명이나 주소로 검색해 보세요.</p>
                    </div>
                  )}
                </div>
                <div className="panel-tip">
                  <span>
                    <Icon name="pin" size={17} />
                  </span>
                  <p>
                    <strong>장소를 추가하려면</strong> 지도에서 정확한 입구 위치를 선택해 주세요.
                  </p>
                </div>
              </aside>

              <div className="map-area">
                <div className={`map-canvas ${placing ? "placing" : ""}`}>
                  <div className="rf-map-search" onKeyDown={event=>{if(event.key==="Escape")setLookup([]);}}>
                    <form className="search-box" onSubmit={searchMap}>
                      <Icon name="search" size={18}/>
                      <input name="keyword" aria-label="TMAP 장소 검색" placeholder="지도에서 장소 또는 주소 검색" onChange={()=>setLookup([])} required/>
                      <button className="rf-map-search-submit" aria-label="검색" disabled={busy}>검색</button>
                    </form>
                    {lookup.length>0&&<ul aria-label="TMAP 장소 검색 결과">
                      {lookup.map((point,i)=><li key={i}><button type="button" onClick={()=>{
                        setSearchedPoint(point);setMapCenter(point);setLookup([]);
                        if(placing)setDraft(point);
                      }}>{point.name}</button></li>)}
                    </ul>}
                  </div>
                  <LiveMap controls searchPoint={placing?null:searchedPoint} selectedId={selectedId} markers={filteredPlaces} draft={draft} center={mapCenter} onDraft={placing?setDraft:undefined}
                    onSelect={id=>{if(!placing)location.assign("/places/"+id);}} onError={notify}/>
                  <div className="map-legend"><span/> RestFlow 설치 장소</div>
                </div>

                {placing ? (
                  <div className="placement-card">
                    <div className="placement-icon">
                      <Icon name="pin" size={21} />
                    </div>
                    <div>
                      <small>새 장소 위치 지정</small>
                      <strong>마커를 원하는 입구 위치로 옮겨주세요</strong>
                      <span>{draft ? "위치가 선택되었습니다." : "지도에서 위치를 선택하세요."}</span>
                    </div>
                    <div className="placement-actions">
                      <button
                        className="secondary"
                        onClick={() => {
                          setPlacing(false);
                          setDraft(null);
                        }}
                      >
                        취소
                      </button>
                      <button className="primary" disabled={!draft} onClick={() => setAdding(true)}>
                        위치 확정 <Icon name="check" size={16} />
                      </button>
                    </div>
                  </div>
                ) : (
                  selected && (
                    <div className="selection-card">
                      <div className="selection-icon">
                        <Icon name="building" size={22} />
                      </div>
                      <div>
                        <small>선택한 장소</small>
                        <strong>{selected.name}</strong>
                        <span>
                          {selected.address}
                        </span>
                      </div>
                      <div className="selection-actions">
                        <button className="delete-place" onClick={() => setDeleting(true)}>
                          <Icon name="trash" size={16} /> 장소 삭제
                        </button>
                        <button onClick={() => location.assign("/places/" + selectedId)}>
                          장소 관리 <Icon name="arrow" size={17} />
                        </button>
                      </div>
                    </div>
                  )
                )}
              </div>
            </section>
          </>
        ) : page === "manage" ? (
          selected && (
            <div className="manage-page">
              <button className="back-button" onClick={() => location.assign("/")}>
                <Icon name="arrow" size={17} /> 설치 장소 관리로 돌아가기
              </button>

              <section className="manage-heading">
                <div>
                  <p className="eyebrow">PLACE OVERVIEW</p>
                  <h1>{selected.name}</h1>
                  <span>
                    <Icon name="pin" size={15} />
                    {selected.address}
                  </span>
                </div>
                <button className="primary" onClick={() => setAddingModule(true)}>
                  <Icon name="plus" size={18} /> 모듈 추가
                </button>
              </section>

              <section className="summary-grid">
                <article>
                  <span className="summary-icon">
                    <Icon name="layers" size={20} />
                  </span>
                  <div>
                    <small>등록 모듈</small>
                    <strong>
                      {selectedModules.length}
                      <em>개</em>
                    </strong>
                  </div>
                </article>
                <article>
                  <span className="summary-icon">
                    <Icon name="check" size={20} />
                  </span>
                  <div>
                    <small>운영 중인 칸</small>
                    <strong>
                      {selectedModules.reduce((sum, module) => sum + module.open, 0)}
                      <em>칸</em>
                    </strong>
                  </div>
                </article>
                <article
                  className={
                    selectedModules.some((module) => module.status === "attention")
                      ? "has-alert"
                      : ""
                  }
                >
                  <span className="summary-icon">!</span>
                  <div>
                    <small>확인 필요</small>
                    <strong>
                      {selectedModules.filter((module) => module.status === "attention").length}
                      <em>건</em>
                    </strong>
                  </div>
                </article>
              </section>

              <div className="manage-layout">
                <section className="module-section">
                  <div className="section-title">
                    <div>
                      <h2>등록된 모듈</h2>
                      <p>각 구역의 운영 상태와 연결 정보를 확인하세요.</p>
                    </div>
                    <span>총 {selectedModules.length}개</span>
                  </div>
                  <div className="module-list">
                    {selected.sensor && <article className="module-row">
                      <span className="module-symbol"><Icon name="toilet" size={19}/></span>
                      <div className="module-info"><strong>시설 전체</strong><small>{selected.sensor.device_id}</small>
                        {moduleConnection(null,selected.sensor.device_id,selected.sensor)}
                      </div>
                    </article>}
                    {selectedModules.map((module) => (
                      <article className="module-row" key={module.id}>
                        <span className="module-symbol">
                          <Icon name="toilet" size={19} />
                        </span>
                        <div className="module-info">
                          <div>
                            <strong>{module.name}</strong>
                            <span className={`status ${module.status}`}>
                              {module.status === "online" ? "등록됨" : "일시 사용 불가"}
                            </span>
                          </div>
                          <small>
                            {module.type} · {module.device}
                          </small>
                          <div className="capacity">
                            <span>
                              <i style={{ width: `${(module.open / module.total) * 100}%` }} />
                            </span>
                            <b>
                              {module.open} / {module.total}칸 운영
                            </b>
                          </div>
                          {moduleConnection(module.id,module.sensor?.device_id ?? module.device,module.sensor)}
                        </div>
                        <button
                          aria-label={`${module.name} 삭제`}
                          className="module-delete"
                          onClick={() => deleteModule(module)}
                        >
                          <Icon name="trash" size={17} />
                        </button>
                      </article>
                    ))}
                    {selectedModules.length === 0 && (
                      <div className="module-empty">
                        <span>
                          <Icon name="layers" size={22} />
                        </span>
                        <strong>등록된 모듈이 없습니다</strong>
                        <p>이 장소에서 운영할 첫 모듈을 추가해 주세요.</p>
                      </div>
                    )}
                  </div>
                </section>

                <aside className="qr-card">
                  <div className="qr-card-head">
                    <span>
                      <Icon name="toilet" size={19} />
                    </span>
                    <div>
                      <h2>장소 관리자 QR</h2>
                      <p>현장 담당자에게 전달하세요.</p>
                    </div>
                  </div>
                  <div className="qr-visual" aria-label="장소 관리자 QR 코드">
                    <img className="rf-qr-image" alt="장소 관리자 QR" src={`/facility/${siteId}/qr.png`}/>
                  </div>
                  <strong>{selected.name}</strong>
                  <small>모든 구역을 한 번에 관리할 수 있습니다.</small>
                  <a className="secondary rf-qr-download" href={`/facility/${siteId}/qr.png`} download="RestFlow-관리자-QR.png">QR 저장</a>
                  <button className="qr-link" disabled={!managerBase} onClick={()=>perform(async()=>{
                    await navigator.clipboard.writeText(managerBase + "/facility/" + siteId);
                    notify("관리자 링크를 복사했습니다.");
                  })}>관리자 링크 복사</button>
                  <button className="secondary" disabled={busy} onClick={()=>perform(async()=>{
                    const result=await api("/api/setup/places/"+siteId+"/claim","POST",{});
                    setClaim(result.claim);
                  })}>최초 인계 코드 발급</button>
                  {claim&&<p className="rf-code">인계 코드 <code>{claim}</code></p>}
                </aside>
              </div>
            </div>
          )
        ) : (
          !auth ? <section className="modal rf-auth">
            <h1>{claimed===null ? "관리자 페이지" : claimed ? "관리자 로그인" : "최초 비밀번호 설정"}</h1>
            {claimed!==null&&<form onSubmit={login}>
              {!claimed&&<label>1회용 인계 코드<input name="claim" required/></label>}
              <label>비밀번호<input name="password" type="password" minLength={8} maxLength={128} required/></label>
              {!claimed&&<label>비밀번호 확인<input name="confirm" type="password" minLength={8} required/></label>}
              <button className="primary" disabled={busy}>{claimed?"로그인":"설정 완료"}</button>
            </form>}
          </section> : selected && (
            <div className="operator-page">
              <div className="operator-top">
                <button className="back-button" onClick={()=>location.reload()}>로그아웃</button>
                <span className="operator-role">현장 운영 관리자</span>
              </div>

              <section className="operator-heading">
                <div>
                  <span className="operator-place-icon">
                    <Icon name="toilet" size={22} />
                  </span>
                  <div>
                    <small>RESTFLOW FACILITY</small>
                    <h1>{selected.name}</h1>
                  </div>
                </div>
                <p>
                  {selected.address}
                </p>
              </section>

              <section className="operator-summary">
                <div>
                  <small>현재 운영 중</small>
                  <strong>
                    {selectedModules
                      .filter((module) => !module.closed)
                      .reduce((sum, module) => sum + module.open, 0)}
                    <span>칸</span>
                  </strong>
                </div>
                <div>
                  <small>전체</small>
                  <strong>
                    {selectedModules.reduce((sum, module) => sum + module.total, 0)}
                    <span>칸</span>
                  </strong>
                </div>
                <div>
                  <small>사용 불가 구역</small>
                  <strong>
                    {selectedModules.filter((module) => module.closed).length}
                    <span>곳</span>
                  </strong>
                </div>
              </section>

              <section className="operator-zones">
                <div className="operator-section-title">
                  <h2>구역별 운영 상태</h2>
                  <span>{selectedModules.length}개 구역</span>
                </div>
                <div className="zone-grid">
                  {selectedModules.map((module) => (
                    <article
                      className={`zone-card ${module.closed ? "closed" : ""}`}
                      key={module.id}
                    >
                      <div className="zone-head">
                        <span>
                          <Icon name="toilet" size={19} />
                        </span>
                        <div>
                          <h3>{module.name}</h3>
                          <small>
                            {module.type} · {module.device}
                          </small>
                        </div>
                        <b>{module.closed ? "사용 불가" : "운영 중"}</b>
                      </div>

                      <div className="zone-control">
                        <p>운영 칸 수</p>
                        <div className="stepper">
                          <button
                            aria-label={`${module.name} 운영 칸 수 줄이기`}
                            disabled={module.closed || module.open === 0}
                            onClick={() => updateModule(module.id, { open: module.open - 1 })}
                          >
                            −
                          </button>
                          <div>
                            <strong>{module.closed ? 0 : module.open}</strong>
                            <span>/ {module.total}칸</span>
                          </div>
                          <button
                            aria-label={`${module.name} 운영 칸 수 늘리기`}
                            disabled={module.closed || module.open === module.total}
                            onClick={() => updateModule(module.id, { open: module.open + 1 })}
                          >
                            +
                          </button>
                        </div>
                      </div>

                      <label className="unavailable-toggle">
                        <span>
                          <strong>일시 사용 불가</strong>
                          <small>청소나 고장 시 사용을 중지합니다.</small>
                        </span>
                        <input
                          checked={Boolean(module.closed)}
                          onChange={(event) =>
                            updateModule(module.id, {
                              closed: event.target.checked,
                              reason: event.target.checked ? module.reason || "청소 중" : "",
                            })
                          }
                          type="checkbox"
                        />
                        <i />
                      </label>

                      {module.closed && (
                        <label className="reason-field">
                          사용 불가 사유
                          <select
                            value={module.reason || "청소 중"}
                            onChange={(event) =>
                              updateModule(module.id, { reason: event.target.value })
                            }
                          >
                            <option>청소 중</option>
                            <option>시설 고장</option>
                            <option>점검 중</option>
                            <option>기타</option>
                          </select>
                        </label>
                      )}
                      {ventilationPanel(module.id)}
                    </article>
                  ))}
                </div>
                {equipment.some(item=>item.zone_id===null) && <article className="zone-card restflow-facility-vent">
                  <div className="zone-head"><div><h3>시설 전체</h3></div></div>
                  {ventilationPanel(null)}
                </article>}
              </section>

              <details className="modal rf-auth rf-password-change"><summary>비밀번호 변경</summary><form onSubmit={event=>{
                event.preventDefault();const data=new FormData(event.currentTarget);
                perform(async()=>{
                  if(data.get("current")!==auth||data.get("password")!==data.get("confirm"))throw Error("현재 비밀번호 또는 새 비밀번호 확인을 확인해 주세요.");
                  const next=String(data.get("password"));
                  await api(facility+"/password","PUT",{password:next},auth);setAuth(next);notify("비밀번호를 변경했습니다.");
                });
              }}>
                <label>현재 비밀번호<input name="current" type="password" required/></label>
                <label>새 비밀번호<input name="password" type="password" minLength={8} required/></label>
                <label>비밀번호 확인<input name="confirm" type="password" minLength={8} required/></label>
                <button className="primary" disabled={busy}>비밀번호 변경</button>
              </form></details>
              <div className={`operator-save ${adminDirty ? "dirty" : ""}`}>
                <div>
                  <span>
                    {adminDirty
                      ? "변경사항이 저장되지 않았습니다."
                      : "모든 변경사항이 저장되었습니다."}
                  </span>
                  <small>저장하면 이용자 앱에 반영됩니다.</small>
                </div>
                <button
                  className="primary"
                  disabled={!adminDirty || busy}
                  onClick={saveOperating}
                >
                  <Icon name="check" size={17} /> 변경사항 저장
                </button>
              </div>
            </div>
          )
        )}
      </main>

      {adding && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setAdding(false)}>
          <section
            aria-labelledby="add-title"
            aria-modal="true"
            className="modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-heading">
              <span>
                <Icon name="pin" size={22} />
              </span>
              <div>
                <p>새 설치 지점</p>
                <h2 id="add-title">장소 추가</h2>
              </div>
              <button aria-label="닫기" onClick={() => setAdding(false)}>
                <Icon name="close" />
              </button>
            </div>
            <div className="location-confirmed">
              <span>
                <Icon name="check" size={16} />
              </span>
              <p>
                <strong>지도에서 위치를 선택했어요</strong>
                {addressStatus}
              </p>
            </div>
            <form onSubmit={savePlace}>
              <label>
                장소 이름 <em>필수</em>
                <input autoFocus name="name" placeholder="예: 시청역 화장실" required />
              </label>
              <label>
                주소 <span>위치 기반 자동 입력</span>
                <input name="address" value={address} onChange={event=>{addressEdited.current=true;setAddress(event.target.value);}} placeholder="예: 서울 중구 세종대로 101" required />
              </label>
              <label>
                상세 위치 안내 <span>선택</span>
                <input name="detail" placeholder="예: 지하 1층, 1번 출구 방향" />
              </label>
              <div className="modal-actions">
                <button className="secondary" type="button" onClick={() => setAdding(false)}>
                  취소
                </button>
                <button className="primary" type="submit">
                  장소 저장
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {addingModule && selected && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={() => setAddingModule(false)}
        >
          <section
            aria-labelledby="module-title"
            aria-modal="true"
            className="modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="modal-heading">
              <span>
                <Icon name="layers" size={22} />
              </span>
              <div>
                <p>{selected.name}</p>
                <h2 id="module-title">모듈 추가</h2>
              </div>
              <button aria-label="닫기" onClick={() => setAddingModule(false)}>
                <Icon name="close" />
              </button>
            </div>
            <form onSubmit={saveModule}>
              <label>
                구역 이름 <em>필수</em>
                <input autoFocus name="name" placeholder="예: 지하 1층 여성 화장실" required />
              </label>
              <label>
                구역 유형 <em>필수</em>
                <select name="type" required defaultValue="여성">
                  <option>여성</option>
                  <option>남성</option>
                  <option>공용</option>
                  <option>여성 장애인</option>
                  <option>남성 장애인</option>
                  <option>공용 장애인</option>
                </select>
              </label>
              <div className="form-columns">
                <label>
                  전체 칸 수 <em>필수</em>
                  <input name="total" type="number" min="1" max="99" defaultValue="5" required />
                </label>
                <label>
                  장치 ID <em>필수</em>
                  <input name="device" placeholder="RF-001" maxLength={64} required />
                </label>
              </div>
              <label className="module-vent-option">
                <input type="checkbox" name="fan_enabled"/> 환기 제어 사용
                <small>Raspberry Pi를 함께 설치할 때 선택하세요.</small>
              </label>
              <div className="modal-actions">
                <button className="secondary" type="button" onClick={() => setAddingModule(false)}>
                  취소
                </button>
                <button className="primary" type="submit">
                  모듈 등록
                </button>
              </div>
            </form>
          </section>
        </div>
      )}

      {deleting && selected && (
        <div className="modal-backdrop" role="presentation" onMouseDown={() => setDeleting(false)}>
          <section
            aria-labelledby="delete-title"
            aria-modal="true"
            className="confirm-modal"
            onMouseDown={(event) => event.stopPropagation()}
            role="dialog"
          >
            <span className="danger-icon">
              <Icon name="trash" size={23} />
            </span>
            <h2 id="delete-title">이 장소를 삭제할까요?</h2>
            <p>
              <strong>{selected.name}</strong>
              지도와 장소 목록에서 삭제됩니다.
            </p>
            {selected.modules > 0 && (
              <div className="delete-warning">
                연결된 모듈 {selected.modules}개도 더 이상 이 장소에서 확인할 수 없습니다.
              </div>
            )}
            <div className="confirm-actions">
              <button className="secondary" onClick={() => setDeleting(false)}>
                취소
              </button>
              <button className="danger-button" onClick={deleteSelectedPlace}>
                장소 삭제
              </button>
            </div>
          </section>
        </div>
      )}

      {toast && (
        <div className="toast" role="status">
          <Icon name="check" size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}
