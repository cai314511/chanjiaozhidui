import io
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from backend.app import create_app


@pytest.fixture
def school_system():
    root=Path(__file__).resolve().parents[1]/'runtime'/'tests'/uuid4().hex
    app=create_app(root)
    client=TestClient(app,raise_server_exceptions=False)
    response=client.post('/api/auth/register',json={
        'username':'course-review-school','password':'test-password-123',
        'name':'课程导入测试高校','role':'university',
    })
    assert response.status_code==200
    return app,client


def test_long_csv_field_returns_validation_error_and_preserves_catalog(school_system):
    app,client=school_system
    good='课程代码,课程名称,学分,总学时,能力标签\nCS101,数据分析,3,48,Python\n'.encode('utf-8-sig')
    assert client.post('/api/university/materials/import',files={
        'file':('课程.csv',good,'text/csv'),
    }).status_code==200
    before=client.get('/api/university/courses').json()
    # 在12MB上传限制内，但超过csv解析器的单字段长度限制。
    oversized_field=('课程名称\n'+'字'*140000).encode('utf-8-sig')
    result=client.post('/api/university/materials/import',files={
        'file':('长字段.csv',oversized_field,'text/csv'),
    })
    assert result.status_code==422,result.text
    assert client.get('/api/university/courses').json()==before


def test_program_document_import_is_idempotent_and_scoped(school_system):
    app,client=school_system
    content='培养依据：数据分析课程与实践要求。'.encode()

    def upload(target,kind='program'):
        response=target.post('/api/university/materials/import',files={
            'file':('program.txt',content,'text/plain'),
        },data={'kind':kind})
        assert response.status_code==200,response.text
        return response.json()['document_id']

    first=upload(client)
    assert upload(client)==first
    assert len(client.get('/api/documents').json())==1
    assert client.get(f'/api/documents/{first}/download').content==content
    # 同一文件可明确归入不同用途，两种用途各自保持幂等。
    teaching=upload(client,'teaching')
    assert teaching!=first
    assert upload(client,'teaching')==teaching
    assert len(client.get('/api/documents').json())==2
    other=TestClient(app)
    response=other.post('/api/auth/register',json={
        'username':'course-review-other','password':'test-password-123',
        'name':'另一所测试高校','role':'university',
    })
    assert response.status_code==200
    assert other.get(f'/api/documents/{first}').status_code==403
    other_id=upload(other)
    assert other_id!=first
    assert len(other.get('/api/documents').json())==1
    assert client.get(f'/api/documents/{other_id}').status_code==403


def test_school_course_import_is_scoped_and_rejects_invented_units(tmp_path):
    app=create_app(tmp_path)
    with TestClient(app) as first, TestClient(app) as second:
        for client,name in [(first,'school-one'),(second,'school-two')]:
            assert client.post('/api/auth/register',json={'username':name,'password':'test-password-123','name':name,'role':'university'}).status_code==200
        content='课程代码,课程名称,学分,总学时,能力标签\nCS101,数据分析,3,48,"Python;SQL"\n'.encode('utf-8-sig')
        response=first.post('/api/university/materials/import',files={'file':('课程.csv',content,'text/csv')},data={'kind':'courses'})
        assert response.status_code==200
        courses=first.get('/api/university/courses').json()['courses']
        assert courses[0]['skills']==['Python','SQL']
        assert courses[0]['hours']==48
        assert second.get('/api/university/courses').json()['courses']==[]
        bad=first.post('/api/university/materials/import',files={'file':('课程.csv','课程名称,学分,总学时\n错误课程,-3,48\n'.encode(),'text/csv')},data={'kind':'courses'})
        assert bad.status_code==422
        assert len(first.get('/api/university/courses').json()['courses'])==1
