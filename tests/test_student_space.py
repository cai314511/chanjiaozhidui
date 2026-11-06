"""学生公开主页的权限、发布快照与头像边界。"""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image, PngImagePlugin

from backend.app import create_app


@pytest.fixture
def space():
    root = Path(__file__).resolve().parents[1] / 'runtime' / 'tests' / uuid4().hex
    app = create_app(root)
    clients = {}
    for role in ('student', 'employer', 'university'):
        client = TestClient(app)
        result = client.post('/api/auth/register', json={
            'username': f'space-{role}', 'password': 'test-password-123',
            'name': f'private-account-{role}', 'role': role,
        })
        assert result.status_code == 200, result.text
        clients[role] = client
    return app, clients


def save_page(client, **changes):
    payload = {
        'display_name': '蔡同学', 'headline': '经济学与人工智能',
        'bio': '欢迎交流我的作品', 'school': '中央财经大学', 'major': '经济学',
        'education': '本科二年级', 'background': '银行智能体项目',
        'interests': ['AI产品', '摄影'], 'strengths': ['产品设计'],
        'links': [{'title': '个人网站', 'url': 'https://example.com/portfolio'}],
        'document_ids': [], 'portfolio_ids': [],
    }
    payload.update(changes)
    return client.put('/api/me/page', json=payload)


def test_page_draft_private_and_published_snapshot_visible_to_three_roles(space):
    app, clients = space
    student = clients['student']
    sid = student.get('/api/auth/me').json()['id']
    assert save_page(student).status_code == 200
    for client in clients.values():
        assert client.get('/api/students').json() == []
        assert client.get(f'/api/students/{sid}').status_code == 404
    assert student.post('/api/me/page/publish').status_code == 200
    for client in clients.values():
        page = client.get(f'/api/students/{sid}').json()
        assert page['display_name'] == '蔡同学'
        assert len(client.get('/api/students').json()) == 1
        assert 'username' not in page and 'school_code' not in page
        assert 'private-account-student' not in str(page)
    assert save_page(student, display_name='私有草稿姓名').status_code == 200
    assert clients['employer'].get(f'/api/students/{sid}').json()['display_name'] == '蔡同学'
    draft = student.get('/api/me/page').json()
    assert draft['draft']['display_name'] == '私有草稿姓名'
    assert draft['published']['display_name'] == '蔡同学'
    assert student.delete('/api/me/page/publish').status_code == 200
    assert clients['employer'].get(f'/api/students/{sid}').status_code == 404
    assert clients['university'].get('/api/students').json() == []
    assert student.get('/api/me/page').json()['draft']['display_name'] == '私有草稿姓名'
    assert TestClient(app).get('/api/students').status_code == 401


def test_other_student_can_view_only_explicitly_published_page(space):
    app, clients = space
    visitor = TestClient(app)
    registered = visitor.post('/api/auth/register', json={
        'username': 'visitor-student', 'password': 'test-password-123',
        'name': '学生访客', 'role': 'student',
    })
    assert registered.status_code == 200
    student = clients['student']
    sid = student.get('/api/auth/me').json()['id']
    assert student.post('/api/me/page/publish').status_code == 422
    assert save_page(student).status_code == 200
    assert visitor.get(f'/api/students/{sid}').status_code == 404
    student.post('/api/me/page/publish')
    assert visitor.get(f'/api/students/{sid}').json()['display_name'] == '蔡同学'
    assert visitor.get('/api/me/page').json()['published'] is None
    assert save_page(student, display_name='新发布姓名').status_code == 200
    student.post('/api/me/page/publish')
    assert visitor.get(f'/api/students/{sid}').json()['display_name'] == '新发布姓名'


def test_selected_files_are_shared_and_withdrawal_revokes_all_roles(space):
    app, clients = space
    student = clients['student']
    selected = student.post('/api/documents', files={
        'file': ('resume.txt', '我的简历'.encode(), 'text/plain'),
    }).json()['id']
    private = student.post('/api/documents', files={
        'file': ('private.txt', '私人记录'.encode(), 'text/plain'),
    }).json()['id']
    portfolio = student.post('/api/portfolio', files={
        'file': ('work.txt', b'my work', 'text/plain'),
    }).json()['id']
    assert save_page(student, document_ids=[selected], portfolio_ids=[portfolio]).status_code == 200
    assert student.post('/api/me/page/publish').status_code == 200
    for role in ('employer', 'university'):
        viewer = clients[role]
        assert viewer.get(f'/api/documents/{selected}').status_code == 200
        assert viewer.get(f'/api/documents/{selected}/download').status_code == 200
        assert viewer.get(f'/api/documents/{private}').status_code == 403
        assert viewer.get(f'/api/portfolio/{portfolio}').status_code == 200
        assert viewer.get(f'/api/portfolio/{portfolio}/file').content == b'my work'
    save_page(student, document_ids=[private])
    assert clients['employer'].get(f'/api/documents/{private}').status_code == 403
    student.delete('/api/me/page/publish')
    for role in ('employer', 'university'):
        assert clients[role].get(f'/api/documents/{selected}').status_code == 403
        assert clients[role].get(f'/api/portfolio/{portfolio}/file').status_code == 403
    assert student.get(f'/api/documents/{selected}').status_code == 200


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:text/html,hello',
                                 'https://name:secret@example.com', '//example.com',
                                 'https://example.com/\nattack'])
def test_page_rejects_unsafe_links(space, url):
    assert save_page(space[1]['student'], links=[{'title': '网站', 'url': url}]).status_code == 422


def test_page_ownership_and_private_fields_rejected(space):
    app, clients = space
    other = clients['employer'].post('/api/documents', files={
        'file': ('other.txt', b'other account', 'text/plain'),
    }).json()['id']
    assert save_page(clients['student'], document_ids=[other]).status_code == 403
    assert save_page(clients['student'], portfolio_ids=[other]).status_code == 422
    assert save_page(clients['student'], school_code='private-code').status_code == 422
    for role in ('employer', 'university'):
        assert clients[role].get('/api/me/page').status_code == 403
        assert save_page(clients[role]).status_code == 403
        assert clients[role].post('/api/me/page/publish').status_code == 403
        assert clients[role].delete('/api/me/page/publish').status_code == 403


def image_bytes(color):
    stream = BytesIO()
    meta = PngImagePlugin.PngInfo()
    meta.add_text('private-metadata', 'secret location')
    Image.new('RGB', (20, 20), color).save(stream, 'PNG', pnginfo=meta)
    return stream.getvalue()


def test_avatar_is_decoded_stripped_and_public_only_from_snapshot(space):
    app, clients = space
    student, employer = clients['student'], clients['employer']
    sid = student.get('/api/auth/me').json()['id']
    first = student.post('/api/me/avatar', files={
        'file': ('head.png', image_bytes('red'), 'image/png'),
    })
    assert first.status_code == 200, first.text
    url = first.json()['avatar_url']
    assert employer.get(url).status_code == 404
    private_image = student.get(url)
    assert private_image.status_code == 200
    assert Image.open(BytesIO(private_image.content)).info == {}
    save_page(student)
    student.post('/api/me/page/publish')
    assert employer.get(url).status_code == 200
    second = student.post('/api/me/avatar', files={
        'file': ('head.png', image_bytes('blue'), 'image/png'),
    }).json()['avatar_url']
    assert second != url
    assert employer.get(second).status_code == 404
    assert employer.get(f'/api/students/{sid}').json()['avatar_url'] == url
    assert employer.get(url).content == private_image.content
    student.delete('/api/me/page/publish')
    assert employer.get(url).status_code == 404


@pytest.mark.parametrize('filename,content', [
    ('head.png', b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'),
    ('head.png', b'not an image'), ('head.svg', image_bytes('red')),
    ('head.png', b'x' * (3 * 1024 * 1024 + 1)),
])
def test_avatar_rejects_spoofed_and_oversized_files(space, filename, content):
    result = space[1]['student'].post('/api/me/avatar', files={
        'file': (filename, content, 'image/png'),
    })
    assert result.status_code == 422
