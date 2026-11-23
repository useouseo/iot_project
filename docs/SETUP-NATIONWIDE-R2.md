# RestFlow 전국 통합 앱 서비스 실행 안내

이 안내는 `RestFlow-Integrated-TMAP-Unified-R2.zip` 기준입니다. 이 브랜치를 내려받아 소스 폴더에서 실행합니다. 이용자 앱은 RestFlow에 등록된 시설의 운영 상태·혼잡도와 TMAP 보행 경로를 보여줍니다. 행사장별 단기 설치형은 [11월 13일 버전 안내](https://github.com/useouseo/iot_project/blob/release/portable-20261113/docs/SETUP-PORTABLE-20261113.md)를 참고하세요.

## 서버와 MariaDB

1. Windows에 Python과 MariaDB를 설치하고 MariaDB 서비스를 켭니다. 이 버전을 처음 쓰면 `START_SERVER.bat`가 DB 정보를 묻습니다. 같은 PC의 기본 설정은 `127.0.0.1:3306`이며 DB 계정과 비밀번호를 입력합니다. 기본 DB 이름은 실사용 `restflow_integrated`, 시연 `restflow_integrated_demo`입니다. 이전 R2 시설을 이어 쓸 때는 같은 DB를 가리키는 기존 R2 `db_config.json`을 복사합니다.
2. `START_SERVER.bat` 실행 후 서버 PC에서 `http://127.0.0.1:8080`을 열어 설치자 화면을 확인합니다. 가상 센서로 시작하려면 `START_DEMO.bat`를 사용합니다.
3. 실물 연결에는 ATOM Lite와 Pi가 접근할 수 있는 HTTPS 주소를 준비합니다. 운영 환경에서는 HTTPS 프록시와 고정 주소를 설정하고, 장소 관리자 QR의 기준 주소는 `RESTFLOW_PUBLIC_URL`로 지정할 수 있습니다.

## 모듈 등록과 ATOM Lite 연결

1. 설치자 화면에서 시설과 구역을 등록합니다. 기존 **모듈 추가** 창에 구역과 장치 ID를 입력하고, Pi까지 쓸 구역에만 **환기 제어 사용**을 체크합니다.
2. 같은 행에서 발급된 키를 복사합니다. ATOM Lite만 쓰는 구역은 센서 키 하나, Pi를 함께 쓰는 구역은 센서 키와 Pi 키가 발급됩니다. 이미 등록한 센서에 Pi를 붙일 때는 같은 행의 **환기 추가**를 사용합니다.
3. ToF4M(VL53L1X) Unit의 SDA/SCL을 ATOM Lite의 G26/G32에 각각 연결하고 GND와 전원을 제품 표기에 맞춥니다. DHT11은 G33에 데이터선을 연결하고 센서 모듈의 전원과 풀업 규격을 확인합니다.
4. `firmware/include/secrets.example.h`를 `secrets.h`로 복사하고 Wi-Fi 정보, HTTPS `API_BASE`, 장치 ID, ATOM Lite 키(`DEVICE_TOKEN`), 검증용 `ROOT_CA`를 설정합니다. `firmware` 폴더에서 `pio run --target upload`와 `pio device monitor`로 업로드 및 로그를 확인합니다.
5. 실제 입구에서 입장과 퇴장을 각각 시험해 ToF 방향과 감지 거리를 교정합니다. 관리자의 습도와 이용자 화면의 혼잡도가 갱신되는지 확인합니다.

## Raspberry Pi와 환기팬 연결

1. 소스의 `raspberry_pi` 폴더를 Pi로 복사합니다. `restflow-fan.env.example`을 `/etc/restflow-fan.env`로 복사하고 `RESTFLOW_SERVER_URL`, `RESTFLOW_DEVICE_ID`, `RESTFLOW_DEVICE_TOKEN`을 입력합니다. 서버 주소와 장치 ID는 센서와 같고, 토큰은 Raspberry Pi용입니다.
2. Pi에서 환경변수를 읽고 `python3 fan_controller.py --dry-run`으로 먼저 명령 수신을 확인합니다. 관리자 웹의 구역 카드에서 수동 출력을 바꿔 Pi가 새 명령을 받고 적용값을 회신하는지 확인합니다.
3. 전원을 끄고 BCM GPIO18(물리 12번)을 XY-MOS의 제어 입력에, Pi GND를 제어측 GND에 연결합니다. 5V 팬은 MOSFET 부하측과 별도 정격 5V 전원을 사용합니다. 기판 단자와 팬 극성은 실물 표기에 맞춥니다.
4. 소스의 `raspberry_pi/README.md`에 따라 `python3-rpi.gpio`와 `restflow-fan.service`를 설치합니다. 제공 서비스는 `/opt/restflow/raspberry_pi` 경로와 `User=pi`를 사용하므로 실제 환경과 맞는지 확인합니다. 기본 출력 신호는 GPIO18의 1kHz 소프트웨어 PWM입니다.

## 휴대폰 앱과 현장 시험

- `mobile/.env.example`을 참고해 로컬의 `mobile/.env.local`에 `EXPO_PUBLIC_RESTFLOW_URL`과 본인의 TMAP 설정을 넣습니다. 같은 Wi-Fi에서 시험할 때는 휴대폰 브라우저에서 PC의 LAN 주소 뒤에 `:8080/user`를 붙여 열리는지 먼저 확인하고 `START_APP.bat`의 Expo Go QR을 스캔합니다. 외부 서비스용 APK는 고정 서버 주소를 설정하고 별도로 빌드합니다.
- 수동 모드에서 0%, 30%, 60%, 100%를 시험해 팬의 실제 기동과 회전을 확인합니다. 화면의 적용값은 Pi가 회신한 PWM 비율입니다.
- 자동 모드에서 목표 습도부터 환기가 강화되고 목표보다 10%p 높은 기준(최대 100%)에서 최대 출력이 되는지 확인합니다. 실제로 비어 있는 구역에서 무인 자동 절전을 켜고 습도가 목표보다 낮은 상태라면, 기본값으로 5분 후 30%, 15분 후 정지하는지 확인합니다.
- 실제 인증키, Wi-Fi 비밀번호, `db_config.json`, `secrets.h`, 키가 들어 있는 `mobile/.env.local`은 공개 저장소에 게시하지 않습니다.
