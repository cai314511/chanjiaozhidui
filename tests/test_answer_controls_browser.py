"""固定数字题号复现测评表单的命名控件读取，业务接口使用真实实现。"""
from playwright.sync_api import expect

from tests.test_api import job_data
from tests.test_browser import browser_system, register, route


def test_numeric_question_identifier_submits_the_named_answer(browser_system):
    browser, base = browser_system
    company = browser.new_context()
    response = company.request.post(base + '/api/auth/register', data={
        'username': 'numeric-question-employer', 'password': 'isolated-answer-123',
        'name': '数字题号测试企业', 'role': 'employer', 'company_tracks': ['AI产品'],
    })
    assert response.ok, response.text()
    spec = job_data()
    spec['questions'] = [{'id': '12345678', 'skill': '产品设计', 'title': '如何验证用户需求？',
                          'kind': 'scenario', 'rubric': '考察需求验证方法'}]
    response = company.request.post(base + '/api/jobs', data=spec)
    assert response.ok, response.text()
    job_id = response.json()['id']
    page = browser.new_page()
    register(page, base, 'student', 'numeric-question-student')
    response = page.request.post(base + '/api/applications', data={'job_id': job_id, 'consent': True})
    assert response.ok, response.text()
    application_id = response.json()['id']
    page.reload()
    expect(page.locator('#discovery-form')).to_be_visible()
    route(page, 'applications')
    page.locator('[data-action=answer]').click()
    text = '先访谈目标用户，再用原型验证需求。'
    page.locator('#answer-form [name="12345678"]').fill(text)
    page.locator('#answer-form [type=submit]').click()
    expect(page.locator('#modal')).not_to_be_visible()
    application = page.request.get(base + '/api/applications/' + application_id).json()
    assert application['answers']['12345678'] == text
    page.close()
    company.close()
