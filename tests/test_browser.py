import socket
import threading
import time
import uuid
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from backend.app import create_app


@pytest.fixture(scope="module")
def browser_system():
    root = Path(__file__).resolve().parents[1] / "runtime" / "browser" / uuid.uuid4().hex
    app = create_app(root)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        thread.join(.05)
    assert server.started
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge", headless=True)
        yield browser, f"http://127.0.0.1:{port}"
        browser.close()
    server.should_exit = True
    thread.join(10)
    sock.close()


def register(page, base, role, name, dismiss_exploration=True):
    page.goto(base)
    page.locator('.topbar [data-action="register"]').click()
    form = page.locator('#auth-form')
    form.locator('[name=username]').fill(name)
    form.locator('[name=password]').fill('browser-test-1234')
    form.locator('[name=name]').fill(name)
    form.locator('[name=role]').select_option(role)
    if role == 'employer':
        form.locator('#company-track-input').fill('AI产品')
    form.locator('[type=submit]').click()
    expect(page.locator('#modal')).not_to_be_visible()
    if role == 'student' and dismiss_exploration:
        expect(page.locator('#exploration-dialog')).to_be_visible()
        page.locator('[data-action=explore-skip][aria-label="跳过探索"]').click()


def route(page, name):
    page.locator(f'.nav [data-id="{name}"]').click()


def test_real_browser_three_surfaces_and_live_weights(browser_system):
    browser, base = browser_system
    errors = []
    employer = browser.new_page(viewport={"width": 1440, "height": 1000})
    employer.on("pageerror", lambda err: errors.append(str(err)))
    register(employer, base, 'employer', 'browser-company')
    route(employer, 'jobs')
    employer.locator('[data-action="new-job"]').first.click()
    form = employer.locator('#job-form')
    for key, value in {"title": "AI产品验证岗位", "city": "北京", "salary_min": "10000", "salary_max": "20000", "description": "隔离浏览器验收数据：负责产品方案和用户验证"}.items():
        form.locator(f'[name="{key}"]').fill(value)
    form.locator('.requirement-row [name=skill]').fill('产品设计')
    form.locator('[data-action="add-requirement"]').click()
    form.locator('.requirement-row').nth(1).locator('[name=skill]').fill('数据分析')
    form.locator('[data-action="add-question"]').click()
    form.locator('[name=qskill]').fill('产品设计')
    form.locator('[name=qtitle]').fill('请设计用户访谈与产品验证方案')
    form.locator('[name=rubric]').fill('1级了解概念，3级能独立设计验证，5级能创新实验方法')
    form.locator('[type=submit]').click()
    expect(employer.locator('.job-card h3')).to_have_text('AI产品验证岗位')

    student = browser.new_page()
    student.on("pageerror", lambda err: errors.append(str(err)))
    register(student, base, 'student', 'browser-student')
    route(student, 'profile')
    profile = student.locator('#profile-form')
    profile.locator('[name=major]').fill('经济学')
    profile.locator('[name=experience]').fill('隔离验收经历：完成用户访谈并设计产品验证方案')
    profile.locator('[type=submit]').click()
    expect(student.locator('#toast')).to_contain_text('画像已保存')
    # 通过真实画像接口写入隔离验收所用的已整理能力，计算结果仍使用正式算法。
    response = student.request.put(base+'/api/profile', data={'major': '经济学', 'abilities': {'产品设计': {'level': 5, 'evidence': '隔离验收的项目经历'}}})
    assert response.status == 200
    route(student, 'jobs')
    student.locator('[data-action="student-match"]').click()
    expect(student.locator('#modal')).to_contain_text('双向匹配度')
    expect(student.locator('#modal .match-art')).to_be_visible()
    student.locator('[data-action="apply-dialog"]').click()
    student.locator('#apply-form [name=consent]').check()
    student.locator('#apply-form [type=submit]').click()
    expect(student.locator('.job-card h3')).to_have_text('AI产品验证岗位')
    student.locator('[data-action="answer"]').click()
    student.locator('#answer-form textarea').fill('我会先访谈目标用户，定义转化指标，再通过对照实验验证产品方案。')
    student.locator('#answer-form [type=submit]').click()
    expect(student.locator('#modal')).not_to_be_visible()

    employer.reload()
    route(employer, 'applications')
    employer.locator('[data-action="review"]').click()
    question_id = employer.locator('#review-form .question small').inner_text().split(' · ')[0]
    review = employer.locator('#review-form')
    review.locator('[name=review_0]').check()
    review.locator('[name=level_0]').fill('4')
    review.locator('[name=evidence_0]').fill(question_id+'：给出访谈和对照实验，并定义转化指标')
    review.locator('[type=submit]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    route(employer, 'weights')
    before = student.request.get(base+'/api/applications').json()[0]['match']['provisional']
    employer.locator('#priority-form select').first.select_option('优先考虑')
    employer.locator('#priority-form select').nth(1).select_option('一般关注')
    employer.locator('#priority-form [type=submit]').click()
    expect(employer.locator('#toast')).to_contain_text('招聘偏好已更新')
    after = student.request.get(base+'/api/applications').json()[0]['match']['provisional']
    assert after != before
    assert employer.locator('#priority-form input[type=number]').count() == 0

    university = browser.new_page()
    university.on("pageerror", lambda err: errors.append(str(err)))
    register(university, base, 'university', 'browser-university')
    route(university, 'university')
    expect(university.locator('#page-content')).to_contain_text('等待足够的本校样本')
    route(university, 'curriculum')
    form = university.locator('#curriculum-form')
    form.locator('[name=gap-skill]').fill('产品设计')
    form.locator('[name=gap-value]').fill('2')
    for name, value in {"cost": "10000", "credits": "3", "teacher_hours": "40", "lab_hours": "20", "study_hours": "60", "months": "6"}.items():
        form.locator(f'[name="limit-{name}"]').fill(value)
    form.locator('[data-action="add-course"]').click()
    for name, value in {"name": "产品实践课", "cost": "5000", "credits": "2", "teacher_hours": "20", "lab_hours": "10", "study_hours": "30", "months": "3"}.items():
        form.locator(f'[name="course-{name}"]').fill(value)
    form.locator('[data-gain="产品设计"]').fill('1.5')
    form.locator('[type=submit]').click()
    expect(university.locator('#curriculum-result')).to_contain_text('产品实践课')
    expect(university.locator('#curriculum-result')).to_contain_text('0.5')

    for page, mobile_routes in [(employer, ['jobs', 'weights', 'applications', 'allocation']),
                                (student, ['profile', 'jobs', 'applications', 'curriculum']),
                                (university, ['university', 'curriculum', 'documents'])]:
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.set_viewport_size({"width": 390, "height": 844})
        page.reload()
        home=page.locator('#university-intelligence') if page is university else page.locator('.recruiting-hero') if page is employer else page.locator('#discovery-form')
        expect(home).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.locator('[data-action="mobile-menu"]').click()
        expect(page.locator('#sidebar')).to_have_class('sidebar open')
        for name in mobile_routes:
            if 'open' not in page.locator('#sidebar').get_attribute('class'):
                page.locator('[data-action="mobile-menu"]').click()
            route(page, name)
            expect(page.locator('#page-content .loading')).to_have_count(0)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), name
        if page == employer:
            page.locator('[data-action="mobile-menu"]').click()
            route(page, 'jobs')
            page.locator('[data-action="edit-job"]').click()
            expect(page.locator('.dialog-head h2')).to_have_text('编辑岗位与测评')
            assert page.locator('#job-form [name=title]').input_value() == 'AI产品验证岗位'
            page.locator('[data-action="close-modal"]').first.click()
    assert errors == []
    for page in [employer, student, university]:
        page.close()
