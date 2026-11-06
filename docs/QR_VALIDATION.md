# QR 자동 연결 수정판 검증

- Python unittest: 44개 통과 (기존 41개 + 자동 QR 인증/주소 우선순위/로컬 주소 차단 3개).
- Python 구문 검사 및 JavaScript node --check 통과.
- 실행 도구 URL 추출, 초기 비밀번호 변경, 기존 비밀번호 보존 확인.
- Windows 실행, Cloudflare 실제 연결, 브라우저 PNG 다운로드, 실제 휴대폰 스캔은 이번 환경에서 미검증.
- 고정 공개 서버는 배포하지 않음. render.yaml과 안내만 포함.
- 기존 docs/VALIDATION.md는 이전 버전의 검증 기록임.
