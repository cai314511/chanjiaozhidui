"""从全量本地招聘CSV构建独立高校需求聚合，写入前备份数据库。"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.store import Store
from backend.university_intelligence import build_demand, publish_demand


def backup_database(store):
    folder = store.root / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ('before-demand-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    with sqlite3.connect(store.path) as source, sqlite3.connect(path) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('需求聚合导入前数据库备份校验失败')
    return path


def main():
    parser = argparse.ArgumentParser(description='从全量招聘CSV导入高校需求聚合')
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'runtime' / 'competition-input')
    parser.add_argument('--store-root', type=Path, default=ROOT / 'data' / 'private')
    parser.add_argument('--csv', type=Path, action='append', dest='csv_paths')
    args = parser.parse_args()
    paths = args.csv_paths or [args.input_dir / name for name in ['上市公司招聘数据2026.csv', '应届生招聘大数据2026.csv']]
    for path in paths:
        if not path.is_file():
            parser.error('输入CSV不存在：' + str(path))
    bundle = build_demand(paths)
    store = Store(args.store_root.resolve())
    backup = backup_database(store)
    publish_demand(store, bundle)
    print(json.dumps({'backup': str(backup), 'history_period': bundle['history_period'],
                      'groups': len(bundle['groups']), 'source_meta': bundle['source_meta']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
