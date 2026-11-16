"""真实隔离存储验证企业来源边界；模型仅在此处替换以检查输入。"""
from tests.test_api import system, account, job_data


def test_employer_agent_receives_only_own_recruitment(system, monkeypatch):
    seen = []
    monkeypatch.setattr('backend.agent.run_agent', lambda message, context: (
        seen.append(context) or {'message': '已核对当前企业岗位', 'draft': None, 'trace': [], 'model': 'isolated', 'elapsed': 0}))
    owner = account(system, 'employer', 'agent-source-employer')
    other = account(system, 'employer', 'agent-source-other')
    student = account(system, 'student', 'agent-source-student')
    own_job = owner.post('/api/jobs', json=job_data()).json()['id']
    other_job = other.post('/api/jobs', json={**job_data(), 'title': '其他企业岗位'}).json()['id']
    applied = student.post('/api/applications', json={'job_id': own_job, 'consent': True})
    assert applied.status_code == 200
    assert owner.post('/api/agent/run', json={'message': '分析岗位应聘情况'}).status_code == 200
    recruitment = seen[-1]['recruitment']
    assert recruitment['job_count'] == 1
    assert recruitment['application_count'] == 1
    assert [job['id'] for job in recruitment['jobs']] == [own_job]
    assert owner.post('/api/agent/run', json={'message': '分析', 'job_id': other_job}).status_code == 403
    assert owner.post('/api/agent/run', json={'message': '分析', 'job_id': own_job}).status_code == 200
    assert seen[-1]['job']['id'] == own_job
    legacy = system.state.store.save('agent_run', owner.get('/api/auth/me').json()['id'], {
        'status': 'completed', 'job_id': other_job, 'result': {'message': '旧版本未限制的岗位引用'}})
    assert all(row['id'] != legacy for row in owner.get('/api/agent/history').json())
    assert student.post('/api/applications/' + applied.json()['id'] + '/withdraw').status_code == 200
    assert owner.post('/api/agent/run', json={'message': '分析岗位应聘情况'}).status_code == 200
    assert seen[-1]['recruitment']['application_count'] == 0
    assert owner.post('/api/agent/run', json={'message': '测评建议', 'application_id': applied.json()['id']}).status_code == 403
