"""非招聘状态不得影响高校需求或新增招聘分配。"""
import pytest
from backend.app import create_app
from tests.test_api import account, job_data


@pytest.mark.parametrize('flags', [{'status':'draft'}, {'status':'paused'}, {'status':'closed'}, {'deleted':True}, {'closed':True}])
def test_inactive_job_excluded_from_insights(tmp_path, flags):
    app=create_app(tmp_path)
    school=account(app,'university','scope-school')
    employer=account(app,'employer','scope-company')
    owner=school.get('/api/auth/me').json()['id']
    for i in range(5):
        app.state.store.save('profile',str(i),{'school_id':owner,'abilities':{'SQL':{'level':2}}})
    spec=job_data();spec['requirements']=[{'skill':'SQL','target':3,'weight':1}]
    assert employer.post('/api/jobs',json=spec).status_code==200
    spec['requirements'][0]['target']=5
    other=employer.post('/api/jobs',json=spec).json()
    item=app.state.store.get(other['id'])
    app.state.store.save('job',item['owner'],{**item['data'],**flags},item['id'])
    row=school.get('/api/university/insights').json()['skills'][0]
    assert row['target']==3 and row['gap']==1


@pytest.mark.parametrize('stage,status', [('declined','published'),('reviewing','paused'),('offer','closed')])
def test_allocation_filters_business_state(tmp_path, monkeypatch, stage, status):
    app=create_app(tmp_path)
    employer=account(app,'employer','allocation-company')
    student=account(app,'student','allocation-student')
    job=employer.post('/api/jobs',json=job_data()).json()
    applied=student.post('/api/applications',json={'job_id':job['id'],'consent':True}).json()
    item=app.state.store.get(applied['id'])
    app.state.store.save('application',item['owner'],{**item['data'],'stage':stage},item['id'])
    item=app.state.store.get(job['id'])
    app.state.store.save('job',item['owner'],{**item['data'],'status':status},item['id'])
    # 断言服务端传给真实求解器的集合，独立于匹配分数和求解器选人。
    from backend.matching import allocate
    def checked(pairs,jobs,budget):
        assert pairs==[]
        return allocate(pairs,jobs,budget)
    monkeypatch.setattr('backend.app.allocate',checked)
    result=employer.post('/api/employer/allocate',json={'salary':50000,'training':10000,'mentor':100})
    assert result.status_code==200 and result.json()['selected']==[]


def test_real_allocation_after_decline_pause_close_and_restore(tmp_path):
    app=create_app(tmp_path)
    company=account(app,'employer','real-allocation-company')
    student=account(app,'student','real-allocation-student')
    spec=job_data()
    spec['requirements']=[{'skill':'产品设计','target':3,'weight':1}]
    spec['questions']=[{'id':'q1','title':'说明验证过程','skill':'产品设计','rubric':'引用具体行动'}]
    job=company.post('/api/jobs',json=spec).json()
    aid=student.post('/api/applications',json={'job_id':job['id'],'consent':True}).json()['id']
    assert student.post(f'/api/applications/{aid}/answers',json={'job_version':1,'answers':{'q1':'访谈、原型测试与修订'}}).status_code==200
    revision=company.get(f'/api/applications/{aid}').json()['revision']
    reviewed=company.post(f'/api/applications/{aid}/review',json={'revision':revision,'abilities':{'产品设计':{'level':5,'evidence':'q1：访谈、原型测试与修订'}},'background':{}})
    assert reviewed.status_code==200,reviewed.text
    assert company.post(f'/api/applications/{aid}/choice',json={'chosen':True}).status_code==200
    budget={'salary':20000,'training':1000,'mentor':10}
    def selected():
        response=company.post('/api/employer/allocate',json=budget)
        assert response.status_code==200,response.text
        return response.json()['selected']
    assert selected()==[aid]
    stage_url=f'/api/recruiting/applications/{aid}/stage'
    assert company.post(stage_url,json={'stage':'declined'}).status_code==200
    assert selected()==[]
    assert company.post(stage_url,json={'stage':'reviewing'}).status_code==200
    assert selected()==[aid]
    for status in ['paused','closed','draft']:
        assert company.post(f'/api/recruiting/jobs/{job["id"]}/status',json={'status':status}).status_code==200
        assert selected()==[]
    assert company.post(f'/api/recruiting/jobs/{job["id"]}/status',json={'status':'published'}).status_code==200
    assert selected()==[aid]
