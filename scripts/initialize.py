import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.initial_data import initialize
from backend.store import Store


def main():
    database = ROOT / 'data' / 'private' / 'chanzhi.sqlite3'
    if database.exists():
        folder = ROOT / 'data' / 'private' / 'backups'
        folder.mkdir(parents=True, exist_ok=True)
        backup = folder / ('before-initialization-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.sqlite3')
        with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
            source.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('备份完整性检查失败')
    result = initialize(Store(database.parent))
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
