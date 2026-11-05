import hashlib
import time

from fastapi import Depends, HTTPException, Request
from pydantic import Field

from backend.schemas import Model


class Workspace(Model):
    user_id: str = Field(min_length=1, max_length=100)


def principal(store, request):
    token = hashlib.sha256(request.cookies.get('chanzhi_session', '').encode()).hexdigest()
    with store.connect() as db:
        row = db.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.token=? AND s.expires>?', (token, time.time())).fetchone()
    if row is None:
        raise HTTPException(401, '请先登录')
    return row, token


def attach_administration(app, store, user, public_user):
    def administrator(request: Request):
        row, token = principal(store, request)
        if row['role'] != 'admin':
            raise HTTPException(403, '需要管理员权限')
        return row, token

    @app.get('/api/admin/accounts')
    def accounts(current=Depends(administrator)):
        with store.connect() as db:
            rows = db.execute("SELECT * FROM users WHERE role IN ('student','university','employer') ORDER BY role,name").fetchall()
        return [public_user(row) for row in rows]

    @app.post('/api/admin/workspace')
    def enter(payload: Workspace, current=Depends(administrator)):
        actor, token = current
        with store.connect() as db:
            target = db.execute('SELECT * FROM users WHERE id=?', (payload.user_id,)).fetchone()
            if target is None or target['role'] not in {'student', 'university', 'employer'}:
                raise HTTPException(404, '工作空间不存在')
            db.execute('INSERT INTO admin_contexts VALUES(?,?) ON CONFLICT(token) DO UPDATE SET target_id=excluded.target_id', (token, target['id']))
        store.audit(actor['id'], 'enter_workspace', target['id'])
        return {**public_user(target), 'administrator': {'id': actor['id'], 'name': actor['name']}}

    @app.delete('/api/admin/workspace')
    def leave(current=Depends(administrator)):
        actor, token = current
        with store.connect() as db:
            db.execute('DELETE FROM admin_contexts WHERE token=?', (token,))
        store.audit(actor['id'], 'leave_workspace', actor['id'])
        return public_user(actor)

    @app.get('/api/university/profile')
    def university_profile(current=Depends(user)):
        if current['role'] != 'university':
            raise HTTPException(403, '需要高校身份')
        rows = store.list('university_profile', current['id'])
        if not rows:
            return None
        result = rows[0]['data']
        skills = {}
        for profile in store.list('profile'):
            if profile['data'].get('school_id') == current['id']:
                for name, observation in profile['data'].get('abilities', {}).items():
                    skills.setdefault(name, []).append(observation['level'])
        result['program']['skills'] = {name: {'level': round(sum(values)/len(values), 2), 'sample_count': len(values),
                                             'evidence': '课程及项目能力自述，统一考核尚未完成'} for name, values in skills.items() if len(values) >= 5}
        return result
