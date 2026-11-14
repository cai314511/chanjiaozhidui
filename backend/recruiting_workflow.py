"""招聘邀约、正式意向与持久招聘计划。状态变更和名额检查共用 SQLite 写事务。"""
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException
from pydantic import Field, model_validator

from backend.matching import allocate
from backend.eligibility import validate_job_publish
from backend.job_state import active_job
from backend.schemas import Budget, Model
from backend.store import encode, now, uid


def resource_cost(job):
    return {'salary': job['salary_max'], 'training': job.get('training_cost', 0),
            'mentor': job.get('mentor_hours', 0)}


def budget_commitments(db, employer_id):
    records = []
    for row in db.execute("SELECT id,data FROM entities WHERE kind='recruiting_offer' AND owner=?", (employer_id,)).fetchall():
        offer = json.loads(row['data'])
        if offer['status'] not in {'accepted', 'hired'}:
            continue
        resources = offer.get('resource_commitment')
        if resources is None:
            version = db.execute('SELECT data FROM job_versions WHERE job_id=? AND version=?',
                                 (offer['job_id'], offer['job_version'])).fetchone()
            if version is None:
                raise HTTPException(409, '既有意向缺少原岗位金额版本，需核对后才能计算企业总预算')
            resources = resource_cost(json.loads(version['data']))
        job = entity_row(db, offer['job_id'], 'job')
        student = db.execute('SELECT name FROM users WHERE id=?', (offer['student_id'],)).fetchone()
        records.append({'offer_id': row['id'], 'status': offer['status'], 'job_id': offer['job_id'],
                        'job_version': offer['job_version'], 'job_title': job['data']['title'],
                        'student_name': student['name'], 'resources': resources})
    used = {key: float(sum((Decimal(str(r['resources'][key])) for r in records), Decimal(0)))
            for key in ('salary', 'training', 'mentor')}
    return records, used


class Invitation(Model):
    starts_at: datetime
    timezone: str = Field(default='Asia/Shanghai', max_length=80)
    duration_minutes: int = Field(default=30, ge=5, le=480)
    instructions: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def valid_time(self):
        if self.starts_at.tzinfo is None:
            raise ValueError('面试时间必须包含时区偏移')
        try:
            zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError:
            raise ValueError('时区不存在')
        if self.starts_at.utcoffset() != self.starts_at.astimezone(zone).utcoffset():
            raise ValueError('面试时间偏移与所选时区不一致')
        if self.starts_at <= datetime.now(timezone.utc):
            raise ValueError('请选择未来的面试时间')
        return self


class InvitationResponse(Model):
    revision: str = Field(min_length=1, max_length=80)
    action: Literal['accept', 'decline', 'reschedule', 'cancel']
    proposal: Invitation | None = None
    note: str = Field(default='', max_length=4000)


class Offer(Model):
    message: str = Field(min_length=1, max_length=4000)


class OfferResponse(Model):
    revision: str = Field(min_length=1, max_length=80)
    action: Literal['accept', 'decline', 'confirm', 'revoke']
    note: str = Field(default='', max_length=4000)


def entity_row(db, ident, kind):
    row = db.execute('SELECT * FROM entities WHERE id=? AND kind=?', (ident, kind)).fetchone()
    if row is None:
        raise HTTPException(404, '记录不存在')
    return {**dict(row), 'data': json.loads(row['data'])}


def write(db, item, data):
    stamp = now()
    db.execute('UPDATE entities SET data=?,updated=? WHERE id=?', (encode(data), stamp, item['id']))
    return {**data, 'id': item['id'], 'created': item['created'], 'revision': stamp}


def insert(db, kind, owner, data):
    ident, stamp = uid(), now()
    db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?)', (ident, kind, owner, encode(data), stamp, stamp))
    return {**data, 'id': ident, 'created': stamp, 'revision': stamp}


def occupancy(db, job_id, exclude=None):
    return sum(1 for row in db.execute("SELECT id,data FROM entities WHERE kind='recruiting_offer'").fetchall()
               if row['id'] != exclude and (d := json.loads(row['data'])).get('job_id') == job_id and d['status'] in {'accepted', 'hired'})


def validate_job_capacity(db, job_id, capacity):
    occupied = occupancy(db, job_id)
    if capacity < occupied:
        raise HTTPException(409, f'该岗位已有{occupied}个已接受意向或录用名额，不能缩减到{capacity}')


def validate_invitation_room(db, data, ident):
    if not data.get('invitation_id'):
        return
    invitation = entity_row(db, data['invitation_id'], 'recruiting_invitation')['data']
    if invitation['status'] != 'confirmed' or invitation.get('interview_id') != ident:
        raise HTTPException(403, '面试邀约已取消或改期，当前面试室已关闭')


def release_application_workflow(db, application_id, reason='withdrawn'):
    for kind in ('recruiting_offer', 'recruiting_invitation'):
        for row in db.execute('SELECT * FROM entities WHERE kind=?', (kind,)).fetchall():
            data = json.loads(row['data'])
            if data.get('application_id') != application_id or data['status'] in {'declined', 'revoked', 'cancelled'}:
                continue
            data['status'] = 'revoked' if kind == 'recruiting_offer' else 'cancelled'
            data.setdefault('history', []).append({'at': now(), 'action': reason})
            write(db, dict(row), data)


def close_job_workflow(db, job_id):
    # 已确认录用保留事实，关闭岗位不再接受待决意向。
    for kind in ('recruiting_offer', 'recruiting_invitation'):
        for row in db.execute('SELECT * FROM entities WHERE kind=?', (kind,)).fetchall():
            data = json.loads(row['data'])
            if data.get('job_id') == job_id and data['status'] in {'sent', 'reschedule_requested', 'confirmed', 'accepted'}:
                data['status'] = 'revoked' if kind == 'recruiting_offer' else 'cancelled'
                data.setdefault('history', []).append({'at': now(), 'action': 'job_closed'})
                write(db, dict(row), data)


def attach_recruiting_workflow(app, store, user, application_result):
    def access(db, application_id, current, employer_only=False, active=True):
        application = entity_row(db, application_id, 'application')
        job = entity_row(db, application['data']['job_id'], 'job')
        is_employer = current['role'] == 'employer' and job['owner'] == current['id']
        is_student = current['role'] == 'student' and application['owner'] == current['id']
        if not is_employer and (employer_only or not is_student):
            raise HTTPException(403, '只能操作自己的有效投递')
        if active and application['data'].get('withdrawn'):
            raise HTTPException(409, '投递已撤回')
        return application, job, is_employer

    def require_open(job):
        if not active_job(job['data']):
            raise HTTPException(409, '岗位当前未开放招聘')

    def history(data, current, action, note=''):
        data.setdefault('history', []).append({'at': now(), 'actor': current['id'], 'action': action, 'note': note})

    @app.get('/api/recruiting/workflow')
    def workflow(current=Depends(user)):
        if current['role'] not in {'student', 'employer'}:
            raise HTTPException(403, '当前身份不能访问招聘流程')
        result = {'invitations': [], 'offers': []}
        with store.connect() as db:
            for kind, key in [('recruiting_invitation', 'invitations'), ('recruiting_offer', 'offers')]:
                for row in db.execute('SELECT * FROM entities WHERE kind=? ORDER BY created DESC', (kind,)).fetchall():
                    data = json.loads(row['data'])
                    if current['id'] not in {data['student_id'], data['employer_id']}:
                        continue
                    application, job, _ = access(db, data['application_id'], current, active=False)
                    student = db.execute('SELECT name FROM users WHERE id=?', (data['student_id'],)).fetchone()
                    result[key].append({**data, 'id': row['id'], 'created': row['created'], 'revision': row['updated'], 'student_name': student['name'],
                                        'job_title': job['data']['title'], 'withdrawn': bool(application['data'].get('withdrawn'))})
        return result

    @app.get('/api/recruiting/jobs/{ident}/spec')
    def job_spec(ident: str, current=Depends(user)):
        with store.connect() as db:
            job = entity_row(db, ident, 'job')
            if current['role'] != 'employer' or job['owner'] != current['id']:
                raise HTTPException(403, '只能编辑本公司的岗位')
            return {**job['data'], 'id': ident, 'owner': job['owner'], 'occupied': occupancy(db, ident)}

    @app.post('/api/recruiting/applications/{ident}/invitations')
    def invite(ident: str, payload: Invitation, current=Depends(user)):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            application, job, _ = access(db, ident, current, employer_only=True)
            require_open(job)
            existing = [json.loads(r['data']) for r in db.execute("SELECT data FROM entities WHERE kind='recruiting_invitation'").fetchall()]
            if any(d['application_id'] == ident and d['status'] in {'sent', 'reschedule_requested', 'confirmed'} for d in existing):
                raise HTTPException(409, '该投递已有有效面试邀约，请先取消或改期')
            data = {**payload.model_dump(mode='json'), 'application_id': ident, 'job_id': job['id'],
                    'student_id': application['owner'], 'employer_id': current['id'], 'status': 'sent', 'waiting_for': application['owner']}
            history(data, current, 'sent')
            return insert(db, 'recruiting_invitation', current['id'], data)

    @app.post('/api/recruiting/invitations/{ident}/respond')
    def invitation_response(ident: str, payload: InvitationResponse, current=Depends(user)):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item = entity_row(db, ident, 'recruiting_invitation')
            data = item['data']
            application, job, is_employer = access(db, data['application_id'], current)
            if payload.revision != item['updated']:
                raise HTTPException(409, '邀约已被另一方更新，请刷新后重新操作')
            action = payload.action
            if data['status'] in {'cancelled', 'declined'}:
                raise HTTPException(409, '邀约已结束')
            if action != 'cancel':
                require_open(job)
            if action in {'accept', 'decline'} and (data.get('waiting_for') != current['id'] or data['status'] == 'confirmed'):
                raise HTTPException(409, '当前无需你确认该邀约')
            if action == 'accept':
                if datetime.fromisoformat(data['starts_at']) <= datetime.now(timezone.utc):
                    raise HTTPException(409, '面试时间已过，请申请改期')
                data['status'] = 'confirmed'
                data['waiting_for'] = None
                room = insert(db, 'interview', application['owner'], {'mode': 'human', 'application_id': application['id'],
                              'invitation_id': ident, 'questions': job['data'].get('questions', []), 'job_version': job['data']['version'],
                              'messages': [{'role': 'assistant', 'text': '面试邀约已确认，等待双方进入面试室。'}],
                              'signals': [], 'consent': True, 'completed': False})
                data['interview_id'] = room['id']
            elif action == 'decline':
                data['status'] = 'declined'
            elif action == 'reschedule':
                if payload.proposal is None:
                    raise HTTPException(422, '改期需提供新的时间、时区和时长')
                data.update(payload.proposal.model_dump(mode='json'))
                data.update(status='reschedule_requested', waiting_for=data['student_id'] if is_employer else data['employer_id'])
            else:
                data['status'] = 'cancelled'
            history(data, current, action, payload.note)
            return write(db, item, data)

    @app.post('/api/recruiting/applications/{ident}/offers')
    def send_offer(ident: str, payload: Offer, current=Depends(user)):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            application, job, _ = access(db, ident, current, employer_only=True)
            require_open(job)
            if application['data'].get('stage') == 'declined':
                raise HTTPException(409, '该投递已标记不合适')
            for row in db.execute("SELECT data FROM entities WHERE kind='recruiting_offer'").fetchall():
                d = json.loads(row['data'])
                if d['application_id'] == ident and d['status'] in {'sent', 'accepted', 'hired'}:
                    raise HTTPException(409, '该投递已有有效意向或录用记录')
            data = {'message': payload.message, 'application_id': ident, 'job_id': job['id'], 'student_id': application['owner'],
                    'employer_id': current['id'], 'status': 'sent', 'job_version': job['data']['version'],
                    'resource_commitment': resource_cost(job['data'])}
            history(data, current, 'sent')
            return insert(db, 'recruiting_offer', current['id'], data)

    @app.post('/api/recruiting/offers/{ident}/respond')
    def offer_response(ident: str, payload: OfferResponse, current=Depends(user)):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item = entity_row(db, ident, 'recruiting_offer')
            data = item['data']
            application, job, is_employer = access(db, data['application_id'], current)
            action = payload.action
            if (action in {'confirm', 'revoke'}) != is_employer:
                raise HTTPException(403, '该操作与当前身份不符')
            if payload.revision != item['updated']:
                raise HTTPException(409, '意向已更新，请刷新后重新操作')
            allowed = {'accept': {'sent'}, 'decline': {'sent', 'accepted'}, 'confirm': {'accepted'}, 'revoke': {'sent', 'accepted', 'hired'}}
            if data['status'] not in allowed[action]:
                raise HTTPException(409, '意向状态已变化，请刷新')
            if action in {'accept', 'confirm'}:
                require_open(job)
                if application['data'].get('stage') == 'declined':
                    raise HTTPException(409, '该投递已被企业标记为不合适')
                if data['job_version'] != job['data']['version']:
                    raise HTTPException(409, '岗位规则已变化，请企业撤销旧意向并重新发出')
            if action == 'accept':
                if occupancy(db, job['id'], ident) >= job['data']['capacity']:
                    raise HTTPException(409, '岗位名额已满，暂时无法接受意向')
                for row in db.execute("SELECT id,data FROM entities WHERE kind='recruiting_offer'").fetchall():
                    other = json.loads(row['data'])
                    if row['id'] != ident and other['student_id'] == current['id'] and other['status'] in {'accepted', 'hired'}:
                        raise HTTPException(409, '你已有已接受或已录用的意向，请先处理原意向')
            data['status'] = {'accept': 'accepted', 'decline': 'declined', 'confirm': 'hired', 'revoke': 'revoked'}[action]
            history(data, current, action, payload.note)
            return write(db, item, data)

    def source_snapshot(current, db=None):
        def read(kind, owner=None):
            if db is None:
                return store.list(kind, owner)
            rows = db.execute('SELECT * FROM entities WHERE kind=?' + (' AND owner=?' if owner else ''), (kind, owner) if owner else (kind,)).fetchall()
            return [{**dict(r), 'data': json.loads(r['data'])} for r in rows]
        jobs = read('job', current['id'])
        job_ids = {j['id'] for j in jobs}
        applications = [a for a in read('application') if a['data']['job_id'] in job_ids]
        students = {a['owner'] for a in applications if not a['data'].get('withdrawn')}
        profiles = [p for sid in students for p in read('profile', sid)]
        offers = [o for o in read('recruiting_offer') if o['owner'] == current['id'] or o['data']['student_id'] in students]
        source = sorted([{'id': r['id'], 'updated': r['updated'], 'data': r['data']} for r in jobs + applications + profiles + offers], key=lambda r: r['id'])
        digest = hashlib.sha256(encode(source).encode()).hexdigest()
        return digest, jobs, applications

    def employer(current):
        if current['role'] != 'employer':
            raise HTTPException(403, '仅企业可以管理招聘计划')

    @app.get('/api/recruiting/plans')
    def plans(current=Depends(user)):
        employer(current)
        digest, _, _ = source_snapshot(current)
        return [{**p['data'], 'id': p['id'], 'created': p['created'], 'stale': p['data']['source_digest'] != digest} for p in store.list('recruiting_plan', current['id'])]

    @app.post('/api/recruiting/plans')
    def save_plan(payload: Budget, current=Depends(user)):
        employer(current)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            digest, job_items, application_items = source_snapshot(current, db)
            commitments, committed = budget_commitments(db, current['id'])
            total_budget = payload.model_dump()
            difference = {key: Decimal(str(total_budget[key])) - Decimal(str(committed[key])) for key in total_budget}
            remaining = {key: float(max(Decimal(0), difference[key])) for key in total_budget}
            shortfall = {key: float(max(Decimal(0), -difference[key])) for key in total_budget}
            overcommitted = any(shortfall.values())
            committed_students = {d['student_id'] for row in db.execute("SELECT data FROM entities WHERE kind='recruiting_offer'").fetchall() if (d := json.loads(row['data']))['status'] in {'accepted', 'hired'}}
            jobs = {j['id']: {**j['data'], 'id': j['id'], 'capacity': max(0, j['data']['capacity'] - occupancy(db, j['id']))} for j in job_items if active_job(j['data'])}
            candidates, pairs = [], []
            for item in application_items:
                job = next(j for j in job_items if j['id'] == item['data']['job_id'])
                student = db.execute('SELECT name FROM users WHERE id=?', (item['owner'],)).fetchone()
                if item['data'].get('withdrawn'):
                    candidates.append({'application_id': item['id'], 'student_id': item['owner'], 'student_name': student['name'],
                                       'job_id': job['id'], 'job_title': job['data']['title'], 'job_version': job['data']['version'],
                                       'requirements': job['data']['requirements'], 'assessment': None, 'profile': {},
                                       'skill_gaps': [], 'status': 'excluded', 'reasons': ['投递已撤回'], 'selected': False})
                    continue
                result = application_result(item, job)
                reasons = []
                if overcommitted: reasons.append('既有承诺已超过企业总预算，请先调整预算或处理原意向')
                if item['owner'] in committed_students: reasons.append('该学生已有已接受或已录用的意向')
                if job['id'] not in jobs: reasons.append('岗位未开放')
                if item['data'].get('stage') == 'declined': reasons.append('企业标记不合适')
                if result['match']['status'] != 'eligible': reasons.append('必要条件或测评证据尚未全部核验' if result['match']['status'] == 'pending' else '必要条件不符合')
                mutual = item['data'].get('student_chosen') and item['data'].get('employer_chosen')
                if not mutual: reasons.append('双方尚未同时表达意向')
                details = result['match'].get('employer', {}).get('details', [])
                candidates.append({'application_id': item['id'], 'student_id': item['owner'], 'student_name': student['name'],
                                   'job_id': job['id'], 'job_title': job['data']['title'], 'job_version': job['data']['version'],
                                   'requirements': job['data']['requirements'], 'assessment': item['data'].get('review'),
                                   'profile': result['profile'], 'skill_gaps': [{'skill': d['skill'], 'gap': d['gap']} for d in details],
                                   'status': result['match']['status'], 'reasons': reasons})
                if not reasons:
                    pairs.append({'application_id': item['id'], 'job_id': job['id'], 'student_id': item['owner'], 'status': 'eligible',
                                  'lower': result['match']['lower'], 'mutual': True})
            result = allocate(pairs, jobs, remaining)
            for candidate in candidates:
                candidate['selected'] = candidate['application_id'] in result['selected']
                if not candidate['selected'] and not candidate['reasons']:
                    candidate['reasons'] = ['预算、岗位剩余名额或同一学生只能入选一个岗位的约束']
            versions = [json.loads(r['data'])['version'] for r in db.execute("SELECT data FROM entities WHERE kind='recruiting_plan' AND owner=?", (current['id'],)).fetchall()]
            data = {'version': max(versions, default=0) + 1, 'budget': total_budget, 'source_digest': digest,
                    'budget_scope': 'total', 'commitments': commitments, 'committed': committed,
                    'remaining_budget': remaining, 'budget_shortfall': shortfall,
                    'total_used': {key: float(Decimal(str(committed[key])) + Decimal(str(result['used'][key]))) for key in total_budget},
                    'status': 'overcommitted' if overcommitted else 'calculated',
                    'jobs': list(jobs.values()), 'candidates': candidates, 'result': result, 'stale': False}
            return insert(db, 'recruiting_plan', current['id'], data)

    @app.get('/api/recruiting/plans/compare')
    def compare_plans(left: str, right: str, current=Depends(user)):
        employer(current)
        with store.connect() as db:
            items = [entity_row(db, ident, 'recruiting_plan') for ident in (left, right)]
            if any(item['owner'] != current['id'] for item in items):
                raise HTTPException(403, '只能比较自己的招聘计划')
        before, after = [i['data'] for i in items]
        digest, _, _ = source_snapshot(current)
        before['stale'] = before['source_digest'] != digest
        after['stale'] = after['source_digest'] != digest
        return {'left': {**before, 'id': left}, 'right': {**after, 'id': right},
                'budget_changes': {k: {'before': before['budget'][k], 'after': after['budget'][k]} for k in before['budget'] if before['budget'][k] != after['budget'][k]},
                'added': [c for c in after['candidates'] if c['selected'] and c['application_id'] not in before['result']['selected']],
                'removed': [c for c in before['candidates'] if c['selected'] and c['application_id'] not in after['result']['selected']]}
