"""将本地CSV全行业企业目录导入独立记录，先备份数据库。"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.market import build_market, publish_market
from backend.store import Store


def backup_database(store):
    folder = store.root / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    target_path = folder / ('before-market-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    with sqlite3.connect(store.path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('导入前数据库备份校验失败')
    return target_path


def main():
    parser = argparse.ArgumentParser(description='从本地招聘CSV导入全行业企业目录')
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'runtime' / 'competition-input')
    parser.add_argument('--store-root', type=Path, default=ROOT / 'data' / 'private')
    parser.add_argument('--csv', type=Path, action='append', dest='csv_paths')
    parser.add_argument('--samples-per-company', type=int, default=2, choices=range(1, 9))
    args = parser.parse_args()
    paths = args.csv_paths or [args.input_dir / name for name in ['上市公司招聘数据2026.csv', '应届生招聘大数据2026.csv']]
    for path in paths:
        if not path.is_file():
            parser.error('输入CSV不存在：' + str(path))
    bundle = build_market(paths, args.samples_per_company)
    store = Store(args.store_root.resolve())
    backup = backup_database(store)
    publish_market(store, bundle)
    print(json.dumps({'companies': len(bundle['companies']), 'scanned_rows': bundle['scanned_rows'],
                      'duplicate_rows': bundle['duplicate_rows'], 'backup': str(backup),
                      'sources': bundle['sources']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
