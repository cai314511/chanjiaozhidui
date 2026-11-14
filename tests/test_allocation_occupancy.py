from tests.test_api import account, job_data, system


def test_accepted_offer_prevents_duplicate_allocation_until_released(system):
    company = account(system, 'employer', 'occupancy-company')
    student = account(system, 'student', 'occupancy-student')
    spec = job_data()
    spec['requirements'] = [{'skill': '产品设计', 'target': 3, 'weight': 1}]
    spec['questions'] = [{'id': 'q1', 'title': '实际项目', 'skill': '产品设计', 'rubric': '说明行动'}]
    job = company.post('/api/jobs', json=spec).json()
    aid = student.post('/api/applications', json={'job_id': job['id'], 'consent': True}).json()['id']
    assert student.post(f'/api/applications/{aid}/answers', json={'job_version': 1, 'answers': {'q1': '访谈并验证方案'}}).status_code == 200
    revision = company.get(f'/api/applications/{aid}').json()['revision']
    assert company.post(f'/api/applications/{aid}/review', json={'revision': revision, 'abilities': {'产品设计': {'level': 5, 'evidence': 'q1'}}, 'background': {}}).status_code == 200
    assert company.post(f'/api/applications/{aid}/choice', json={'chosen': True}).status_code == 200
    budget = {'salary': 40000, 'training': 2000, 'mentor': 20}
    assert company.post('/api/employer/allocate', json=budget).json()['selected'] == [aid]
    offer = company.post(f'/api/recruiting/applications/{aid}/offers', json={'message': '确认录用意向'}).json()
    accepted = student.post(f"/api/recruiting/offers/{offer['id']}/respond", json={'action': 'accept', 'revision': offer['revision']})
    assert accepted.status_code == 200
    assert company.post('/api/employer/allocate', json=budget).json()['selected'] == []
    assert company.post(f"/api/recruiting/offers/{offer['id']}/respond", json={'action': 'revoke', 'revision': accepted.json()['revision']}).status_code == 200
    assert company.post('/api/employer/allocate', json=budget).json()['selected'] == [aid]
