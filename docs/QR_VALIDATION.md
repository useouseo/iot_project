# MariaDB + QR 자동 연결 검증 (2026-11-06)

- 첨부된 RestFlow_v3_MariaDB.zip을 기준으로 수정했습니다. MariaDB 커넥터와 저장 계층을 유지합니다.
- MariaDB 11.4.13, Python 3.12, mariadb==1.1.14, qrcode==8.2에서 Python 테스트 47개 통과.
- 실제 MariaDB에 연결한 HTTP API 테스트: 관리자 인증, 서버 공개 URL 우선 사용, 로컬 주소 차단, 기존 QR/센서/시설/비밀번호 기능.
- 공개 실행기의 live/demo 선택, 기존 비밀번호 보존, 자동 공개 URL QR 생성, Ctrl+C 시 HTTP 서버와 터널 프로세스 정리를 검증했습니다. 이 실행기 시험은 실제 MariaDB/HTTP를 사용하고 Windows 및 Cloudflare 프로세스만 모의 처리합니다.
- JavaScript node --check 및 변경 Python 파일 구문 검사 통과.
- Windows BAT/실제 cloudflared 연결/실제 휴대폰 스캔/ESP32 기기 2대 실물 연결/브라우저 PNG 다운로드는 이번 환경에서 미검증입니다.
- 유료 서버 구매/배포는 수행하지 않았습니다.
- 테스트 DB는 실사용 DB와 분리한 _test 및 _launcher_test 이름을 사용하며 종료 시 삭제합니다. DB 생성/삭제 권한이 필요합니다.
- docs/VALIDATION.md 및 기존 스크린샷은 첨부 원본의 이전 검증 자료입니다.
