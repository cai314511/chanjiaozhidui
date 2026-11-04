import json

from playwright.sync_api import expect

from tests.test_browser import browser_system, register, route
from tests.test_competition_api import source_data
from tests.test_decision import decision_input


def test_research_governance_and_four_year_decision_ui(browser_system):
    browser, base = browser_system
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    register(page, base, 'university', 'competition-browser-school')
    route(page, 'research')
    page.locator('[data-action=research-source]').click()
    form = page.locator('#research-source-form')
    for name, value in {'title': '隔离浏览器测试来源', 'url': 'https://example.org/data',
                        'license_basis': '仅用于隔离浏览器测试的来源声明', 'scope': '北京测试专业同年度需求'}.items():
        form.locator(f'[name={name}]').fill(value)
    form.locator('[name=research_permitted]').check()
    form.locator('[name=redaction_reviewed]').check()
    form.locator('[type=submit]').click()
    expect(page.locator('#modal')).not_to_be_visible()
    expect(page.locator('#page-content')).to_contain_text('隔离浏览器测试来源')

    case, jobs, employment = decision_input()
    for kind, records in [('recruitment', jobs), ('employment', employment)]:
        page.locator('[data-action=research-import]').click()
        form = page.locator('#research-import-form')
        form.locator('[name=kind]').select_option(kind)
        form.locator('[name=file]').set_input_files({'name': kind+'.json', 'mimeType': 'application/json',
                                                   'buffer': json.dumps(records, ensure_ascii=False).encode()})
        form.locator('[type=submit]').click()
        expect(page.locator('#modal')).not_to_be_visible()
    datasets = page.request.get(base+'/api/competition/datasets').json()
    employment_id = next(d['id'] for d in datasets if d['kind'] == 'employment')
    route(page, 'decision')
    page.locator('[data-action=decision-create]').click()
    form = page.locator('#decision-create-form')
    form.locator('[name=title]').fill('浏览器隔离四年决策')
    form.locator('[name=employment_id]').select_option(employment_id)
    form.locator('[name=configuration]').set_input_files({'name': 'case.json', 'mimeType': 'application/json',
        'buffer': json.dumps({'program': case['program'], 'actions': case['actions'], 'admissions': case['admissions']}, ensure_ascii=False).encode()})
    expect(form.locator('[name=min_seats]')).to_have_value('80')
    for index, scenario in enumerate(case['scenarios']):
        for key in ['demand_growth', 'salary_growth', 'skill_gain_factor', 'probability']:
            form.locator(f'[name="{key}_{index}"]').fill(str(scenario[key]))
    form.locator('[name=skill_employment_elasticity]').fill('.2')
    form.locator('[name=assumptions]').fill('隔离测试：参数来自测试输入，不是官方实证')
    form.locator('[name=market_scope_confirmed]').check()
    form.locator('[name=annual_demand_confirmed]').check()
    form.locator('[type=submit]').click()
    expect(page.locator('#modal')).not_to_be_visible()
    page.locator('[data-action=decision-run]').click()
    expect(page.locator('#decision-output')).to_contain_text('四年推演与不调整基线')
    expect(page.locator('#decision-output')).to_contain_text('产品实践')
    expect(page.locator('#decision-output')).to_contain_text('师资短板')
    run_id = page.request.get(base+'/api/competition/runs').json()[0]['id']
    exported = page.request.get(base+f'/api/competition/runs/{run_id}/export?format=json').json()
    assert exported['result']['best']['action_ids'] == ['a']
    assert page.request.get(base+f'/api/competition/runs/{run_id}/export?format=csv').status == 200

    source = page.request.post(base+'/api/competition/sources', data=source_data('evaluation')).json()
    test_records = [{**jobs[0], 'record_id': 'held-out', 'skills': [{'name': '产品设计', 'level': 5, 'weight': 1}]}]
    response = page.request.post(base+'/api/competition/datasets', data={'source_id': source['id'], 'kind': 'recruitment', 'records': test_records})
    assert response.status == 200
    page.locator('[data-action=decision-evaluate]').click()
    page.locator('#evaluation-form [type=submit]').click()
    expect(page.locator('#evaluation-output')).to_contain_text('40 → 80')
    page.locator('[data-action=close-modal]').click()
    page.set_viewport_size({'width': 390, 'height': 844})
    for name in ['research', 'decision', 'rules']:
        page.locator('[data-action=mobile-menu]').click()
        route(page, name)
        expect(page.locator('#page-content .loading')).to_have_count(0)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), name
    page.locator('[data-action=mobile-menu]').click()
    page.locator('[data-action=demo-toggle]').click()
    expect(page.locator('.account-info strong')).to_have_text('展示账号')
    expect(page.locator('.nav [data-id=documents]')).to_have_count(0)
    page.locator('#agent-toggle').click()
    expect(page.locator('#agent-drawer')).not_to_be_visible()
    page.reload()
    expect(page.locator('.account-info strong')).to_have_text('展示账号')
    expect(page.locator('.nav [data-id=documents]')).to_have_count(0)
    assert errors == []
    page.close()
