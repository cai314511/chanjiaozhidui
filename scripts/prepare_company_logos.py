"""建立全量Logo待核验队列，并下载人工核对过官方来源的图片。"""

import argparse
import base64
import hashlib
import json
import math
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote_to_bytes, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.company_logos import LOGO_ROOT, MAX_BYTES, initialize_registry, read_registry, register_verified_logo


def inspect_page(url):
    with httpx.Client(timeout=20, follow_redirects=True, max_redirects=5, trust_env=False) as client:
        response = client.get(url)
        response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    candidates = []
    for node in soup.find_all(['img', 'link']):
        descriptor = ' '.join([str(node.get('alt', '')), str(node.get('class', '')), str(node.get('id', '')),
                               str(node.get('src', '')), str(node.get('href', '')), str(node.get('rel', ''))])
        if 'logo' in descriptor.casefold() or node.name == 'link' and 'icon' in descriptor.casefold():
            src = node.get('src') or node.get('data-src') or node.get('href')
            if src:
                candidates.append({'url': 'embedded:' + src.split(',', 1)[0].split(';')[0][5:] if src.startswith('data:') else urljoin(str(response.url), src), 'alt': node.get('alt', '')})
    return {'url': str(response.url), 'title': soup.title.get_text(' ', strip=True) if soup.title else '',
            'candidates': candidates[:25], 'footer': soup.get_text(' ', strip=True)[-350:]}


def rasterize_svg(content):
    """仅离线渲染已审核的静态矢量标识，服务端始终只提供重编码PNG。"""
    if len(content) > MAX_BYTES or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('SVG包含禁止的文档声明或内容过大')
    try:
        document = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError('SVG不是有效XML') from exc
    allowed = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'polygon', 'polyline', 'line', 'defs',
               'clipPath', 'linearGradient', 'radialGradient', 'stop', 'title', 'desc', 'style', 'mask', 'use'}
    if document.tag.split('}')[-1] != 'svg':
        raise ValueError('SVG缺少根元素')
    for node in document.iter():
        if node.tag.split('}')[-1] not in allowed:
            raise ValueError('SVG包含活动内容或不支持的元素')
        for name, value in node.attrib.items():
            local = name.split('}')[-1].casefold()
            if local.startswith('on') or local == 'src' or '\\' in value:
                raise ValueError('SVG包含事件或外部资源引用')
            if local == 'href' and not re.fullmatch(r'#[A-Za-z_][\w:.-]*', value):
                raise ValueError('SVG只允许文档内已命名形状引用')
        text = ' '.join(node.attrib.values()) + ' ' + (node.text or '')
        if '@' in text or 'javascript:' in text.casefold() or any(not value.strip().strip('"\'').startswith('#') for value in re.findall(r'url\((.*?)\)', text, re.I)):
            raise ValueError('SVG包含外部样式或资源')
    viewbox = document.get('viewBox', '').replace(',', ' ').split()
    try:
        if len(viewbox) == 4:
            width, height = float(viewbox[2]), float(viewbox[3])
        else:
            width = float(re.sub(r'(?:px|pt)$', '', document.get('width', '')))
            height = float(re.sub(r'(?:px|pt)$', '', document.get('height', '')))
    except ValueError as exc:
        raise ValueError('SVG缺少可验证的尺寸') from exc
    if not all(math.isfinite(value) and 8 <= value <= 4096 for value in (width, height)):
        raise ValueError('SVG尺寸超出限制')
    scale = min(1, 1024 / max(width, height))
    width, height = max(8, round(width * scale)), max(8, round(height * scale))
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        context = browser.new_context(java_script_enabled=False, offline=True, viewport={'width': width, 'height': height})
        page = context.new_page()
        data = base64.b64encode(content).decode('ascii')
        page.set_content('<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'">'
                         f'<style>body{{margin:0}}img{{display:block;width:{width}px;height:{height}px}}</style>'
                         f'<img src="data:image/svg+xml;base64,{data}">')
        result = page.locator('img').screenshot(omit_background=True, timeout=10000)
        browser.close()
    return result


def extract_svg_raster(content):
    """提取官方SVG包装内唯一的PNG；不解析DTD、不发起外部资源请求。"""
    if len(content) > MAX_BYTES or b'<!ENTITY' in content.upper():
        raise ValueError('SVG包装含实体声明或内容过大')
    try:
        document = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError('SVG包装不是有效XML') from exc
    nodes = list(document.iter())
    if document.tag.split('}')[-1] != 'svg' or len(nodes) != 2 or nodes[1].tag.split('}')[-1] != 'image':
        raise ValueError('仅允许单个内嵌栅格图像的SVG包装')
    node = nodes[1]
    if any(name.split('}')[-1].casefold().startswith('on') for name in node.attrib):
        raise ValueError('SVG包装包含事件属性')
    href = node.get('href') or node.get('{http://www.w3.org/1999/xlink}href', '')
    if not href.startswith('data:image/png;base64,'):
        raise ValueError('SVG包装不得引用外部图片或其他格式')
    return base64.b64decode(''.join(href.split(',', 1)[1].split()), validate=True)


def download_approved(entry, companies, root):
    names = set(entry['company_names'])
    matches = [company['id'] for company in companies if company['name'] in names]
    if len(matches) != len(names):
        raise ValueError('核验清单中的企业名称未全部精确匹配目录：' + entry['brand'])
    source = entry['source']
    allowed = set(entry['allowed_asset_hosts'])
    if urlparse(source['asset_url']).scheme != 'https' or urlparse(source['asset_url']).hostname not in allowed:
        raise ValueError('图片URL不在人工核验的官方资源主机清单中')
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        url = source['asset_url']
        for _ in range(6):
            with client.stream('GET', url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': source['page_url']}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    if urlparse(url).scheme != 'https' or urlparse(url).hostname not in allowed:
                        raise ValueError('资源跳转离开已核验的官方资源主机')
                    continue
                response.raise_for_status()
                if int(response.headers.get('content-length', '0')) > MAX_BYTES:
                    raise ValueError('图片超过4MB')
                parts, size = [], 0
                for part in response.iter_bytes():
                    size += len(part)
                    if size > MAX_BYTES:
                        raise ValueError('图片超过4MB')
                    parts.append(part)
                content = b''.join(parts)
                break
        else:
            raise ValueError('资源跳转超过5次')
    if entry.get('embedded_selector'):
        soup = BeautifulSoup(content, 'html.parser')
        nodes = soup.select(entry['embedded_selector'])
        node = nodes[entry.get('embedded_index', 0)]
        inline = node.get('src', '')
        if not inline.startswith(('data:image/png', 'data:image/svg+xml')) or ',' not in inline:
            raise ValueError('官方页面中未找到指定的内嵌图片标识')
        header, encoded = inline.split(',', 1)
        content = base64.b64decode(encoded, validate=True) if ';base64' in header else unquote_to_bytes(encoded)
    if entry.get('rasterize_svg'):
        source = {**source, 'original_download_sha256': hashlib.sha256(content).hexdigest(),
                  'processing': '官方静态SVG经禁脚本、禁网络浏览器等比栅格化；本地仅提供PNG'}
        content = rasterize_svg(content)
    if entry.get('extract_svg_png'):
        source = {**source, 'original_download_sha256': hashlib.sha256(content).hexdigest(),
                  'processing': '仅提取官方SVG包装内唯一的data:image/png栅格图像，不读取DTD或任何外部资源'}
        content = extract_svg_raster(content)
    return register_verified_logo(root, matches, brand=entry['brand'], asset_name=entry['asset_name'],
        content=content, source=source, aliases=entry['company_names'])


def main():
    parser = argparse.ArgumentParser(description='准备已核验官方来源的本地企业Logo')
    parser.add_argument('--store-root', type=Path, default=ROOT / 'data' / 'private')
    parser.add_argument('--logo-root', type=Path, default=LOGO_ROOT)
    parser.add_argument('--initialize', action='store_true')
    parser.add_argument('--inspect', action='append', default=[])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--brand', action='append', default=[])
    args = parser.parse_args()
    companies = []
    if args.initialize or args.manifest:
        database = args.store_root.resolve() / 'chanzhi.sqlite3'
        if not database.is_file():
            parser.error('市场目录数据库不存在')
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
            row = connection.execute("SELECT data FROM entities WHERE id='market-catalog-v1' AND kind='market_catalog' AND owner='local-market-import'").fetchone()
        if not row:
            parser.error('尚未导入全量市场目录')
        companies = json.loads(row[0])['companies']
    if args.initialize:
        initialize_registry(companies, args.logo_root, priority_ids=[company['id'] for company in companies[:20]])
    failed = False
    for url in args.inspect:
        try:
            print(json.dumps(inspect_page(url), ensure_ascii=True), flush=True)
        except httpx.HTTPError as exc:
            print(json.dumps({'url': url, 'error': type(exc).__name__}), flush=True)
            failed = True
    if not args.initialize and not args.manifest:
        if failed:
            raise SystemExit(1)
        return
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
        for entry in manifest:
            if args.brand and entry['brand'] not in args.brand:
                continue
            metadata = download_approved(entry, companies, args.logo_root)
            print(json.dumps({'brand': entry['brand'], 'companies': len(entry['company_names']), **metadata}, ensure_ascii=True), flush=True)
    registry = read_registry(args.logo_root)
    verified = [entry for entry in registry['companies'].values() if entry['status'] == 'verified']
    print(json.dumps({'total': len(registry['companies']), 'verified': len(verified),
                      'assets': len({entry['asset'] for entry in verified}), 'pending': len(registry['pending_queue'])}))


if __name__ == '__main__':
    main()
