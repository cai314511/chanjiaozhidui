from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route


def test_glass_commands_focus_and_voice_lifecycle(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    register(page, base, 'student', 'glass-student')
    expect(page.locator('.nav-capsule')).to_have_count(1)
    assert '比赛' not in page.locator('#page-content').inner_text()
    page.keyboard.press('Alt+Space')
    expect(page.locator('#command-panel')).to_be_visible()
    page.locator('#command-panel input').fill('资料')
    expect(page.locator('#command-results mark')).to_have_text('资料')
    page.keyboard.press('Enter')
    expect(page.locator('#page-content')).to_contain_text('资料与证据库')
    # 已确认取消卡片放大与模块缩略条；普通导航、弹窗和语音继续可用。
    expect(page.locator('.expand-module')).to_have_count(0)
    expect(page.locator('#focus-stage')).to_have_count(0)
    expect(page.locator('#module-dock')).to_have_count(0)
    route(page, 'profile')
    assert page.locator('#profile-form input[type=number]:visible').count() == 0
    page.locator('[data-action=voice-intro]').first.click()
    expect(page.locator('.water-canvas')).to_be_visible(timeout=20000)
    expect(page.locator('#voice-transcript')).to_be_visible()
    page.locator('#voice-transcript').fill('我完成了一次用户调研，独立整理了访谈记录。')
    page.locator('#voice-send').click()
    expect(page.locator('#voice-error')).to_contain_text('DeepSeek')
    page.locator('[data-action=close-modal]').click()
    expect(page.locator('#modal')).not_to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert errors == []
    page.close()


def test_turquoise_readability_and_moving_water(browser_system):
    from pathlib import Path
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='no-preference')
    register(page, base, 'student', 'turquoise-student')
    route(page, 'profile')
    assert page.locator('.field textarea').first.evaluate('(e)=>parseFloat(getComputedStyle(e).fontSize)') >= 15
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'visual-review'
    root.mkdir(parents=True, exist_ok=True)
    expect(page.locator('.page')).to_have_css('filter', 'none')
    page.screenshot(path=str(root / 'profile.png'))
    page.locator('[data-action=voice-intro]').first.click()
    expect(page.locator('.droplet-stage')).to_have_attribute('data-render', 'ready', timeout=20000)
    first = page.locator('.water-canvas').screenshot()
    page.wait_for_timeout(700)
    second = page.locator('.water-canvas').screenshot()
    assert first != second
    page.screenshot(path=str(root / 'voice.png'))
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.voice-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
    page.screenshot(path=str(root / 'voice-mobile.png'))
    page.close()
