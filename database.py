"""MariaDB configuration and a small transaction wrapper."""
import json
import os
from pathlib import Path
import re

import pymysql
from pymysql.constants import CLIENT

CONFIG_PATH = Path(__file__).with_name("db_config.json")


def load_config():
    path = Path(os.environ.get("RESTFLOW_DB_CONFIG", CONFIG_PATH))
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for key, default in {
        "host": "127.0.0.1", "port": 3306, "user": "restflow", "password": "",
        "database": "restflow_integrated", "demo_database": "restflow_integrated_demo",
    }.items():
        config[key] = os.environ.get("RESTFLOW_DB_" + key.upper(), config.get(key, default))
    config["port"] = int(config["port"])
    for key in ("database", "demo_database"):
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", config[key]):
            raise ValueError("DB 이름은 영문·숫자·밑줄 1~64자입니다.")
    if config["database"].lower() == config["demo_database"].lower():
        raise ValueError("실사용 DB와 시연 DB를 분리해 주세요.")
    return config


def connect(config, database=None):
    options = {key: config[key] for key in ("host", "port", "user", "password")}
    return pymysql.connect(**options, database=database, charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor, client_flag=CLIENT.FOUND_ROWS)


class Database:
    def __init__(self, config, name, close_on_exit=True):
        self.connection = connect(config, name)
        self.close_on_exit = close_on_exit

    def execute(self, sql, params=()):
        cursor = self.connection.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        try:
            if error_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            if self.close_on_exit:
                self.close()

    def close(self):
        self.connection.close()
