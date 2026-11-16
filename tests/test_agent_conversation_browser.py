"""界面响应使用显式模型替身；后端权限及存储另测。"""
import pytest
from pathlib import Path
from playwright.sync_api import expect
from tests.test_browser import browser_system, register


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_result_replaces_orb_and_actions(browser_system, role):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    pending, deleted = [], []
    page.route('**/api/agent/run', lambda route: pending.append(route))
    page.route('**/api/agent/history/*', lambda route: (deleted.append(route.request.url), route.fulfill(json={'status': 'withdrawn'})))
    register(page, base, role, 'conversation-' + role)
    page.locator('#agent-toggle').click()
    drawer = page.locator('#agent-drawer')
    field = drawer.locator('textarea')
    field.fill('第一轮问题')
    field.press('Enter')
    expect(drawer).to_have_attribute('data-view', 'thinking')
    pending.pop().fulfill(json={'id': 'run-1', 'message': '详细回答\n' * 40, 'draft': None, 'trace': [], 'model': 'isolated', 'elapsed': .1})
    expect(drawer).to_have_attribute('data-view', 'conversation')
    expect(drawer.locator('.agent-orb-wrap')).not_to_be_visible()
    assert drawer.locator('#agent-messages').bounding_box()['height'] >= 280
    page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
    drawer.get_by_role('button', name='复制回复', exact=True).click()
    expect(page.locator('#toast')).to_contain_text('已复制')
    assert page.evaluate('navigator.clipboard.readText()').replace('\r\n', '\n') == '详细回答\n' * 40
    drawer.get_by_role('button', name='追问这条回复', exact=True).click()
    expect(drawer.locator('.agent-followup')).to_be_visible()
    field.fill('第二轮问题')
    expect(drawer).to_have_attribute('data-view', 'composing')
    drawer.get_by_role('button', name='查看历史对话', exact=True).click()
    expect(drawer.locator('#agent-messages')).to_contain_text('第一轮问题')
    field.press('Enter')
    expect(drawer).to_have_attribute('data-view', 'thinking')
    assert pending[-1].request.post_data_json['parent_run_id'] == 'run-1'
    pending.pop().fulfill(json={'id': 'run-2', 'message': '第二轮回答', 'draft': None, 'trace': [], 'model': 'isolated', 'elapsed': .1})
    expect(drawer).to_have_attribute('data-view', 'conversation')
    expect(drawer.locator('#agent-messages')).to_contain_text('第一轮问题')
    drawer.get_by_role('button', name='撤回这条问答', exact=True).last.click()
    expect(drawer.locator('#agent-messages')).not_to_contain_text('第二轮回答')
    expect(drawer.locator('#agent-messages')).not_to_contain_text('第二轮问题')
    assert len(deleted) == 1
    page.set_viewport_size({'width': 390, 'height': 844})
    assert drawer.locator('#agent-messages').bounding_box()['height'] >= 200
    assert field.bounding_box()['y'] + field.bounding_box()['height'] < 844
    evidence = Path(__file__).resolve().parents[1] / 'runtime' / 'agent-conversation-review'
    evidence.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(evidence / (role + '-mobile.png')))
    page.set_viewport_size({'width': 1440, 'height': 900})
    page.screenshot(path=str(evidence / (role + '-desktop.png')))
    drawer.get_by_role('button', name='撤回这条问答', exact=True).click()
    expect(drawer).to_have_attribute('data-view', 'idle')
    expect(drawer.locator('.agent-orb-wrap')).to_be_visible()
    expect(drawer.locator('.message')).to_have_count(0)
    page.close()


def test_real_history_retraction_and_unsaved_vs_saved_profile(browser_system, monkeypatch):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    register(page, base, 'student', 'conversation-profile-rollback')
    profile = page.request.get(base + '/api/profile').json()
    profile['career'] = '已经保存的方向'
    assert page.request.put(base + '/api/profile', data=profile).ok
    draft = {**profile, 'career': '来自助手的待确认方向'}
    monkeypatch.setattr('backend.agent.run_agent', lambda message, context: {
        'message': '根据你提供的信息整理方向', 'draft': draft,
        'trace': [], 'model': '隔离模型', 'elapsed': .1})

    def generate():
        page.locator('#agent-toggle').click()
        page.locator('#agent-form textarea').fill('整理我的职业方向')
        page.locator('#agent-form textarea').press('Enter')
        expect(page.locator('#agent-drawer')).to_have_attribute('data-view', 'conversation')
        page.get_by_role('button', name='检查并填写到表单', exact=True).click()
        expect(page.locator('#profile-form [name=career]')).to_have_value(draft['career'])

    generate()
    page.locator('#agent-toggle').click()
    page.get_by_role('button', name='撤回这条问答', exact=True).click()
    expect(page.locator('#profile-form [name=career]')).to_have_value(profile['career'])
    assert page.request.get(base + '/api/agent/history').json() == []
    page.locator('#agent-toggle').click()
    generate()
    page.locator('#profile-form [type=submit]').click()
    expect(page.locator('#profile-form')).to_have_attribute('data-profile-saved', 'true')
    page.locator('#agent-toggle').click()
    page.get_by_role('button', name='撤回这条问答', exact=True).click()
    expect(page.locator('#agent-drawer')).to_have_attribute('data-view', 'idle')
    assert page.request.get(base + '/api/profile').json()['career'] == draft['career']
    expect(page.locator('#profile-form [name=career]')).to_have_value(draft['career'])
    page.locator('#agent-form textarea').fill('刷新后仍可查看的问题')
    page.locator('#agent-form textarea').press('Enter')
    expect(page.locator('#agent-drawer')).to_have_attribute('data-view', 'conversation')
    page.reload()
    page.locator('#agent-toggle').click()
    expect(page.locator('#agent-messages')).to_contain_text('刷新后仍可查看的问题')
    page.route('**/api/agent/history/*', lambda route: route.fulfill(status=503, json={'detail': '隔离撤回失败'}))
    page.get_by_role('button', name='撤回这条问答', exact=True).click()
    expect(page.locator('#toast')).to_contain_text('撤回未完成')
    expect(page.locator('#agent-messages')).to_contain_text('刷新后仍可查看的问题')
    page.close()


def test_unsaved_job_form_is_discarded_without_publishing(browser_system, monkeypatch):
    from tests.test_api import job_data
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    register(page, base, 'employer', 'conversation-job-rollback')
    monkeypatch.setattr('backend.agent.run_agent', lambda message, context: {
        'message': '岗位草稿待你确认', 'draft': job_data(),
        'trace': [], 'model': '隔离模型', 'elapsed': .1})
    page.locator('#agent-toggle').click()
    page.locator('#agent-form textarea').fill('整理岗位说明')
    page.locator('#agent-form textarea').press('Enter')
    page.get_by_role('button', name='检查并填写到表单', exact=True).click()
    modal = page.locator('#modal')
    expect(modal.locator('#job-form')).to_be_visible()
    modal.locator('[name=title]').fill('尚未发布的岗位修改')
    page.mouse.click(5, 100)
    expect(modal).not_to_be_visible()
    page.get_by_role('button', name='撤回这条问答', exact=True).click()
    expect(page.locator('#agent-drawer')).to_have_attribute('data-view', 'idle')
    assert page.request.get(base + '/api/agent/history').json() == []
    assert page.request.get(base + '/api/jobs').json() == []
    page.locator('#agent-form textarea').fill('重新整理岗位说明')
    page.locator('#agent-form textarea').press('Enter')
    page.get_by_role('button', name='检查并填写到表单', exact=True).click()
    expect(modal.locator('[name=title]')).to_have_value(job_data()['title'])
    page.close()
