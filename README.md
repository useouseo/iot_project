# RestFlow · 탈부착형 화장실 혼잡 안내 IoT

ATOM Lite + VL53L1X → Wi-Fi 이벤트 수집 → SQLite → 방문객 지도 / 관리자 운영 화면의 시제품입니다. 제공된 계획서의 최종 방향대로 **최근 10분 통행량 기반 추정 혼잡도**를 표시합니다. 실제 내부 인원수·대기시간·배터리 잔량을 추정값으로 꾸며 표시하지 않습니다.

## 실행

Python 3.12 권장. 별도 DB 서버나 Node 빌드는 필요 없습니다.

```sh
cd /workspace/iot_project
python -m venv /workspace/.venvs/iot
/workspace/.venvs/iot/bin/pip install -r requirements.txt
/workspace/.venvs/iot/bin/python server.py --demo
```

포트 8000, 방문객 경로 `/`, 관리자 경로 `/admin`입니다. 기본 바인딩은 127.0.0.1입니다. `--demo`는 별도 DB에 최초 세 곳의 가상 데이터를 만들고 화면에 시연 표시를 합니다. 서버 재시작 시 기존 DB를 유지하며, 2분 이후 가상 장치는 오프라인으로 바뀝니다. 관리자 화면의 ‘시연 통행 데이터 추가’로 새 기록을 만들 수 있습니다. 실제 측정처럼 계속 신호를 꾸며 보내지 않습니다.

방문객은 QR을 스캔해 `/`에서 모바일 지도를 확인합니다. 방문객 화면에는 관리자 진입 메뉴가 없습니다. 관리자는 PC 또는 휴대폰에서 `/admin` 주소로 직접 접속합니다. **최초 관리자 비밀번호는 `1234`**이며 로그인 후 ‘관리자 비밀번호 변경’에서 현재 비밀번호·새 비밀번호·확인을 입력해 변경할 수 있습니다. 파일 토큰이나 `ADMIN_TOKEN` 환경변수는 더 이상 사용하지 않습니다. 기존 `.runtime/admin-token` 파일은 남아 있어도 로그인에 사용하지 않습니다. 비밀번호는 DB에 salt+PBKDF2 해시로 저장하고 로그인은 8시간 HttpOnly 쿠키 세션으로 유지합니다. 비밀번호 변경 시 다른 로그인 세션은 만료됩니다. `.runtime`을 보존하면 변경한 비밀번호도 재시작 후 유지됩니다. 데모·실사용 모드는 각각 별도 DB이므로 비밀번호도 각각 저장됩니다.

실제 센서용 실행은 `--demo` 없이 시작합니다. `.runtime/live.sqlite3`에 최초 두 곳의 시설을 만들고 장치 등록 전에는 ‘확인 필요’를 표시합니다.

```sh
/workspace/.venvs/iot/bin/python server.py
```

기본 포트가 사용 중이면 `--port 8001`. 외부 연결이 필요할 때만 `--host 0.0.0.0`과 별도 HTTPS 프록시를 설정합니다. 관리자 화면의 ‘방문객 QR’에서 휴대폰으로 실제 접속 가능한 주소를 입력하고 ‘주소 저장 · QR 생성’을 누르세요. QR은 화면에 표시되며 PNG/SVG 다운로드 버튼으로 브라우저의 다운로드 폴더에 저장할 수 있습니다. 관리자 화면에 저장한 주소가 우선이고, 미설정 시 `PUBLIC_URL` 환경변수를 초기값으로 사용합니다. QR은 서버에서 생성하고 외부 QR 서비스로 URL을 보내지 않습니다. 현재 외부 배포·DNS·TLS 인증서는 설정하지 않았습니다.

## 화장실 개수·지도 위치·QR 설정

화장실 수는 고정돼 있지 않습니다. 관리자의 ‘화장실 추가’에서 이름과 운영 칸 수를 입력하면 새 시설이 추가됩니다. 선택한 시설의 ‘삭제’를 누르면 지도·목록에서 제거되며 연결된 장치 수신은 중지됩니다. 기존 통행 기록은 DB에 보존합니다. 모두 삭제해도 재시작 시 예시 시설이 되살아나지 않으며 다시 추가할 수 있습니다. 추가한 시설은 실제 센서 모드에서는 장치 등록 전 ‘확인 필요’이고, 데모 모드에서는 가상 장치가 자동 연결돼 시연 데이터 추가로 시험할 수 있습니다.

관리자로 로그인하면 지도 마커를 마우스 또는 터치로 드래그할 수 있습니다. 지도 아래의 ‘위치 저장’을 눌러야 방문객 화면에 반영되며 ‘되돌리기’로 저장 전 위치를 취소할 수 있습니다. 자동 갱신 중에도 편집 위치를 유지합니다. 마커에 키보드 초점을 두고 방향키로 1%, Shift+방향키로 5%씩 옮길 수 있습니다. 빈 지도 클릭과 선택 사항인 좌표 직접 입력도 지원합니다. 방문객 화면은 위치를 편집할 수 없습니다.

QR 이미지 파일은 서버에 자동 저장되지 않습니다. ‘방문객 QR’에서 생성 후 ‘PNG 다운로드’ 또는 ‘SVG 다운로드’를 눌러 저장하세요. `localhost` 주소를 인코딩하면 현재 PC에서만 열립니다. 같은 Wi-Fi의 휴대폰으로 시험하려면 서버를 `start_demo.bat --host 0.0.0.0`으로 실행하고, `ipconfig`에서 확인한 PC의 IPv4 주소를 사용해 `http://PC_IP:8000`을 QR 주소로 입력합니다. Windows 방화벽에서 신뢰하는 사설 네트워크의 해당 접속이 허용돼 있어야 합니다. 외부 방문객에게 배포할 때는 실제 공개 HTTPS 주소를 사용합니다. URL 입력만으로 서버나 방화벽 설정이 바뀌지는 않습니다.

업데이트 시 기존 서버를 Ctrl+C로 종료하고 파일을 덮어쓰되 `.runtime` 폴더는 보존하세요. `start_demo.bat`를 다시 실행하고 브라우저에서 Ctrl+F5를 눌러 새 화면을 불러오세요.

## 포함 기능

- 모바일 대응 행사장 지도, 시설 선택, 단계·수신 시각, 5초 갱신, 서버 연결 실패 표시.
- 관리자 비밀번호 로그인·변경, 화장실 추가·삭제, 시설명·칸 수·지도 마커 드래그·위치 저장, 지도 PNG/JPEG 업로드, 장치 등록과 토큰 1회 발급.
- 2분 수신 단절 또는 품질 저하 시 ‘확인 필요’, 최근 2시간 입·퇴장 막대그래프.
- 장치별 토큰 인증, 부팅 ID+순번 중복 방지, 동시 요청 처리, 발생시각 검증, 예외 계산 초기화.
- 단일 VL53L1X 두 ROI 순차 측정 펌웨어, 되돌아감/불완전 통과 배제, NVS 대기열·Wi-Fi 재전송.
- 관리자 화면에서 방문객 URL 설정, 로컬 QR 생성 및 PNG/SVG 다운로드, 실제 장치 API를 사용하는 Python 시뮬레이터.

## 검증

```sh
/workspace/.venvs/iot/bin/python -m unittest discover -s tests -v
g++ -std=c++11 -Wall -Wextra -pedantic tests/direction_test.cpp -o /tmp/direction_test
/tmp/direction_test
node --check web/app.js
```

선택 브라우저 시험에는 `requirements-dev.txt`와 Chromium이 필요합니다. 이 클라우드에는 `/usr/bin/chromium`이 있으며 스크립트가 우선 사용합니다. 다른 환경에서는 `python -m playwright install chromium`으로 설치합니다.

```sh
/workspace/.venvs/iot/bin/pip install -r requirements-dev.txt
/workspace/.venvs/iot/bin/python tools/browser_smoke.py
```

센서 API를 시험하려면 실사용 모드 관리자 화면에서 장치를 등록하고 발급 토큰을 `DEVICE_TOKEN` 환경변수에 안전하게 설정한 뒤 실행합니다. 장치마다 별도 `--state` 파일을 사용합니다. 실제 발생시각과 부팅 ID/순번을 유지하여 실패 시 재전송합니다.

```sh
/workspace/.venvs/iot/bin/python tools/simulate.py --device atom-entrance-a --count 3
/workspace/.venvs/iot/bin/python tools/simulate.py --device atom-entrance-a --direction out
```

## 설계·부품·시험 자료

- [부품 검토, 96,100원 내역, 배선·전원·센서 교정](docs/HARDWARE.md)
- [혼잡도 수식, DB, API와 구현 범위](docs/ARCHITECTURE.md)
- [검증 결과와 실물 인수 시험](docs/VALIDATION.md)
- [시연 및 발표 구성](docs/DEMO.md)
- [방문객 데스크톱 화면](docs/screenshots/visitor-desktop.png), [모바일](docs/screenshots/visitor-mobile.png), [관리자](docs/screenshots/admin-desktop.png)

ESP32 전체 크로스 컴파일은 현재 환경의 PlatformIO 레지스트리 정책 차단으로 미검증입니다. 네트워크 초안에 `api.registry.platformio.org`, `dl.registry.platformio.org`를 추가했으며 자동 적용·게시는 하지 않았습니다. 환경 설정에서 반영한 뒤 `firmware` 디렉터리에서 `pio run`을 다시 실행해야 합니다. 이후 내려받기 리다이렉트 도메인이 차단되면 실제 오류를 보고 필요한 도메인만 추가합니다. 컴파일 성공 전 실물 업로드 가능 상태라고 주장하지 않습니다.

하드웨어 정확도·배터리 지속시간·실제 행사 네트워크와 혼잡도 임계값은 현장 검증이 남아 있습니다. 소스는 다운로드 가능한 별도 GitHub 브랜치로 제공합니다. 외부 서비스 배포·환경 게시는 하지 않았습니다.

로그인 화면에서 예전 ‘관리자 토큰’ 오류가 나오면 업데이트 전 서버가 실행 중일 수 있습니다. start_demo.bat로 열어 둔 기존 서버 창을 Ctrl+C로 종료하고, 최신 파일이 있는 폴더에서 다시 실행한 뒤 Ctrl+F5로 갱신하세요. 새 서버는 health의 auth_mode=password를 제공하며, 구버전과 새 화면이 섞이면 로그인 화면에 재시작 안내를 표시합니다. 이미 변경한 비밀번호는 업데이트로 초기화하지 않습니다.
