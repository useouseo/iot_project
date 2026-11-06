# RestFlow v3 · MariaDB 기반 탈부착형 화장실 혼잡 안내 IoT

ATOM Lite + VL53L1X가 입·퇴장 이벤트를 Wi-Fi로 전송하고, Python 서버가 MariaDB에 저장한 뒤 최근 10분 통행량 기반 혼잡도를 방문객 지도와 관리자 화면에 표시하는 시제품입니다. 정확한 내부 인원수나 대기시간을 주장하지 않습니다.

## v3 변경 사항

- 기존 SQLite 저장 계층을 공식 `mariadb` Python 커넥터와 MariaDB 서버로 완전히 교체했습니다.
- 강의안/WEEK6 예제와 같은 `mariadb.connect(...)`, `cursor(dictionary=True)`, `?` 파라미터 바인딩 구조를 사용합니다.
- 연결마다 commit/rollback과 cursor/connection close를 보장합니다.
- 실사용 DB와 시연 DB를 각각 `restflow`, `restflow_demo`로 분리합니다.
- 접속정보는 소스가 아니라 `db_config.json` 또는 환경변수로 관리합니다.
- 웹 화면, API, 혼잡도 계산, 관리자 로그인, ESP32 이벤트 형식은 v2와 동일합니다.

## 준비 사항

- Python 3.12 이상
- MariaDB Server가 설치되고 서비스가 실행 중이어야 함
- DB를 만들 수 있는 MariaDB 계정 또는 미리 생성된 `restflow`, `restflow_demo` DB에 권한이 있는 계정

## Windows 빠른 실행 — QR 자동 연결

1. PC의 MariaDB 서비스를 실행합니다. Python 3.12 64-bit와 인터넷 연결이 필요합니다.
2. **`start_public.bat`를 더블클릭합니다.** 기본은 실제 센서 모드입니다.
3. 설정 파일이 없으면 MariaDB 접속정보를 입력합니다. 기존 `db_config.json`은 그대로 사용합니다.
4. 초기 관리자 비밀번호를 사용 중이면 새 비밀번호(8~128자)를 설정합니다. 입력 중 글자는 보이지 않습니다.
5. 자동으로 열린 관리자 화면에서 로그인하고 **QR 생성**만 누릅니다. 공개 주소가 자동으로 연결됩니다.
6. 방문객은 생성된 QR로 다른 Wi-Fi·LTE·5G에서도 접속할 수 있습니다.

**PC·MariaDB·검은 실행 창을 유지하세요.** 종료는 Ctrl+C입니다. 재실행하면 주소가 바뀌므로 QR도 다시 생성해야 합니다. MariaDB 데이터와 이미 변경한 비밀번호는 보존됩니다. Quick Tunnel은 시험용이며 고정 주소와 가용성을 보장하지 않습니다.

| 실행 파일 | 용도 | 데이터베이스 |
|---|---|---|
| `start_public.bat` | 실제 기기 연결 + 외부 QR 접속 | `database` (기본 `restflow`) |
| `start_public_demo.bat` | 가상 데이터 + 외부 QR 접속 | `demo_database` (기본 `restflow_demo`) |
| `start_demo.bat` | 기존 PC 로컬 가상 데이터 시연 | `demo_database` |

상세 절차와 문제 해결은 [QR 시작 안내](QR_시작안내.txt)를 확인하세요.

관리자 주소 필드는 읽기 전용입니다. `POST /api/qr`는 서버의 공개 주소를 우선 사용하며 QR SVG와 목적지를 함께 반환합니다. 이전에 저장된 수동 URL은 새 QR 버튼에 영향을 주지 않습니다. 외부용 QR에 localhost/사설 IP를 넣으려 하면 안내를 표시합니다. PNG/SVG 다운로드 기능은 유지합니다.

`db_config.json`에는 DB 비밀번호가 들어갈 수 있습니다. Git/메신저에 공유하지 마십시오. `.gitignore`에서 제외합니다.

## 수동 실행

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_mariadb.py
.\.venv\Scripts\python.exe server.py --demo
```

DB 설정을 다시 하려면 서버를 종료한 뒤 다음을 실행합니다.

```powershell
.\.venv\Scripts\python.exe setup_mariadb.py
```

8000번 포트가 사용 중이면:

```powershell
.\.venv\Scripts\python.exe server.py --demo --port 8001
```

같은 Wi-Fi의 휴대폰에서 접속하려면:

```powershell
.\.venv\Scripts\python.exe server.py --demo --host 0.0.0.0
```

`ipconfig`에서 확인한 PC IPv4 주소로 `http://PC_IP:8000`에 접속하고 Windows 방화벽은 사설 네트워크만 허용합니다.

## DB 계정에 생성 권한이 없는 경우

MariaDB 관리자 계정으로 아래와 같이 DB와 전용 사용자를 먼저 만들 수 있습니다. 비밀번호는 반드시 변경하십시오.

```sql
CREATE DATABASE restflow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE restflow_demo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'restflow_app'@'localhost' IDENTIFIED BY 'change-this-password';
GRANT ALL PRIVILEGES ON restflow.* TO 'restflow_app'@'localhost';
GRANT ALL PRIVILEGES ON restflow_demo.* TO 'restflow_app'@'localhost';
FLUSH PRIVILEGES;
```

그 다음 `setup_mariadb.py`에서 `restflow_app` 계정을 입력합니다.

## 환경변수 방식

`db_config.json` 대신 다음 환경변수를 모두 설정할 수 있습니다.

- `RESTFLOW_DB_HOST`
- `RESTFLOW_DB_PORT`
- `RESTFLOW_DB_USER`
- `RESTFLOW_DB_PASSWORD`
- `RESTFLOW_DB_DATABASE`
- `RESTFLOW_DB_DEMO_DATABASE`

`RESTFLOW_DB_CONFIG`으로 다른 JSON 설정 파일 경로를 지정할 수도 있습니다.

## 시연 모드와 실제 센서 모드

- `server.py --demo`: `demo_database`를 사용하고 세 가상 화장실과 시연 통행 이벤트를 제공합니다.
- `server.py`: `database`를 사용하며 관리자 화면에서 실제 장치를 등록해야 합니다.

실제 장치 연결 절차:

1. 관리자 화면에서 화장실별 장치 ID를 등록하고 한 번 표시되는 토큰을 보관합니다.
2. `firmware/include/secrets.example.h`를 `secrets.h`로 복사합니다.
3. Wi-Fi, HTTPS API 주소, 장치 ID, 장치 토큰, 인증서 정보를 입력합니다.
4. PlatformIO로 펌웨어를 빌드하고 ATOM Lite에 업로드합니다.

임시 public 실행은 매번 주소가 바뀝니다. 재실행 후에는 기기의 `API_BASE`도 새 주소로 바꾸고 다시 업로드해야 합니다. QR 기능은 기기의 Wi-Fi·토큰·인증서를 자동 설정하지 않습니다.

ESP32 전체 빌드와 실물 센서 정확도·배터리 시간·현장 Wi-Fi는 아직 검증되지 않았습니다.

## MariaDB 테이블

- `toilets`: 화장실 이름, 운영 칸 수, 지도 위치, 활성 상태
- `devices`: 장치 ID, 화장실 연결, 토큰 해시, 마지막 수신, 품질
- `sessions`: 장치 부팅 ID별 마지막 순번
- `events`: 입·퇴장 방향, 발생·수신 시각, 중복방지 키
- `settings`: 지도와 방문자 URL
- `audit`: 장치 등록과 관리 이력
- `admin_credentials`: 관리자 비밀번호 salt/hash
- `admin_sessions`: 관리자 로그인 세션

## 검증

MariaDB 서비스와 `db_config.json`이 준비된 상태에서:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

테스트는 실사용 DB와 분리된 `_test` 및 `_launcher_test` DB를 만들고 종료 시 삭제합니다. DB 생성/삭제 권한이 필요합니다. 첨부 원본의 검증 기록은 MariaDB 12.0.2 기준입니다. 이번 QR 변경의 검증 범위는 [QR 검증 기록](docs/QR_VALIDATION.md)에 별도로 기록합니다.

## 운영 주의

현재 서버는 소규모 수업 시제품입니다. 외부 공개 운영 전에는 HTTPS 프록시, 로그인 시도 제한, DB 백업, 이벤트 보관 정책, 모니터링을 추가해야 합니다. MariaDB 접속 포트를 인터넷에 직접 공개하지 마십시오.
