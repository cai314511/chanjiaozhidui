"""隔离库中以普通表单运行高级决策，不上传JSON配置。"""
import time

from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route
from tests.test_competition_api import prepare
from tests.test_decision import decision_input


def test_teacher_advanced_case_from_forms_without_json(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    register(page, base, 'university', 'teacher-forms-school')
    # 结构化研究数据通过正式API登记，课程/专业/方向/情景全部由下面的可见表单填写。
    class RequestClient:
        def post(self, path, json):
            response = page.request.post(base + path, data=json)
            class Response:
                status_code = response.status
                text = response.text()
                def json(self):
                    return response.json()
            return Response()
    case = prepare(RequestClient())
    page.request.post(base+'/api/university/materials/import', multipart={
        'file': {'name': 'catalog.csv', 'mimeType': 'text/csv', 'buffer': '课程代码,课程名称,学分,总学时\nc,基础课程,3,48\n'.encode()}})
    route(page, 'university-workspace')
    page.locator('[data-action=uw-new]').click()
    form = page.locator('#uw-form')
    form.locator('[name=major]').fill('测试专业')
    form.locator('[name=job_target]').fill('产品经理')
    form.locator('[type=submit]').click()
    page.locator('#uw-course-list [value=c]').check()
    form.locator('[type=submit]').click()
    page.locator('#uw-add-target').click()
    row=page.locator('[data-target]')
    for key,value in {'skill':'产品设计','gap':'2','evidence':'隔离测试能力观测'}.items():
        row.locator(f'[name={key}]').fill(value)
    row.locator('[name=confirmed]').check()
    form.locator('[type=submit]').click()
    for key in ['cost','credits','teacher_hours','lab_hours','study_hours','months']:
        form.locator(f'[name=limit-{key}]').fill('10000' if key=='cost' else '100' if key!='months' else '12')
    form.locator('[type=submit]').click()
    page.locator('#uw-add-action').click()
    row=page.locator('[data-uw-action]')
    row.locator('[name=name]').fill('产品实践')
    row.locator('[name=kind]').select_option('add')
    values={'cost':'5000','credits':'2','teacher_hours':'32','lab_hours':'20','study_hours':'32','months':'4','gain-产品设计':'2','evidence':'隔离测试教学评审','modules':'产品项目','semester':'第4学期','project':'产品原型作品'}
    for key,value in values.items():
        row.locator(f'[name="{key}"]').fill(value)
    for key in ['cost','credits','teacher_hours','lab_hours','study_hours','months','gains']:
        row.locator(f'[name=confirmed-{key}]').check()
    row.locator('[name=confirmed]').check()
    row.locator('[name=plan-confirmed]').check()
    form.locator('[type=submit]').click()
    page.locator('.uw-advanced summary').click()
    form.locator('[name=advanced-enabled]').check()
    form.locator('[name=adv-recruitment_id]').select_option(case['recruitment_id'])
    form.locator('[name=adv-employment_id]').select_option(case['employment_id'])
    program=case['program']
    for key in ['code','region','current_seats','completion_rate','split_timing']:
        form.locator(f'[name=adv-program-{key}]').fill(str(program[key]))
    for i,value in enumerate(program['pipeline_graduates']):
        form.locator(f'[name=adv-pipeline-{i}]').fill(str(value))
    course=page.locator('[data-adv-course=c]')
    course.locator('[name=teacher_hours]').fill('48')
    course.locator('[name=lab_hours]').fill('0')
    course.locator('[name=protected]').check()
    for key,value in program['skills']['产品设计'].items():
        page.locator('[data-adv-skill]').locator(f'[name={key}]').fill(str(value))
    for key,value in program['constraints'].items():
        form.locator(f'[name=adv-constraint-{key}]').fill(str(value))
    page.locator('#uw-add-direction').click()
    d={**program['directions'][0],'current_count':100}
    for key,value in d.items():
        page.locator('[data-adv-direction]').locator(f'[name={key}]').fill('、'.join(value) if isinstance(value,list) else str(value))
    page.locator('#uw-add-group').click()
    for key,value in program['groups'][0].items():
        page.locator('[data-adv-group]').locator(f'[name={key}]').fill('、'.join(value) if isinstance(value,list) else str(value))
    page.locator('[data-adv-action] [name=curriculum_hours]').fill('32')
    for key,value in case['admissions'].items():
        form.locator(f'[name=adv-admission-{key}]').fill(str(value))
    for i,scenario in enumerate(case['scenarios']):
        for key,value in scenario.items():
            if key!='name':
                form.locator(f'[name=adv-scenario-{i}-{key}]').fill(str(value))
    for key in ['skill_employment_elasticity','skill_salary_elasticity','implementation_lag','max_rounds','assumptions']:
        form.locator(f'[name=adv-{key}]').fill(str(case[key]))
    form.locator('[name=adv-market_scope_confirmed]').check()
    form.locator('[name=adv-annual_demand_confirmed]').check()
    form.locator('[type=submit]').click()
    expect(page.locator('#university-workspace')).to_contain_text('已保存高级决策结果', timeout=20000)
    runs=page.request.get(base+'/api/competition/runs').json()
    assert runs
    result=page.request.get(base+'/api/competition/runs/'+runs[0]['id']).json()
    assert len(result['result']['best']['forecast']['scenarios'][0]['adjustment']['years']) == 4
    with page.expect_response(lambda response:'/api/university/report?run_id='+runs[0]['id'] in response.url) as report_wait:
        page.locator('.uw-advanced [data-action=university-selected-report]').click()
    assert report_wait.value.json()['source']['run_id']==runs[0]['id']
    expect(page.locator('#page-content')).to_contain_text('产品实践')
    expect(page.locator('#page-content')).to_contain_text('第4学期')
    expect(page.locator('#page-content')).to_contain_text('产品原型作品')
    page.set_viewport_size({'width':390,'height':844})
    # ECharts在ResizeObserver回调后调整canvas，等待实际响应式布局完成。
    # wait_for_function会在页面内eval字符串，被本站CSP拦截；在测试端轮询同一布局条件。
    deadline = time.monotonic() + 5
    while not page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'):
        if time.monotonic() >= deadline:
            break
        page.wait_for_timeout(30)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), page.evaluate(
        '({width:innerWidth,scroll:document.documentElement.scrollWidth})')
    page.close()
