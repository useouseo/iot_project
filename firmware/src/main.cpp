#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <VL53L1X.h>
#include <ArduinoJson.h>
#include <time.h>
#include "direction.h"
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

VL53L1X tof;
DirectionCounter counter;
Preferences prefs;
SemaphoreHandle_t lock;
struct Event { char boot[17]; uint32_t seq; uint32_t at; int8_t direction; };
struct Pending { uint32_t version=1; uint32_t size=0; bool overflow=false; Event events[64]; } pending;
char bootId[17]; uint32_t seq=0;
volatile bool sensorGood=false;
volatile uint32_t lastSample=0;
bool ready=false,a=false,b=false;
uint16_t distanceA=0,distanceB=0;uint8_t statusA=255,statusB=255;

void persist(){prefs.putBytes("pending",&pending,sizeof(pending));}
void enqueue(int direction){
  const time_t now=time(nullptr);
  if(now<1700000000)return; // No invented timestamps before NTP sync.
  xSemaphoreTake(lock,portMAX_DELAY);
  if(pending.size==64){pending.overflow=true;persist();}
  else{
    Event &e=pending.events[pending.size++];strlcpy(e.boot,bootId,sizeof(e.boot));
    e.seq=++seq;e.at=uint32_t(now);e.direction=direction;persist();
  }
  xSemaphoreGive(lock);
}
const char* quality(){
  if(!sensorGood||uint32_t(millis()-lastSample)>2000||time(nullptr)<1700000000)return "fault";
  return pending.overflow?"degraded":"good";
}
int post(const char* path,JsonDocument &doc){
  WiFiClientSecure tls;tls.setCACert(ROOT_CA);HTTPClient http;
  String url=String(API_BASE)+path;
  if(!url.startsWith("https://"))return -1;
  if(!http.begin(tls,url))return -1;
  http.setConnectTimeout(2500);http.setTimeout(2500);
  http.addHeader("Content-Type","application/json");http.addHeader("Authorization",String("Bearer ")+DEVICE_TOKEN);
  String body;serializeJson(doc,body);int result=http.POST(body);http.end();return result;
}
void networkTask(void*){
  uint32_t heartbeat=0,reconnect=0;
  for(;;){
    if(WiFi.status()!=WL_CONNECTED){
      if(uint32_t(millis()-reconnect)>10000){reconnect=millis();WiFi.reconnect();}
      vTaskDelay(pdMS_TO_TICKS(250));continue;
    }
    Event event;bool available;
    xSemaphoreTake(lock,portMAX_DELAY);
    // Expired packets cannot affect current congestion; record loss as degraded.
    while(pending.size && time(nullptr)>1700000000 && pending.events[0].at+86400<uint32_t(time(nullptr))){
      memmove(pending.events,pending.events+1,(--pending.size)*sizeof(Event));pending.overflow=true;persist();
    }
    available=pending.size>0;if(available)event=pending.events[0];
    String q=quality();xSemaphoreGive(lock);
    if(available){
      StaticJsonDocument<512> doc;doc["device_id"]=DEVICE_ID;doc["boot_id"]=event.boot;
      doc["seq"]=event.seq;doc["direction"]=event.direction>0?"in":"out";
      doc["occurred_at"]=event.at;doc["quality"]=q;
      int status=post("/api/events",doc);
      if(status==200){
        xSemaphoreTake(lock,portMAX_DELAY);
        memmove(pending.events,pending.events+1,(--pending.size)*sizeof(Event));persist();xSemaphoreGive(lock);
      }else{Serial.printf("Delivery pending (HTTP %d). Check clock / ID / token / TLS.\n",status);vTaskDelay(pdMS_TO_TICKS(3000));}
    }
    if(uint32_t(millis()-heartbeat)>30000){
      StaticJsonDocument<256> doc;doc["device_id"]=DEVICE_ID;doc["quality"]=q;
      if(post("/api/heartbeat",doc)==200)heartbeat=millis();
    }
    vTaskDelay(pdMS_TO_TICKS(100));
  }
}
bool measure(uint8_t center,bool was,bool &valid,uint16_t &distance,uint8_t &status){
  tof.setROICenter(center);
  uint16_t mm=tof.readSingle();distance=mm;status=tof.ranging_data.range_status; // single shot applies ROI before acquiring sample
  valid=!tof.timeoutOccurred() && tof.ranging_data.range_status==VL53L1X::RangeValid;
  return valid ? (was?mm<RELEASE_MM:mm<DETECT_MM) : false;
}
void setup(){
  Serial.begin(115200);pinMode(39,INPUT_PULLUP);
  lock=xSemaphoreCreateMutex();prefs.begin("restflow",false);
  if(prefs.getBytesLength("pending")==sizeof(pending))prefs.getBytes("pending",&pending,sizeof(pending));
  if(pending.version!=1 || pending.size>64)pending=Pending();
  snprintf(bootId,sizeof(bootId),"%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
  Wire.begin(SDA_PIN,SCL_PIN);tof.setTimeout(200);
  ready=tof.init();
  if(ready){tof.setDistanceMode(VL53L1X::Long);ready=tof.setMeasurementTimingBudget(50000);tof.setROISize(ROI_WIDTH,ROI_HEIGHT);}
  WiFi.mode(WIFI_STA);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);configTime(0,0,"pool.ntp.org","time.google.com");
  xTaskCreatePinnedToCore(networkTask,"network",8192,nullptr,1,nullptr,0);
  Serial.println("RestFlow started; calibrate ROI direction and distance before use.");
}
void loop(){
  static uint32_t retry=0,hold=0,logAt=0;
  if(!ready){
    sensorGood=false;
    if(uint32_t(millis()-retry)>5000){retry=millis();ready=tof.init();if(ready){tof.setDistanceMode(VL53L1X::Long);ready=tof.setMeasurementTimingBudget(50000);tof.setROISize(ROI_WIDTH,ROI_HEIGHT);}}
    delay(50);return;
  }
  bool va=false,vb=false;
  a=measure(ROI_A_CENTER,a,va,distanceA,statusA);b=measure(ROI_B_CENTER,b,vb,distanceB,statusB);
  lastSample=millis();sensorGood=va&&vb;
  if(uint32_t(millis()-logAt)>1000){logAt=millis();Serial.printf("A=%u status=%u B=%u status=%u valid=%d/%d\n",distanceA,statusA,distanceB,statusB,va,vb);}
  if(!sensorGood){counter.invalidate();a=b=false;}
  else{int direction=counter.update(a,b,millis());if(direction)enqueue(direction);}
  // Intentional operator acknowledgement after investigating overflow/loss.
  if(digitalRead(39)==LOW){if(!hold)hold=millis();if(uint32_t(millis()-hold)>3000){xSemaphoreTake(lock,portMAX_DELAY);pending.overflow=false;persist();xSemaphoreGive(lock);hold=millis();}}
  else hold=0;
  delay(2);
}
