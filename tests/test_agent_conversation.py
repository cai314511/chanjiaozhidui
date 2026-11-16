"""真实存储和权限测试；模型输出仅在此测试中隔离。"""
from tests.test_api import system, account


def test_followup_and_retraction_are_owned_and_preserve_profile(system, monkeypatch):
    contexts = []

    def isolated_reply(message, context):
        contexts.append((message, context))
        return {'message': '隔离回复', 'draft': None, 'trace': [], 'model': 'test', 'elapsed': 0}

    monkeypatch.setattr('backend.agent.run_agent', isolated_reply)
    owner = account(system, 'student', 'conversation-owner')
    stranger = account(system, 'student', 'conversation-stranger')
    first = owner.post('/api/agent/run', json={'message': '准备数据分析岗位'}).json()
    ident = first['id']
    assert stranger.post('/api/agent/run', json={'message': '追问', 'parent_run_id': ident}).status_code == 403
    reply = owner.post('/api/agent/run', json={'message': '具体怎么做', 'parent_run_id': ident})
    assert reply.status_code == 200, reply.text
    assert '准备数据分析岗位' in contexts[-1][0]
    assert '隔离回复' in contexts[-1][0]
    before = owner.get('/api/profile').json()
    assert stranger.delete('/api/agent/history/' + ident).status_code == 403
    assert owner.delete('/api/agent/history/' + ident).status_code == 200
    assert all(row['id'] != ident for row in owner.get('/api/agent/history').json())
    assert owner.post('/api/agent/run', json={'message': '追问', 'parent_run_id': ident}).status_code == 404
    assert owner.get('/api/profile').json() == before
    assert owner.delete('/api/agent/history/' + ident).status_code == 200
