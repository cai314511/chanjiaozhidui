"""真实Edge验收报告引用；业务输入全部保存在browser_system的隔离目录。"""
from playwright.sync_api import expect
from pathlib import Path

from tests.test_browser import browser_system, register, route
from tests.test_university_flow_fixes import optimization_input


def test_optimization_report_button_history_gap_and_identity(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    register(page, base, 'university', 'flow-report-school')
    route(page, 'curriculum')
    payload = optimization_input()
    page.locator('[name=gap-skill]').fill('SQL')
    page.locator('[name=gap-value]').fill('2')
    for key, value in payload['limits'].items():
        page.locator('[name=limit-' + key + ']').fill(str(value))
    page.locator('[data-action=add-course]').click()
    course = payload['courses'][0]
    page.locator('[name=course-name]').fill(course['name'])
    for key in payload['limits']:
        page.locator('[name=course-' + key + ']').fill(str(course[key]))
    page.locator('[data-gain=SQL]').fill('1')
    page.locator('#curriculum-form [type=submit]').click()
    entry = page.locator('#curriculum-result [data-action=university-selected-report]')
    expect(entry).to_be_visible()
    ident = entry.get_attribute('data-id')
    entry.click()
    root = page.locator('#university-report')
    expect(root.locator('.report-source-strip')).to_have_attribute('data-report-reference', ident)
    expect(root.locator('.report-action')).to_contain_text('SQL实践')
    expect(root.locator('.report-action')).to_contain_text('待补充 学时')
    expect(root.locator('.report-action')).to_contain_text('原课程结构尚未登记')
    expect(root.locator('[data-report-chart=skills]')).to_have_attribute('aria-label', 'SQL，原始缺口2，剩余缺口1')
    expect(root.locator('[data-metric=cost] .report-after')).to_contain_text('500')
    expect(root.locator('[data-report-chart=resources] canvas')).to_have_count(1)
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'university-flow-fixes'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / 'optimization-desktop.png'), full_page=True)
    route(page, 'curriculum')
    page.locator('[data-action=plan-detail][data-id="' + ident + '"]').click()
    page.locator('#modal [data-action=university-selected-report]').click()
    expect(root.locator('.report-source-strip')).to_have_attribute('data-report-reference', ident)
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(folder / 'optimization-mobile.png'), full_page=True)
    page.evaluate("window.dispatchEvent(new Event('identity-reset'))")
    with page.expect_response(lambda response: response.url.endswith('/api/university/report')):
        page.locator('[data-action=reload]').click()
    expect(root.locator('.report-source-strip')).to_have_attribute('data-report-reference', '')
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.locator('[data-action=logout]').click()
    expect(page.locator('.topbar [data-action=register]')).to_be_visible()
    register(page, base, 'university', 'flow-report-other-school')
    route(page, 'university')
    expect(root.locator('.report-source-strip')).to_have_attribute('data-report-reference', '')
    expect(root.locator('.report-action')).to_have_count(0)
    assert errors == []
    page.close()


def test_decision_view_a_and_execute_b_keep_selected_run(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto(base)
    assert page.request.post(base + '/api/demo/enter').status == 200
    assert page.request.post(base + '/api/demo/switch', data={'role': 'university'}).status == 200
    cases = page.request.get(base + '/api/competition/cases').json()
    first = page.request.post(base + '/api/competition/cases/' + cases[0]['id'] + '/run').json()
    second = page.request.post(base + '/api/competition/cases/' + cases[0]['id'] + '/run').json()
    page.reload()
    route(page, 'decision')
    page.locator('[data-action=decision-result][data-id="' + first['id'] + '"]').click()
    expect(page.locator('#decision-output')).not_to_be_empty()
    route(page, 'university')
    expect(page.locator('.report-source-strip')).to_have_attribute('data-report-reference', first['id'])
    route(page, 'decision')
    page.locator('[data-action=decision-run]').first.click()
    entry = page.locator('#decision-output [data-action=university-selected-report]')
    expect(entry).to_be_visible()
    newest = entry.get_attribute('data-id')
    assert newest not in [first['id'], second['id']]
    entry.click()
    expect(page.locator('.report-source-strip')).to_have_attribute('data-report-reference', newest)
    page.close()
