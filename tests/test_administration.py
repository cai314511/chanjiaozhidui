import json

from fastapi.testclient import TestClient

from backend.initial_data import initialize
from tests.test_api import account, system


def test_initialization_and_admin_permissions(system):
    store = system.state.store
    assert initialize(store)['created']
    assert not initialize(store)['created']
    assert len(store.list('profile')) == 15
    assert len(store.list('university_profile')) == 3
    assert store.list('job') == []
    credentials = json.loads((store.root / 'account-access.json').read_text(encoding='utf-8'))
    admin = TestClient(system)
    secret = next(c for c in credentials if c['role'] == 'admin')
    assert admin.post('/api/auth/login', json={k: secret[k] for k in ['username','password']}).status_code == 200
    accounts = admin.get('/api/admin/accounts').json()
    student = next(a for a in accounts if a['role'] == 'student')
    university = next(a for a in accounts if a['role'] == 'university')
    token = admin.cookies.get('chanzhi_session')
    assert admin.post('/api/admin/workspace', json={'user_id': student['id']}).status_code == 200
    assert admin.cookies.get('chanzhi_session') == token
    assert admin.get('/api/profile').json()['school_name']
    docs = admin.get('/api/documents').json()
    assert len(docs) == 1
    assert admin.get('/api/documents/'+docs[0]['id']+'/download').status_code == 200
    assert admin.post('/api/admin/workspace', json={'user_id': university['id']}).status_code == 200
    assert admin.get('/api/university/insights').json()['sample_count'] == 5
    assert admin.get('/api/university/profile').json()['program']['courses']
    assert admin.get('/api/documents/'+docs[0]['id']).status_code == 403
    assert admin.delete('/api/admin/workspace').json()['role'] == 'admin'
    assert admin.post('/api/admin/workspace', json={'user_id': secret.get('id','nonexistent')}).status_code == 404
    normal = account(system, 'student', 'independent-student')
    assert normal.get('/api/admin/accounts').status_code == 403
    assert normal.post('/api/admin/workspace', json={'user_id': university['id']}).status_code == 403
    assert normal.post('/api/auth/register', json={'username':'badadmin','password':'test-password-123','name':'bad','role':'admin'}).status_code == 422
    assert admin.post('/api/auth/logout').status_code == 200
    assert admin.get('/api/admin/accounts').status_code == 401
