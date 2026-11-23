"""Copy the Demo-Font facility data to a fresh integrated MariaDB database."""
import argparse
from pathlib import Path
import sqlite3

from database import load_config
from server import app, db, init_db

TABLES = {
    'places': ('id','name','address','lat','lon','manager_hash'),
    'zones': ('id','place_id','name','device','total','open','closed','reason','accessible'),
    'site_access': ('place_id','claim_hash','password_hash'),
    'module_access': ('zone_id','slug','claim_hash','password_hash','kind'),
}


def migrate(source_path, config):
    init_db(config)
    uri = Path(source_path).resolve().as_uri() + '?mode=ro'
    source = sqlite3.connect(uri, uri=True)
    try:
        with app.app_context(), db() as connection:
            if connection.execute('SELECT 1 FROM places LIMIT 1 FOR UPDATE').fetchone():
                raise ValueError('빈 실사용 DB를 지정해 주세요.')
            counts = {}
            for table, columns in TABLES.items():
                fields = ','.join(columns)
                markers = ','.join('?' for _ in columns)
                rows = source.execute(f'SELECT {fields} FROM {table}').fetchall()
                target = ','.join(f'`{column}`' for column in columns)
                for row in rows:
                    connection.execute(f'INSERT INTO {table} ({target}) VALUES ({markers})', row)
                counts[table] = len(rows)
        return counts
    finally:
        source.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('sqlite_file', type=Path)
    args = parser.parse_args()
    print(migrate(args.sqlite_file, load_config()))
