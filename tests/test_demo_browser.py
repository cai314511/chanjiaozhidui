from pathlib import Path

from playwright.sync_api import expect

from tests.test_browser import browser_system, route


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
