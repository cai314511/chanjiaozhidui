import json
import socket
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from playwright.sync_api import expect, sync_playwright

from backend.app import create_app
from backend.initial_data import initialize


def test_one_login_switches_three_surfaces_and_keeps_context():
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'admin-browser' / uuid.uuid4().hex
    app = create_app(root)
    initialize(app.state.store)
    access = json.loads((root / 'account-access.json').read_text(encoding='utf-8'))[0]
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    base = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic()+15
    while not server.started and time.monotonic() < deadline:
        thread.join(.05)
    assert server.started
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='msedge', headless=True)
            page = browser.new_page(viewport={'width':1440,'height':1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base)
            page.locator('[data-action=admin-login]').click()
            page.locator('#auth-form [name=username]').fill(access['username'])
            page.locator('#auth-form [name=password]').fill(access['password'])
            page.locator('#auth-form [type=submit]').click()
            expect(page.locator('#page-content')).to_contain_text('统一管理入口')
            assert page.locator('#page-content [data-action=admin-enter]').count() == 19
            page.locator('#page-content .panel').filter(has=page.locator('h3', has_text='学生端')).locator('[data-action=admin-enter]').first.click()
            expect(page.locator('#page-content')).to_contain_text('让机会了解你')
            expect(page.locator('.admin-toolbar')).to_contain_text('管理员')
            page.reload()
            expect(page.locator('.admin-toolbar')).to_contain_text('管理员')
            page.locator('.nav [data-id=documents]').click()
            expect(page.locator('#page-content')).to_contain_text('个人简历.md')
            page.locator('[data-action=admin-return]').click()
            expect(page.locator('#page-content')).to_contain_text('统一管理入口')
            page.locator('#page-content .panel').filter(has=page.locator('h3', has_text='高校端')).locator('[data-action=admin-enter]').first.click()
            expect(page.locator('#page-content')).to_contain_text('学生能力汇总')
            page.locator('[data-action=admin-switch]').click()
            page.locator('#modal .panel').filter(has=page.locator('h3', has_text='企业端')).locator('[data-action=admin-enter]').click()
            expect(page.locator('#page-content')).to_contain_text('等待企业发布岗位')
            page.locator('[data-action=admin-return]').click()
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert errors == [], errors
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()
