"""报告交付状态与快照变更使用隔离的真实决策输入。"""
import copy

from backend.decision import run_decision
from tests.test_decision import decision_input
from tests.test_university_courses import school_system


def save_decision(app, client, mutate=None):
    owner = client.get('/api/auth/me').json()['id']
    case, recruitment, employment = decision_input()
    if mutate:
        mutate(case)
    result = run_decision(case, recruitment, employment)
    ident = app.state.store.save('decision_run', owner, {
        'case': case, 'result': result, 'provenance': [],
    })
    return ident, case


def test_not_calculated_and_missing_inputs_have_distinct_status(school_system):
    app, client = school_system
    assert client.get('/api/university/report').json()['calculation']['state'] == 'not_calculated'
    ident, _ = save_decision(app, client)
    saved = app.state.store.get(ident)
    saved['data']['result'].update(best=None, status='incomplete', missing=['岗位能力证据'])
    app.state.store.save('decision_run', saved['owner'], saved['data'], ident)
    report = client.get('/api/university/report').json()
    assert report['calculation']['state'] == 'missing_inputs'
    assert report['calculation']['missing'] == ['岗位能力证据']
    assert report['actions'] == []


def test_infeasible_candidate_is_diagnostic_only_with_real_budget_difference(school_system):
    app, client = school_system
    def impossible(case):
        case['program']['constraints']['budget'] = 0
        case['program']['constraints']['teacher_hours_max'] = 0
    save_decision(app, client, impossible)
    report = client.get('/api/university/report').json()
    assert report['calculation']['state'] == 'infeasible'
    assert report['actions'] == []
    assert report['constraint_checks']
    candidate = report['constraint_checks'][0]
    assert '调整预算超出上限' in candidate['violations']
    assert next(r for r in candidate['resources'] if r['id'] == 'cost')['shortfall'] == 5000
    assert report['courses_after'] == []


def test_no_improvement_keeps_candidate_out_of_recommendations(school_system):
    app, client = school_system
    save_decision(app, client, lambda case: case['actions'][0].update(skill_delta={}))
    report = client.get('/api/university/report').json()
    assert report['calculation']['state'] == 'no_improvement'
    assert report['actions'] == []


def test_saved_snapshot_detects_new_case_versions_without_mutating_run(school_system):
    from backend.university_report_metadata import report_source_versions
    app, client = school_system
    ident, case = save_decision(app, client)
    store = app.state.store
    saved = store.get(ident)
    case_id = store.save('decision_case', saved['owner'], case)
    saved['data']['case_id'] = case_id
    saved['data']['source_versions'] = report_source_versions(store, saved['owner'], case, [])
    store.save('decision_run', saved['owner'], saved['data'], ident)
    original = copy.deepcopy(store.get(ident)['data'])
    changed = copy.deepcopy(case)
    changed['program']['constraints']['budget'] += 1
    changed['actions'][0]['reason'] += '新项目依据'
    changed['program']['courses'][0]['name'] += '修订'
    store.save('decision_case', saved['owner'], changed, case_id)
    report = client.get('/api/university/report').json()
    assert report['calculation']['state'] == 'success'
    assert report['version_check']['stale'] is True
    assert {'courses', 'actions', 'resources'} <= {d['id'] for d in report['version_check']['changes']}
    assert report['program']['courses'][0]['name'] == case['program']['courses'][0]['name']
    assert store.get(ident)['data'] == original


def test_recalculate_requires_confirmation_and_keeps_original_run(school_system):
    app, client = school_system
    store = app.state.store
    owner = client.get('/api/auth/me').json()['id']
    case, recruitment, employment = decision_input()
    def dataset(kind, records):
        return store.save('research_dataset', owner, {
            'kind': kind, 'records': records, 'sha256': kind + '-hash', 'split': 'development',
            'source_snapshot': {'title': '隔离测试证据'}, 'processing': {},
        })
    case['recruitment_id'] = dataset('recruitment', recruitment)
    case['employment_id'] = dataset('employment', employment)
    case_id = store.save('decision_case', owner, case)
    run = client.post(f'/api/competition/cases/{case_id}/run')
    assert run.status_code == 200, run.text
    ident = run.json()['id']
    original = copy.deepcopy(store.get(ident)['data'])
    case['program']['constraints']['budget'] = 0
    store.save('decision_case', owner, case, case_id)
    report = client.get('/api/university/report', params={'run_id': ident}).json()
    payload = {'run_id': ident, 'versions_token': report['version_check']['token'], 'confirmed': False}
    assert client.post('/api/university/report/recalculate', json=payload).status_code == 422
    payload['confirmed'] = True
    bad = {**payload, 'versions_token': 'old-version'}
    assert client.post('/api/university/report/recalculate', json=bad).status_code == 409
    response = client.post('/api/university/report/recalculate', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['id'] != ident
    assert store.get(ident)['data'] == original
    updated = store.get(response.json()['id'])
    assert updated['data']['supersedes_run_id'] == ident
    assert updated['data']['case']['program']['constraints']['budget'] == 0


def test_confirmed_teaching_plan_survives_schema_and_report(school_system):
    from backend.competition_schemas import DecisionCase
    app, client = school_system
    case, recruitment, employment = decision_input()
    plan = {'confirmed': True, 'old_modules': [], 'modules': [
        {'name': '真实课程项目', 'hours': 20, 'assessment': '已确认评分表'}],
        'prerequisites': ['基础课程'], 'semester': '大三上', 'project': '企业任务',
        'investment_notes': '复用现有实验室', 'timeline': []}
    case['actions'][0]['teaching_plan'] = plan
    parsed = DecisionCase.model_validate(case).model_dump()
    assert parsed['actions'][0]['teaching_plan']['modules'][0]['hours'] == 20
    result = run_decision(parsed, recruitment, employment)
    store = app.state.store
    owner = client.get('/api/auth/me').json()['id']
    store.save('decision_run', owner, {'case': parsed, 'result': result, 'provenance': []})
    assert client.get('/api/university/report').json()['actions'][0]['teaching_plan']['semester'] == '大三上'


def test_changed_recruitment_reference_is_reported_as_demand_version(school_system):
    from backend.university_report_metadata import report_source_versions
    app, client = school_system
    ident, case = save_decision(app, client)
    store = app.state.store
    saved = store.get(ident)
    case_id = store.save('decision_case', saved['owner'], case)
    saved['data'].update(case_id=case_id, source_versions=report_source_versions(store, saved['owner'], case, []))
    store.save('decision_run', saved['owner'], saved['data'], ident)
    case['recruitment_id'] = store.save('research_dataset', saved['owner'], {'sha256': 'new-demand-evidence'})
    store.save('decision_case', saved['owner'], case, case_id)
    report = client.get('/api/university/report').json()
    assert 'demand' in [item['id'] for item in report['version_check']['changes']]


def test_optimization_detects_catalog_changes_without_workspace_save(school_system):
    from backend.university_report_metadata import fingerprint
    from tests.test_university_flow_fixes import optimization_input
    app, client = school_system
    store = app.state.store
    owner = client.get('/api/auth/me').json()['id']
    ident = client.post('/api/university/optimize', json=optimization_input()).json()['id']
    workspace_id = store.save('university_workspace', owner, {'version': 1})
    saved = store.get(ident)
    saved['data'].update(workspace_id=workspace_id, workspace_version=1,
                         source_versions={'catalog': fingerprint(None)})
    store.save('optimization', owner, saved['data'], ident)
    store.save('university_course_catalog', owner, {'courses': [], 'sources': ['新课程证据']})
    report = client.get('/api/university/report', params={'optimization_id': ident}).json()
    assert report['version_check']['stale']
    assert 'catalog' in [item['id'] for item in report['version_check']['changes']]


def test_zero_benefit_selection_is_not_an_improvement_recommendation(school_system):
    from tests.test_university_flow_fixes import optimization_input
    app, client = school_system
    data = optimization_input()
    data['gaps'] = {'SQL': 0}
    data['courses'][0].update(cost=0, gains={'SQL': 0})
    ident = client.post('/api/university/optimize', json=data).json()['id']
    saved = app.state.store.get(ident)
    saved['data']['result'].update(selected=['sql'], benefit=0)
    app.state.store.save('optimization', saved['owner'], saved['data'], ident)
    report = client.get('/api/university/report', params={'optimization_id': ident}).json()
    assert report['calculation']['state'] == 'no_improvement'
    assert report['actions'] == []
    assert report['courses_after'] == []


def test_workspace_fingerprint_ignores_navigation_but_tracks_real_input():
    from backend.university_report_metadata import workspace_input_fingerprint
    inputs = {'id': 'w', 'major': '经济学', 'step': 1, 'version': 1,
              'advanced': {'enabled': True, 'case_id': 'case-a', 'run_id': 'run-a', 'assumptions': '已确认教学假设'}}
    changed = copy.deepcopy(inputs)
    changed.update(step=4, version=2, result={'selected': []}, optimization_id='old', ai_suggestions=[])
    changed['advanced'].update(enabled=False, case_id='case-b', run_id='run-b')
    assert workspace_input_fingerprint(inputs) == workspace_input_fingerprint(changed)
    changed['major'] = '金融科技'
    assert workspace_input_fingerprint(inputs) != workspace_input_fingerprint(changed)


def test_linked_advanced_run_requires_current_workspace_and_reports_staleness(school_system):
    from backend.university_report_metadata import workspace_input_fingerprint
    app, client = school_system
    store = app.state.store
    owner = client.get('/api/auth/me').json()['id']
    case, recruitment, employment = decision_input()
    workspace = {'major': '经济学', 'advanced': {'assumptions': '已确认教学假设'}}
    workspace_id = store.save('university_workspace', owner, workspace)
    case.update(workspace_id=workspace_id, workspace_input_hash=workspace_input_fingerprint(workspace))
    for key, kind, records in [('recruitment_id', 'recruitment', recruitment), ('employment_id', 'employment', employment)]:
        case[key] = store.save('research_dataset', owner, {
            'kind': kind, 'records': records, 'sha256': kind, 'split': 'development',
            'source_snapshot': {'title': '隔离测试证据'}, 'processing': {},
        })
    response = client.post('/api/competition/cases', json=case)
    assert response.status_code == 200, response.text
    ident = response.json()['id']
    run = client.post(f'/api/competition/cases/{ident}/run')
    assert run.status_code == 200, run.text
    run_id = run.json()['id']
    workspace['major'] = '金融科技'
    store.save('university_workspace', owner, workspace, workspace_id)
    assert client.post(f'/api/competition/cases/{ident}/run').status_code == 409
    assert client.post('/api/competition/cases', json=case).status_code == 409
    report = client.get('/api/university/report', params={'run_id': run_id}).json()
    assert 'workspace' in [change['id'] for change in report['version_check']['changes']]
