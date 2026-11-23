"""Configure the two MariaDB databases for RestFlow."""
from getpass import getpass
import json
import re

from pymysql import MySQLError

from database import CONFIG_PATH, connect


def main():
    previous = json.loads(CONFIG_PATH.read_text(encoding='utf-8')) if CONFIG_PATH.exists() else {}

    def ask(key, label, default):
        default = previous.get(key, default)
        return input(f'{label} [{default}]: ').strip() or default

    config = dict(
        host=ask('host', 'DB 호스트', '127.0.0.1'),
        port=int(ask('port', 'DB 포트', 3306)),
        user=ask('user', 'DB 사용자', 'root'),
        password=getpass('MariaDB 비밀번호: '),
        database=ask('database', '실사용 DB', 'restflow_integrated'),
        demo_database=ask('demo_database', '시연 DB', 'restflow_integrated_demo'),
    )
    names = (config['database'], config['demo_database'])
    if not 1 <= config['port'] <= 65535:
        raise ValueError('DB 포트 범위를 확인해 주세요.')
    if names[0].lower() == names[1].lower() or any(not re.fullmatch(r'[A-Za-z0-9_]{1,64}', n) for n in names):
        raise ValueError('서로 다른 DB 이름을 영문·숫자·밑줄로 입력해 주세요.')
    for name in names:
        try:
            connect(config, name).close()
        except MySQLError as error:
            if error.args[0] != 1049:
                raise
            with connect(config) as connection, connection.cursor() as cursor:
                cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4')
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('MariaDB 연결 설정을 저장했습니다.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, MySQLError) as error:
        raise SystemExit(f'MariaDB 설정 실패: {error}')
