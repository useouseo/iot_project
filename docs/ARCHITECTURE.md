> **정보/위치 저장 분리:** `PUT /api/toilet-info/{id}`는 이름·칸 수만, `PUT /api/layout-position/{id}`는 이미지 X/Y만 변경합니다. 둘 다 축제 소속을 검사합니다. 기존 전체 정보 PUT은 이전 클라이언트 호환용으로 유지합니다.

> **축제 삭제:** `festivals.active`를 0으로 바꾸는 보관 처리입니다. 관리자 전용 `DELETE /api/festivals/{id}`에 JSON `confirm_name`을 보내야 하고, 활성 축제를 잠가 마지막 축제 삭제를 막습니다. 삭제된 공개 주소/상태 API는 410, 장치 이벤트는 401로 응답합니다. 목록·인증·상태 자산은 1번 축제의 활성 여부와 무관하게 동작합니다.

> **축제별 운영:** `festivals(id,name,mode,public_id,map)`와 `toilets.festival_id`로 데이터를 구분합니다. 관리자 선택은 `/admin?festival_id=...`, 방문객은 `/f/{public_id}`에 고정됩니다. API는 `festival_id` 쿼리로 범위를 정하고 변경·조회 대상 화장실의 소속을 검증합니다. `FestivalScope`는 요청마다 만드는 뷰이며 공유 Store의 현재 축제를 변경하지 않습니다. 관리자 계정과 장치 인증은 공통이고, 센서 이벤트는 고유 장치 ID·토큰을 통해 연결된 화장실/축제로 귀속됩니다.
>
> `GET/POST /api/festivals`는 관리자 전용 목록/생성입니다. 유형은 생성 후 고정되고 기존 `/api/map-mode` 변경은 409를 반환합니다. 배치도는 축제별 `festivals.map`, 위도/경도와 이미지 X/Y는 해당 축제의 화장실에 저장됩니다. 기존 자료는 1번 ‘기존 축제’로 자동 이전되며 `/`는 이 축제로 계속 연결됩니다. [운영·마이그레이션·QR 안내](OUTDOOR.md)

# 시스템 설계와 API

현재 MariaDB·QR·배포 준비 버전의 구조입니다. 센서는 미도착이고 유료 서버는 미구매입니다. 실제 내부 인원·예상 대기시간은 제공하지 않습니다.

```mermaid
flowchart LR
  A[VL53L1X: A/B ROI 순차 측정] --> B[ATOM Lite: 방향 상태 전이]
  B --> C[NVS 재전송 대기열]
  C -->|Wi-Fi · HTTPS · 장치 토큰| D[Python HTTP API]
  D --> E[(MariaDB · InnoDB)]
  E --> F[최근 10분 혼잡도 계산]
  F --> G[방문객 지도 · 5초 폴링]
  E --> H[관리자: 설정·장치·통행 추이]
```

## 설정과 실행

| 항목 | 의미 |
|---|---|
| `db_config.json` / `RESTFLOW_DB_CONFIG` / `--db-config` | MariaDB 접속 설정 파일. Git 제외 |
| `RESTFLOW_DB_HOST`, `RESTFLOW_DB_PORT`, `RESTFLOW_DB_USER` | 접속 호스트·포트·사용자 |
| `RESTFLOW_DB_PASSWORD` / `RESTFLOW_DB_PASSWORD_FILE` | DB 비밀번호. FILE 지정이 우선 |
| `RESTFLOW_DB_DATABASE`, `RESTFLOW_DB_DEMO_DATABASE` | live/demo DB 이름 |
| `PUBLIC_URL` | 고정 서버의 방문객 HTTPS 주소. PC public 실행기는 임시 주소를 자동 연결 |
| `RESTFLOW_INITIAL_ADMIN_PASSWORD` / `RESTFLOW_INITIAL_ADMIN_PASSWORD_FILE` | 새 서버의 초기 관리자 비밀번호. 이미 변경한 비밀번호는 유지 |

PC는 `start_public_demo.bat`(가상) 또는 `start_public.bat`(실제 센서)를 사용합니다. 서버 구매 후에는 `deploy/`가 live 모드를 자동 실행합니다. `--demo`는 가상 데이터용 별도 DB를 선택하는 서버 옵션입니다. 두 DB는 직접 동기화되지 않습니다.

## 초기 혼잡도 모델

현재 10분 입장 I, 퇴장 O, 그 직전 10분 입장 P, 현재 운영 칸 수 S에 대해:

`score = (0.6×I + 0.4×max(0,I−O) + 0.2×max(0,I−P)) / S`

- score < 0.8: 여유, 0.8 이상 2 미만: 보통, 2 이상: 혼잡.
- 마지막 이벤트/heartbeat가 120초 초과거나 quality가 good이 아니면 확인 필요.
- 모든 계산은 `occurred_at` 기준이다. 재연결 때 늦게 도착한 10분 초과 이벤트는 현재 통행량에 더하지 않는다.
- 최근 구간만 사용하므로 하루 전체 누적 오차를 유지하지 않는다. 입·퇴장 차이는 내부 실제 인원이 아니다.
- 임계값·가중치는 **검증 전 초기 가설**이다. 실측 대기열 라벨과 비교해 교정해야 한다. 최근 기록 만료나 통신 단절로 단계가 바뀔 수 있다. 장기간 머무르는 이용자의 체류는 이 모델로 직접 알 수 없다.
- 관리자 초기화는 `reset_at` 이후 기록만 현재 계산에 반영한다. 원본 이벤트·통행 추이는 보존한다.

## DB

| 테이블 | 핵심 내용 |
|---|---|
| toilets | 이름, 운영 칸 수, 지도 좌표(%), 예외 초기화 시각 |
| devices | 장치 ID, 화장실 FK(1:1), 토큰 SHA-256, 마지막 수신, 품질 |
| sessions | 장치+부팅 ID의 마지막 순번 |
| events | 장치+부팅 ID+순번 UNIQUE, 방향, 발생/수신 시각 |
| settings | 업로드 지도(data URI), 호환용 수동 방문객 URL |
| admin_credentials | 관리자 비밀번호 salt·PBKDF2 해시 |
| admin_sessions | 관리자 세션 토큰 해시·만료 시각 |
| audit | 장치 등록·계산 초기화 이력 |

한 HTTP 요청마다 MariaDB 연결과 트랜잭션을 열고 성공 시 commit, 오류 시 rollback한 뒤 cursor와 connection을 닫는다. 이벤트 수신은 장치 행을 `FOR UPDATE`로 잠가 같은 장치의 동시 요청을 직렬화하고 `(device_id, boot_id, seq)` UNIQUE 키로 중복 저장을 방지한다. 동일 이벤트 키의 동일 내용은 200/duplicate로 응답한다. 키가 같고 내용이 다르면 409, 새 키의 순번 역전도 409. 부팅 ID가 달라지면 순번 1부터 가능하며 이전 부팅 대기열도 재전송할 수 있다. 장치 시계는 UTC Unix 초, 30초 초과 미래/24시간 초과 과거는 400. 원본 이벤트 자동 삭제 정책은 현재 없으므로 긴 행사 운영 시 보관·백업 정책을 설정한다.

## HTTP API

모든 요청 본문은 JSON. 관리자는 POST /api/login 비밀번호 인증 후 HttpOnly·SameSite=Strict 쿠키로 세션을 유지하고, 장치만 `Authorization: Bearer <token>`을 사용한다. 방문객 API는 공개 읽기이며 방문객 화면에는 관리자 링크가 없다. 관리자는 /admin에 직접 접속한다. 토큰은 URL에 넣지 않는다.

| 메서드 / 경로 | 인증 | 기능 |
|---|---|---|
| GET /api/health | 없음 | HTTP·DB 가용성 |
| GET /api/status | 없음 | 지도, 시설, 단계, 연결, 갱신시각, demo 플래그 |
| POST /api/qr | 관리자 | 공개 주소 자동 선택, url과 SVG 반환. 현재 QR 버튼 사용 경로 |
| GET /api/qr.svg | 없음 | 저장된 방문객 주소(없으면 PUBLIC_URL)의 QR SVG를 로컬 생성. 미설정 409 |
| POST /api/login | 없음 | password: 8시간 관리자 쿠키 세션 발급. 공개 실행/배포에서 초기 비밀번호 변경 |
| POST /api/logout | 관리자 | 현재 세션 만료 |
| PUT /api/password | 관리자 | current_password, new_password(4~128자). 변경 후 다른 세션 만료 |
| POST /api/toilets | 관리자 | name, stalls, 선택적 x/y. 개수 고정 없이 추가 |
| DELETE /api/toilets/1 | 관리자 | 비활성화해 목록에서 제거·장치 수신 중지. 원본 기록 보존 |
| GET /api/admin | 관리자 | 장치 목록(토큰 제외), visitor_url·automatic_visitor_url |
| GET /api/history?toilet_id=1 | 관리자 | 최근 2시간 입·퇴장 통행량, 10분 단위 12구간 |
| PUT /api/toilets/1 | 관리자 | name, stalls(1~100), x/y(3~97 정수 %) |
| PUT /api/visitor-url | 관리자 | url: http(s) 방문객 주소 저장, URL 내 사용자명·비밀번호 거부 |
| PUT /api/map | 관리자 | image: 최대 2MB PNG/JPEG data URI. SVG 거부 |
| POST /api/devices | 관리자 | id, toilet_id로 등록, token을 한 번 반환 |
| POST /api/reset | 관리자 | toilet_id의 혼잡도 계산 구간 초기화 |
| POST /api/demo | 관리자 | --demo일 때만 가상 기록 추가 |
| POST /api/events | 장치 | 통과 이벤트 저장 |
| POST /api/heartbeat | 장치 | device_id, quality(good/degraded/fault) |

```json
{
  "device_id": "atom-entrance-a",
  "boot_id": "a-new-random-id-per-boot",
  "seq": 1,
  "direction": "in",
  "occurred_at": 1793865600,
  "quality": "good"
}
```

위 시각은 형식 설명용으로 실행할 때는 현재 UTC Unix 초를 사용한다. 배터리 %는 측정원이 없으므로 계약에 포함하지 않는다. 시뮬레이터는 동일 API와 파일 대기열을 사용한다. 관리자 비밀번호는 별도 admin_credentials 테이블에 salt와 PBKDF2-SHA256(200,000회) 해시로 저장한다. admin_sessions에는 무작위 세션 토큰의 SHA-256과 만료 시각만 보관한다. 공개 settings 응답에는 인증 정보를 포함하지 않는다. 세션은 새로고침 후에도 유지되고 로그아웃·비밀번호 변경·만료 시 폐기된다. 장치 토큰은 원문을 DB에 저장하지 않는다.

## 실행 범위

현재는 소규모 시제품용 단일 프로세스 Python ThreadingHTTPServer와 별도 MariaDB 서버 구조다. 실사용과 시연은 각각 `database`, `demo_database`로 분리한다. PC 시연은 Quick Tunnel로 HTTPS를 연결한다. 고정 서버용 deploy/에는 Caddy HTTPS와 DB 백업·복원을 준비했으며 실제 적용은 서버 구매 후 확인한다. 장기간/대규모 운영의 요청 제한·관리자 계정 확장·로그인 시도 제한·모니터링·이벤트 보관 정책은 별도 검토 사항이다. 역사적 혼잡 단계 스냅샷·설정 변경 이력 전체는 구현하지 않았고 현재 추이 화면은 **원본 통행량**이다. 실사용 초기 예시 시설은 두 곳이지만 추가·삭제로 개수를 자유롭게 바꿀 수 있다. 삭제는 active=0으로 보관해 이벤트 FK를 유지하며 해당 장치의 인증을 거부한다.

관리자 지도는 Pointer Events로 마우스/터치 드래그와 취소를 지원하고, 이동 초안은 저장 전까지 클라이언트에 유지한다. 좌표는 기존과 동일한 3~97% 정수 범위다. 방문객에게는 서버에 저장된 좌표만 제공한다. QR의 SVG는 서버에서 생성하고, PNG는 브라우저에서 흰 배경의 1024×1024 이미지로 변환해 다운로드한다. 이미지 파일을 서버 디스크에 쓰지 않는다.


## MariaDB QR 자동 연결 변경

- `POST /api/qr`: 관리자 세션 필요. 서버 public_url을 우선 사용해 SVG와 URL을 반환합니다. 없으면 브라우저 origin을 사용하되 로컬/사설 IP를 거부합니다. 기존 GET QR/수동 URL 저장 API는 호환성을 위해 유지합니다.
- `GET /api/admin`: `automatic_visitor_url`을 추가합니다.
- `tools/public_start.py`: MariaDB 설정을 재사용하고 기본 live Store를 만든 뒤 초기 관리자 비밀번호를 변경하고 서버를 바인딩합니다. Quick Tunnel URL을 받으면 server.public_url을 설정합니다. 종료 시 터널과 HTTP 서버를 닫으며 DB 데이터는 삭제하지 않습니다.
- `start_public_demo.bat`는 동일 실행기에 --demo를 전달합니다.


## 유료 서버 구매 전 배포 준비

- deploy/compose.yaml: MariaDB 11.4 + non-root Python 앱 + Caddy HTTPS, 영구 DB/인증서 볼륨, 자동 재시작 및 상태 검사. DB/앱 포트는 호스트에 게시하지 않습니다.
- RESTFLOW_DB_PASSWORD_FILE은 DB 비밀번호의 파일 입력을 지원하며 일반 환경변수보다 우선합니다.
- RESTFLOW_INITIAL_ADMIN_PASSWORD(_FILE)는 기본 비밀번호일 때만 최초 비밀번호를 적용합니다. 이미 변경한 비밀번호는 유지합니다.
- deploy/configure.py는 도메인·이메일과 비밀 파일을 생성하며 기존 비밀값을 보존합니다. deploy/install.sh는 실제 구매한 Ubuntu 24.04 서버의 /opt/restflow에서만 실행합니다.
- 백업은 한국 시간 03:00 로컬 SQL 압축 파일로 저장하며, 명시적 --confirm-replace 옵션으로 복원합니다. 자세한 단계와 미검증 범위는 docs/배포준비.md에 있습니다.
