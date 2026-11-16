"""使用真实上传与页面资源；模型回复只在界面边界测试中隔离。"""
import pytest
from playwright.sync_api import expect
from tests.test_browser import browser_system, register, route


@pytest.mark.parametrize('role', ['student', 'employer', 'university'])
def test_agent_upload_has_visible_consent_and_preview(browser_system, role):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    requests = []
    page.route('**/api/agent/run', lambda r: (requests.append(r.request.post_data_json), r.fulfill(json={
        'message': '已读取确认正文', 'draft': None, 'trace': [], 'model': 'isolated', 'elapsed': 0})))
    register(page, base, role, 'agent-upload-' + role)
    page.locator('#agent-toggle').click()
    drawer = page.locator('#agent-drawer')
    expect(drawer.get_by_role('button', name='上传文件', exact=True)).to_be_visible()
    drawer.locator('input[type=file]').set_input_files({'name': '岗位材料.txt', 'mimeType': 'text/plain', 'buffer': '负责数据分析与项目协作'.encode()})
    expect(drawer.locator('.agent-attachments')).to_contain_text('岗位材料.txt')
    drawer.get_by_role('button', name='查看文件正文', exact=True).click()
    expect(page.locator('#modal')).to_contain_text('负责数据分析与项目协作')
    page.locator('#modal [data-action=close-modal]').click()
    field = drawer.locator('textarea[name=message]')
    field.fill('整理上传的材料')
    field.press('Enter')
    expect(page.locator('#toast')).to_contain_text('确认')
    assert requests == []
    drawer.locator('[name=send_documents]').check()
    field.press('Enter')
    expect(drawer.locator('#agent-messages')).to_contain_text('已读取确认正文')
    assert requests[0]['send_documents'] and len(requests[0]['document_ids']) == 1
    page.set_viewport_size({'width': 390, 'height': 844})
    assert field.bounding_box()['y'] + field.bounding_box()['height'] < 844
    page.close()


def test_employer_modes_send_selected_owned_sources(browser_system):
    from tests.test_api import job_data
    browser, base = browser_system
    company = browser.new_page(viewport={'width': 1440, 'height': 900})
    register(company, base, 'employer', 'agent-mode-sources')
    job = company.request.post(base + '/api/jobs', data=job_data()).json()
    student = browser.new_page()
    register(student, base, 'student', 'agent-mode-candidate')
    response = student.request.post(base + '/api/applications', data={'job_id': job['id'], 'consent': True})
    assert response.ok
    application = response.json()
    student.close()
    company.reload()
    company.locator('#agent-toggle').click()
    drawer = company.locator('#agent-drawer')
    drawer.locator('[name=agent_job]').select_option(job['id'])
    drawer.locator('[name=agent_application]').select_option(application['id'])
    requests = []
    company.route('**/api/agent/run', lambda r: (requests.append(r.request.post_data_json),r.fulfill(json={
        'message': '已核对岗位与授权投递', 'draft': None, 'trace': [], 'model': 'isolated', 'elapsed': 0})))
    for mode, label in [('chat', '聊天咨询'), ('job', '岗位草稿'), ('assessment', '测评建议')]:
        drawer.locator('textarea[name=message]').fill('请分析当前岗位和选定投递')
        drawer.get_by_role('tab', name=label, exact=True).click()
        drawer.locator('textarea[name=message]').press('Enter')
        expect(drawer).to_have_attribute('data-view', 'conversation')
        assert requests[-1]['mode'] == mode
        assert requests[-1]['job_id'] == job['id']
        assert requests[-1]['application_id'] == application['id']
    company.close()


def test_mascot_art_visible_on_every_navigation_page(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
    page.goto(base)
    assert page.request.post(base + '/api/demo/enter').ok
    for role in ['student', 'employer', 'university']:
        assert page.request.post(base + '/api/demo/switch', data={'role': role}).ok
        page.reload()
        names = page.locator('.nav [data-action=route]').evaluate_all('nodes=>nodes.map(node=>node.dataset.id)')
        for name in names:
            route(page, name)
            entry = page.locator('#agent-toggle')
            expect(entry).to_have_attribute('data-mascot-ready', 'true')
            expect(entry.locator('.mascot-entry-art')).to_be_visible()
            assert entry.evaluate('el=>{const r=el.getBoundingClientRect();return r.width>50&&r.bottom<=innerHeight&&el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}'), (role, name)
    page.close()
