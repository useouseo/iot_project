import React, {useEffect, useRef, useState} from 'react';
import {ActivityIndicator, Button, StyleSheet, Text, View} from 'react-native';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import {WebView} from 'react-native-webview';

const origin = (process.env.EXPO_PUBLIC_RESTFLOW_URL || '').trim().replace(/\/+$/, '');
const configured = /^https?:\/\/[^/?#@]+$/i.test(origin);
const page = origin + '/user';
const locationBridge = `
  window.restflowNativeLocation = () => new Promise((resolve, reject) => {
    const id = String(Date.now()) + '-' + Math.random().toString(36).slice(2);
    const timer = setTimeout(() => finish(null, '현재 위치 확인 시간이 초과됐습니다.'), 45000);
    function finish(fix, error) {
      clearTimeout(timer);
      window.removeEventListener('restflow-location', receive);
      if (error) reject(new Error(error));
      else resolve(fix);
    }
    function receive(event) {
      if (event.detail.id === id) finish(event.detail.fix, event.detail.error);
    }
    window.addEventListener('restflow-location', receive);
    window.ReactNativeWebView.postMessage(JSON.stringify({type:'location', id}));
  });
  true;
`;

export default function App() {
  const web = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const [failure, setFailure] = useState('');
  useEffect(()=>{
    if (!configured || loaded || failure) return;
    const timer = setTimeout(()=>setFailure('이용자 화면을 불러오는 시간이 초과됐습니다.'), 20000);
    return ()=>clearTimeout(timer);
  },[loaded,failure]);
  async function onMessage(event) {
    const sender = event.nativeEvent.url?.replace(/\/$/, '');
    if (sender !== origin && sender !== page) return;
    let request;
    try { request = JSON.parse(event.nativeEvent.data); } catch { return; }
    if (request?.type !== 'location' || typeof request.id !== 'string') return;
    let response;
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== 'granted') throw new Error('휴대폰 설정에서 위치 권한을 허용해 주세요.');
      const fix = await Location.getCurrentPositionAsync({accuracy: Location.Accuracy.High});
      const {latitude, longitude, accuracy} = fix.coords;
      response = {id:request.id, fix:{coords:{latitude, longitude, accuracy:accuracy ?? 0}, timestamp:fix.timestamp}};
    } catch (error) {
      response = {id:request.id, error:error.message || '현재 위치를 확인하지 못했습니다.'};
    }
    const detail = JSON.stringify(response).replace(/</g,'\\u003c');
    web.current?.injectJavaScript(`window.dispatchEvent(new CustomEvent('restflow-location', {detail:${detail}})); true;`);
  }
  return <SafeAreaProvider style={styles.screen}><SafeAreaView style={styles.screen}>
    {configured && !failure ? <View style={styles.screen}>
      <WebView ref={web} source={{uri:page}} style={styles.screen} containerStyle={styles.screen} domStorageEnabled
        originWhitelist={[origin]}
        onShouldStartLoadWithRequest={({url})=>url==='about:blank' || url.split(/[?#]/)[0].replace(/\/$/,'')===page}
        injectedJavaScriptBeforeContentLoaded={locationBridge} injectedJavaScript={locationBridge}
        onMessage={onMessage}
        onLoad={event=>{if(event.nativeEvent.url?.startsWith(page))setLoaded(true);}}
        onError={event=>setFailure(event.nativeEvent.description || '서버에 연결할 수 없습니다.')}
        onHttpError={event=>{if(event.nativeEvent.url===page)setFailure(`서버 응답 오류 (${event.nativeEvent.statusCode})`);}}
        onContentProcessDidTerminate={()=>setFailure('아이폰이 이용자 화면을 닫았습니다.')}
      />
      {!loaded && <View style={styles.loading}><ActivityIndicator/><Text>RestFlow 화면 연결 중…</Text><Text selectable>{page}</Text></View>}
    </View> : <View style={styles.message}>
      <Text style={styles.title}>RestFlow</Text>
      <Text>{configured ? failure : 'mobile/.env.local에 RestFlow 서버 주소를 설정해 주세요.'}</Text>
      {configured && <><Text selectable>{page}</Text><Button title="다시 연결" onPress={()=>{setLoaded(false);setFailure('');}}/></>}
    </View>}
  </SafeAreaView></SafeAreaProvider>;
}
const styles = StyleSheet.create({
  screen:{flex:1,backgroundColor:'#f4f6f2'},
  loading:{...StyleSheet.absoluteFillObject,justifyContent:"center",alignItems:"center",gap:12,backgroundColor:"#f4f6f2"},
  message:{flex:1,justifyContent:'center',padding:24,gap:12},
  title:{fontSize:24,fontWeight:'700',color:'#294737'},
});
