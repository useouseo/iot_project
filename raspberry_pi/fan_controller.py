#!/usr/bin/env python3
"""RestFlow Raspberry Pi fan controller (GPIO18 -> XY-MOS trigger input)."""
import argparse
import json
import os
import signal
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class FanOutput:
    def __init__(self, gpio, frequency, dry_run=False):
        self.gpio,self.frequency,self.dry_run=gpio,frequency,dry_run
        self.current=0
        self.gpio_module=None
        self.pwm=None
        if not dry_run:
            try:
                import RPi.GPIO as GPIO
            except ImportError as error:
                raise SystemExit('RPi.GPIO가 없습니다. Raspberry Pi에서 sudo apt install python3-rpi.gpio를 실행하세요.') from error
            self.gpio_module=GPIO
            GPIO.setwarnings(False);GPIO.setmode(GPIO.BCM);GPIO.setup(gpio,GPIO.OUT,initial=GPIO.LOW)
            self.pwm=GPIO.PWM(gpio,frequency);self.pwm.start(0)

    def set(self,percent,kickstart_ms=0):
        percent=max(0,min(100,int(percent)))
        if percent>0 and self.current==0 and percent<100 and kickstart_ms>0:
            self._write(100);time.sleep(kickstart_ms/1000)
        self._write(percent);self.current=percent

    def _write(self,percent):
        if self.dry_run:
            print(f'[DRY-RUN] GPIO{self.gpio} {self.frequency}Hz PWM={percent}%',flush=True)
        else:
            self.pwm.ChangeDutyCycle(percent)

    def close(self):
        try:self.set(0)
        finally:
            if self.pwm:self.pwm.stop()
            if self.gpio_module:self.gpio_module.cleanup(self.gpio)


def request_json(base,path,token,method='GET',body=None,timeout=8):
    url=base.rstrip('/')+path
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
    headers={'Accept':'application/json','Authorization':'Bearer '+token}
    if data is not None:headers['Content-Type']='application/json'
    request=Request(url,data=data,headers=headers,method=method)
    context=ssl.create_default_context()
    try:
        with urlopen(request,timeout=timeout,context=context) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        try:message=json.loads(error.read().decode('utf-8')).get('error')
        except Exception:message=None
        raise RuntimeError(message or f'HTTP {error.code}') from error
    except (URLError,TimeoutError,json.JSONDecodeError) as error:
        raise RuntimeError(str(error)) from error


def configuration():
    parser=argparse.ArgumentParser()
    parser.add_argument('--server',default=os.environ.get('RESTFLOW_SERVER_URL',''))
    parser.add_argument('--device-id',default=os.environ.get('RESTFLOW_DEVICE_ID',''))
    parser.add_argument('--token',default=os.environ.get('RESTFLOW_DEVICE_TOKEN',''))
    parser.add_argument('--gpio',type=int,default=18)
    parser.add_argument('--frequency',type=int,default=1000)
    parser.add_argument('--interval',type=float,default=5)
    parser.add_argument('--fail-safe-percent',type=int,default=60)
    parser.add_argument('--fail-safe-after',type=int,default=30)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if not args.server or not args.device_id or not args.token:
        parser.error('--server, --device-id, --token 또는 대응 환경변수가 필요합니다')
    parsed=urlparse(args.server)
    if parsed.scheme!='https' and parsed.hostname not in ('127.0.0.1','localhost'):
        parser.error('운영 서버는 HTTPS 주소를 사용하세요')
    if not 0<=args.fail_safe_percent<=100 or args.interval<1 or args.fail_safe_after<1:
        parser.error('팬 출력은 0~100, 주기는 1초 이상이어야 합니다')
    return args


def main():
    args=configuration()
    fan=FanOutput(args.gpio,args.frequency,args.dry_run)
    running=True;last_success=0.0;last_mode='startup';last_error=''

    def stop(*_):
        nonlocal running
        running=False
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    try:
        while running:
            started=time.monotonic();ok=False
            try:
                query=urlencode({'device_id':args.device_id})
                command=request_json(args.server,'/api/fan-command?'+query,args.token)
                target=int(command['pwm_percent'])
                frequency=int(command.get('pwm_frequency_hz',args.frequency))
                if frequency!=args.frequency:
                    raise RuntimeError(f'서버 PWM {frequency}Hz와 로컬 설정 {args.frequency}Hz가 다릅니다')
                fan.set(target,int(command.get('kickstart_ms',0)))
                last_mode=str(command.get('mode','automatic'));last_success=time.monotonic();last_error='';ok=True
                print(f"fan={fan.current}% mode={last_mode} reason={command.get('reason','')}",flush=True)
            except Exception as error:
                last_error=str(error)
                if not last_success or time.monotonic()-last_success>=args.fail_safe_after:
                    fan.set(args.fail_safe_percent)
                    last_mode='fail_safe'
                print(f'control error: {last_error}; fan={fan.current}%',file=sys.stderr,flush=True)
            try:
                request_json(args.server,'/api/fan-status',args.token,'POST',{
                    'device_id':args.device_id,'applied_percent':fan.current,'mode':last_mode,
                    'ok':ok,'error_message':last_error or None,
                })
            except Exception as error:
                print(f'status report error: {error}',file=sys.stderr,flush=True)
            delay=max(0.1,args.interval-(time.monotonic()-started))
            time.sleep(delay)
    finally:
        fan.close()


if __name__=='__main__':main()
