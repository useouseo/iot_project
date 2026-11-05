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

포트 8000, 방문객 경로 `/`, 관리자 경로 `/admin`입니다. 기본 바인딩은 127.0.0.1입니다. `--demo`는 별도 DB에 세 곳의 가상 데이터를 만들고 화면에 시연 표시를 합니다. 서버 재시작 시 기존 DB를 유지하며, 2분 이후 가상 장치는 오프라인으로 바뀝니다. 관리자 화면의 ‘시연 통행 데이터 추가’로 새 기록을 만들 수 있습니다. 실제 측정처럼 계속 신호를 꾸며 보내지 않습니다.

관리자 토큰은 `ADMIN_TOKEN` 환경변수(16자 이상)를 사용합니다. 미설정이면 최초 실행 때 `.runtime/admin-token` 파일을 권한 0600으로 생성합니다. 해당 파일의 값을 사용자가 로컬에서 확인해 로그인하면 됩니다. 토큰을 채팅·Git·스크린샷에 공유하지 마세요. 브라우저는 새로고침하면 다시 로그인해야 합니다.

실제 센서용 실행은 `--demo` 없이 시작합니다. `.runtime/live.sqlite3`에 두 곳의 시설만 만들고 장치 등록 전에는 ‘확인 필요’를 표시합니다.

```sh
/workspace/.venvs/iot/bin/python server.py
```

기본 포트가 사용 중이면 `--port 8001`. 외부 연결이 필요할 때만 `--host 0.0.0.0`과 별도 HTTPS 프록시를 설정합니다. `PUBLIC_URL`에 휴대폰에서 실제 접속 가능한 방문객 HTTPS 주소를 설정하면 관리자 화면에서 QR을 생성합니다. QR은 서버에서 생성하고 외부 QR 서비스로 URL을 보내지 않습니다. 현재 외부 배포·DNS·TLS 인증서는 설정하지 않았습니다.

## 포함 기능

- 모바일 대응 행사장 지도, 시설 선택, 단계·수신 시각, 5초 갱신, 서버 연결 실패 표시.
- 관리자 토큰 인증, 시설명·칸 수·좌표 저장, 지도 PNG/JPEG 업로드, 장치 등록과 토큰 1회 발급.
- 2분 수신 단절 또는 품질 저하 시 ‘확인 필요’, 최근 2시간 입·퇴장 막대그래프.
- 장치별 토큰 인증, 부팅 ID+순번 중복 방지, 동시 요청 처리, 발생시각 검증, 예외 계산 초기화.
- 단일 VL53L1X 두 ROI 순차 측정 펌웨어, 되돌아감/불완전 통과 배제, NVS 대기열·Wi-Fi 재전송.
- 로컬 QR 생성, 실제 장치 API를 사용하는 Python 시뮬레이터.

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
