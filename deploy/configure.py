"""Prepare a future VPS deployment without creating or purchasing a server."""
import argparse
import getpass
import ipaddress
from pathlib import Path
import re
import secrets
import os


def hostname(value):
    value=value.strip().rstrip('.').encode('idna').decode('ascii').lower()
    try:ipaddress.ip_address(value)
    except ValueError:pass
    else:raise ValueError('HTTPS용 도메인 이름을 입력하세요. IP 주소는 사용할 수 없습니다.')
    if len(value)>253 or '.' not in value or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',p) for p in value.split('.')):
        raise ValueError('도메인 이름만 입력하세요. https://, 경로, 포트는 빼세요.')
    return value


def configure(directory,domain,email,password=None):
    domain=hostname(domain)
    if not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',email):
        raise ValueError('인증서 알림을 받을 이메일 주소를 입력하세요.')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    secret_dir=directory/'.secrets'
    secret_dir.mkdir(mode=0o700,exist_ok=True)
    os.chmod(secret_dir,0o700)
    names=('db_root_password','db_password','admin_password','db_client.cnf')
    existing=[(secret_dir/name).exists() for name in names]
    if any(existing) and not all(existing):
        raise ValueError('.secrets 일부 파일이 누락됐습니다. 기존 백업에서 복구하세요. DB 비밀번호를 임의로 재생성하지 않습니다.')
    created=not all(existing)
    if created:
        if password is None or not 8<=len(password)<=128 or password=='1234':
            raise ValueError('새 관리자 비밀번호는 8~128자로 지정하세요.')
        db_password=secrets.token_hex(32)
        values=(secrets.token_hex(32),db_password,password,
                '[client]\nuser=restflow_app\npassword='+db_password+'\nhost=localhost\n')
        for name,value in zip(names,values):
            # Directory 0700 protects host access. Read-only 0444 files allow the
            # non-root app to read Docker Compose bind-mounted secrets.
            fd=os.open(secret_dir/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
            with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(value+'\n')
            os.chmod(secret_dir/name,0o444)
    env=directory/'.env'
    env.write_text('RESTFLOW_DOMAIN='+domain+'\nACME_EMAIL='+email+'\n',encoding='utf-8')
    os.chmod(env,0o600)
    return created


def main():
    p=argparse.ArgumentParser();p.add_argument('--domain',required=True);p.add_argument('--email',required=True)
    p.add_argument('--admin-password-file',help='자동화 시 사용할 비밀번호 파일 경로. 비밀번호를 인자로 직접 넘기지 않습니다.')
    args=p.parse_args()
    directory=Path(__file__).resolve().parent
    password=None
    if not (directory/'.secrets/admin_password').exists():
        if args.admin_password_file:
            password=Path(args.admin_password_file).read_text(encoding='utf-8').rstrip('\r\n')
        else:
            password=getpass.getpass('서버용 관리자 비밀번호 (8~128자): ')
            if password!=getpass.getpass('비밀번호 확인: '):raise ValueError('비밀번호가 일치하지 않습니다.')
    created=configure(directory,args.domain,args.email,password)
    print('서버 설정 준비 완료. '+('DB 비밀번호를 생성했습니다.' if created else '기존 비밀번호를 유지했습니다.'))
    print('서버 구매나 배포는 이 명령만으로 실행되지 않습니다.')


if __name__=='__main__':
    try:main()
    except (ValueError,OSError) as error:raise SystemExit(str(error))
