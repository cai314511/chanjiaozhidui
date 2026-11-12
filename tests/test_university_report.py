"""报告使用真实决策计算结果，区分专业对口率与就业率。"""
from fastapi.testclient import TestClient

from backend.decision import run_decision
from tests.test_decision import decision_input
from tests.test_university_courses import school_system


def save_run(app, client):
    owner = client.get('/api/auth/me').json()['id']
    case, recruitment, employment = decision_input()
    employment[0]['related_employed'] = 60
    result = run_decision(case, recruitment, employment)
    ident = app.state.store.save('decision_run', owner, {
        'case': case, 'result': result, 'provenance': [], 'case_id': 'isolated-case',
    })
    return ident, result


def test_report_projects_only_from_saved_own_decision(school_system):
    app, client = school_system
    ident, result = save_run(app, client)
    response = client.get('/api/university/report')
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['source']['run_id'] == ident
    assert {s['name'] for s in report['scenarios']} == {'乐观', '基准', '悲观'}
    base = next(s for s in report['scenarios'] if s['name'] == '基准')
    assert len(base['years']) == 4
    assert base['years'][0]['match_after'] == base['years'][0]['match_before']
    assert base['years'][-1]['match_after'] == 100
    metrics = {m['id']: m for m in report['metrics']}
    assert metrics['related']['before'] == 60
    assert metrics['related']['after'] is None
    assert metrics['cost']['before'] == 0
    assert metrics['cost']['after'] == 5000
    assert report['actions'][0]['added'][0]['name'] == '产品实践'
    assert report['resources'][0]['after'] == result['best']['program']['totals']['cost']
    other = TestClient(app)
    assert other.post('/api/auth/register', json={'username': 'report-other', 'password': 'test-password-123',
                                                  'name': '其他高校', 'role': 'university'}).status_code == 200
    foreign = other.get('/api/university/report').json()
    assert foreign['source']['run_id'] is None
    assert all(m['before'] is None for m in foreign['metrics'])


def test_missing_inputs_remain_missing_and_report_is_school_only(school_system):
    app, client = school_system
    report = client.get('/api/university/report')
    assert report.status_code == 200
    assert report.json()['forecast_status'] == 'incomplete'
    assert all(not s['years'] for s in report.json()['scenarios'])
    assert all(m['after'] is None for m in report.json()['metrics'])
    student = TestClient(app)
    student.post('/api/auth/register', json={'username': 'report-student', 'password': 'test-password-123',
                                            'name': '学生', 'role': 'student'})
    assert student.get('/api/university/report').status_code == 403
    assert student.get('/api/university/courses/export').status_code == 403


def test_partial_forecast_keeps_three_scenarios_without_fabricated_years(school_system):
    app, client = school_system
    owner = client.get('/api/auth/me').json()['id']
    case, recruitment, employment = decision_input()
    recruitment[0]['verified_headcount'] = None
    result = run_decision(case, recruitment, employment)
    app.state.store.save('decision_run', owner, {'case': case, 'result': result, 'provenance': []})
    report = client.get('/api/university/report').json()
    assert report['forecast_status'] == 'incomplete'
    assert len(report['scenarios']) == 3
    assert all(not scenario['years'] for scenario in report['scenarios'])
    related = next(m for m in report['metrics'] if m['id'] == 'related')
    assert related['before'] is None


def test_baseline_metric_respects_explicit_baseline_skill_gain_factor(school_system):
    app, client = school_system
    owner = client.get('/api/auth/me').json()['id']
    case, recruitment, employment = decision_input()
    next(s for s in case['scenarios'] if s['name'] == '基准')['skill_gain_factor'] = .5
    result = run_decision(case, recruitment, employment)
    app.state.store.save('decision_run', owner, {'case': case, 'result': result, 'provenance': []})
    report = client.get('/api/university/report').json()
    metric = next(m for m in report['metrics'] if m['id'] == 'match')
    baseline = next(s for s in report['scenarios'] if s['name'] == '基准')
    assert metric['after'] == baseline['years'][-1]['match_after'] == 75
    assert report['skills'][0]['after'] == 3


def test_school_ability_evidence_remains_visible_without_job_targets(school_system):
    app, client = school_system
    owner = client.get('/api/auth/me').json()['id']
    for index in range(5):
        app.state.store.save('profile', f'local-{index}', {'school_id': owner,
                             'abilities': {'SQL': {'level': 2, 'evidence': '隔离课程实践'}}})
    app.state.store.save('profile', 'outside-school', {'school_id': 'other-school',
                         'abilities': {'SQL': {'level': 5, 'evidence': '其他学校'}}})
    report = client.get('/api/university/report').json()
    assert report['student_skills'] == [{'name': 'SQL', 'level': 2, 'count': 5}]
    assert report['metrics'][0]['before'] is None
