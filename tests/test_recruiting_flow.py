from fastapi.testclient import TestClient
import json

from backend.app import create_app


def test_candidate_materials_contact_and_message_ownership(tmp_path):
    app=create_app(tmp_path/'formal')
    with TestClient(app) as client, TestClient(app) as outsider:
        assert client.post('/api/demo/enter').status_code==200
        student=client.get('/api/auth/me').json()
        client.post('/api/demo/switch',json={'role':'employer'})
        assert any(c['id']==student['id'] for c in client.get('/api/recruiting/candidates').json())
        detail=client.get('/api/recruiting/candidates/'+student['id'])
        assert detail.status_code==200
        assert 'school_code' not in detail.json() and detail.json()['documents']
        assert client.get(detail.json()['documents'][0]['url']).status_code==200
        for work in detail.json()['portfolio']:
            assert client.get(work['url']).status_code==200
        assert client.put('/api/recruiting/favorites/'+student['id']).status_code==200
        thread=client.post('/api/conversations',json={'target_id':student['id']}).json()['id']
        assert client.post('/api/conversations/'+thread+'/messages',json={'text':'请介绍投研助手项目'}).status_code==200
        client.post('/api/demo/switch',json={'role':'student'})
        assert client.get('/api/conversations/'+thread+'/messages').json()[-1]['text']=='请介绍投研助手项目'
        assert client.post('/api/conversations/'+thread+'/messages',json={'text':'我负责产品需求与引用核查设计'}).status_code==200
        assert client.get('/api/recruiting/candidates').status_code==403
        outsider.post('/api/demo/enter')
        assert outsider.get('/api/conversations/'+thread+'/messages').status_code in {403,404}
        client.post('/api/demo/switch',json={'role':'university'})
        assert client.get('/api/conversations/'+thread+'/messages').status_code==403
        assert client.get('/api/competition/runs').json()
        assert client.get('/api/university/courses').json()['courses']


def test_demo_preserves_formal_session_and_rejects_cross_origin(tmp_path):
    app=create_app(tmp_path/'formal')
    with TestClient(app) as client:
        formal=client.post('/api/auth/register',json={'username':'formal-student','password':'long-password-123','name':'正式账号','role':'student'}).json()
        client.post('/api/demo/enter')
        demo=client.get('/api/auth/me').json()
        assert demo['id']!=formal['id']
        assert client.get('/api/jobs',headers={'X-Workspace-ID':formal['id']}).status_code==409
        assert client.post('/api/demo/switch',json={'role':'employer'},headers={'Origin':'https://external.example'}).status_code==403
        client.post('/api/demo/exit')
        assert client.get('/api/auth/me').json()['id']==formal['id']


def test_new_application_appears_for_company_and_withdraw_revokes_material(tmp_path):
    app=create_app(tmp_path/'formal')
    with TestClient(app) as client:
        client.post('/api/demo/enter')
        sid=client.get('/api/auth/me').json()['id']
        previous=client.get('/api/applications').json()
        used={a['job_id'] for a in previous}
        target=next(j for j in client.get('/api/jobs').json() if j['id'] not in used)
        upload=client.post('/api/documents',files={'file':('项目补充.md','独立测试项目材料'.encode(),'text/markdown')})
        assert upload.status_code==200
        did=upload.json()['id']
        applied=client.post('/api/applications',json={'job_id':target['id'],'consent':True,'document_ids':[did]})
        assert applied.status_code==200
        aid=applied.json()['id']
        client.post('/api/demo/switch',json={'role':'employer'})
        row=next(c for c in client.get('/api/recruiting/candidates').json() if c['id']==sid)
        assert any(a['id']==aid for a in row['applications'])
        assert client.get('/api/documents/'+did).status_code==200
        client.post('/api/demo/switch',json={'role':'student'})
        assert client.post('/api/applications/'+aid+'/withdraw').status_code==200
        client.post('/api/demo/switch',json={'role':'employer'})
        assert client.get('/api/documents/'+did).status_code==403


def test_expired_demo_can_exit_and_restore_formal_session(tmp_path):
    app=create_app(tmp_path/'formal')
    with TestClient(app) as client:
        formal=client.post('/api/auth/register',json={'username':'expiry-user','password':'long-password-123','name':'正式账号','role':'student'}).json()
        client.post('/api/demo/enter')
        key=client.cookies.get('chanzhi_demo_workspace')
        path=tmp_path/'formal/demo'/key/'workspace.json'
        data=json.loads(path.read_text());data['expires']=0
        path.write_text(json.dumps(data))
        assert client.get('/api/auth/me').status_code==401
        assert client.get('/api/demo/status').json()['expired'] is True
        assert client.post('/api/demo/exit').status_code==200
        assert client.get('/api/auth/me').json()['id']==formal['id']
