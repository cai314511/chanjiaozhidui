"""按随机体验凭证路由到独立FastAPI实例，正式认证Cookie始终不变。"""
import hashlib
import json
import re
import secrets
import shutil
import threading
import time
from collections import OrderedDict
from http.cookies import SimpleCookie

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Literal
from starlette.responses import JSONResponse

from backend.demo_seed import seed_workspace
from backend.store import Store


class Role(BaseModel):
    role: Literal['student', 'employer', 'university']


class DemoRouter:
    def __init__(self, app, root, factory):
        self.app, self.root, self.factory = app, root, factory
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.apps = OrderedDict()
        self.creation_attempts = {}
        self.reset_attempts = {}
        self.controls = FastAPI()

        def read(request):
            key = request.cookies.get('chanzhi_demo_workspace', '')
            if not re.fullmatch('[a-f0-9]{64}', key):
                return None
            path = self.root / key / 'workspace.json'
            if not path.is_file():
                return None
            data = json.loads(path.read_text(encoding='utf-8'))
            if data['expires'] < time.time():
                return None
            return key, data

        self.read = read

        def persist(key, data):
            path = self.root / key / 'workspace.json'
            temp = path.with_suffix('.pending')
            temp.write_text(json.dumps(data), encoding='utf-8')
            temp.replace(path)

        def evict(key):
            self.apps.pop(key,None)
            old_path=str((self.root/key/'chanzhi.sqlite3').resolve())
            from backend import market,university_intelligence
            market._CACHE.pop(old_path,None)
            market._VIEW_CACHE.pop(old_path,None)
            university_intelligence._CACHE.pop(old_path,None)

        def cleanup():
            from scripts.cleanup_demo import expired_spaces
            resolved=self.root.resolve()
            for folder in expired_spaces(resolved):
                if folder.parent!=resolved or not re.fullmatch('[a-f0-9]{64}',folder.name):
                    raise ValueError('过期体验空间路径不在允许范围')
                evict(folder.name)
                try:
                    shutil.rmtree(folder)
                except PermissionError:
                    # Windows下在途请求可能短暂占用文件，下次创建时重试回收。
                    continue

        def creation_limit(request, resetting=None):
            instant=time.monotonic()
            host=request.client.host if request.client else 'unknown'
            key=hashlib.sha256(host.encode()).hexdigest()
            attempts=[t for t in self.creation_attempts.get(key,[]) if instant-t<3600]
            if len(attempts)>=10 or sum(instant-t<60 for t in attempts)>=2:
                raise HTTPException(429,'体验空间创建过于频繁，请稍后继续')
            resets=[t for t in self.reset_attempts.get(resetting,[]) if instant-t<3600] if resetting else []
            if resetting and len(resets)>=3:
                raise HTTPException(429,'当前浏览器重置过于频繁，请稍后继续')
            self.creation_attempts[key]=attempts+[instant]
            return resets

        def create(replacing=None):
            cleanup()
            occupied=len(list(self.root.glob('*/workspace.json')))-(1 if replacing else 0)
            if occupied >= 100:
                raise HTTPException(429, '体验空间暂满，请联系管理员清理已过期空间')
            key = secrets.token_hex(32)
            store = Store(self.root / key)
            main = seed_workspace(store)
            data = {'role': 'student', 'main': main, 'expires': time.time()+7*86400, 'tokens': {}, 'agent_calls': []}
            with store.connect() as db:
                for role, ident in main.items():
                    token = secrets.token_urlsafe(40)
                    data['tokens'][role] = token
                    db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), ident, data['expires']))
            persist(key, data)
            return key, data

        def mark(response, key, active):
            response.set_cookie('chanzhi_demo_workspace', key, httponly=True, samesite='strict', max_age=7*86400)
            response.set_cookie('chanzhi_demo_active', '1' if active else '0', httponly=True, samesite='strict', max_age=7*86400)

        @self.controls.get('/api/demo/status')
        def status(request: Request):
            item = read(request)
            return {'active': bool(item and request.cookies.get('chanzhi_demo_active') == '1'),
                    'role': item[1]['role'] if item else None,
                    'expired': bool(not item and request.cookies.get('chanzhi_demo_active')=='1')}

        @self.controls.post('/api/demo/enter')
        def enter(request: Request, response: Response):
            with self.lock:
                item=read(request)
                if not item:
                    creation_limit(request)
                    item=create()
                key, data = item
                mark(response, key, True)
            return {'active': True, 'role': data['role']}

        @self.controls.post('/api/demo/switch')
        def switch(payload: Role, request: Request):
            with self.lock:
                item = read(request)
                if not item or request.cookies.get('chanzhi_demo_active') != '1':
                    raise HTTPException(401, '请先进入演示空间')
                key, data = item
                data['role'] = payload.role
                persist(key, data)
            return {'active': True, 'role': payload.role}

        @self.controls.post('/api/demo/exit')
        def leave(request: Request, response: Response):
            item = read(request)
            if item:
                mark(response, item[0], False)
            else:
                response.set_cookie('chanzhi_demo_active','0',httponly=True,samesite='strict',max_age=7*86400)
                response.delete_cookie('chanzhi_demo_workspace')
            return {'active': False}

        @self.controls.post('/api/demo/reset')
        def reset(request: Request, response: Response):
            with self.lock:
                item=read(request)
                if not item or request.cookies.get('chanzhi_demo_active') != '1':
                    raise HTTPException(401, '请先进入演示空间')
                old_key,old_data=item
                resets=creation_limit(request,old_key)
                key, data = create(replacing=old_key)
                old_data['expires']=0
                persist(old_key,old_data)
                self.reset_attempts[key]=resets+[time.monotonic()]
                self.reset_attempts.pop(old_key,None)
                cleanup()
                mark(response, key, True)
            return {'active': True, 'role': data['role']}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path']
        request = Request(scope)
        origin = request.headers.get('origin')
        if path.startswith('/api/demo/'):
            from urllib.parse import urlsplit
            if origin and scope['method'] not in {'GET', 'HEAD'} and urlsplit(origin).netloc != request.headers.get('host'):
                return await JSONResponse({'detail':'请求来源不匹配'},403)(scope,receive,send)
            async def control_send(message):
                if message['type']=='http.response.start':
                    message['headers'] += [(b'cache-control',b'no-store'),(b'x-content-type-options',b'nosniff')]
                await send(message)
            return await self.controls(scope, receive, control_send)
        if not path.startswith('/api/') or request.cookies.get('chanzhi_demo_active') != '1':
            return await self.app(scope, receive, send)
        with self.lock:
            item = self.read(request)
            if not item:
                return await JSONResponse({'detail':'体验空间已过期，请退出后重新进入'},401)(scope,receive,send)
            key, data = item
            if path.startswith('/api/admin/') or path.startswith('/api/auth/') and path != '/api/auth/me':
                return await JSONResponse({'detail':'当前空间不提供正式账号管理'},403)(scope,receive,send)
            uses_agent=path=='/api/agent/run' or path.startswith('/api/interviews/') and path.endswith('/turn')
            if uses_agent and scope['method']=='POST':
                calls = [t for t in data['agent_calls'] if time.time()-t<3600]
                if len(calls)>=20:
                    return await JSONResponse({'detail':'当前体验空间的助手调用次数已达上限，请稍后继续'},429)(scope,receive,send)
                data['agent_calls'] = calls+[time.time()]
                meta=self.root/key/'workspace.json'
                pending=meta.with_suffix('.pending')
                pending.write_text(json.dumps(data),encoding='utf-8')
                pending.replace(meta)
            if key not in self.apps:
                self.apps[key] = self.factory(self.root/key, enable_demo=False)
                if len(self.apps)>3:
                    old_key,_=self.apps.popitem(last=False)
                    old_path=str((self.root/old_key/'chanzhi.sqlite3').resolve())
                    from backend import market,university_intelligence
                    market._CACHE.pop(old_path,None)
                    market._VIEW_CACHE.pop(old_path,None)
                    university_intelligence._CACHE.pop(old_path,None)
            self.apps.move_to_end(key)
            child = self.apps[key]
        # 仅向子应用注入该空间的内部会话，真实登录Cookie不会进入演示数据库。
        cookie = SimpleCookie()
        cookie['chanzhi_session'] = data['tokens'][data['role']]
        headers = [(k,v) for k,v in scope['headers'] if k.lower()!=b'cookie']
        headers.append((b'cookie',cookie.output(header='').strip().encode()))
        await child({**scope,'headers':headers},receive,send)
