"""模型响应在界面单测中隔离；真实 DeepSeek 在独立验收中调用。"""
import pytest
from playwright.sync_api import expect

from tests.test_browser import browser_system, register
from tests.test_browser import route as navigate_route


@pytest.mark.parametrize('role,mode,label', [
    ('student', 'profile', '个人材料'),
    ('employer', 'job', '岗位草稿'),
    ('university', 'curriculum', '培养建议'),
])
def test_prominent_orb_modes_and_outside_close_preserve_question(browser_system, role, mode, label):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    pending = []
    page.route('**/api/agent/run', lambda route: pending.append(route))
    register(page, base, role, 'mode-navigation-' + role)
    page.locator('#agent-toggle').click()
    drawer = page.locator('#agent-drawer')
    tabs = drawer.get_by_role('tablist', name='助手模式')
    expect(tabs).to_be_visible()
    expect(tabs.get_by_role('tab', name='聊天咨询')).to_have_attribute('aria-selected', 'true')
    orb = drawer.locator('.agent-orb-stage')
    expect(orb).to_have_attribute('data-render', 'ready')
    box, outer = orb.bounding_box(), drawer.bounding_box()
    assert box['width'] >= 140
    assert abs(box['x'] + box['width'] / 2 - outer['x'] - outer['width'] / 2) < 20
    assert drawer.locator('.drawer-head .agent-orb-stage').count() == 0
    drawer.locator('textarea').fill('保留未发送问题')
    tabs.get_by_role('tab', name=label).click()
    expect(drawer.locator('[name=mode]')).to_have_value(mode)
    expect(drawer.locator('#agent-mode-description')).not_to_be_empty()
    expect(drawer.locator('textarea')).to_have_value('保留未发送问题')
    drawer.locator('textarea').press('Enter')
    expect(orb).to_have_attribute('data-mode', 'thinking')
    expect(tabs.get_by_role('tab', name='聊天咨询')).to_be_disabled()
    assert len(pending) == 1 and pending[0].request.post_data_json['mode'] == mode
    pending.pop().fulfill(json={'message': '隔离模式测试回复', 'draft': None, 'trace': [], 'model': '界面替身', 'elapsed': .1})
    expect(drawer.locator('#agent-messages')).to_contain_text('隔离模式测试回复')
    drawer.locator('textarea').fill('关闭后继续写')
    page.mouse.click(700, 100)
    expect(drawer).not_to_be_visible()
    page.locator('#agent-toggle').click()
    expect(drawer.locator('textarea')).to_have_value('关闭后继续写')
    page.set_viewport_size({'width': 390, 'height': 844})
    assert drawer.evaluate('(el)=>el.scrollHeight<=el.clientHeight+1')
    input_box = drawer.locator('textarea').bounding_box()
    assert input_box['y'] + input_box['height'] < 844
    page.close()


def test_shared_dialog_backdrop_keeps_form_draft_and_search_closes(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.goto(base)
    page.locator('.topbar [data-action=register]').click()
    modal = page.locator('#modal')
    field = modal.locator('[name=username]')
    field.fill('keep-local-draft')
    modal.locator('[name=password]').fill('not-persisted-password')
    page.mouse.click(6, 100)
    expect(modal).not_to_be_visible()
    page.locator('.topbar [data-action=register]').click()
    expect(modal.locator('[name=username]')).to_have_value('keep-local-draft')
    expect(modal.locator('[name=password]')).to_have_value('')
    page.mouse.click(6, 100)
    page.locator('[data-action=commands]').first.click()
    expect(page.locator('#command-panel')).to_be_visible()
    page.mouse.click(6, 100)
    expect(page.locator('#command-panel')).not_to_be_visible()
    page.close()


@pytest.mark.parametrize('role,label', [('student', '学生端'), ('employer', '企业端'), ('university', '高校端')])
def test_chat_uses_general_guidance_without_forced_material_tool(monkeypatch, role, label):
    from backend import agent

    sent = []

    class IsolatedResponse:
        status_code = 200

        def json(self):
            return {'choices': [{'message': {'content': '{"message":"你好，可以先告诉我你的目标。","draft":null}'}}], 'usage': {'total_tokens': 12}}

    class IsolatedClient:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            sent.append(kwargs['json'])
            return IsolatedResponse()

    monkeypatch.setattr(agent, 'configuration', lambda: {'key': 'isolated-key', 'model': 'isolated-model', 'base': 'https://isolated.invalid'})
    monkeypatch.setattr(agent.httpx, 'Client', IsolatedClient)
    result = agent.run_agent('你好', {'mode': 'chat', 'role': role, 'documents': []})
    assert result['message'].startswith('你好')
    assert sent[0]['tool_choice'] == 'auto'
    assert '通用问题' in sent[0]['messages'][0]['content']
    assert label in sent[0]['messages'][0]['content']


def test_enter_sends_direct_message(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    assert page.request.post(base + '/api/demo/enter').status == 200
    assert page.request.post(base + '/api/demo/switch', data={'role': 'employer'}).status == 200
    page.goto(base)
    navigate_route(page, 'students')
    page.locator('[data-action=candidate-detail]').first.click()
    page.locator('#modal [data-action=contact-person]').click()
    field = page.locator('#direct-message-form textarea')
    field.fill('回车发送站内消息')
    field.press('Shift+Enter')
    expect(field).to_have_value('回车发送站内消息\n')
    field.press('Enter')
    expect(page.locator('.direct-bubble').last).to_contain_text('回车发送站内消息')
    page.close()


def test_voice_text_enter_keeps_consent_guard_and_outside_close_keeps_transcript(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.route('**/api/voice/speak', lambda route: route.fulfill(status=503, json={'detail': '隔离播报，不测试扬声器'}))
    sent = []

    def fail_turn(route):
        sent.append(route.request.post_data_json)
        route.fulfill(status=503, json={'detail': '隔离接口失败'})

    page.route('**/api/interviews/*/turn', fail_turn)
    register(page, base, 'student', 'voice-enter-consent')
    navigate_route(page, 'profile')
    with page.expect_response(lambda response: response.url.endswith('/api/interviews') and response.request.method == 'POST') as pending:
        page.locator('[data-action=voice-intro]').first.click()
    ident = pending.value.json()['id']
    transcript = page.locator('#voice-transcript')
    expect(transcript).to_be_visible()
    expect(page.locator('#voice-error')).to_contain_text('隔离播报')
    transcript.fill('关闭后保留本轮转写')
    page.mouse.click(5, 150)
    expect(page.locator('#modal')).not_to_be_visible()
    page.evaluate("async id=>{const {actions}=await import('/assets/core.js');await actions['join-interview']({dataset:{id}})}", ident)
    expect(transcript).to_have_value('关闭后保留本轮转写')
    expect(page.locator('#voice-error')).to_contain_text('隔离播报')
    transcript.press('Enter')
    expect(page.locator('#voice-error')).to_contain_text('请确认允许')
    assert sent == []
    page.locator('#voice-consent').check()
    transcript.press('Enter')
    expect(page.locator('#voice-error')).to_contain_text('隔离接口失败')
    assert len(sent) == 1 and sent[0]['text'] == '关闭后保留本轮转写' and sent[0]['consent'] is True
    page.mouse.click(5, 150)
    expect(page.locator('#modal')).not_to_be_visible()
    page.close()
