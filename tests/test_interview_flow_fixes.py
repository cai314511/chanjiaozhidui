from concurrent.futures import ThreadPoolExecutor

from tests.test_api import account, job_data, system


def setup_room(system, mode):
    employer = account(system, 'employer', 'flow-company')
    student = account(system, 'student', 'flow-student')
    spec = job_data()
    spec['questions'] = [{'id': 'project', 'title': '讲述项目', 'skill': '产品设计', 'rubric': '实际行动'}]
    job = employer.post('/api/jobs', json=spec).json()
    application = student.post('/api/applications', json={'job_id': job['id'], 'consent': True}).json()
    room = student.post('/api/interviews', json={'mode': mode, 'application_id': application['id']}).json()
    return employer, student, job, application, room


def test_preset_evidence_keeps_question_and_version_until_explicit_submission(system):
    employer, student, job, application, room = setup_room(system, 'preset')
    assert room['job_version'] == job['version']
    path = '/api/interviews/' + room['id']
    result = student.post(path + '/turn', json={'text': '我完成了访谈和原型验证', 'revision': room['revision']}).json()
    assert result['completed']
    assert next(m for m in result['messages'] if m['role'] == 'user')['question_id'] == 'project'
    current = student.get('/api/applications').json()[0]
    assert current['answers'] == {}
    assert student.post('/api/applications/' + application['id'] + '/answers', json={
        'job_version': room['job_version'], 'answers': {'project': '核对后的项目回答'}}).status_code == 200
    assert employer.get('/api/applications').json()[0]['answers']['project'] == '核对后的项目回答'
    current = employer.get('/api/applications').json()[0]
    assert employer.post('/api/applications/' + application['id'] + '/review', json={
        'revision': current['revision'], 'abilities': {'产品设计': {'level': 4, 'evidence': 'project'}}, 'background': {}}).status_code == 200
    assert student.post('/api/applications/' + application['id'] + '/answers', json={
        'job_version': room['job_version'], 'answers': {'project': '再次核对的回答'}}).status_code == 200
    assert employer.get('/api/applications').json()[0]['review'] is None
    history = student.get('/api/applications/' + application['id'] + '/history').json()
    assert any(row['answers']['project'] == '核对后的项目回答' and row['review'] for row in history)


def test_preset_submission_rejects_changed_job_and_withdrawal(system):
    employer, student, job, application, room = setup_room(system, 'preset')
    spec = job_data()
    spec['description'] = '更新职责'
    spec['questions'] = room['questions']
    response = employer.put('/api/jobs/' + job['id'], params={'version': job['version']}, json=spec)
    assert response.status_code == 200, response.text
    payload = {'job_version': room['job_version'], 'answers': {'project': '旧岗位回答'}}
    path = '/api/applications/' + application['id']
    assert student.post(path + '/answers', json=payload).status_code == 409
    assert student.post(path + '/withdraw').status_code == 200
    assert student.post(path + '/answers', json=payload).status_code == 409
    assert employer.get('/api/interviews/' + room['id']).status_code == 403


def test_parallel_ice_does_not_conflict_with_messages_or_drop_candidates(system):
    employer, student, _, _, room = setup_room(system, 'human')
    path = '/api/interviews/' + room['id']
    call_id = 'parallel-call-12345678'
    offer = student.post(path + '/signal', json={'revision': room['revision'], 'call_id': call_id, 'kind': 'offer', 'payload': {}}).json()
    def candidate(index):
        return employer.post(path + '/signal', json={'revision': offer['revision'], 'call_id': call_id, 'kind': 'candidate', 'payload': {'index': index}})
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(candidate, range(12)))
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    latest = student.get(path).json()
    assert latest['revision'] == offer['revision']
    assert {s['payload']['index'] for s in latest['signals'] if s['kind'] == 'candidate'} == set(range(12))
    assert student.post(path + '/turn', json={'revision': offer['revision'], 'text': '文字记录'}).status_code == 200
    assert len(student.get(path).json()['signals']) == 13
