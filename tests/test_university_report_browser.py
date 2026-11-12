"""真实Canvas报告、情景切换及三端助手的首屏可交互性。"""
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route


def assert_input_visible(page):
    for selector in ['#agent-form textarea', '#agent-form .agent-speech', '#agent-form [type=submit]']:
        box = page.locator(selector).bounding_box()
        assert box and box['y'] >= 0 and box['y'] + box['height'] <= page.viewport_size['height'], (selector, box)
        assert page.locator(selector).evaluate('el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}')


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_agent_input_stays_visible_with_history_and_expanded_settings(browser_system, role):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1280, 'height': 720})
    register(page, base, role, 'visible-composer-' + role)
    page.locator('#agent-toggle').click()
    assert_input_visible(page)
    assert page.locator('#agent-form textarea').evaluate('el=>document.activeElement===el')
    page.locator('#agent-form details summary').click()
    page.locator('#agent-messages').evaluate("el=>el.innerHTML='<p>很长的历史消息</p>'.repeat(100)")
    assert_input_visible(page)
    for size in [{'width': 390, 'height': 844}, {'width': 844, 'height': 390}]:
        page.set_viewport_size(size)
        assert_input_visible(page)
    page.close()


def test_report_canvas_scenarios_curriculum_and_mobile(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    errors = []
    page.on('pageerror', lambda err: errors.append(str(err)))
    page.goto(base)
    assert page.request.post(base + '/api/demo/enter').status == 200
    assert page.request.post(base + '/api/demo/switch', data={'role': 'university'}).status == 200
    page.reload()
    route(page, 'university')
    root = page.locator('#university-report')
    expect(root).to_be_visible()
    expect(root.locator('.report-metric')).to_have_count(5)
    expect(root.locator('[data-report-scenario]')).to_have_count(3)
    expect(root.locator('[data-report-scenario="基准"]')).to_have_attribute('aria-pressed', 'true')
    expect(root.locator('[data-report-chart="forecast"] canvas')).to_have_count(1)
    expect(root.locator('[data-report-chart="skills"] canvas')).to_have_count(1)
    expect(root.locator('[data-report-chart="resources"] canvas')).to_have_count(1)
    expect(root.locator('.report-action')).to_contain_text('综合实践')
    expect(root.locator('[data-metric="related"]')).to_contain_text('70')
    root.locator('[data-report-scenario="悲观"]').click()
    expect(root.locator('[data-report-scenario="悲观"]')).to_have_attribute('aria-pressed', 'true')
    expect(root.locator('#report-forecast-caption')).to_contain_text('悲观')
    data = root.locator('[data-report-chart="forecast"]').evaluate('(el)=>echarts.getInstanceByDom(el).getOption().series[1].data')
    report = page.request.get(base + '/api/university/report').json()
    pessimistic = next(s for s in report['scenarios'] if s['name'] == '悲观')
    assert data == [y['match_after'] for y in pessimistic['years']]
    root.locator('[data-forecast-metric="employment"]').click()
    employment_data = root.locator('[data-report-chart="forecast"]').evaluate('(el)=>echarts.getInstanceByDom(el).getOption().series[1].data')
    assert employment_data == [round(y['employment_after'] * 100, 3) for y in pessimistic['years']]
    root.locator('[data-forecast-metric="admissions"]').click()
    admissions_data = root.locator('[data-report-chart="forecast"]').evaluate('(el)=>echarts.getInstanceByDom(el).getOption().series[1].data')
    assert admissions_data == [y['admissions_after'] for y in pessimistic['years']]
    root.locator('[data-forecast-metric="match"]').click()
    related_after = root.locator('[data-metric="related"] .report-after').inner_text()
    assert '待跟踪' in related_after
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'university-report-review'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / 'report-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.wait_for_timeout(200)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    for canvas in root.locator('canvas').all():
        assert canvas.bounding_box()['width'] <= 390
    page.screenshot(path=str(folder / 'report-mobile.png'), full_page=True)
    page.evaluate('window.oldReport=document.querySelector("[data-report-chart=forecast]")')
    page.locator('#agent-toggle').click()
    assert_input_visible(page)
    page.screenshot(path=str(folder / 'assistant-mobile.png'))
    page.locator('[data-action=close-agent]').click()
    page.set_viewport_size({'width': 1440, 'height': 1000})
    route(page, 'home')
    expect(page.locator('#university-intelligence')).to_be_visible()
    assert page.evaluate('echarts.getInstanceByDom(window.oldReport)===undefined')
    assert errors == []
    page.close()
