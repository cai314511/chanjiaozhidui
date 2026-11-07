"""来源可追溯的本地企业Logo注册表；未核验企业保持文字标识。"""

import hashlib
import io
import json
import errno
import os
import re
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.store import now


LOGO_ROOT = Path(__file__).resolve().parents[1] / 'Assets' / 'company-logos'
MAX_BYTES = 4 * 1024 * 1024
MAX_DIMENSION = 4096
_REGISTRY_CACHE = {}
_ASSET_CACHE = {}
_LOCK = threading.RLock()


@contextmanager
def _registry_writer(root, timeout=5):
    """仅串行化同一目录的写者；HTTP读取继续使用上一完整注册表。"""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / '.registry-write.lock').open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError('企业Logo注册表写锁等待超过时限') from exc
                time.sleep(0.025)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_registry(root, registry):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / 'registry.json'
    temporary = root / ('.registry-' + uuid.uuid4().hex + '.part')
    try:
        temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        deadline = time.monotonic() + 2
        while True:
            try:
                temporary.replace(target)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
    finally:
        temporary.unlink(missing_ok=True)
    with _LOCK:
        _REGISTRY_CACHE.pop(str(root.resolve()), None)


def read_registry(root=LOGO_ROOT, *, refresh=False):
    root = Path(root).resolve()
    path = root / 'registry.json'
    try:
        info = path.stat()
    except FileNotFoundError:
        return {'version': 1, 'companies': {}, 'pending_queue': []}
    stamp = (info.st_mtime_ns, info.st_size)
    with _LOCK:
        cached = _REGISTRY_CACHE.get(str(root))
        if not refresh and cached and cached[0] == stamp:
            return cached[1]
        result = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result.get('companies'), dict):
            raise ValueError('企业Logo注册表格式无效')
        _REGISTRY_CACHE[str(root)] = (stamp, result)
        return result


def initialize_registry(companies, root=LOGO_ROOT, priority_ids=()):
    with _registry_writer(root):
        previous = read_registry(root, refresh=True)
        entries = dict(previous['companies'])
        for company in companies:
            ident = company['id']
            if not re.fullmatch(r'[0-9a-f]{24}', ident):
                raise ValueError('企业ID必须为24位十六进制标识')
            entries.setdefault(ident, {'id': ident, 'name': company['name'], 'brand': None,
                'asset': None, 'source': None, 'status': 'pending', 'aliases': []})
        pending = {ident for ident, entry in entries.items() if entry['status'] != 'verified'}
        priorities = list(dict.fromkeys(ident for ident in priority_ids if ident in pending))
        queue = priorities + sorted(pending - set(priorities), key=lambda ident: entries[ident]['name'])
        registry = {'version': 1, 'updated_at': now(), 'companies': entries, 'pending_queue': queue,
                    'scope': '全量企业ID建立待核验队列；verified表示官方来源及企业品牌关系已核对，不代表品牌授权背书。'}
        _write_registry(root, registry)
    return registry


def normalize_logo(content):
    if not content or len(content) > MAX_BYTES:
        raise ValueError('Logo文件为空或超过4MB')
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {'PNG', 'JPEG', 'WEBP', 'GIF', 'ICO'}:
                raise ValueError('仅接收可安全解码的栅格图片')
            if max(image.size) > MAX_DIMENSION or min(image.size) < 8 or getattr(image, 'n_frames', 1) != 1:
                raise ValueError('Logo尺寸须为8至4096像素且仅含单帧')
            image.verify()
        with Image.open(io.BytesIO(content)) as original:
            original.load()
            raster = ImageOps.exif_transpose(original).convert('RGBA')
            raster.thumbnail((1024, 1024))
            # 复制像素后重编码，丢弃原文件附加内容、EXIF及文本元数据。
            clean = Image.new('RGBA', raster.size)
            clean.paste(raster)
            buffer = io.BytesIO()
            clean.save(buffer, format='PNG', optimize=True)
            result = buffer.getvalue()
            return result, {'width': clean.width, 'height': clean.height,
                            'sha256': hashlib.sha256(result).hexdigest()}
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError('Logo图片解码或完整性校验失败') from exc


def register_verified_logo(root, company_ids, *, brand, asset_name, content, source, aliases):
    root = Path(root).resolve()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,59}', asset_name):
        raise ValueError('Logo资产名称须为1至60位小写字母、数字或连字符')
    for field in ('page_url', 'asset_url', 'relationship_url'):
        parsed = urlparse(str(source.get(field, '')))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('官方来源和关系证据须记录有效HTTPS地址')
    if not str(source.get('relationship_note', '')).strip():
        raise ValueError('须说明企业与品牌的官方核验依据')
    normalized, metadata = normalize_logo(content)
    provenance = {**source, 'verified_at': now(), 'download_sha256': hashlib.sha256(content).hexdigest(),
                  'asset_sha256': metadata['sha256'], 'width': metadata['width'], 'height': metadata['height']}
    with _registry_writer(root):
        registry = read_registry(root, refresh=True)
        if not company_ids or any(ident not in registry['companies'] for ident in company_ids):
            raise ValueError('核验企业须已进入待核验队列')
        filename = asset_name + '-' + metadata['sha256'][:12] + '.png'
        target = root / filename
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != metadata['sha256']:
                raise ValueError('同名内容寻址资产的校验值不一致，未覆盖已有文件')
        else:
            target.write_bytes(normalized)
        entries = dict(registry['companies'])
        for ident in company_ids:
            entries[ident] = {**entries[ident], 'brand': brand, 'asset': filename, 'source': provenance,
                              'status': 'verified', 'aliases': list(dict.fromkeys(aliases))}
        registry = {**registry, 'companies': entries, 'updated_at': now(),
                    'pending_queue': [ident for ident in registry['pending_queue'] if ident not in company_ids]}
        _write_registry(root, registry)
    return metadata


def _safe_asset(ident, root):
    if not re.fullmatch(r'[0-9a-f]{24}', ident):
        return None
    root = Path(root).resolve()
    item = read_registry(root)['companies'].get(ident)
    if not item or item.get('status') != 'verified':
        return None
    filename = item.get('asset')
    if not isinstance(filename, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}\.png', filename):
        return None
    path = (root / filename).resolve()
    try:
        path.relative_to(root)
        info = path.stat()
    except (ValueError, FileNotFoundError, OSError):
        return None
    expected = (item.get('source') or {}).get('asset_sha256')
    signature = (str(path), info.st_mtime_ns, info.st_size, expected)
    with _LOCK:
        valid = _ASSET_CACHE.get(str(path))
        if valid == signature:
            return path
        if info.st_size > MAX_BYTES or not expected:
            return None
        content = path.read_bytes()
        if not content.startswith(b'\x89PNG\r\n\x1a\n') or hashlib.sha256(content).hexdigest() != expected:
            return None
        try:
            normalize_logo(content)
        except ValueError:
            return None
        _ASSET_CACHE[str(path)] = signature
    return path


def logo_fields(ident, root=LOGO_ROOT):
    path = _safe_asset(ident, root)
    if path is None:
        return {'logo_url': None, 'logo_status': 'pending'}
    return {'logo_url': '/api/company-logos/' + ident, 'logo_status': 'verified'}


def attach_company_logos(app, root=LOGO_ROOT):
    @app.get('/api/company-logos/{ident}')
    def company_logo(ident: str):
        path = _safe_asset(ident, root)
        if path is None:
            raise HTTPException(404, '暂无已核验的本地企业Logo')
        return FileResponse(path, media_type='image/png', headers={
            'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'public,max-age=3600',
            'Content-Security-Policy': "default-src 'none'; sandbox", 'Content-Disposition': 'inline'})
