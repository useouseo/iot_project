# 시스템 설계와 API

이미지는 외관 참고이고 최종 요구사항은 PDF의 마지막 선정 주제와 오차 대응 방식으로 해석했다. 정확한 내부 인원·예상 대기시간은 제공하지 않는다. 문서에 적힌 팀원에게 메시지나 업무 배정을 전송하지 않았다.

```mermaid
flowchart LR
  A[VL53L1X: A/B ROI 순차 측정] --> B[ATOM Lite: 방향 상태 전이]
  B --> C[NVS 재전송 대기열]
  C -->|Wi-Fi · HTTPS · 장치 토큰| D[Python HTTP API]
  D --> E[(SQLite WAL)]
  E --> F[최근 10분 혼잡도 계산]
  F --> G[방문객 지도 · 5초 폴링]
  E --> H[관리자: 설정·장치·통행 추이]
```

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
| settings | 업로드 지도(data URI) |
| audit | 장치 등록·계산 초기화 이력 |

한 HTTP 요청당 DB 연결, WAL, 이벤트 쓰기에 BEGIN IMMEDIATE. 동일 이벤트 키의 동일 내용은 200/duplicate로 응답한다. 키가 같고 내용이 다르면 409, 새 키의 순번 역전도 409. 부팅 ID가 달라지면 순번 1부터 가능하며 이전 부팅 대기열도 재전송할 수 있다. 장치 시계는 UTC Unix 초, 30초 초과 미래/24시간 초과 과거는 400. 원본 이벤트 자동 삭제 정책은 현재 없으므로 긴 행사 운영 시 보관·백업 정책을 설정한다.

## HTTP API

모든 요청 본문은 JSON. 관리자/장치 인증은 각각 `Authorization: Bearer <token>`. 방문객 API는 공개 읽기다. 토큰은 URL에 넣지 않는다.

| 메서드 / 경로 | 인증 | 기능 |
|---|---|---|
| GET /api/health | 없음 | HTTP·DB 가용성 |
| GET /api/status | 없음 | 지도, 시설, 단계, 연결, 갱신시각, demo 플래그 |
| GET /api/qr.svg | 없음 | 저장된 방문객 주소(없으면 PUBLIC_URL)의 QR SVG를 로컬 생성. 미설정 409 |
| GET /api/admin | 관리자 | 장치 목록(토큰 제외) |
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

위 시각은 형식 설명용으로 실행할 때는 현재 UTC Unix 초를 사용한다. 배터리 %는 측정원이 없으므로 계약에 포함하지 않는다. 시뮬레이터는 동일 API와 파일 대기열을 사용한다. 관리자 토큰은 브라우저 메모리에만 보관하며 새로고침 시 재로그인한다. 장치 토큰은 원문을 DB에 저장하지 않는다.

## 실행 범위

현재는 소규모 시제품용 단일 프로세스 Python ThreadingHTTPServer+SQLite다. 실제 행사 공개 운영 전 HTTPS 종단, 요청 제한, 관리자 계정·토큰 회수/교체, 모니터링·DB 백업, 운영 로그·보관 정책을 별도 배치한다. 역사적 혼잡 단계 스냅샷·설정 변경 이력 전체는 구현하지 않았고 현재 추이 화면은 **원본 통행량**이다. 화장실 두 곳이 기본이며 설정 화면에서 이름/칸 수/위치/장치 등록을 지원한다. 동적 시설 추가·삭제는 현재 범위 밖이다.

관리자 지도는 Pointer Events로 마우스/터치 드래그와 취소를 지원하고, 이동 초안은 저장 전까지 클라이언트에 유지한다. 좌표는 기존과 동일한 3~97% 정수 범위다. 방문객에게는 서버에 저장된 좌표만 제공한다. QR의 SVG는 서버에서 생성하고, PNG는 브라우저에서 흰 배경의 1024×1024 이미지로 변환해 다운로드한다. 이미지 파일을 서버 디스크에 쓰지 않는다.
