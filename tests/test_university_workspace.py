"""高校向导真实存储、校级隔离与确认边界；Header身份仅用于隔离API测试。"""
import importlib.util

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from backend.store import Store
from backend.university_courses import attach_university_courses
from backend.university_intelligence import _courses


def workspace_system(tmp_path):
    assert importlib.util.find_spec('backend.university_workspace'), '高校无JSON向导API尚未实现'
    from backend.university_workspace import attach_university_workspace
    app = FastAPI()
    store = Store(tmp_path)
    def current(x_school: str = Header('school-a'), x_role: str = Header('university')):
        return {'id': x_school, 'role': x_role}
    attach_university_courses(app, store, current)
    attach_university_workspace(app, store, current)
    return TestClient(app), store


def test_draft_version_owner_and_partial_course_mapping(tmp_path):
    client, store = workspace_system(tmp_path)
    store.save('university_course_catalog', 'school-a', {'courses': [
        {'code': 'A', 'name': '统计', 'credits': 2, 'hours': None, 'skills': ['Python']},
        {'code': 'B', 'name': '经济', 'credits': 2, 'hours': None, 'skills': []}], 'sources': []}, 'university-courses:school-a')
    assert _courses(store, 'school-a')['Python'] == 1
    draft = client.post('/api/university/workspaces', json={'major': '经济学'}).json()
    ident = draft['id']
    assert draft['version'] == 1
    assert client.get('/api/university/workspaces/' + ident, headers={'x-school': 'school-b'}).status_code == 403
    changed = client.put('/api/university/workspaces/' + ident, json={**draft, 'major': '经济学2'} )
    assert changed.status_code == 200, changed.text
    assert changed.json()['version'] == 2
    assert client.put('/api/university/workspaces/' + ident, json=draft).status_code == 409
    assert client.post('/api/university/workspaces', json={}, headers={'x-role': 'student'}).status_code == 403


def test_course_batch_revision_atomic_with_sources(tmp_path):
    client, store = workspace_system(tmp_path)
    store.save('university_course_catalog', 'school-a', {'courses': [
        {'code': 'A', 'name': '统计', 'credits': 2, 'hours': None, 'skills': []}], 'sources': []}, 'university-courses:school-a')
    payload = {'revisions': [{'code': 'A', 'hours': 32, 'skills': ['Python'], 'source_note': '教研室审核', 'confirmed': True}]}
    result = client.patch('/api/university/courses', json=payload)
    assert result.status_code == 200, result.text
    course = client.get('/api/university/courses').json()['courses'][0]
    assert course['hours'] == 32 and course['skills'] == ['Python']
    assert course['field_confirmations']['skills'] is True
    assert course['field_sources']['hours']['note'] == '教研室审核'
    payload['revisions'].append({'code': 'missing', 'hours': 3, 'confirmed': True, 'source_note': '审核'})
    assert client.patch('/api/university/courses', json=payload).status_code == 422


def test_ai_consent_and_manual_calculation_without_invented_baseline(tmp_path):
    client, store = workspace_system(tmp_path)
    doc = store.save('document', 'school-a', {'name': '方案', 'blocks': [{'location': '第1行', 'text': '统计课程训练Python'}]})
    draft = client.post('/api/university/workspaces', json={'major': '经济学'}).json()
    ident = draft['id']
    assert client.post(f'/api/university/workspaces/{ident}/extract', json={'document_ids': [doc], 'send_documents': False}).status_code == 422
    assert client.post(f'/api/university/workspaces/{ident}/extract', json={'document_ids': [doc], 'send_documents': True}, headers={'x-school': 'school-b'}).status_code == 403
    draft.update({'course_codes': [], 'skill_targets': [{'skill': 'Python', 'gap': 2, 'priority': 'core', 'confirmed': True, 'evidence': '教研室评审'}],
                  'limits': {'cost': 100, 'credits': 3, 'teacher_hours': 50, 'lab_hours': 50, 'study_hours': 50, 'months': 6},
                  'teaching_actions': [{'id': 'new-1', 'name': '数据项目', 'kind': 'add', 'cost': 20, 'credits': 2, 'teacher_hours': 20, 'lab_hours': 10, 'study_hours': 20, 'months': 3, 'gains': {'Python': 1}, 'confirmed': True,
                    'field_confirmations': {key: True for key in ['cost', 'credits', 'teacher_hours', 'lab_hours', 'study_hours', 'months', 'gains']},
                    'teaching_plan': {'confirmed': True, 'old_modules': [], 'modules': [{'name': 'Python项目', 'hours': 20, 'assessment': '数据作品'}], 'prerequisites': '统计学', 'semester': '第4学期', 'project': '分析报告', 'investment_notes': '已有机房', 'timeline': []}}]})
    saved = client.put(f'/api/university/workspaces/{ident}', json=draft)
    assert saved.status_code == 200, saved.text
    result = client.post(f'/api/university/workspaces/{ident}/calculate', json={'version': saved.json()['version']})
    assert result.status_code == 200, result.text
    assert result.json()['result']['selected'] == ['new-1']
    assert result.json()['result']['remaining']['Python'] == 1
    optimization = store.list('optimization', 'school-a')[0]['data']
    assert optimization['input']['courses'][0]['teaching_plan']['semester'] == '第4学期'
    assert 'employment' not in optimization
    stale = client.post(f'/api/university/workspaces/{ident}/calculate', json={'version': 1})
    assert stale.status_code == 409


def test_cost_objective_uses_cheapest_equal_benefit_solution():
    assert importlib.util.find_spec('backend.university_workspace')
    from backend import university_workspace
    assert hasattr(university_workspace, 'optimize_workspace'), '尚未实现同收益最小成本'
    common = {'credits': 1, 'teacher_hours': 1, 'lab_hours': 1, 'study_hours': 1, 'months': 1}
    courses = [dict(common, id='costly', name='高投入', cost=90, gains={'Python': 2}),
               dict(common, id='cheap', name='低投入', cost=10, gains={'Python': 2})]
    result = university_workspace.optimize_workspace({'Python': 2}, {'Python': 1}, courses,
        {'cost': 100, 'credits': 1, 'teacher_hours': 1, 'lab_hours': 1, 'study_hours': 1, 'months': 1}, 'cost_control')
    assert result['selected'] == ['cheap']
    assert result['used']['cost'] == 10 and result['remaining']['Python'] == 0


def test_ai_selected_blocks_advice_is_editable_unconfirmed_and_has_no_invented_numbers(tmp_path, monkeypatch):
    import json
    from backend import university_workspace as module
    client, store = workspace_system(tmp_path)
    doc = store.save('document', 'school-a', {'name': '合成培养段落', 'blocks': [
        {'location': '第1行', 'text': '统计课程加入Python数据分析项目，以分析报告作为作品。'},
        {'location': '第2行', 'text': '未授权外发内容'}]})
    draft = client.post('/api/university/workspaces', json={'major': '经济学'}).json()
    requests=[]
    class ExternalResponse:
        def raise_for_status(self):
            pass
        def json(self):
            evidence=[{'document_id':doc,'location':'第1行','quote':'加入Python数据分析项目'}]
            return {'choices':[{'message':{'content':json.dumps({'suggestions':[], 'teaching_suggestions':[
                {'name':'数据项目','course_name':'统计','new_modules':['Python项目'],'project':'分析报告','cost':999,'gains':{'Python':5},'evidence':evidence}]})}}]}
    class ExternalClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self,*args):
            pass
        def post(self,url,**kwargs):
            requests.append(kwargs['json'])
            return ExternalResponse()
    monkeypatch.setattr(module,'configuration',lambda:{'key':'test-only-key','base':'https://example.invalid','model':'test-only'})
    monkeypatch.setattr(module.httpx,'Client',ExternalClient)
    response=client.post(f"/api/university/workspaces/{draft['id']}/extract",json={'document_ids':[doc],'block_selections':{doc:[0]},'send_documents':True})
    assert response.status_code==200,response.text
    advice=response.json()['workspace']['teaching_suggestions'][0]
    assert advice['confirmed'] is False
    assert advice['cost'] is None and advice['gains']=={}
    assert advice['teaching_plan']['modules'][0]['name']=='Python项目'
    assert '未授权外发内容' not in json.dumps(requests,ensure_ascii=False)


def test_unconfirmed_values_and_unknown_action_kind_cannot_calculate(tmp_path):
    client,store=workspace_system(tmp_path)
    draft=client.post('/api/university/workspaces',json={'major':'经济学',
        'skill_targets':[{'skill':'Python','gap':1,'confirmed':'false','evidence':'待审核'}],
        'teaching_actions':[{'id':'x','name':'删除动作','kind':'delete','confirmed':True,
                             'field_confirmations':{key:True for key in ['cost','credits','teacher_hours','lab_hours','study_hours','months','gains']},
                             **{key:1 for key in ['cost','credits','teacher_hours','lab_hours','study_hours','months']},'gains':{'Python':1}}],
        'limits':{key:10 for key in ['cost','credits','teacher_hours','lab_hours','study_hours','months']}}).json()
    response=client.post(f"/api/university/workspaces/{draft['id']}/calculate",json={'version':draft['version']})
    assert response.status_code==422,response.text
    draft['skill_targets'][0]['confirmed']=True
    saved=client.put('/api/university/workspaces/'+draft['id'],json=draft).json()
    response=client.post(f"/api/university/workspaces/{draft['id']}/calculate",json={'version':saved['version']})
    assert response.status_code==422,response.text
    assert not store.list('optimization','school-a')
