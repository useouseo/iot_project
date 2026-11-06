"""Interactive first-run setup for RestFlow's MariaDB databases."""
from getpass import getpass
import json
from pathlib import Path
import sys

import mariadb

from server import DB_CONFIG_PATH, Store, database_name


def ask(label, default=''):
    suffix=f' [{default}]' if default else ''
    value=input(f'{label}{suffix}: ').strip()
    return value or default


def main():
    print('RestFlow MariaDB 최초 설정')
    print('MariaDB 서비스가 실행 중이어야 합니다. 비밀번호는 화면에 표시되지 않습니다.')
    existing={}
    if DB_CONFIG_PATH.exists():
        try:existing=json.loads(DB_CONFIG_PATH.read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
    host=ask('DB 호스트',str(existing.get('host','localhost')))
    try:port=int(ask('DB 포트',str(existing.get('port',3306))))
    except ValueError:
        print('포트는 숫자여야 합니다.');return 1
    user=ask('DB 사용자',str(existing.get('user','root')))
    password=getpass('DB 비밀번호(없으면 Enter): ')
    live=ask('실사용 DB 이름',str(existing.get('database','restflow')))
    demo=ask('시연 DB 이름',str(existing.get('demo_database','restflow_demo')))
    try:
        database_name(live);database_name(demo,'demo_database')
        if live==demo:raise ValueError('실사용 DB와 시연 DB 이름은 달라야 합니다')
    except ValueError as error:
        print(error);return 1
    config=dict(host=host,port=port,user=user,password=password,database=live,demo_database=demo)
    try:
        missing=[]
        for name in (live,demo):
            try:
                connection=mariadb.connect(host=host,port=port,user=user,password=password,database=name)
                connection.close()
            except mariadb.Error as error:
                if getattr(error,'errno',None)==1049:missing.append(name)
                else:raise
        if missing:
            connection=mariadb.connect(host=host,port=port,user=user,password=password)
            cursor=connection.cursor()
            for name in missing:
                cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            connection.commit();cursor.close();connection.close()
        Store(config,False);Store(config,True)
    except mariadb.Error as error:
        print(f'MariaDB 설정 실패: {error}')
        print('계정에 DB 생성 권한이 없으면 관리자 계정으로 DB를 먼저 만든 뒤 다시 실행하세요.')
        return 1
    DB_CONFIG_PATH.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'설정 완료: {DB_CONFIG_PATH}')
    print(f'실사용 DB={live}, 시연 DB={demo}')
    return 0


if __name__=='__main__':sys.exit(main())
