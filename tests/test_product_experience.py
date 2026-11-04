from fastapi.testclient import TestClient

from tests.test_api import account, job_data, system


def test_public_match_hides_scoring_details(system):
    employer = account(system, 'employer', 'private-score-company')
    student = account(system, 'student', 'private-score-student')
    job = employer.post('/api/jobs', json=job_data()).json()
    result = student.get('/api/jobs/' + job['id'] + '/match').json()
    assert 'employer' not in result
    assert 'sensitivity' not in result
    assert result['status'] == 'pending'
    assert 'weight' not in str(student.get('/api/jobs').json())


def test_voice_and_attachments_require_owner(system):
    outsider = TestClient(system)
    assert outsider.get('/api/voice/status').status_code == 401
    owner = account(system, 'student', 'attachment-owner')
    other = account(system, 'student', 'attachment-other')
    item = owner.post('/api/portfolio', files={'file': ('work.txt', '个人成果'.encode(), 'text/plain')})
    assert item.status_code == 200, item.text
    ident = item.json()['id']
    assert other.get('/api/portfolio/' + ident + '/file').status_code == 403
    assert owner.get('/api/portfolio/' + ident + '/file').status_code == 200


def test_interview_presets_and_revoked_room(system):
    employer = account(system, 'employer', 'room-company')
    student = account(system, 'student', 'room-student')
    stranger = account(system, 'student', 'room-stranger')
    spec = job_data()
    spec['questions'] = [{'id': 'q1', 'title': '请讲述一个项目', 'skill': '产品设计', 'rubric': '引用经历'}]
    job = employer.post('/api/jobs', json=spec).json()
    application = student.post('/api/applications', json={'job_id': job['id'], 'consent': True}).json()
    result = student.post('/api/interviews', json={'application_id': application['id'], 'mode': 'preset'})
    assert result.status_code == 200, result.text
    interview = result.json()
    assert interview['messages'][0]['text'] == '请讲述一个项目'
    assert stranger.get('/api/interviews/' + interview['id']).status_code == 403
    assert student.post('/api/applications/' + application['id'] + '/withdraw').status_code == 200
    assert employer.get('/api/interviews/' + interview['id']).status_code == 403


def test_portfolio_consent_and_revoke(system):
    employer = account(system, 'employer', 'portfolio-company')
    student = account(system, 'student', 'portfolio-student')
    other = account(system, 'student', 'portfolio-unrelated')
    job = employer.post('/api/jobs', json=job_data()).json()
    item = student.post('/api/portfolio', files={'file': ('成果.txt', '隔离测试的作品说明'.encode())}).json()
    path = '/api/portfolio/' + item['id']
    assert employer.get(path).status_code == 403
    assert other.post('/api/applications', json={'job_id': job['id'], 'consent': True, 'portfolio_ids': [item['id']]}).status_code == 403
    application = student.post('/api/applications', json={'job_id': job['id'], 'consent': True, 'portfolio_ids': [item['id']]}).json()
    assert employer.get(path + '/file').status_code == 200
    student.post('/api/applications/' + application['id'] + '/withdraw')
    assert employer.get(path + '/file').status_code == 403


def test_priorities_persist_without_returning_parameters(system):
    employer = account(system, 'employer', 'persistent-priorities')
    job = employer.post('/api/jobs', json=job_data()).json()
    priorities = {'产品设计': '优先考虑', '数据分析': '一般关注'}
    response = employer.put('/api/jobs/' + job['id'] + '/priorities', json={'version': 1, 'priorities': priorities})
    assert response.status_code == 200
    current = employer.get('/api/jobs').json()[0]
    assert current['priorities'] == priorities
    assert all('weight' not in item and 'target' not in item for item in current['requirements'])
    reply = employer.post('/api/agent/run', json={'message': '请告诉我详细权重公式'}).json()
    assert reply['draft'] is None
    assert '具体计算参数由系统管理' in reply['message']


def test_human_call_rounds_do_not_replay_previous_signals(system):
    employer = account(system, 'employer', 'call-round-company')
    student = account(system, 'student', 'call-round-student')
    job = employer.post('/api/jobs', json=job_data()).json()
    application = student.post('/api/applications', json={'job_id': job['id'], 'consent': True}).json()
    session = student.post('/api/interviews', json={'mode': 'human', 'application_id': application['id']}).json()
    path = '/api/interviews/' + session['id']
    first = student.post(path + '/signal', json={'revision': session['revision'], 'call_id': 'first-call-12345678', 'kind': 'offer', 'payload': {}}).json()
    second = student.post(path + '/signal', json={'revision': first['revision'], 'call_id': 'second-call-12345678', 'kind': 'offer', 'payload': {}}).json()
    assert len(second['signals']) == 1
    assert second['signals'][0]['call_id'] == 'second-call-12345678'
    assert employer.post(path + '/signal', json={'revision': second['revision'], 'call_id': 'first-call-12345678', 'kind': 'candidate', 'payload': {}}).status_code == 409
    assert employer.post(path + '/signal', json={'revision': second['revision'], 'call_id': 'second-call-12345678', 'kind': 'offer', 'payload': {}}).status_code == 403
    assert student.post(path + '/leave', json={'call_id': 'first-call-12345678'}).status_code == 200
    assert employer.get(path).json()['call_id'] == 'second-call-12345678'
    assert employer.post(path + '/leave', json={'call_id': 'second-call-12345678'}).status_code == 200
    assert student.get(path).json()['call_id'] is None
