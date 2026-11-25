"""演示空间使用真实API和隔离数据库，不接触真实账号。"""
from fastapi.testclient import TestClient
from io import BytesIO
from openpyxl import load_workbook

from backend.app import create_app


def test_demo_recruiting_plan_changes_with_budget_and_exports(tmp_path):
    with TestClient(create_app(tmp_path / 'formal')) as client:
        assert client.post('/api/demo/enter').is_success
        assert client.post('/api/demo/switch', json={'role': 'employer'}).is_success
        ready = client.get('/api/recruiting/plans/readiness')
        assert ready.is_success
        assert ready.json()['eligible_students'] >= 2
        assert ready.json()['blocked']
        resources = {'training': 20000, 'mentor': 240}
        large = client.post('/api/recruiting/plans', json={**resources, 'salary': 150000}).json()
        small = client.post('/api/recruiting/plans', json={**resources, 'salary': 30000}).json()
        assert (len(large['result']['selected']), len(small['result']['selected'])) == (4, 2)
        comparison = client.get('/api/recruiting/plans/compare', params={'left': large['id'], 'right': small['id']})
        assert comparison.is_success and comparison.json()['removed']
        removed = {candidate['application_id'] for candidate in comparison.json()['removed']}
        assert all('月度薪资预算余额不足' in row['reasons'] for row in small['candidates']
                   if row['application_id'] in removed)
        path = f"/api/recruiting/plans/{large['id']}/export"
        download = client.get(path)
        assert download.is_success
        workbook = load_workbook(BytesIO(download.content), read_only=True)
        assert workbook.sheetnames == ['招聘总览', '建议名单', '待办与未入选', '岗位名额', '既有承诺']
        assert len(list(workbook['建议名单'].values)) == len(large['result']['selected']) + 1
        own_review = next(row for row in large['candidates'] if row['student_name'] == '蔡雨轩')
        assert client.post('/api/demo/switch', json={'role': 'student'}).is_success
        assert client.get(path).status_code == 403
        assert client.post(f"/api/applications/{own_review['application_id']}/withdraw").is_success
        assert client.post('/api/demo/switch', json={'role': 'employer'}).is_success
        stale = load_workbook(BytesIO(client.get(path).content), read_only=True)
        rows = [*stale['建议名单'].values, *stale['待办与未入选'].values]
        assert any(row[0] == '已撤回投递' and row[1] == own_review['job_title'] for row in rows)


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
