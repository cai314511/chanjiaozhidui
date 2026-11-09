"""企业候选人、收藏、岗位状态与站内双向消息。权限在接口入口检查。"""
import hashlib
import json
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import Field

from backend.presentation import public_product
from backend.schemas import Model
from backend.store import encode, now, uid


class JobStatus(Model):
    status: Literal['draft', 'published', 'paused', 'closed']


class Contact(Model):
    target_id: str = Field(min_length=1, max_length=100)


class Message(Model):
    text: str = Field(min_length=1, max_length=4000)


class Stage(Model):
    stage: Literal['new', 'reviewing', 'interview', 'offer', 'declined']


def attach_recruiting(app, store, user, flat, application_result):
    def employer(current):
        if current['role'] != 'employer':
            raise HTTPException(403, '仅企业账号可管理招聘')

    def active_applications(employer_id, student_id=None):
        jobs = {j['id'] for j in store.list('job', employer_id)}
        return [a for a in store.list('application', student_id) if a['data']['job_id'] in jobs and not a['data'].get('withdrawn')]

    def account(ident):
        with store.connect() as db:
            row = db.execute('SELECT id,name,role FROM users WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise HTTPException(404, '账号不存在')
        return dict(row)

    def favorite_id(owner, student):
        return 'candidate-star-' + hashlib.sha256((owner+':'+student).encode()).hexdigest()

    @app.get('/api/recruiting/candidates')
    def candidates(current=Depends(user)):
        employer(current)
        grouped = {}
        for item in active_applications(current['id']):
            sid = item['owner']
            if sid not in grouped:
                profile = store.list('profile', sid)
                p = profile[0]['data'] if profile else {}
                grouped[sid] = {'id': sid, 'name': account(sid)['name'], 'major': p.get('major',''),
                                'school': p.get('school_name',''), 'career': p.get('career',''),
                                'favorite': bool(store.get(favorite_id(current['id'],sid), 'candidate_favorite')), 'applications': []}
            job = store.get(item['data']['job_id'], 'job')
            result = application_result(item, job)
            grouped[sid]['applications'].append({'id':item['id'],'job_id':job['id'],'title':job['data']['title'],
                'stage':item['data'].get('stage','new'), 'match':public_product(result['match']), 'created':item['created']})
        return list(grouped.values())

    @app.get('/api/recruiting/candidates/{student_id}')
    def candidate(student_id: str, current=Depends(user)):
        employer(current)
        apps = active_applications(current['id'], student_id)
        if not apps:
            raise HTTPException(403, '没有该学生的有效投递授权')
        p = store.list('profile',student_id)
        profile = p[0]['data'] if p else {}
        docs = set(d for a in apps for d in a['data'].get('document_ids',[]))
        works = set(d for a in apps for d in a['data'].get('portfolio_ids',[]))
        def resources(ids, kind):
            result=[]
            for ident in ids:
                item=store.get(ident,kind)
                if item and item['owner']==student_id:
                    result.append({'id':ident,'name':item['data'].get('name','资料'),
                                   'mime':item['data'].get('mime',''),
                                   'url':f'/api/documents/{ident}' if kind=='document' else f'/api/portfolio/{ident}/file'})
            return result
        return public_product({'id':student_id,'name':account(student_id)['name'],
                'school':profile.get('school_name',''),'major':profile.get('major',''),
                'career':profile.get('career',''),'experience':profile.get('experience',''),
                'abilities':profile.get('abilities',{}),'documents':resources(docs,'document'),
                'portfolio':resources(works,'portfolio'),'favorite':bool(store.get(favorite_id(current['id'],student_id),'candidate_favorite'))})

    @app.put('/api/recruiting/favorites/{student_id}')
    def favorite(student_id: str, current=Depends(user)):
        candidate(student_id,current)
        store.save('candidate_favorite',current['id'],{'student_id':student_id},favorite_id(current['id'],student_id))
        return {'saved':True}

    @app.delete('/api/recruiting/favorites/{student_id}')
    def unfavorite(student_id: str, current=Depends(user)):
        employer(current)
        with store.connect() as db:
            db.execute("DELETE FROM entities WHERE id=? AND kind='candidate_favorite' AND owner=?",(favorite_id(current['id'],student_id),current['id']))
        return {'saved':False}

    @app.post('/api/recruiting/jobs/{ident}/status')
    def job_status(ident: str, payload: JobStatus, current=Depends(user)):
        employer(current)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM entities WHERE id=? AND kind='job'",(ident,)).fetchone()
            if row is None or row['owner']!=current['id']:
                raise HTTPException(403,'只能管理本公司的岗位')
            data=json.loads(row['data']);data['status']=payload.status
            db.execute('UPDATE entities SET data=?,updated=? WHERE id=?',(encode(data),now(),ident))
        return {'id':ident,'status':payload.status}

    @app.post('/api/recruiting/applications/{ident}/stage')
    def stage(ident: str, payload: Stage, current=Depends(user)):
        employer(current)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM entities WHERE id=? AND kind='application'",(ident,)).fetchone()
            if row is None:raise HTTPException(404,'投递不存在')
            data=json.loads(row['data'])
            job=db.execute("SELECT owner FROM entities WHERE id=? AND kind='job'",(data['job_id'],)).fetchone()
            if not job or job['owner']!=current['id'] or data.get('withdrawn'):raise HTTPException(403,'没有当前投递授权')
            data['stage']=payload.stage
            db.execute('UPDATE entities SET data=?,updated=? WHERE id=?',(encode(data),now(),ident))
        return {'id':ident,'stage':payload.stage}

    def conversation(ident,current):
        item=store.get(ident,'conversation')
        if item is None:raise HTTPException(404,'会话不存在')
        if current['id'] not in item['data']['participants']:raise HTTPException(403,'只能访问自己的会话')
        return item

    @app.post('/api/conversations')
    def contact(payload: Contact,current=Depends(user)):
        other=account(payload.target_id)
        if {current['role'],other['role']}!={'student','employer'}:raise HTTPException(403,'仅支持企业与学生沟通')
        emp=current['id'] if current['role']=='employer' else other['id']
        sid=other['id'] if other['role']=='student' else current['id']
        if not active_applications(emp,sid):raise HTTPException(403,'请先完成岗位投递授权后联系')
        ident='conversation-'+hashlib.sha256((emp+':'+sid).encode()).hexdigest()
        with store.connect() as db:
            stamp=now()
            db.execute('INSERT OR IGNORE INTO entities VALUES(?,?,?,?,?,?)',
                       (ident,'conversation',emp,encode({'participants':[emp,sid]}),stamp,stamp))
        return {'id':ident}

    @app.get('/api/conversations')
    def conversations(current=Depends(user)):
        if current['role'] not in {'employer','student'}:raise HTTPException(403,'当前身份没有消息权限')
        result=[]
        for item in store.list('conversation'):
            people=item['data']['participants']
            if current['id'] not in people:continue
            other=account(next(i for i in people if i!=current['id']))
            messages=[m for m in store.list('direct_message',item['id'])]
            last=messages[0]['data'] if messages else {}
            result.append({'id':item['id'],'other':other,'last_text':last.get('text','开始沟通岗位与发展方向'),'updated':messages[0]['created'] if messages else item['created']})
        return sorted(result,key=lambda x:x['updated'],reverse=True)

    @app.get('/api/conversations/{ident}/messages')
    def messages(ident: str,current=Depends(user)):
        conversation(ident,current)
        return [flat(m) for m in reversed(store.list('direct_message',ident))]

    @app.post('/api/conversations/{ident}/messages')
    def send_message(ident: str,payload: Message,current=Depends(user)):
        conversation(ident,current)
        text=payload.text.strip()
        if not text:raise HTTPException(422,'消息不能为空')
        message_id=store.save('direct_message',ident,{'text':text,'sender':current['id']})
        return flat(store.get(message_id,'direct_message'))
