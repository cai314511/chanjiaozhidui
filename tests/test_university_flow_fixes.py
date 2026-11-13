"""隔离数据库验证优化与决策报告的引用、快照及归属。"""
from fastapi.testclient import TestClient

from tests.test_university_courses import school_system
from tests.test_university_report import save_run
from tests.test_decision import decision_input
from backend.decision import run_decision


def optimization_input():
    return {'gaps': {'SQL': 2}, 'weights': {'SQL': 1},
            'limits': {'cost': 800, 'credits': 3, 'teacher_hours': 40,
                       'lab_hours': 20, 'study_hours': 80, 'months': 6},
            'courses': [{'id': 'sql', 'name': 'SQL实践', 'gains': {'SQL': 1},
                         'cost': 500, 'credits': 2, 'teacher_hours': 24,
                         'lab_hours': 10, 'study_hours': 50, 'months': 3}]}


def test_saved_optimization_opens_its_own_report_without_borrowing_decision(school_system):
    app, client = school_system
    save_run(app, client)
    response = client.post('/api/university/optimize', json=optimization_input())
    assert response.status_code == 200, response.text
    ident = response.json()['id']
    report = client.get('/api/university/report', params={'optimization_id': ident}).json()
    assert report['source']['optimization_id'] == ident
    assert report['source']['run_id'] is None
    assert report['actions'][0]['added'][0]['name'] == 'SQL实践'
    assert report['actions'][0]['added'][0]['hours'] is None
    assert report['resources'][0]['limit'] == 800
    assert report['resources'][0]['after'] == 500
    assert report['resources'][0]['before'] is None
    assert report['skills'][0]['gap_before'] == 2
    assert report['skills'][0]['gap_after'] == 1
    assert report['skills'][0]['before'] is None
    assert all(not scenario['years'] for scenario in report['scenarios'])
    assert report['metrics'][0]['before'] is None
    assert next(m for m in report['metrics'] if m['id'] == 'cost')['after'] == 500


def test_report_explicit_run_stays_on_a_after_b_is_saved(school_system):
    app, client = school_system
    first, _ = save_run(app, client)
    owner = client.get('/api/auth/me').json()['id']
    case, recruitment, employment = decision_input()
    case['title'] = '项目B零预算'
    case['program']['name'] = '专业B'
    case['program']['constraints']['budget'] = 0
    second = app.state.store.save('decision_run', owner, {
        'case': case, 'result': run_decision(case, recruitment, employment),
        'provenance': [], 'case_id': 'case-b',
    })
    assert first != second
    report = client.get('/api/university/report', params={'run_id': first})
    assert report.status_code == 200
    assert report.json()['source']['run_id'] == first
    assert report.json()['source']['case_id'] == 'isolated-case'
    assert report.json()['program']['name'] != '专业B'
    assert next(m for m in report.json()['metrics'] if m['id'] == 'cost')['after'] == 5000


def test_report_references_are_owned_typed_and_unambiguous(school_system):
    app, client = school_system
    run, _ = save_run(app, client)
    plan = client.post('/api/university/optimize', json=optimization_input()).json()['id']
    other = TestClient(app)
    other.post('/api/auth/register', json={'username': 'flow-other', 'password': 'test-password-123',
                                         'name': '其他高校', 'role': 'university'})
    for key, ident in [('run_id', run), ('optimization_id', plan)]:
        assert other.get('/api/university/report', params={key: ident}).status_code == 403
        assert client.get('/api/university/report', params={key: 'missing'}).status_code == 404
        assert client.get('/api/university/report', params={key: ''}).status_code == 404
    assert client.get('/api/university/report', params={'run_id': plan}).status_code == 404
    assert client.get('/api/university/report', params={'run_id': run, 'optimization_id': plan}).status_code == 422
