"""真实 Edge 表单闭环；数据全部由本测试注册的隔离账号创建。"""
from pathlib import Path
from datetime import datetime

import pytest

from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route
from tests.test_api import job_data


EVIDENCE = Path(__file__).resolve().parents[1] / 'runtime' / 'remaining-fixes-20261114' / 'recruiting'


def close_modal(page):
    page.locator('#modal [data-action=close-modal]').first.click()
    expect(page.locator('#modal')).not_to_be_visible()


def capture(page, name, full_page=True):
    page.screenshot(path=str(EVIDENCE / name), full_page=full_page, animations='disabled')


@pytest.mark.parametrize('zone,starts_at,wall', [
    ('Asia/Shanghai', '2027-01-10T10:00:00+08:00', '2027-01-10T10:00'),
    ('UTC', '2027-01-10T10:00:00+00:00', '2027-01-10T10:00'),
    ('America/New_York', '2027-07-10T10:00:00-04:00', '2027-07-10T10:00'),
    ('America/New_York', '2027-11-07T01:30:37-04:00', '2027-11-07T01:30'),
    ('America/New_York', '2027-11-07T01:30:37-05:00', '2027-11-07T01:30'),
])
def test_reschedule_in_utc_browser_preserves_chosen_zone_instant(browser_system, zone, starts_at, wall):
    browser, base = browser_system
    context = browser.new_context(timezone_id='UTC')
    student = browser.new_context(timezone_id='UTC')
    # API仅创建隔离复现材料；改期的打开、预填和提交都由真实Edge页面执行。
    suffix = zone.replace('/', '-').lower()+'-'+starts_at.replace(':', '').replace('+', 'p')
    for client, role in [(context.request, 'employer'), (student.request, 'student')]:
        assert client.post(base+'/api/auth/register', data={'username': 'tz-'+role+'-'+suffix, 'password': 'timezone-test-1234', 'name': role, 'role': role}).ok
    job = context.request.post(base+'/api/jobs', data=job_data()).json()
    aid = student.request.post(base+'/api/applications', data={'job_id': job['id'], 'consent': True}).json()['id']
    invitation = context.request.post(base+'/api/recruiting/applications/'+aid+'/invitations', data={'starts_at': starts_at, 'timezone': zone, 'duration_minutes': 30}).json()
    page = context.new_page()
    page.goto(base)
    page.locator('[data-action=invitation-reschedule]').click()
    form = page.locator('#workflow-form')
    expect(form.locator('[name=starts_at]')).to_have_value(wall)
    form.locator('[type=submit]').click()
    expect(page.locator('#modal')).not_to_be_visible()
    saved = context.request.get(base+'/api/recruiting/workflow').json()['invitations'][0]
    assert saved['id'] == invitation['id']
    assert datetime.fromisoformat(saved['starts_at']) == datetime.fromisoformat(starts_at)
    page.close()
    context.close()
    student.close()


@pytest.mark.parametrize('wall,expected,error', [
    ('2027-03-14T03:30', '2027-03-14T03:30:00-04:00', ''),
    ('2027-03-14T02:30', '', '该时区不存在这个时间'),
    ('2027-11-07T01:30', '', '该时区存在重复时刻'),
])
def test_reschedule_dst_wall_time_roundtrip_or_clear_error(browser_system, wall, expected, error):
    browser, base = browser_system
    context = browser.new_context(timezone_id='UTC')
    student = browser.new_context(timezone_id='UTC')
    suffix = wall.replace('-', '').replace(':', '').lower()
    for client, role in [(context.request, 'employer'), (student.request, 'student')]:
        assert client.post(base+'/api/auth/register', data={'username': 'dst-'+role+'-'+suffix, 'password': 'timezone-test-1234', 'name': role, 'role': role}).ok
    job = context.request.post(base+'/api/jobs', data=job_data()).json()
    aid = student.request.post(base+'/api/applications', data={'job_id': job['id'], 'consent': True}).json()['id']
    original = '2027-01-10T10:00:00-05:00'
    context.request.post(base+'/api/recruiting/applications/'+aid+'/invitations', data={'starts_at': original, 'timezone': 'America/New_York', 'duration_minutes': 30})
    page = context.new_page()
    page.goto(base)
    page.locator('[data-action=invitation-reschedule]').click()
    form = page.locator('#workflow-form')
    form.locator('[name=starts_at]').fill(wall)
    form.locator('[type=submit]').click()
    if error:
        expect(form.locator('.error-text')).to_contain_text(error)
    else:
        expect(page.locator('#modal')).not_to_be_visible()
    saved = context.request.get(base+'/api/recruiting/workflow').json()['invitations'][0]
    assert datetime.fromisoformat(saved['starts_at']) == datetime.fromisoformat(original if error else expected)
    page.close()
    context.close()
    student.close()


def test_complete_recruiting_ui_and_mobile_recovery(browser_system):
    browser, base = browser_system
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    errors = []
    employer = browser.new_page(viewport={'width': 1440, 'height': 1000})
    student = browser.new_page(viewport={'width': 1365, 'height': 1000})
    for page in (employer, student):
        page.on('pageerror', lambda error: errors.append(str(error)))
    register(employer, base, 'employer', 'closure-ui-company')
    expect(employer.locator('[data-recruit-chart=stages]')).to_contain_text('暂无招聘数据')
    assert employer.locator('[data-recruit-chart=stages] canvas').count() == 0
    capture(employer, '01-empty-desktop.png')
    employer.set_viewport_size({'width': 390, 'height': 844})
    assert employer.evaluate('document.documentElement.scrollWidth <= innerWidth')
    capture(employer, '01-empty-mobile.png')
    employer.set_viewport_size({'width': 1440, 'height': 1000})
    route(employer, 'jobs')
    employer.locator('[data-action=new-job]').first.click()
    job = employer.locator('#job-form')
    for key, value in {'title': '毕业资格与招聘闭环验收岗位', 'city': '北京', 'salary_min': '10000', 'salary_max': '15000',
                       'description': '负责产品研究与实验验证', 'graduation_from': '2027-01', 'graduation_to': '2027-12',
                       'degrees': '本科', 'academic_statuses': '在读', 'training_cost': '1000', 'mentor_hours': '10'}.items():
        job.locator(f'[name={key}]').fill(value)
    job.locator('[name=skill]').fill('产品设计')
    job.locator('[name=target]').fill('4')
    job.locator('[name=weight]').fill('80')
    job.locator('[name=mandatory]').check()
    job.locator('[type=submit]').click()
    expect(job.locator('#job-error')).to_contain_text('配置题目和评分标准')
    job.locator('[data-action=add-question]').click()
    job.locator('[name=qskill]').fill('产品设计')
    job.locator('[name=qtitle]').fill('如何验证一个产品方案？')
    job.locator('[name=rubric]').fill('1了解概念，3独立验证，4设计复杂实验，5创新方法')
    job.locator('[type=submit]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    employer.locator('[data-action=edit-job]').click()
    expect(employer.locator('#job-form [name=target]')).to_have_value('4')
    expect(employer.locator('#job-form [name=weight]')).to_have_value('80')
    expect(employer.locator('#job-form [name=graduation_to]')).to_have_value('2027-12')
    close_modal(employer)

    register(student, base, 'student', 'closure-ui-student')
    route(student, 'profile')
    profile = student.locator('#profile-form')
    profile.locator('[name=major]').fill('经济学')
    profile.locator('[name=school_name]').fill('隔离验收学校')
    profile.locator('[name=graduation_month]').fill('2027-06')
    profile.locator('[name=degree]').select_option('本科')
    profile.locator('[name=academic_status]').select_option('在读')
    profile.locator('[name=career]').fill('产品研究与实验设计')
    profile.locator('[type=submit]').click()
    expect(student.locator('#toast')).to_contain_text('画像已保存')
    route(student, 'documents')
    student.locator('[data-action=upload]').first.click()
    student.locator('#upload-form [name=file]').set_input_files({'name': '教育证明.txt', 'mimeType': 'text/plain',
                                                               'buffer': '隔离测试证明：在读本科，预计2027年6月毕业。'.encode()})
    student.locator('#upload-form [type=submit]').click()
    expect(student.locator('#modal')).not_to_be_visible()
    route(student, 'jobs')
    target_job = student.locator('.job-card').filter(has_text='毕业资格与招聘闭环验收岗位')
    expect(target_job.locator('.qualification-summary')).to_contain_text('待核实')
    expect(target_job.locator('.qualification-summary')).to_contain_text('学生自报')
    target_job.locator('[data-action=student-match]').click()
    student.locator('[data-action=apply-dialog]').click()
    student.locator('#apply-form input[name^=doc_]').check()
    student.locator('#apply-form [name=consent]').check()
    student.locator('#apply-form [type=submit]').click()
    expect(student.locator('#modal')).not_to_be_visible()
    student.locator('[data-action=answer]').click()
    student.locator('#answer-form textarea').fill('先访谈用户，定义转化指标，通过分组对照实验验证产品方案。')
    student.locator('#answer-form [type=submit]').click()
    expect(student.locator('#modal')).not_to_be_visible()

    employer.reload()
    route(employer, 'applications')
    expect(employer.locator('.qualification-summary')).to_contain_text('待核实')
    employer.locator('[data-action=review]').first.click()
    review = employer.locator('#review-form')
    qid = review.locator('.question small').inner_text().split(' · ')[0]
    review.locator('[name=review_0]').check()
    review.locator('[name=level_0]').fill('4')
    review.locator('[name=evidence_0]').fill(qid + '：回答提供了访谈、分组对照和转化指标')
    for key in ('graduation_month', 'degree', 'academic_status'):
        review.locator('[name=bg_'+key+']').check()
    review.locator('[type=submit]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    expect(employer.locator('.qualification-summary')).to_contain_text('符合')
    capture(employer, '02-qualification-desktop.png')
    employer.locator('#qualification-filter').select_option('pending')
    expect(employer.locator('#page-content')).to_contain_text('暂无符合筛选的候选人')
    employer.locator('#qualification-filter').select_option('eligible')
    employer.locator('[data-action=candidate-detail]').click()
    employer.locator('#modal [data-action=choice]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    route(employer, 'allocation')
    for key, value in {'salary': '30000', 'training': '2000', 'mentor': '20'}.items():
        employer.locator('#allocation-form [name='+key+']').fill(value)
    employer.locator('#allocation-form [type=submit]').click()
    expect(employer.locator('#allocation-result')).to_contain_text('建议入选 1 人')
    capture(employer, '02-plan-selected-desktop.png')

    route(employer, 'applications')
    employer.locator('[data-action=application-workflow]').first.click()
    employer.locator('#modal [data-action=invite-candidate]').click()
    employer.locator('#workflow-form [name=starts_at]').fill('2027-01-10T10:00')
    employer.locator('#workflow-form [name=timezone]').fill('Asia/Shanghai')
    employer.locator('#workflow-form [name=instructions]').fill('准备产品实验项目')
    employer.locator('#workflow-form [type=submit]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    student.reload()
    route(student, 'applications')
    student.locator('[data-action=invitation-reschedule]').click()
    student.locator('#workflow-form [name=starts_at]').fill('2027-01-11T14:00')
    student.locator('#workflow-form [type=submit]').click()
    expect(student.locator('#modal')).not_to_be_visible()
    employer.reload()
    employer.locator('[data-action=invitation-accept]').click()
    expect(employer.locator('#modal')).to_contain_text('面试已确认')
    employer.locator('#modal [data-action=join-interview]').click()
    expect(employer.locator('#modal #human-connect')).to_be_visible()
    capture(employer, '03-employer-interview-room.png', full_page=False)
    close_modal(employer)
    student.reload()
    student.locator('[data-action=join-interview]').click()
    expect(student.locator('#modal #human-connect')).to_be_visible()
    close_modal(student)

    route(employer, 'applications')
    employer.locator('[data-action=application-workflow]').first.click()
    employer.locator('#modal [data-action=offer-candidate]').click()
    employer.locator('#workflow-form [name=message]').fill('正式录用意向：产品研究岗位，月薪15000元')
    employer.locator('#workflow-form [type=submit]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    student.reload()
    student.locator('[data-action=offer-accept]').click()
    expect(student.locator('#modal')).to_contain_text('已预留名额')
    close_modal(student)
    employer.reload()
    employer.locator('[data-action=offer-confirm]').click()
    expect(employer.locator('#modal')).to_contain_text('企业已确认录用')
    close_modal(employer)
    route(employer, 'allocation')
    expect(employer.locator('#allocation-result')).to_contain_text('来源已变化')
    employer.locator('#allocation-form [name=salary]').fill('20000')
    employer.locator('#allocation-form [type=submit]').click()
    expect(employer.locator('#allocation-result')).to_contain_text('招聘计划 v2')
    expect(employer.locator('#allocation-form h3')).to_have_text('企业招聘总预算')
    salary_row = employer.locator('#allocation-result table').first.locator('tbody tr').first
    expect(salary_row.locator('td').nth(2)).to_have_text('15,000')
    expect(salary_row.locator('td').nth(3)).to_have_text('5,000')
    expect(salary_row.locator('td').nth(5)).to_have_text('15,000')
    employer.locator('[data-action=compare-plans]').click()
    expect(employer.locator('#plan-comparison')).to_contain_text('closure-ui-student')
    expect(employer.locator('#plan-comparison')).to_contain_text('移出建议')
    capture(employer, '04-plan-comparison-desktop.png')
    employer.locator('[data-action=logout]').click()
    employer.locator('.sidebar [data-action=login]').click()
    employer.locator('#auth-form [name=username]').fill('closure-ui-company')
    employer.locator('#auth-form [name=password]').fill('browser-test-1234')
    employer.locator('#auth-form [type=submit]').click()
    expect(employer.locator('#modal')).not_to_be_visible()
    route(employer, 'allocation')
    expect(employer.locator('#allocation-result')).to_contain_text('招聘计划 v2')
    expect(employer.locator('#allocation-form [name=salary]')).to_have_value('20000')
    employer.set_viewport_size({'width': 390, 'height': 844})
    employer.locator('[data-action=compare-plans]').click()
    expect(employer.locator('#plan-comparison')).to_contain_text('closure-ui-student')
    assert employer.evaluate('document.documentElement.scrollWidth <= innerWidth')
    capture(employer, '05-plan-mobile.png')
    student.set_viewport_size({'width': 390, 'height': 844})
    student.reload()
    expect(student.locator('[data-action=join-interview]')).to_be_visible()
    student.locator('[data-action=mobile-menu]').click()
    route(student, 'applications')
    expect(student.locator('#page-content')).to_have_attribute('data-rendered-route', 'applications')
    assert student.evaluate('document.documentElement.scrollWidth <= innerWidth')
    capture(student, '06-student-workflow-mobile.png')
    employer.locator('#allocation-form [name=salary]').fill('10000')
    employer.locator('#allocation-form [type=submit]').click()
    expect(employer.locator('#allocation-result [role=alert]').first).to_contain_text('既有承诺已超过企业总预算')
    expect(employer.locator('#allocation-result [role=alert]').first).to_contain_text('5,000')
    assert employer.request.get(base+'/api/recruiting/workflow').json()['offers'][0]['status'] == 'hired'
    assert employer.evaluate('document.documentElement.scrollWidth <= innerWidth')
    capture(employer, '07-overcommitted-total-budget-mobile.png')
    assert not errors, errors
    employer.close()
    student.close()
