# RestFlow 휴대용 단기 설치 안내

이 안내는 `20261113_tmap.zip`의 `spaces-v1` 기준입니다. 행사장·임시 시설에 ATOM Lite와 ToF 센서를 설치하고, 공간마다 별도 QR로 방문객 웹을 제공하는 구성입니다. 전국 통합 서비스는 [R2 실행 안내](SETUP-NATIONWIDE-R2.md)를 참고하세요.

## 준비물과 센서 배선

- Windows PC, Python 3.12 64비트, MariaDB Server, PlatformIO, USB 데이터 케이블, 장치가 접속할 Wi-Fi
- 출입구당 ATOM Lite 1대와 M5Stack ToF4M(VL53L1X) Unit 1개, Grove 케이블, 현장에 맞는 전원
- Grove의 G26/SDA, G32/SCL, GND를 센서의 같은 표기에 연결합니다. VCC는 사용 중인 Unit의 제조사 규격을 확인합니다. 센서는 출입 방향을 따라 두 감지 영역이 앞뒤로 놓이게 설치합니다. 탈부착 설치는 낙하 방지용 보조 고정을 사용하세요.

## 실제 센서로 실행

1. MariaDB 서비스를 켜고 ZIP을 푼 폴더에서 `start_public.bat`를 실행합니다. 첫 실행이면 DB 호스트 `localhost`, 포트 `3306`, MariaDB 계정과 비밀번호를 입력합니다. 기본 DB 이름은 실사용 `restflow`, 시연 `restflow_demo`입니다. 기존 설정이 있으면 이 버전의 `db_config.json`을 이어 씁니다.
2. 열린 관리자 화면에서 공간을 추가할 때 실내 또는 야외를 선택합니다. 실내는 배치도, 야외는 TMAP으로 입구 위치를 등록합니다. 화장실과 운영 칸 수를 입력한 뒤 센서마다 다른 장치 ID를 등록해 토큰을 확보합니다.
3. `firmware/include/secrets.example.h`를 같은 폴더에 `secrets.h`로 복사합니다. `WIFI_SSID`, `WIFI_PASSWORD`, 실행 창에 표시된 공개 HTTPS `API_BASE`, `DEVICE_ID`, 장치별 `DEVICE_TOKEN`, 서버 인증서를 검증할 `ROOT_CA`를 입력합니다.
4. USB로 ATOM Lite를 연결하고 `firmware` 폴더에서 `pio run --target upload`, `pio device monitor`를 실행합니다. 현장에서 입장·퇴장을 각각 시험합니다. 방향이 반대이거나 감지가 누락되면 두 감지 영역의 방향과 거리 임계값을 현장에 맞춥니다.
5. 관리자 화면에서 수신 상태와 통행 이력을 확인합니다. 선택한 공간의 방문객 QR을 발급하고 휴대폰으로 열어 같은 공간인지 확인합니다.

장비 없이 시연할 때는 `start_public_demo.bat`를 실행합니다. TMAP이 필요한 경우 지도 키와 보행 경로 키를 로컬에서 설정한 뒤 실행하세요. `start_with_tmap.bat`는 TMAP 키를 설정한 시연용입니다. 지도와 경로 설정은 각각 `RESTFLOW_TMAP_MAP_KEY`, `RESTFLOW_TMAP_ROUTE_KEY`입니다.

## 현장에서 확인할 점

- Quick Tunnel 사용 중에는 PC·MariaDB·실행 창·인터넷 연결을 유지합니다. 임시 공개 주소가 바뀌면 방문객 QR을 다시 생성하고, 장치의 `API_BASE`를 새 주소로 설정해 펌웨어를 다시 올립니다.
- 보조배터리를 쓰면 실제 행사 시간 동안 저부하 자동 차단 여부와 운전 시간을 확인합니다.
- 장비 토큰, Wi-Fi 비밀번호, DB 설정, 실제 TMAP 키는 현장 담당자에게 별도로 전달합니다.

[공동 개발자 실행 안내](TEAM_SETUP.md) · [하드웨어 배선과 ToF 교정](HARDWARE.md)
