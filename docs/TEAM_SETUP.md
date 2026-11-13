# 공동 개발자 실행 안내

기준일: **2026-11-13 (KST)**

버전: **spaces-v1**

개발 브랜치: **feature/outdoor-tmap-navigation**

## 1. 코드 받기

[개발 브랜치 ZIP 다운로드](https://github.com/useouseo/iot_project/archive/refs/heads/feature/outdoor-tmap-navigation.zip)를 받아 압축을 풉니다. Git을 사용하면 다음과 같이 받습니다.

```text
git clone --branch feature/outdoor-tmap-navigation https://github.com/useouseo/iot_project.git
```

`start_public_demo.bat`, `server.py`, `web` 폴더가 있는 곳이 실제 프로젝트 폴더입니다. 기본 브랜치의 예전 ZIP과 혼동하지 마세요.

## 2. 내 PC 준비

- Windows, **Python 3.12 64-bit**, **MariaDB Server**를 설치합니다.
- MariaDB 서비스를 실행합니다. 설치 때 정한 DB 계정 비밀번호를 확인해 둡니다.
- TMAP 앱 키는 **카톡방에서 별도 전달**받습니다. 저장소의 키 입력칸은 비워 둡니다.

## 3. TMAP 키 한 번 설정하기

프로젝트 폴더의 **start_with_tmap.bat**를 우클릭해 메모장으로 엽니다. 다음 두 줄의 `=` 뒤에 전달받은 키를 입력하고 저장합니다.

```bat
set "RESTFLOW_TMAP_MAP_KEY=전달받은_지도용_키"
set "RESTFLOW_TMAP_ROUTE_KEY=전달받은_보행자_API_키"
```

한 키에 지도와 보행자 API 권한이 모두 있으면 두 줄에 같은 키를 넣습니다. 이후에는 **start_with_tmap.bat 더블클릭**으로 실행하면 됩니다. 이 파일은 `start_public_demo.bat`와 같은 폴더에 둡니다.

이 실행 파일은 **시연 DB 모드**입니다. 실제 센서를 받을 때는 같은 키 환경에서 `start_public.bat`를 실행해야 합니다. 자세한 기기 설정은 [하드웨어 안내](HARDWARE.md)를 참고하세요.

## 4. 첫 실행의 DB 설정

본인 PC에 MariaDB를 기본 설정으로 설치한 경우의 예시입니다.

| 입력 항목 | 입력할 값 |
|---|---|
| DB 호스트 `[localhost]` | Enter |
| DB 포트 `[3306]` | Enter |
| DB 사용자 `[root]` | 별도 계정이 없으면 Enter |
| DB 비밀번호 | **본인 PC의 MariaDB 계정 비밀번호** |
| 실사용 DB `[restflow]` | Enter |
| 시연 DB `[restflow_demo]` | Enter |

DB 설정은 해당 폴더의 `db_config.json`에 저장됩니다. 그다음 관리자 비밀번호를 설정하라는 안내가 나오면 설정합니다. **DB 비밀번호와 웹 관리자 비밀번호는 서로 다른 것**입니다.

## 5. 화면 확인

1. 열린 관리자 화면에 로그인합니다.
2. 상단 **추가**를 눌러 공간 이름과 **실내 / 야외** 유형을 선택합니다.
3. **화장실·지도 관리**에서 화장실을 추가합니다.
4. 실내는 배치도를 올리고, 야외는 실제 지도에서 입구를 지정합니다. 둘 다 마커를 옮긴 뒤 지도 아래 **위치 저장**을 누릅니다.
5. 이름·칸 수는 오른쪽 **변경사항 저장**으로 따로 저장합니다.
6. **방문객 QR**에서 해당 공간의 QR을 생성해 휴대폰으로 접속합니다. 야외는 위치 권한을 허용하고 마커 선택 → 길찾기를 확인합니다.

시연 데이터와 실제 센서 데이터는 별도 DB입니다. 생성한 공간도 각각 독립 목록·지도·센서·QR을 사용합니다.


## 6. 실행을 유지하거나 종료하기

- QR 외부 접속 중에는 **PC·MariaDB·검은 실행 창·인터넷 연결을 유지**합니다.
- 종료는 `Ctrl+C`입니다. 종료해도 DB 데이터는 남습니다.
- Quick Tunnel 재실행으로 공개 주소가 바뀌면 **방문객 QR도 새로 생성**합니다.
- 이미 실행 중이면 기존 창을 종료한 뒤 다시 실행합니다.

## 7. 문제가 생기면

### Cloudflare 다운로드에서 진행되지 않음

[Windows 64-bit 공식 실행 파일](https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe)을 브라우저로 받아 `cloudflared.exe`로 이름을 바꾸고 프로젝트의 `.runtime` 폴더에 넣은 뒤 다시 실행합니다. **ARM64 PC는 해당 아키텍처의 파일**을 사용합니다.

### 예전 화면이 뜸

실행 창의 폴더를 확인하고 **server.py와 web을 같은 폴더에서 함께 업데이트**했는지 확인합니다. 재실행 후 브라우저에서 `Ctrl+Shift+R`을 누릅니다. 관리자 지도 아래 **화면·서버 버전: spaces-v1**이 표시돼야 합니다.

### 위치가 부정확함

PC 위치는 오차가 클 수 있습니다. 휴대폰에서 HTTPS 주소로 접속하고 위치 권한을 허용해 야외에서 확인합니다. `내 위치 확인`은 위치를 새로 요청합니다. 오차가 크면 지도에서 출발 위치를 확인한 뒤 계속할지 결정합니다.

## 8. 공유할 파일 / 공유하지 않을 파일

- **공유:** 소스 코드, 변경 문서, 키가 비어 있는 실행 파일.
- **키 전달:** 카톡방에서 별도 공유. 실제 키는 문서·커밋·PR에 적지 않습니다.
- **공유하지 않음:** 본인 DB 비밀번호가 든 `db_config.json`, 개인 키를 입력한 BAT, 장치 토큰·개인 비밀번호.

특히 **start_with_tmap.bat는 빈 양식이 Git에 등록된 파일**입니다. 키를 넣은 후에는 변경 파일로 표시되므로 `git add .`로 함께 커밋하지 마세요. 파일 업데이트 때도 본인 키를 덮어쓰지 않게 보존합니다.

전체 변경 내용: [CHANGES-2026-11-13.md](CHANGES-2026-11-13.md)
