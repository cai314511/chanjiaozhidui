"""隔离构建研究资料，验证真实浏览器操作，不代表正式资料内容验收。"""

import socket
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from backend.app import create_app
from backend.evidence import publish_bundle
from tests.test_browser import register, route


@pytest.fixture(scope='module')
def evidence_browser():
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'evidence-browser' / uuid.uuid4().hex
    app = create_app(root)
    # 专门隔离的界面测试输入，验证分页、筛选和出处展示。
    jobs = [{'id': str(i), 'title': f'AI产品验证岗位{i}', 'city': '北京', 'industry': 'AI产品',
             'month': '2026-03', 'salary': [10000, 15000], 'skills': ['Python'],
             'education': '本科', 'experience': '无需经验', 'description': '隔离界面验收：Python需求分析',
             'provenance': [{'file': '隔离测试.csv', 'line': i + 2}]} for i in range(25)]
    publish_bundle(app.state.store, {'created_at': '2026-11-05', 'scope': '隔离测试', 'inventory': [],
        'recruitment': {'jobs': jobs, 'sources': [], 'scanned_rows': 25, 'duplicate_rows': 0,
                        'invalid_dates': 0, 'scope': '隔离测试样本', 'method': '界面验收'},
        'documents': [{'id': 'test-document', 'title': '隔离产业证据', 'kind': '产业指南', 'status': '已提取',
                       'pages': None, 'basis': '隔离测试资料', 'path': '隔离.docx', 'sha256': 'a' * 64,
                       'blocks': [{'location': '段落1', 'text': '人工智能与产教融合的隔离证据', 'excerpt': False}]}]})
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        thread.join(.05)
    assert server.started
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            yield browser, f'http://127.0.0.1:{sock.getsockname()[1]}'
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_shared_evidence_search_sources_and_mobile(evidence_browser, role):
    browser, base = evidence_browser
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    register(page, base, role, 'evidence-' + role)
    expect(page.locator('.brand h2')).to_have_text('智链产教')
    expect(page.locator('.evidence-teaser')).to_contain_text('25 条相关历史公告')
    route(page, 'evidence')
    expect(page.locator('#evidence-jobs details')).to_have_count(20)
    page.locator('[data-action=evidence-page]').click()
    expect(page.locator('#evidence-jobs details')).to_have_count(5)
    form = page.locator('#evidence-job-filter')
    form.locator('[name=q]').fill('岗位24')
    form.locator('[type=submit]').click()
    expect(page.locator('#evidence-jobs details')).to_have_count(1)
    page.locator('#evidence-jobs summary').click()
    expect(page.locator('#evidence-jobs')).to_contain_text('原CSV第 26 行')
    document_form = page.locator('#evidence-document-filter')
    document_form.locator('[name=q]').fill('产教融合')
    document_form.locator('[type=submit]').click()
    page.locator('[data-action=evidence-document]').click()
    expect(page.locator('#modal')).to_contain_text('段落1')
    expect(page.locator('#modal')).to_contain_text('人工智能与产教融合')
    page.locator('[data-action=close-modal]').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    expect(page.locator('#evidence-job-filter')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('[data-action=evidence-document]').click()
    assert page.locator('#modal').evaluate('(el)=>el.scrollWidth<=el.clientWidth')
    assert errors == [], errors
    page.close()


def test_earlier_search_responses_cannot_replace_newer_results(evidence_browser):
    browser, base = evidence_browser
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    register(page, base, 'student', 'evidence-race-student')
    route(page, 'evidence')
    expect(page.locator('#evidence-jobs details')).to_have_count(20)
    held = []

    def delay_earlier(request_route):
        query = parse_qs(urlsplit(request_route.request.url).query).get('q', [''])[0]
        if query in {'岗位1', '人工智能'}:
            held.append(request_route)
        else:
            request_route.continue_()

    page.route('**/api/evidence/jobs?**', delay_earlier)
    page.route('**/api/evidence/documents?**', delay_earlier)
    for selector, earlier, latest, result_selector, expected in [
        ('#evidence-job-filter', '岗位1', '岗位24', '#evidence-jobs details', 1),
        ('#evidence-document-filter', '人工智能', '不存在的证据', '#evidence-documents article', 0),
    ]:
        form = page.locator(selector)
        form.locator('[name=q]').fill(earlier)
        with page.expect_request(lambda request: parse_qs(urlsplit(request.url).query).get('q') == [earlier]):
            form.locator('[type=submit]').click()
        page.wait_for_timeout(50)
        assert len(held) == 1
        form.locator('[name=q]').fill(latest)
        form.locator('[type=submit]').click()
        expect(page.locator(result_selector)).to_have_count(expected)
        with page.expect_response(lambda response: parse_qs(urlsplit(response.url).query).get('q') == [earlier]):
            held.pop().continue_()
        page.wait_for_timeout(100)
        expect(page.locator(result_selector)).to_have_count(expected)
    page.close()
