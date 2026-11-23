# Raspberry Pi 팬 제어

GPIO18의 3.3V PWM 신호로 XY-MOS 트리거 입력을 제어합니다. 팬 전원은 GPIO가 아니라 별도의 정격 5V 전원에서 공급하고, Raspberry Pi GND와 MOSFET 신호 GND를 공통으로 연결합니다. 제품 기판의 실제 VIN, VOUT, TRIG/PWM, GND 표기를 확인한 뒤 결선하세요.

## 시험

하드웨어 없이 API 통신만 시험합니다.

```bash
python3 fan_controller.py --server https://도메인 --device-id atom-entrance-a --token 발급토큰 --dry-run
```

실물 연결 후 `--dry-run`을 제거합니다. 서버가 30초 이상 응답하지 않으면 기본적으로 60% 안전 출력으로 전환하며, 정상 명령이 돌아오면 자동 복구합니다.

## 자동 실행

1. 이 폴더를 `/opt/restflow/raspberry_pi`에 복사합니다.
2. `restflow-fan.env.example`을 `/etc/restflow-fan.env`로 복사하고 실제 주소·ID·토큰을 입력합니다.
3. `sudo apt install python3-rpi.gpio`를 실행합니다.
4. 서비스 파일을 `/etc/systemd/system/restflow-fan.service`로 복사합니다.
5. `sudo systemctl daemon-reload && sudo systemctl enable --now restflow-fan`을 실행합니다.

팬이 저출력에서 기동하지 않으면 제어기가 0%에서 운전 상태로 바뀔 때 0.5초간 100% 기동 출력을 적용합니다. 실제 팬의 극성, 기동전류, 최소 회전 출력을 반드시 확인하세요.
