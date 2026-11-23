export type Availability = "closed" | "busy" | "normal" | "free" | "unknown";
export type Restroom = "women" | "men" | "shared" | "any";
export type Preferences = {restroom: Restroom; accessibleFirst: boolean};

export const restroomLabels = {women:"여성", men:"남성", shared:"공용", any:"상관없음"};
export const defaultPreferences: Preferences = {restroom:"any", accessibleFirst:false};
export const availabilityLabels: Record<Availability, string> = {
  closed:"이용 불가", busy:"혼잡", normal:"보통", free:"여유", unknown:"정보 없음",
};

export type Sensor = {state:Availability; online:boolean; entries:number|null};
type Zone = {kind?:string; open:number; total:number; closed:boolean; accessible:boolean; sensor?:Sensor|null};

export function sensorLevel(entries:number, operating:number):Availability {
  if (!operating) return "closed";
  return entries >= operating*2 ? "busy" : entries >= operating ? "normal" : "free";
}
export function summarize(zones: Zone[], restroom: Restroom, facilitySensor?:Sensor|null) {
  const matches = (kind:string) => zones.filter(zone => zone.kind === kind || zone.kind === kind+"-accessible");
  let matched = restroom === "any" ? zones : matches(restroom);
  let basis = restroom === "any" ? "전체" : restroomLabels[restroom];
  if (!matched.length && (restroom === "women" || restroom === "men")) {
    matched = matches("shared");
    basis = "공용";
  }
  const open = matched.reduce((sum, zone) => sum + (zone.closed ? 0 : zone.open), 0);
  const total = matched.reduce((sum, zone) => sum + zone.total, 0);
  const active = matched.filter(zone => !zone.closed && zone.open > 0);
  const allMeasured = active.length > 0 && active.every(zone => zone.sensor?.entries != null);
  const useFacility = !allMeasured && Boolean(facilitySensor) && open > 0;
  const state = !total ? "unknown" : !open ? "closed" : allMeasured
    ? sensorLevel(active.reduce((sum, zone) => sum + (zone.sensor?.entries ?? 0), 0), open)
    : useFacility ? facilitySensor!.state : "unknown";
  return {open,total,basis,state,crowdBasis:useFacility ? "시설 전체" : basis,accessible:matched.some(zone => zone.accessible && !zone.closed && zone.open > 0)};
}

const penalty: Record<Availability, number> = {free:0,normal:180,busy:360,unknown:700,closed:1100};
export function score(place: ReturnType<typeof summarize> & {distance:number}, preferAccessible:boolean) {
  return place.distance + penalty[place.state] + (preferAccessible && !place.accessible ? 800 : 0);
}

export function readPreferences(key="restflow-user-preferences"): Preferences | null {
  try {
    const saved = JSON.parse(localStorage.getItem(key) || "null");
    if (saved && Object.hasOwn(restroomLabels,saved.restroom) && typeof saved.accessibleFirst === "boolean") return saved;
  } catch { /* Storage can be disabled. */ }
  return null;
}
