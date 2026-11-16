"""键盘、输入法和遮罩关闭回归；模型替身仅隔离界面行为，真实模型另验。"""
import pytest
from playwright.sync_api import expect

from tests.test_browser import browser_system, register


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_desktop_enter_sends_once_and_shift_enter_and_ime_do_not_send(browser_system, role):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    requests = []

    def reply(route):
        requests.append(route.request.post_data_json)
        route.fulfill(json={'message': '隔离键盘测试回复', 'draft': None, 'trace': [], 'model': '界面测试替身', 'elapsed': .1})

    page.route('**/api/agent/run', reply)
    register(page, base, role, 'keyboard-' + role)
    page.locator('#agent-toggle').click()
    field = page.locator('#agent-form textarea')
    field.fill('第一行')
    field.press('Shift+Enter')
    expect(field).to_have_value('第一行\n')
    field.dispatch_event('keydown', {'key': 'Enter', 'code': 'Enter', 'isComposing': True})
    field.dispatch_event('keydown', {'key': 'Enter', 'code': 'Enter', 'keyCode': 229})
    assert requests == []
    field.fill('确认发送')
    field.press('Enter')
    expect(page.locator('#agent-messages')).to_contain_text('隔离键盘测试回复')
    assert [request['message'] for request in requests] == ['确认发送']
    page.close()


def test_exploration_backdrop_closes_after_scrolling_and_keeps_answers(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    register(page, base, 'student', 'exploration-backdrop', dismiss_exploration=False)
    modal = page.locator('#exploration-dialog')
    modal.locator('[data-action=guide-select]').filter(has_text='技术与创造').click()
    modal.locator('#guide-text').fill('保留本次探索补充')
    # 点击内部不关闭；拖拽从内部到外部不误关闭。
    modal.locator('h2').click()
    box = modal.bounding_box()
    page.mouse.move(box['x'] + box['width'] / 2, box['y'] + 45)
    page.mouse.down()
    page.mouse.move(8, 200)
    page.mouse.up()
    expect(modal).to_be_visible()
    page.mouse.click(8, 200)
    expect(modal).not_to_be_visible()
    progress = page.request.get(base + '/api/me/exploration').json()
    assert progress['answers']['interests'] == ['技术与创造']
    assert progress['text'] == '保留本次探索补充'
    page.locator('#discovery-form [data-action=exploration-start]').click()
    for choice in ['技术与创造', '写代码与做产品', '科技研发']:
        button = modal.locator('[data-action=guide-select]').filter(has_text=choice)
        if button.get_attribute('aria-pressed') != 'true':
            button.click()
        modal.locator('[data-action=guide-next]').click()
    expect(modal).to_contain_text('这些方向，值得先了解一下')
    for viewport in [{'width': 1440, 'height': 900}, {'width': 390, 'height': 844}]:
        page.set_viewport_size(viewport)
        modal.evaluate('(el)=>el.scrollTop=el.scrollHeight')
        page.mouse.click(5, 200)
        expect(modal).not_to_be_visible()
        page.locator('#discovery-form [data-action=exploration-start]').click()
        if viewport['width'] == 1440:
            for _ in range(3):
                modal.locator('[data-action=guide-next]').click()
            expect(modal).to_contain_text('这些方向，值得先了解一下')
    expect(modal).to_be_visible()
    page.keyboard.press('Escape')
    expect(modal).not_to_be_visible()
    page.close()


def test_touch_keyboard_enter_keeps_newline(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True)
    register(page, base, 'student', 'touch-enter')
    page.locator('#agent-toggle').click()
    field = page.locator('#agent-form textarea')
    field.fill('手机输入')
    field.press('Enter')
    expect(field).to_have_value('手机输入\n')
    page.close()
