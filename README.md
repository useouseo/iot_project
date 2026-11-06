# RestFlow · MariaDB 기반 화장실 혼잡 안내

ATOM Lite + VL53L1X → HTTPS 이벤트 수신 → MariaDB → 방문객 지도·관리자 화면으로 구성된 IoT 시제품입니다. 최근 10분 통행량으로 혼잡 단계를 추정하며, 정확한 내부 인원수나 대기시간을 표시하지 않습니다.

**최종 준비본 · 2026-11-06**

- **센서 2대는 아직 미도착**: 실제 기기 연결·정확도 시험은 남아 있습니다.
- **유료 서버는 아직 미구매**: 배포용 설정을 준비했으며 실제 구매·배포는 하지 않았습니다.
- **PC에서 휴대폰 QR 외부 접속은 확인**했습니다.
- 이 기본 브랜치가 최신 준비본입니다. [ZIP 다운로드](https://github.com/useouseo/iot_project/archive/refs/heads/codex-mariadb-public-qr-20261106.zip)

## 지금 실행하는 방법

Windows에 **Python 3.12 64-bit와 MariaDB Server**가 필요합니다. MariaDB 서비스를 실행한 뒤 압축을 푼 폴더에서 아래 파일을 더블클릭합니다. CMD에 Python 명령어를 직접 입력할 필요는 없습니다.

| 실행 파일 | 사용할 때 | DB 기본 이름 |
|---|---|---|
| **`start_public_demo.bat`** | **지금: 센서 없이 가상 데이터로 QR 시연** | `restflow_demo` |
| **`start_public.bat`** | **센서 도착 후: PC에서 실제 장치 데이터 수신 + QR 접속** | `restflow` |

1. 첫 실행이면 MariaDB 접속정보를 입력합니다. 기존 `db_config.json`은 그대로 사용합니다.
2. 관리자 비밀번호가 초기값이면 새 비밀번호(8~128자)를 설정합니다. 입력 중 글자는 표시되지 않습니다.
3. 자동으로 열린 관리자 화면에 로그인하고 **QR 생성**을 누릅니다. 주소를 직접 입력하지 않습니다.
4. QR을 PNG/SVG로 저장하거나 휴대폰으로 스캔합니다. 다른 Wi-Fi·LTE·5G에서도 접속할 수 있습니다.

두 모드의 시설·장치·기록·관리자 비밀번호는 분리돼 있습니다. 가상 데이터가 실제 센서 기록에 섞이지 않습니다. 센서를 연결하지 않은 live 화면의 ‘확인 필요’ 표시는 정상입니다.

### 처음 나오는 DB 입력값

같은 PC에 기본 설정으로 MariaDB를 설치했다면 다음과 같습니다.

| 질문 | 입력 |
|---|---|
| DB 호스트 `[localhost]` | Enter |
| DB 포트 `[3306]` | Enter |
| DB 사용자 `[root]` | 별도 계정이 없다면 Enter |
| DB 비밀번호 | MariaDB 설치 때 정한 DB 계정 비밀번호 |
| 실사용 DB `[restflow]` / 시연 DB `[restflow_demo]` | Enter |

**DB 비밀번호와 웹 관리자 비밀번호는 서로 다릅니다.** `db_config.json`에는 DB 접속정보가 있으므로 공유하거나 GitHub에 올리지 않습니다.

### PC 공개 접속을 유지하려면

- PC·MariaDB·검은 실행 창·인터넷 연결을 유지합니다. PC 절전 모드를 피합니다.
- 종료는 `Ctrl+C`입니다. 실행을 종료해도 MariaDB 데이터는 유지됩니다.
- 다시 실행하면 임시 공개 주소가 바뀌므로 **QR을 새로 생성**해야 합니다.
- 실제 기기도 임시 공개 주소를 사용한다면 **기기의 `API_BASE`도 갱신·재업로드**해야 합니다.
- Quick Tunnel은 시험용입니다. 같은 주소를 계속 쓰는 서버 배포와는 구분합니다.

포트가 사용 중이면 기존 실행 창을 종료하거나 CMD에서 `start_public_demo.bat --port 8001` / `start_public.bat --port 8001`을 실행합니다. DB 설정을 다시 입력하려면 `.venv\Scripts\python.exe setup_mariadb.py`를 실행합니다.

## 센서가 도착하면

1. `start_public.bat`를 실행합니다.
2. 관리자에서 화장실별로 서로 다른 장치 ID를 등록하고 각각의 토큰을 보관합니다.
3. `firmware/include/secrets.example.h`를 `secrets.h`로 복사해 Wi-Fi, 공개 HTTPS `API_BASE`, 장치별 ID·토큰, 서버 인증서를 검증할 `ROOT_CA`를 설정합니다.
4. 각 기기에 펌웨어를 빌드·업로드하고 수신·방향·설치 위치를 검증합니다.

실행 파일만 누른다고 기기 설정이나 펌웨어 업로드가 자동으로 되지는 않습니다. [하드웨어 안내](docs/HARDWARE.md)와 [실물 검증 항목](docs/VALIDATION.md)을 확인하세요.

## 서버를 구매하면

`deploy/`에 **Ubuntu 24.04 VPS 한 대**용 설치·실행·HTTPS·DB 영구 저장·자동 재시작·매일 백업·복원 구성을 준비했습니다. 지금 실행할 필요는 없습니다.

서버를 구매한 뒤에는 소스를 `/opt/restflow`에 놓고 실제 도메인·이메일·관리자 비밀번호를 설정해 적용합니다. 서버에서는 Windows BAT 대신 Docker Compose가 실제 센서 모드로 실행됩니다. PC DB는 자동 이전되지 않으므로 필요하면 백업·복원합니다.

**[서버 구매 후 적용 안내](docs/배포준비.md)**에 설치 순서와 확인 명령을 정리했습니다. 고정 주소를 유지하면 서버 재시작 후에도 기존 QR을 계속 사용할 수 있습니다.

## 기능과 검증

- 방문객 지도·시설 선택·혼잡 단계·수신 상태, 5초 갱신.
- 관리자 로그인·비밀번호 변경, 시설 추가·삭제, 지도 업로드·위치 편집, 장치 등록, 통행 추이.
- 장치별 토큰, 부팅 ID+순번 중복 방지, 발생시각 검증, MariaDB 영구 저장.
- QR 공개 주소 자동 연결, PNG/SVG 다운로드, live/demo DB 분리.
- Python 테스트 **52개**, 컨테이너 HTTPS·재시작 후 데이터 보존·SQL 백업/복원 검증 완료. 실제 센서와 구매한 VPS 검증은 별도입니다.

[현재 검증 기록](docs/VALIDATION.md) · [QR·배포 검증 상세](docs/QR_VALIDATION.md) · [시연 순서](docs/DEMO.md) · [API·구조](docs/ARCHITECTURE.md)

개발 검사는 MariaDB 및 시험 DB 생성·삭제 권한이 있는 환경에서 실행합니다. 실사용 DB와 분리된 `_test`, `_launcher_test` DB를 사용합니다.

```text
python -m unittest discover -s tests -v
node --check web/app.js
```

환경변수 또는 `RESTFLOW_DB_CONFIG`으로 DB 설정을 지정할 수 있습니다. 배포에서는 비밀번호를 파일로 전달하며 기존에 변경한 관리자 비밀번호를 덮어쓰지 않습니다. 상세 설정은 [구조 문서](docs/ARCHITECTURE.md)에 있습니다. GitHub Actions에서도 동일한 Python 검사와 JS/Shell/C++ 검사를 실행합니다.
