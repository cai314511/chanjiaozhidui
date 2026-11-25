"""冷缓存下延迟静态资源，检查首次绘制与功能可用性。"""

from playwright.sync_api import expect

from tests.test_browser import browser_system
from tests.test_voice_synthesis_fallback_browser import SPEECH_DEVICE, open_voice


def test_agent_entry_waits_for_the_role_art(browser_system):
    browser, base = browser_system
    page = browser.new_page()
    page.goto(base)
    assert page.request.post(base + '/api/demo/enter').ok
    assert page.request.post(base + '/api/demo/switch', data={'role': 'student'}).ok
    pending = []
    page.route('**/mascots/student*', lambda req: pending.append(req))
    page.reload(wait_until='domcontentloaded')
    expect(page.locator('.nav')).to_be_visible()
    assert pending
    entry = page.locator('#agent-toggle')
    expect(entry).to_be_hidden(timeout=500)
    for req in pending[:]:
        if req.request.url.endswith('-entry.webp'):
            req.continue_()
    expect(entry).to_have_attribute('data-mascot-role', 'student')
    expect(entry).to_be_visible()
    for req in pending:
        if req.request.url.endswith('.png'):
            req.abort()
    page.close()


def test_voice_first_frame_has_no_old_placeholder(browser_system):
    browser, base = browser_system
    page = browser.new_page()
    page.add_init_script('(' + SPEECH_DEVICE + ')()')
    pending = []
    page.route('**/assets/water-orb.js', lambda req: pending.append(req))
    open_voice(page, base, 'slow-first-water-frame')
    stage = page.locator('.droplet-stage')
    expect(stage).to_be_visible()
    expect(stage.locator('.droplet')).to_be_hidden(timeout=500)
    expect(page.locator('#voice-status')).to_contain_text('正在回答', timeout=2000)
    page.locator('#voice-transcript').fill('三维资源加载时也可以编辑')
    height = stage.evaluate('el=>el.clientHeight')
    assert len(pending) == 1
    pending.pop().continue_()
    expect(stage).to_have_attribute('data-render', 'ready')
    expect(stage.locator('canvas')).to_be_visible()
    assert stage.evaluate('el=>el.clientHeight') == height
    expect(page.locator('#voice-transcript')).to_have_value('三维资源加载时也可以编辑')
    page.close()
