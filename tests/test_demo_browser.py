from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system, route


def test_employer_demo_readiness_comparison_and_download(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1365, 'height': 920}, reduced_motion='reduce')
    # 公网 HTTP 上不提供 crypto.randomUUID，文字业务应该照常完成。
    page.add_init_script("Object.defineProperty(Crypto.prototype, 'randomUUID', {value: undefined})")
    page.goto(base)
    assert page.request.post(base + '/api/demo/enter').ok
    assert page.request.post(base + '/api/demo/switch', data={'role': 'employer'}).ok
    page.reload()
    expect(page.locator('.nav [data-id=weights]')).to_have_count(0)
    page.locator('.recruiting-hero [data-action=new-job]').click()
    page.locator('#job-form [data-action=add-question]').click()
    expect(page.locator('#job-form .question-row')).to_have_count(1)
    page.locator('#job-form [name=skill]').fill('数据分析')
    page.locator('#job-form [data-action=fill-missing-questions]').click()
    expect(page.locator('#job-form .question-row').last.locator('[name=qskill]')).to_have_value('数据分析')
    page.locator('#modal [data-action=close-modal]').first.click()
    route(page, 'jobs')
    job = page.locator('.recruiting-job-list .job-card').filter(
        has=page.get_by_role('heading', name='AI产品经理', exact=True))
    job.locator('[data-action=candidate-job]').click()
    expect(page.locator('#candidate-job-filter')).to_have_value('demo-job-0')
    expect(page.locator('.candidate-job-row strong')).to_have_text(['AI产品经理'] * 9)
    page.locator('[data-action=route][data-id=allocation]').last.click()
    expect(page.locator('#allocation-readiness')).to_contain_text('可纳入分配')
    form = page.locator('#allocation-form')
    for version, budget in [(1, '150000'), (2, '30000')]:
        form.locator('[name=salary]').fill(budget)
        form.locator('[type=submit]').click()
        expect(page.locator('#allocation-result h3').get_by_text(f'招聘计划 v{version}', exact=True)).to_be_visible()
    page.locator('[data-action=compare-plans]').click()
    expect(page.locator('#plan-comparison')).to_contain_text('移出建议')
    expect(page.locator('#plan-comparison')).to_contain_text('月度薪资预算余额不足')
    expect(page.locator('#toast')).not_to_have_class('show', timeout=6000)
    evidence = Path('runtime/recruiting-core-review')
    evidence.mkdir(parents=True, exist_ok=True)
    page.locator('#plan-comparison').scroll_into_view_if_needed()
    page.screenshot(path=str(evidence / '招聘计划预算对比.png'))
    with page.expect_download() as event:
        page.get_by_role('link', name='导出计划 Excel').first.click()
    assert event.value.suggested_filename.endswith('.xlsx')
    event.value.save_as(str(evidence / '企业招聘计划-演示验收.xlsx'))
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#allocation-readiness').scroll_into_view_if_needed()
    page.screenshot(path=str(evidence / '招聘分配-移动端.png'))
    page.close()


def test_demo_role_pages_and_private_message_flow(browser_system):
    browser,base=browser_system
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    page.goto(base)
    page.locator('.discovery-hero [data-action=demo-enter]').click()
    expect(page.locator('.demo-toolbar')).to_be_visible(timeout=60000)
    page.locator('[data-action=demo-role][data-id=employer]').click()
    expect(page.locator('.recruiting-chart canvas')).to_have_count(2,timeout=30000)
    route(page,'students')
    expect(page.locator('.student-card')).to_have_count(15)
    page.locator('[data-action=candidate-detail]').first.click()
    expect(page.locator('#modal')).to_be_visible()
    expect(page.locator('#modal [data-action=space-public-document]')).not_to_have_count(0)
    page.locator('#modal [data-action=contact-person]').click()
    expect(page.locator('#direct-message-form')).to_be_visible()
    page.locator('#direct-message-form textarea').fill('期待进一步交流项目设计')
    page.locator('#direct-message-form button[type=submit]').click()
    expect(page.locator('.direct-bubble').last).to_contain_text('期待进一步交流项目设计')
    page.locator('[data-action=demo-role][data-id=university]').click()
    expect(page.locator('[data-intel-chart] canvas').first).to_be_visible(timeout=30000)
    for target in ['research','decision','curriculum','documents','evidence']:
        route(page,target)
        expect(page.locator('#page-content')).not_to_contain_text('读取未完成')
        expect(page.locator('.demo-toolbar')).to_be_visible()
    folder=Path('runtime/demo-review');folder.mkdir(parents=True,exist_ok=True)
    page.locator('[data-action=demo-role][data-id=employer]').click()
    expect(page.locator('.recruiting-chart canvas')).to_have_count(2)
    page.screenshot(path=str(folder/'employer-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('.demo-toolbar')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(folder/'employer-mobile.png'),full_page=True)
    page.locator('[data-action=demo-exit]').click()
    expect(page.locator('.discovery-hero')).to_be_visible()
    assert not errors,errors
    page.close()
