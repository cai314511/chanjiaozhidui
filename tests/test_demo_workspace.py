"""演示空间使用真实API和隔离数据库，不接触真实账号。"""
from fastapi.testclient import TestClient

from backend.app import create_app


def test_demo_switch_retention_and_formal_isolation(tmp_path):
    app = create_app(tmp_path / 'formal')
    with TestClient(app) as client:
        assert client.post('/api/demo/enter').status_code == 200
        student = client.get('/api/auth/me').json()
        assert student['name'] == '蔡雨轩' and student['role'] == 'student'
        assert client.get('/api/jobs').json()
        switched = client.post('/api/demo/switch', json={'role': 'employer'})
        assert switched.status_code == 200
        assert client.get('/api/auth/me').json()['role'] == 'employer'
        assert client.get('/api/recruiting/candidates').json()
        assert client.post('/api/demo/switch', json={'role': 'admin'}).status_code == 422
        assert client.get('/api/admin/accounts').status_code == 403
        assert client.post('/api/demo/exit').status_code == 200
        assert client.get('/api/auth/me').status_code == 401
        assert client.post('/api/demo/enter').status_code == 200
        assert client.get('/api/auth/me').json()['role'] == 'employer'
    with app.state.store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM entities').fetchone()[0] == 0


def test_different_visitors_have_separate_workspaces(tmp_path):
    app = create_app(tmp_path / 'formal')
    with TestClient(app) as first, TestClient(app) as second:
        first.post('/api/demo/enter')
        second.post('/api/demo/enter')
        first.post('/api/demo/switch', json={'role': 'employer'})
        second.post('/api/demo/switch', json={'role': 'employer'})
        one = first.get('/api/jobs').json()[0]
        assert first.post('/api/recruiting/jobs/' + one['id'] + '/status', json={'status': 'paused'}).status_code == 200
        two = next(j for j in second.get('/api/jobs').json() if j['id'] == one['id'])
        assert two['status'] != 'paused'


def test_reset_recovers_slot_and_creation_is_throttled(tmp_path):
    app=create_app(tmp_path/'formal')
    with TestClient(app) as client:
        assert client.post('/api/demo/enter').status_code==200
        old=client.cookies.get('chanzhi_demo_workspace')
        assert client.post('/api/demo/reset').status_code==200
        new=client.cookies.get('chanzhi_demo_workspace')
        assert new!=old
        assert not (tmp_path/'formal/demo'/old).exists()
        assert (tmp_path/'formal/demo'/new/'workspace.json').is_file()
        assert client.post('/api/demo/reset').status_code==429
        assert client.get('/api/auth/me').status_code==200
