from concurrent.futures import ThreadPoolExecutor

from tests.test_api import account, job_data, system


def test_concurrent_duplicate_apply_is_rejected(system):
    employer = account(system, 'employer', 'company-duplicate')
    student = account(system, 'student', 'student-duplicate')
    jid = employer.post('/api/jobs', json=job_data()).json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: student.post('/api/applications', json={'job_id': jid, 'consent': True}).status_code, range(2)))
    assert sorted(results) == [200, 409]


def test_profile_update_cannot_restore_withdrawn_consent(system):
    employer = account(system, 'employer', 'company-race')
    student = account(system, 'student', 'student-race')
    jid = employer.post('/api/jobs', json=job_data()).json()['id']
    aid = student.post('/api/applications', json={'job_id': jid, 'consent': True}).json()['id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(student.put, '/api/profile', json={'major': '经济学'})
        second = pool.submit(student.post, f'/api/applications/{aid}/withdraw')
        assert first.result().status_code == 200
        assert second.result().status_code == 200
    assert employer.get(f'/api/applications/{aid}').status_code == 403


def test_student_learning_resources_cannot_be_exceeded(system):
    student = account(system, 'student', 'student-learning')
    student.put('/api/profile', json={'resources': {'budget': 100, 'study_hours': 10, 'months': 1}})
    payload = {'gaps': {'产品设计': 2}, 'weights': {'产品设计': 1}, 'courses': [
        {'id': 'a', 'name': '超出预算的方案', 'cost': 200, 'credits': 0, 'teacher_hours': 0,
         'lab_hours': 0, 'study_hours': 5, 'months': 1, 'gains': {'产品设计': 2}}],
        'limits': {'cost': 999999, 'credits': 0, 'teacher_hours': 0, 'lab_hours': 0, 'study_hours': 99, 'months': 12}}
    response = student.post('/api/student/optimize', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['selected'] == []
    plans = student.get('/api/student/plans').json()
    assert plans[0]['input']['limits']['cost'] == 100


def test_profile_change_invalidates_unsubmitted_first_review(system):
    employer = account(system, 'employer', 'company-first-review')
    student = account(system, 'student', 'student-first-review')
    spec = job_data()
    spec['questions'] = [{'id': 'q1', 'title': '设计产品方案', 'kind': 'text', 'skill': '产品设计', 'rubric': '评价产品设计'}]
    jid = employer.post('/api/jobs', json=spec).json()['id']
    aid = student.post('/api/applications', json={'job_id': jid, 'consent': True}).json()['id']
    assert student.post(f'/api/applications/{aid}/answers', json={'job_version': 1, 'answers': {'q1': '先研究用户'}}).status_code == 200
    revision = employer.get(f'/api/applications/{aid}').json()['revision']
    student.put('/api/profile', json={'major': '金融学'})
    response = employer.post(f'/api/applications/{aid}/review', json={'revision': revision, 'abilities': {'产品设计': {'level': 4, 'evidence': 'q1：用户研究'}}})
    assert response.status_code == 409
