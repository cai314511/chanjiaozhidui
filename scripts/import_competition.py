"""从用户指定的比赛数据构建本机产业研究资料，不调用外部API。"""

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.evidence import build_recruitment, extract_reference, publish_bundle
from backend.store import Store, now


def extract_csv(data_root, cache, seven):
    targets = [
        ('招聘数据/分年份保存数据.rar', '上市公司招聘数据2026.csv'),
        ('应届生招聘数据/分年份保存数据/分年份保存数据.rar', '分年份保存数据\\应届生招聘大数据2026.csv'),
    ]
    files = []
    for archive, member in targets:
        target = cache / Path(member.replace('\\', '/')).name
        # 每次提取指定成员，7-Zip检查CRC；不信任上次未完成的解压缓存。
        subprocess.run([str(seven), 'e', '-y', '-sccUTF-8', '-o' + str(cache), str(data_root / archive), member],
                       check=True, cwd=ROOT, capture_output=True, timeout=180)
        if not target.is_file():
            raise FileNotFoundError(f'指定CSV未成功提取：{target.name}')
        files.append(target)
    return files


def backup_database(store):
    folder = store.root / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    backup = folder / ('before-competition-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
    with sqlite3.connect(store.path) as source, sqlite3.connect(backup) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('导入前数据库备份完整性检查失败')
    return backup


def main():
    parser = argparse.ArgumentParser(description='导入智链产教比赛数据，保留来源与现有业务')
    parser.add_argument('--data-root', type=Path, default=ROOT / '比赛数据')
    parser.add_argument('--store-root', type=Path, default=ROOT / 'data' / 'private')
    parser.add_argument('--seven-zip', type=Path, default=Path('C:/Program Files/7-Zip/7z.exe'))
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    if not data_root.is_dir():
        parser.error('比赛数据目录不存在')
    seven = str(args.seven_zip) if args.seven_zip.is_file() else shutil.which('7z')
    if not seven:
        parser.error('需要本机7-Zip读取RAR年份成员')
    cache = ROOT / 'runtime' / 'competition-input'
    cache.mkdir(parents=True, exist_ok=True)
    recruitment = build_recruitment(extract_csv(data_root, cache, seven))
    for source in recruitment['sources']:
        source['archive'] = ('招聘数据/分年份保存数据.rar' if source['name'].startswith('上市公司')
                             else '应届生招聘数据/分年份保存数据/分年份保存数据.rar')
        source['member'] = (source['name'] if source['name'].startswith('上市公司')
                            else '分年份保存数据/' + source['name'])
    print(json.dumps({'stage': 'recruitment', 'scanned': recruitment['scanned_rows'], 'selected': len(recruitment['jobs'])}), flush=True)
    paths = list((data_root / '各省支持产业、代表企业、招聘岗位、薪资水平、报考大学、报考专业分析').glob('*.docx'))
    paths += list((data_root / '本科生就业报告').glob('*.pdf'))
    # 优先接入三所现有高校所在地区及主要AI/金融科技产业地区的规划正文。
    regions = ('北京', '上海', '广东', '江苏', '浙江', '四川', '湖北', '山东', '安徽', '天津', '重庆', '福建')
    paths += [p for p in (data_root / '政策文件').rglob('*.pdf')
              if '规划纲要' in p.stem and any(region in p.stem for region in regions)]
    documents = []
    for i, path in enumerate(sorted(set(paths))):
        documents.append(extract_reference(path, data_root))
        if (i + 1) % 10 == 0:
            print(json.dumps({'stage': 'references', 'processed': i + 1, 'total': len(paths)}), flush=True)
    inventory = [
        {'name': '招聘数据 / 应届生招聘数据', 'status': '已接入两份2026年CSV', 'reason': '2014—2025历史年份和汇总RAR不重复纳入本期岗位样本。'},
        {'name': '各省产业与报考指南', 'status': f'已接入{sum(d["kind"] == "产业指南" for d in documents)}份', 'reason': '汇编内容保留原文出处；未将其中的预测或观点当作已测量的岗位数据。'},
        {'name': '本科生就业报告', 'status': '2023—2026版已登记', 'reason': '正文按实际可提取情况展示；2025版文字编码异常待OCR，出版年与毕业届别分别保留。'},
        {'name': '政策文件', 'status': f'已接入{sum(d["kind"] == "政策文件" for d in documents)}份重点地区规划', 'reason': '按人工智能、数字金融、人才培养等关键词定位页码。'},
        {'name': '工商数据', 'status': '未纳入展示', 'reason': '分卷工商数据涉及企业与联系人明细；本轮岗位、薪资及培养依据不依赖这些个人标识。'},
    ]
    bundle = {'version': 1, 'created_at': now(), 'scope': '用户提供的比赛资料；2026年招聘文件相关岗位样本与产业、政策、就业文献。',
              'recruitment': recruitment, 'documents': documents, 'inventory': inventory}
    store = Store(args.store_root)
    backup = backup_database(store)
    publish_bundle(store, bundle)
    with store.connect() as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('导入后数据库完整性检查失败')
    output = ROOT / 'outputs' / 'competition-import'
    output.mkdir(parents=True, exist_ok=True)
    report = {'imported_at': bundle['created_at'], 'backup': str(backup.relative_to(args.store_root)),
              'recruitment': {k: v for k, v in recruitment.items() if k != 'jobs'},
              'unique_jobs': len(recruitment['jobs']),
              'documents': [{k: v for k, v in d.items() if k != 'blocks'} for d in documents], 'inventory': inventory}
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'ready': True, 'jobs': len(recruitment['jobs']), 'documents': len(documents), 'manifest': 'outputs/competition-import/manifest.json'}), flush=True)


if __name__ == '__main__':
    main()
