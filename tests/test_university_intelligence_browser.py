"""在隔离数据中走真实CSV聚合、站内发布与教务导入，不模拟图表接口。"""

import csv
import socket
import threading
import time
import uuid
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from backend.app import create_app
from backend.university_intelligence import build_demand, publish_demand
from tests.test_browser import register, route


@pytest.fixture(scope='module')
def university_observatory():
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'university-observatory-browser' / uuid.uuid4().hex
    app = create_app(root)
    # 小型明确标注的隔离CSV输入，使用正式全量解析器计算统计。
    path = root / '隔离历史招聘.csv'
    common = {'企业名称': '隔离农业企业', '招聘岗位': '数据研究员', '上市公司行业': '农业',
              '工作城市': '北京', '最低月薪': '8000', '最高月薪': '10000',
              '职位描述': 'Python、SQL、数据分析', '招聘发布日期': '2026-01-01'}
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(common))
        writer.writeheader()
        writer.writerows([common, {**common, '招聘发布日期': '2026-02-01'},
                          {**common, '企业名称': '隔离医药企业', '上市公司行业': '医药制造业', '工作城市': '上海'},
                          {**common, '企业名称': '隔离未知企业', '上市公司行业': '', '工作城市': '广州'}])
    publish_demand(app.state.store, build_demand([path]))
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
            yield browser, f'http://127.0.0.1:{sock.getsockname()[1]}', root
            browser.close()
    finally:
        server.should_exit = True
        thread.join(10)
        sock.close()


def register_api(context, base, role, name):
    response = context.request.post(base + '/api/auth/register', data={
        'username': name, 'password': 'isolated-browser-1234', 'name': name, 'role': role,
        'company_tracks': ['农业'] if role == 'employer' else [],
    })
    assert response.status == 200, response.text()
    return response.json()


def test_canvas_filters_live_updates_courses_and_university_only_inputs(university_observatory):
    browser, base, root = university_observatory
    school = browser.new_page(viewport={'width': 1440, 'height': 1050})
    school.clock.install()
    errors = []
    school.on('pageerror', lambda error: errors.append(str(error)))
    school.on('console', lambda message: errors.append(message.text) if message.text.startswith('MODULE_LOCATION') else None)
    school.add_init_script("window.addEventListener('error', event=>console.error('MODULE_LOCATION',event.filename,event.lineno,event.colno));")
    school.set_default_timeout(10000)
    try:
        register(school, base, 'university', 'observatory-school')
    except Exception as error:
        raise AssertionError(f'高校注册界面未能就绪：{errors}; {school.locator("body").inner_text()}') from error
    account = school.request.get(base + '/api/auth/me').json()
    employer = browser.new_context()
    register_api(employer, base, 'employer', 'observatory-employer')
    requirements = [{'skill': skill, 'target': 4} for skill in ['Python', 'SQL', '数据分析']]
    job_payload = {'title': '隔离站内数据岗位', 'industry': '农业', 'city': '北京',
                   'salary_min': 10000, 'salary_max': 15000, 'capacity': 2,
                   'description': 'Python、SQL、数据分析', 'requirements': requirements}
    assert employer.request.post(base + '/api/jobs', data=job_payload).status == 200
    for index in range(5):
        student = browser.new_context()
        register_api(student, base, 'student', f'observatory-student-{index}')
        response = student.request.put(base + '/api/profile', data={
            'school_code': account['school_code'], 'career': '农业研究',
            'abilities': {skill: {'level': 2, 'evidence': '隔离教学验证输入'} for skill in ['Python', 'SQL', '数据分析']},
        })
        assert response.status == 200, response.text()
        student.close()
    route(school, 'home')
    root_view = school.locator('#university-intelligence')
    expect(root_view.locator('canvas')).to_have_count(6)
    assert school.evaluate('window.echarts.version') == '6.0.0'
    expect(root_view.locator('.intel-metrics article').nth(0)).to_contain_text('4')
    expect(root_view.locator('.intel-metrics article').nth(1)).to_contain_text('1')
    expect(root_view.locator('[data-intel-chart=radar] canvas')).to_have_count(1)
    expect(root_view.locator('[data-intel-chart=coverage]')).to_contain_text('尚未接入课程与技能映射')
    form = root_view.locator('#university-intel-filter')
    with school.expect_response(lambda response: '/api/university/intelligence?' in response.url and 'track=' in response.url):
        form.locator('[name=track]').select_option('农业')
    expect(root_view.locator('.intel-metrics article').nth(0)).to_contain_text('2')
    form.locator('[name=city]').select_option('上海')
    expect(root_view.locator('.intel-metrics article').nth(0).locator('strong')).to_have_text('0')
    expect(root_view.locator('[data-intel-chart=trend]')).to_contain_text('当前范围没有历史趋势')
    form.locator('[name=city]').select_option('北京')
    expect(root_view.locator('.intel-metrics article').nth(0).locator('strong')).to_have_text('2')
    assert employer.request.post(base + '/api/jobs', data={**job_payload, 'title': '新增真实平台岗位'}).status == 200
    school.locator('[data-action=university-intel-refresh]').click()
    expect(root_view.locator('.intel-metrics article').nth(1).locator('strong')).to_have_text('2')
    school.locator('.intel-next [data-action=university-import]').click()
    import_form = school.locator('#university-import-form')
    import_form.locator('[name=file]').set_input_files({
        'name': '隔离教务课程.csv', 'mimeType': 'text/csv',
        'buffer': '课程代码,课程名称,学分,总学时,能力标签\nC01,数据实践,3,48,Python;SQL;数据分析\n'.encode('utf-8-sig'),
    })
    import_form.locator('[type=submit]').click()
    expect(school.locator('#university-import-error')).to_contain_text('导入')
    school.locator('[data-action=close-modal]').click()
    school.locator('[data-action=university-intel-refresh]').click()
    expect(root_view.locator('[data-intel-chart=coverage] canvas')).to_have_count(1)
    coverage = school.locator('[data-intel-chart=coverage]').evaluate('(el)=>window.echarts.getInstanceByDom(el).getOption().series[0].data')
    assert coverage == [1, 1, 1]
    assert root_view.locator('[data-action=website],[data-action=portfolio-upload]').count() == 0
    school.screenshot(path=str(root / 'dashboard-desktop.png'), full_page=True)
    school.set_viewport_size({'width': 390, 'height': 844})
    school.wait_for_timeout(150)
    assert school.evaluate('document.documentElement.scrollWidth<=innerWidth')
    for canvas in root_view.locator('canvas').all():
        assert canvas.bounding_box()['width'] <= 390
    school.screenshot(path=str(root / 'dashboard-mobile.png'), full_page=True)
    school.set_viewport_size({'width': 1440, 'height': 1050})
    school.evaluate('window.__oldIntelHost=document.querySelector("[data-intel-chart=trend]")')
    route(school, 'curriculum')
    expect(school.locator('#curriculum-form')).to_be_visible()
    assert school.evaluate('window.echarts.getInstanceByDom(window.__oldIntelHost)===undefined')
    assert school.locator('#page-content [data-action=website],#page-content [data-action=portfolio-upload]').count() == 0
    school.locator('[data-action=university-demand-gaps]').click()
    expect(school.locator('.gap-row')).to_have_count(3)
    for gap in school.locator('.gap-row [name=gap-value]').all():
        expect(gap).to_have_value('2')
    school.locator('[data-action=university-course-library]').first.click()
    expect(school.locator('#modal')).to_contain_text('数据实践')
    school.locator('[data-action=university-course-candidate]').click()
    expect(school.locator('.course-card [name=course-name]').last).to_have_value('数据实践')
    expect(school.locator('.course-card [name=course-credits]').last).to_have_value('3')
    curriculum = school.locator('#curriculum-form')
    for name, value in {'cost': '10000', 'credits': '3', 'teacher_hours': '48',
                        'lab_hours': '24', 'study_hours': '72', 'months': '6'}.items():
        curriculum.locator(f'[name=limit-{name}]').fill(value)
    for name, value in {'cost': '5000', 'teacher_hours': '48', 'lab_hours': '24',
                        'study_hours': '72', 'months': '4'}.items():
        curriculum.locator(f'[name=course-{name}]').fill(value)
    for gain in curriculum.locator('[data-gain]').all():
        gain.fill('1.5')
    curriculum.locator('[type=submit]').click()
    expect(school.locator('#curriculum-result')).to_contain_text('数据实践')
    expect(school.locator('#curriculum-result')).to_contain_text('0.5')
    plans = school.request.get(base + '/api/university/plans').json()
    assert len(plans) == 1
    assert plans[0]['result']['benefit'] == 4.5
    assert plans[0]['result']['used']['cost'] == 5000
    # 使用浏览器时钟验证正式60秒刷新器，不替换API或图表数据。
    route(school, 'home')
    expect(root_view.locator('.intel-metrics article').nth(1).locator('strong')).to_have_text('2')
    assert employer.request.post(base + '/api/jobs', data={**job_payload, 'title': '轮询新增岗位'}).status == 200
    school.clock.run_for(60050)
    expect(root_view.locator('.intel-metrics article').nth(1).locator('strong')).to_have_text('3')
    assert errors == [], errors
    employer.close()
    school.close()
