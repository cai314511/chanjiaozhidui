"""核对本地Logo覆盖、图像和来源，并导出全量待核验CSV与审查图。"""

import argparse
import csv
import json
import math
import sqlite3
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.company_logos import LOGO_ROOT, logo_fields, read_registry


def excel_safe(value):
    text = str(value or '')
    return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text


def main():
    parser = argparse.ArgumentParser(description='核对本地企业Logo及完整待核验队列')
    parser.add_argument('--logo-root', type=Path, default=LOGO_ROOT)
    parser.add_argument('--store-root', type=Path, default=ROOT / 'data' / 'private')
    parser.add_argument('--preview', type=Path)
    args = parser.parse_args()
    registry = read_registry(args.logo_root)
    companies = registry['companies']
    database = args.store_root.resolve() / 'chanzhi.sqlite3'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        record = connection.execute("SELECT data FROM entities WHERE id='market-catalog-v1' AND kind='market_catalog' AND owner='local-market-import'").fetchone()
    catalog_ids = {company['id'] for company in json.loads(record[0])['companies']}
    if not catalog_ids <= set(companies):
        raise ValueError('注册表漏掉市场目录企业ID')
    verified = [company for company in companies.values() if company['status'] == 'verified']
    for company in verified:
        if logo_fields(company['id'], args.logo_root)['logo_status'] != 'verified':
            raise ValueError('已核验企业的图片无法通过完整性校验：' + company['id'])
        if any(not company['source'].get(field) for field in ['page_url', 'asset_url', 'relationship_url', 'relationship_note']):
            raise ValueError('已核验企业缺少官方来源或关系证据')
    pending = registry['pending_queue']
    if set(pending) != {ident for ident, company in companies.items() if company['status'] != 'verified'}:
        raise ValueError('待核验队列与注册表状态不一致')
    with (args.logo_root / 'pending.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['queue_position', 'company_id', 'company_name', 'status', 'review_reason'])
        for index, ident in enumerate(pending, 1):
            writer.writerow([index, ident, excel_safe(companies[ident]['name']), 'pending', '待核验官方来源、完整Logo及企业品牌关系'])
    with (args.logo_root / 'verified.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['company_id', 'company_name', 'brand', 'asset', 'official_page', 'asset_source', 'relationship_source', 'review_note'])
        for company in verified:
            source = company['source']
            writer.writerow([company['id'], excel_safe(company['name']), company['brand'], company['asset'],
                             source['page_url'], source['asset_url'], source['relationship_url'], source['relationship_note']])
    unique = {company['asset']: company for company in verified}
    if args.preview:
        columns, cell_width, cell_height = 3, 300, 135
        image = Image.new('RGB', (columns * cell_width, math.ceil(len(unique) / columns) * cell_height), 'white')
        draw = ImageDraw.Draw(image)
        for index, company in enumerate(unique.values()):
            left, top = index % columns * cell_width, index // columns * cell_height
            logo = Image.open(args.logo_root / company['asset']).convert('RGBA')
            logo.thumbnail((250, 80))
            image.paste(logo, (left + (cell_width - logo.width) // 2, top + 10 + (80 - logo.height) // 2), logo)
            draw.text((left + 12, top + 104), company['brand'], fill='#202020')
            draw.rectangle((left, top, left + cell_width - 1, top + cell_height - 1), outline='#dddddd')
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.preview)
    print(json.dumps({'catalog_companies': len(catalog_ids), 'registry_companies': len(companies),
        'verified_companies': len(verified), 'independent_images': len(unique), 'pending_companies': len(pending),
        'pending_csv': str(args.logo_root / 'pending.csv'), 'verified_csv': str(args.logo_root / 'verified.csv'),
        'preview': str(args.preview) if args.preview else None}, ensure_ascii=True))


if __name__ == '__main__':
    main()
