"""仅清理本项目演示目录下已过期且带完整清单的体验空间。"""
import argparse
import json
import re
import shutil
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def expired_spaces(root):
    resolved=root.resolve()
    if not resolved.is_dir():return []
    result=[]
    for meta in resolved.glob('*/workspace.json'):
        folder=meta.parent.resolve()
        if folder.parent!=resolved or not re.fullmatch('[a-f0-9]{64}',folder.name) or folder.is_symlink():continue
        data=json.loads(meta.read_text(encoding='utf-8'))
        if not isinstance(data.get('expires'),(int,float)) or set(data.get('main',{}))!={'student','employer','university'}:continue
        if data['expires']<time.time():result.append(folder)
    return result


def main():
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run',action='store_true')
    mode.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    root=(ROOT/'data/private/demo').resolve()
    spaces=expired_spaces(root)
    print('过期体验空间：',len(spaces))
    for folder in spaces:
        print(folder)
        if args.apply:
            if folder.parent!=root:raise ValueError('目录超出范围')
            shutil.rmtree(folder)


if __name__=='__main__':main()
