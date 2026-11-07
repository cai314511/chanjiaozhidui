import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image


def png_bytes(size=(64, 32)):
    # 隔离测试生成的图块，只检验文件管线，不充当真实企业Logo。
    buffer = io.BytesIO()
    Image.new('RGBA', size, (10, 80, 180, 255)).save(buffer, format='PNG')
    return buffer.getvalue()


def test_queue_covers_every_catalog_id_and_preserves_verified_entries(tmp_path):
    from backend.company_logos import initialize_registry, read_registry, register_verified_logo
    companies = [{'id': 'a' * 24, 'name': '甲公司'}, {'id': 'b' * 24, 'name': '乙公司'}]
    initialize_registry(companies, tmp_path, priority_ids=['b' * 24])
    registry = read_registry(tmp_path)
    assert set(registry['companies']) == {'a' * 24, 'b' * 24}
    assert all(item['status'] == 'pending' and item['asset'] is None for item in registry['companies'].values())
    assert registry['pending_queue'][0] == 'b' * 24
    register_verified_logo(tmp_path, ['a' * 24], brand='甲品牌', asset_name='brand-a',
        content=png_bytes(), source={'page_url': 'https://official.example/about',
        'asset_url': 'https://official.example/logo.png', 'relationship_url': 'https://official.example/about',
        'relationship_note': '隔离测试证据'}, aliases=['甲公司'])
    initialize_registry(companies + [{'id': 'c' * 24, 'name': '丙公司'}], tmp_path)
    registry = read_registry(tmp_path)
    assert registry['companies']['a' * 24]['status'] == 'verified'
    assert set(registry['pending_queue']) == {'b' * 24, 'c' * 24}


def test_validation_rejects_active_content_oversized_images_and_path_traversal(tmp_path):
    from backend.company_logos import normalize_logo, register_verified_logo
    for content in [b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                    b'<html>not an image</html>', b'\x89PNG\r\n\x1a\ntruncated']:
        with pytest.raises(ValueError):
            normalize_logo(content)
    with pytest.raises(ValueError):
        normalize_logo(png_bytes((4097, 4097)))
    with pytest.raises(ValueError):
        register_verified_logo(tmp_path, ['a' * 24], brand='测试', asset_name='../outside',
            content=png_bytes(), source={'page_url': 'https://official.example', 'asset_url': 'https://official.example/logo.png',
            'relationship_url': 'https://official.example', 'relationship_note': '测试'}, aliases=[])
    assert not (tmp_path.parent / 'outside.png').exists()


def test_only_verified_safe_local_images_are_served_and_registry_changes_invalidate_cache(tmp_path):
    from backend.company_logos import attach_company_logos, initialize_registry, logo_fields, register_verified_logo
    ident = 'a' * 24
    initialize_registry([{'id': ident, 'name': '甲公司'}], tmp_path)
    app = FastAPI()
    attach_company_logos(app, root=tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/company-logos/' + ident).status_code == 404
        assert logo_fields(ident, tmp_path) == {'logo_url': None, 'logo_status': 'pending'}
        register_verified_logo(tmp_path, [ident], brand='甲品牌', asset_name='brand-a', content=png_bytes(),
            source={'page_url': 'https://official.example', 'asset_url': 'https://official.example/logo.png',
                    'relationship_url': 'https://official.example', 'relationship_note': '隔离测试'}, aliases=['甲公司'])
        assert logo_fields(ident, tmp_path)['logo_url'].startswith('/api/company-logos/' + ident)
        response = client.get('/api/company-logos/' + ident)
        assert response.status_code == 200
        assert response.headers['content-type'] == 'image/png'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert Image.open(io.BytesIO(response.content)).size == (64, 32)
        assert client.get('/api/company-logos/../../registry.json').status_code == 404
        assert client.get('/api/company-logos/%2E%2E%2Fregistry.json').status_code == 404
        assert client.get('/api/company-logos/' + 'b' * 24).status_code == 404
        registry_path = tmp_path / 'registry.json'
        registry = json.loads(registry_path.read_text(encoding='utf-8'))
        registry['companies'][ident]['asset'] = '../private.png'
        registry_path.write_text(json.dumps(registry), encoding='utf-8')
        assert client.get('/api/company-logos/' + ident).status_code == 404
        assert logo_fields(ident, tmp_path)['logo_url'] is None


def test_official_svg_conversion_is_static_and_blocks_external_or_active_content():
    from scripts.prepare_company_logos import rasterize_svg
    for payload in [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.com/track.png"/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.com/logo.svg#icon"/></svg>',
        b'<!DOCTYPE svg [<!ENTITY x "secret">]><svg xmlns="http://www.w3.org/2000/svg">&x;</svg>',
    ]:
        with pytest.raises(ValueError):
            rasterize_svg(payload)
    # 仅检验已安装浏览器的安全格式转换，不是企业品牌素材。
    converted = rasterize_svg(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 32"><defs><rect id="mark" width="64" height="32" fill="#1256ab"/></defs><use href="#mark"/></svg>')
    assert Image.open(io.BytesIO(converted)).size == (64, 32)


def test_registry_write_recovers_from_brief_windows_reader_lock(tmp_path, monkeypatch):
    from pathlib import Path
    from backend.company_logos import initialize_registry, read_registry

    original = Path.replace
    attempts = []

    def transient_lock(path, target):
        # 仅模拟Windows短暂文件共享锁，不代替真实文件写入。
        attempts.append(path)
        if len(attempts) < 3:
            raise PermissionError('模拟其他读取器短暂占用注册表')
        return original(path, target)

    monkeypatch.setattr(Path, 'replace', transient_lock)
    initialize_registry([{'id': 'a' * 24, 'name': '甲公司'}], tmp_path)
    assert len(attempts) == 3
    assert read_registry(tmp_path)['pending_queue'] == ['a' * 24]


def test_svg_raster_wrapper_extraction_never_reads_external_images():
    import base64
    from scripts.prepare_company_logos import extract_svg_raster

    encoded = base64.b64encode(png_bytes()).decode('ascii')
    encoded = '\n'.join(encoded[index:index + 50] for index in range(0, len(encoded), 50))
    wrapper = ('<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
               '<svg xmlns="http://www.w3.org/2000/svg"><image href="data:image/png;base64,' + encoded + '"/></svg>')
    assert extract_svg_raster(wrapper.encode()) == png_bytes()
    with pytest.raises(ValueError):
        extract_svg_raster(b'<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///private.png"/></svg>')


def test_failed_registry_publish_keeps_previous_logo_available(tmp_path, monkeypatch):
    from backend import company_logos as logos
    ident = 'a' * 24
    logos.initialize_registry([{'id': ident, 'name': '甲公司'}], tmp_path)
    source = {'page_url': 'https://official.example', 'asset_url': 'https://official.example/logo.png',
              'relationship_url': 'https://official.example', 'relationship_note': '隔离测试'}
    logos.register_verified_logo(tmp_path, [ident], brand='甲品牌', asset_name='brand-a',
                                 content=png_bytes(), source=source, aliases=['甲公司'])
    before = (tmp_path / 'registry.json').read_bytes()
    app = FastAPI()
    logos.attach_company_logos(app, root=tmp_path)

    def fail_publish(*args):
        # 明确隔离的发布失败注入，验证上一版本引用继续可用。
        raise RuntimeError('模拟注册表发布失败')

    monkeypatch.setattr(logos, '_write_registry', fail_publish)
    with pytest.raises(RuntimeError, match='注册表发布失败'):
        logos.register_verified_logo(tmp_path, [ident], brand='甲品牌', asset_name='brand-a',
                                     content=png_bytes((65, 32)), source=source, aliases=['甲公司'])
    assert (tmp_path / 'registry.json').read_bytes() == before
    with TestClient(app) as client:
        response = client.get('/api/company-logos/' + ident)
        assert response.status_code == 200
        assert Image.open(io.BytesIO(response.content)).size == (64, 32)


def test_concurrent_processes_and_threads_preserve_every_brand(tmp_path):
    import subprocess
    import sys
    import time
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    from backend.company_logos import initialize_registry, read_registry, register_verified_logo

    companies = [{'id': f'{index:024x}', 'name': '隔离企业' + str(index)} for index in range(6)]
    initialize_registry(companies, tmp_path)
    worker = '''
import sys,time
from pathlib import Path
from backend.company_logos import register_verified_logo
from tests.test_company_logos import png_bytes
root,index=Path(sys.argv[1]),int(sys.argv[2])
(root / ('ready-' + str(index))).write_text('ready')
deadline=time.monotonic()+15
while not (root / 'start').exists():
    if time.monotonic()>deadline: raise RuntimeError('start timeout')
    time.sleep(.005)
register_verified_logo(root,[f'{index:024x}'],brand='隔离品牌'+str(index),asset_name='process-'+str(index),
content=png_bytes(),source={'page_url':'https://official.example','asset_url':'https://official.example/logo.png',
'relationship_url':'https://official.example','relationship_note':'隔离并发测试'},aliases=[])
'''
    processes = [subprocess.Popen([sys.executable, '-c', worker, str(tmp_path), str(index)],
                                  cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for index in range(4)]
    deadline = time.monotonic() + 15
    try:
        while sum(path.exists() for path in (tmp_path / ('ready-' + str(index)) for index in range(4))) < 4:
            assert time.monotonic() < deadline
            time.sleep(.01)
        (tmp_path / 'start').write_text('start')
        for process in processes:
            _, error = process.communicate(timeout=20)
            assert process.returncode == 0, error.decode(errors='replace')
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    def threaded(index):
        return register_verified_logo(tmp_path, [f'{index:024x}'], brand='隔离品牌' + str(index),
            asset_name='thread-' + str(index), content=png_bytes(), source={
                'page_url': 'https://official.example', 'asset_url': 'https://official.example/logo.png',
                'relationship_url': 'https://official.example', 'relationship_note': '隔离并发测试'}, aliases=[])

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(threaded, [4, 5]))
    result = read_registry(tmp_path)
    assert len(result['companies']) == 6
    assert all(entry['status'] == 'verified' for entry in result['companies'].values())
    assert result['pending_queue'] == []
