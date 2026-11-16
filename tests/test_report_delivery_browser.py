"""Edge 验证图文导出固定情景、字体与窄屏阅读。"""
from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system, route


def test_report_export_freezes_scenario_and_contains_static_charts(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
    page.goto(base)
    assert page.request.post(base + '/api/demo/enter').status == 200
    assert page.request.post(base + '/api/demo/switch', data={'role': 'university'}).status == 200
    page.reload()
    route(page, 'university')
    root = page.locator('#university-report')
    expect(root.locator('[data-action=report-export]')).to_be_visible()
    expect(root.locator('[data-report-chart=forecast] canvas')).to_have_count(1)
    assert root.locator('.report-description').first.evaluate('el=>parseFloat(getComputedStyle(el).fontSize)') >= 14
    expect(root.locator('.report-executive article')).to_have_count(3)
    expect(root.locator('.report-roadmap')).to_contain_text('待补充已确认的实施学期')
    assert '方法与基础' not in root.inner_text()
    root.locator('[data-report-scenario="悲观"]').click()
    with page.expect_popup() as popup_info:
        root.locator('[data-action=report-export]').click()
    exported = popup_info.value
    expect(exported).to_have_url(base + '/assets/report-preview.html')
    expect(exported.get_by_role('button', name='返回诊断报告', exact=True)).to_be_visible()
    expect(exported.locator('[data-export-scenario]')).to_have_attribute('data-export-scenario', '悲观')
    expect(exported.locator('.report-executive')).to_contain_text('悲观情景专业与岗位匹配变化')
    expect(exported.locator('canvas')).to_have_count(0)
    expect(exported.locator('img.report-static-chart')).to_have_count(3)
    assert exported.locator('[data-report-chart]').evaluate_all('hosts=>hosts.every(host=>!host.querySelector("img")||host.querySelector("img").getBoundingClientRect().bottom<=host.getBoundingClientRect().bottom+1)')
    expect(exported.locator('.report-export-resources')).to_contain_text('上限')
    expect(exported.locator('[data-print-report]')).to_be_visible()
    assert exported.locator('.report-executive').evaluate('el=>getComputedStyle(el).display') == 'grid'
    exported.evaluate('window.print=()=>{window.reportPrintInvoked=true}')
    exported.locator('[data-print-report]').click()
    exported.wait_for_function('window.reportPrintInvoked===true')
    assert exported.url != 'about:blank'
    root.locator('[data-report-scenario="乐观"]').click()
    expect(exported.locator('[data-export-scenario]')).to_have_attribute('data-export-scenario', '悲观')
    folder = Path(__file__).resolve().parents[1] / 'runtime' / 'remaining-fixes-20261114' / 'report'
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / 'report-desktop.png'), full_page=True)
    exported.screenshot(path=str(folder / 'export-desktop.png'), full_page=True)
    exported.pdf(path=str(folder / 'report-print.pdf'), print_background=True, format='A4')
    with exported.expect_download() as download_info:
        exported.locator('[data-save-report]').click()
    filename = folder / 'report-fixed-pessimistic.html'
    download_info.value.save_as(str(filename))
    offline = browser.new_page(viewport={'width': 1440, 'height': 900})
    offline.goto(filename.as_uri())
    assert offline.locator('.report-executive').evaluate('el=>getComputedStyle(el).display') == 'grid'
    expect(offline.locator('img.report-static-chart')).to_have_count(3)
    offline.close()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    toggle = page.locator('#agent-toggle')
    assert toggle.evaluate('el=>getComputedStyle(el).position') == 'fixed'
    assert root.bounding_box()['x'] + root.bounding_box()['width'] <= toggle.bounding_box()['x']
    assert toggle.bounding_box()['y'] + toggle.bounding_box()['height'] <= 844
    page.screenshot(path=str(folder / 'report-mobile.png'), full_page=True)
    assert root.locator('.report-description').first.evaluate('el=>parseFloat(getComputedStyle(el).fontSize)') >= 14
    exported.get_by_role('button', name='返回诊断报告', exact=True).click()
    expect(root).to_be_visible()
    assert page.url == base + '/'
    page.close()
