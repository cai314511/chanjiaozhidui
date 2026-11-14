from tests.test_recruiting_closure import setup_case, response_payload
from tests.test_api import job_data


def committed_case(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    spec = {**job_data(), 'questions': job['questions'], 'capacity': 2}
    assert employer.put('/api/jobs/' + job['id'] + '?version=1', json=spec).status_code == 200
    # 第二位候选具有真实测评与企业复核，可进入正式求解。
    answer = students[1].post(f'/api/applications/{aids[1]}/answers', json={
        'job_version': 2, 'answers': {'q1': '访谈验证方案', 'q2': '分析关键指标'}})
    assert answer.status_code == 200
    detail = employer.get('/api/applications/' + aids[1]).json()
    assert employer.post('/api/applications/' + aids[1] + '/review', json={
        'revision': detail['revision'], 'abilities': {
            '产品设计': {'level': 5, 'evidence': 'q1'}, '数据分析': {'level': 5, 'evidence': 'q2'}}, 'background': {}}).status_code == 200
    for client in (students[1], employer):
        assert client.post('/api/applications/' + aids[1] + '/choice', json={'chosen': True}).status_code == 200
    offer = employer.post('/api/recruiting/applications/' + aids[0] + '/offers', json={'message': '正式意向'}).json()
    assert students[0].post('/api/recruiting/offers/' + offer['id'] + '/respond',
        json=response_payload(students[0], 'offers', offer['id'], 'accept')).status_code == 200
    return app, employer, students, job, aids, offer, spec


def test_total_budget_deducts_commitments_before_real_solver(tmp_path):
    _, employer, _, _, aids, _, _ = committed_case(tmp_path)
    first = employer.post('/api/recruiting/plans', json={'salary': 30000, 'training': 2000, 'mentor': 20}).json()
    assert first['budget_scope'] == 'total'
    assert first['committed'] == {'salary': 20000, 'training': 1000, 'mentor': 10}
    assert first['remaining_budget']['salary'] == 10000
    assert first['result']['selected'] == []
    second = employer.post('/api/recruiting/plans', json={'salary': 40000, 'training': 2000, 'mentor': 20}).json()
    assert second['result']['selected'] == [aids[1]]
    assert second['total_used'] == {'salary': 40000, 'training': 2000, 'mentor': 20}


def test_hired_cost_uses_offer_version_and_release_restores_budget(tmp_path):
    app, employer, _, job, _, offer, spec = committed_case(tmp_path)
    assert employer.post('/api/recruiting/offers/' + offer['id'] + '/respond',
        json=response_payload(employer, 'offers', offer['id'], 'confirm')).status_code == 200
    assert employer.put('/api/jobs/' + job['id'] + '?version=2', json={**spec, 'salary_max': 30000}).status_code == 200
    # 兼容本轮先前生成的无金额快照记录，必须读取其原岗位版本。
    stored = app.state.store.get(offer['id'])
    stored['data'].pop('resource_commitment', None)
    app.state.store.save(stored['kind'], stored['owner'], stored['data'], stored['id'])
    budget = {'salary': 10000, 'training': 500, 'mentor': 5}
    plan = employer.post('/api/recruiting/plans', json=budget).json()
    assert plan['committed']['salary'] == 20000
    assert plan['budget_shortfall'] == {'salary': 10000, 'training': 500, 'mentor': 5}
    assert plan['status'] == 'overcommitted' and plan['result']['selected'] == []
    assert employer.post('/api/recruiting/offers/' + offer['id'] + '/respond',
        json=response_payload(employer, 'offers', offer['id'], 'revoke')).status_code == 200
    newer = employer.post('/api/recruiting/plans', json=budget).json()
    assert newer['committed'] == {'salary': 0, 'training': 0, 'mentor': 0}
    assert employer.get('/api/recruiting/plans').json()[1]['stale'] is True


def test_decimal_commitments_do_not_report_false_budget_excess(tmp_path):
    _, employer, students, job, aids = setup_case(tmp_path)
    spec = {**job_data(), 'questions': job['questions'], 'capacity': 2,
            'salary_min': 0, 'salary_max': 0, 'training_cost': 0, 'mentor_hours': 0.1}
    for i in range(2):
        assert employer.put('/api/jobs/' + job['id'] + '?version=' + str(i + 1),
                            json={**spec, 'mentor_hours': 0.1 if i == 0 else 0.2}).status_code == 200
        offer = employer.post('/api/recruiting/applications/' + aids[i] + '/offers', json={'message': '隔离小数资源边界'}).json()
        assert students[i].post('/api/recruiting/offers/' + offer['id'] + '/respond',
            json=response_payload(students[i], 'offers', offer['id'], 'accept')).status_code == 200
    plan = employer.post('/api/recruiting/plans', json={'salary': 0, 'training': 0, 'mentor': 0.3}).json()
    assert plan['status'] == 'calculated'
    assert plan['committed']['mentor'] == 0.3
    assert plan['budget_shortfall']['mentor'] == 0
