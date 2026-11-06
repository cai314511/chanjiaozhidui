"""由学生明确发布的主页快照；草稿和未选资源始终私有。"""

import json
import warnings
from io import BytesIO
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError
from pydantic import Field, StringConstraints, field_validator

from backend.schemas import Model
from backend.store import encode, now, uid


ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
ResourceId = Annotated[str, StringConstraints(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')]


class PageLink(Model):
    title: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)

    @field_validator('url')
    @classmethod
    def safe_url(cls, value):
        if any(character.isspace() or ord(character) < 32 for character in value):
            raise ValueError('网站链接不得包含空白或控制字符')
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme.lower() in {'http', 'https'} and parsed.hostname
                     and parsed.username is None and parsed.password is None
                     and '\\' not in value)
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ValueError('请输入完整的 HTTP 或 HTTPS 网站链接，不含账号密码')
        return value


class StudentPage(Model):
    display_name: str = Field(default='', max_length=80)
    headline: str = Field(default='', max_length=160)
    bio: str = Field(default='', max_length=5000)
    school: str = Field(default='', max_length=160)
    major: str = Field(default='', max_length=160)
    education: str = Field(default='', max_length=500)
    background: str = Field(default='', max_length=5000)
    interests: list[ShortText] = Field(default_factory=list, max_length=30)
    strengths: list[ShortText] = Field(default_factory=list, max_length=30)
    links: list[PageLink] = Field(default_factory=list, max_length=20)
    document_ids: list[ResourceId] = Field(default_factory=list, max_length=20)
    portfolio_ids: list[ResourceId] = Field(default_factory=list, max_length=20)

    @field_validator('document_ids', 'portfolio_ids')
    @classmethod
    def unique_ids(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('请勿重复选择同一资源')
        return values


def _page_id(owner):
    return 'student_page:' + owner


def published_resource(store, owner, ident, kind):
    """旧资料入口也复核当前发布快照，撤回后不再获得主页授权。"""
    if kind not in {'document', 'portfolio'}:
        return False
    page = store.get(_page_id(owner), 'student_page')
    published = page['data'].get('published') if page else None
    if not published or ident not in published.get(kind + '_ids', []):
        return False
    resource = store.get(ident, kind)
    return bool(resource and resource['owner'] == owner)


def attach_student_space(app, store, user):
    def student(current):
        if current['role'] != 'student':
            raise HTTPException(403, '仅学生可以管理自己的主页')

    def page_data(owner):
        page = store.get(_page_id(owner), 'student_page')
        return page['data'] if page else {'draft': StudentPage().model_dump(), 'published': None}

    def update_page(owner, change):
        # 单条记录保存草稿与发布快照，防止并发保存覆盖撤回或头像变更。
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data FROM entities WHERE id=? AND kind=?',
                             (_page_id(owner), 'student_page')).fetchone()
            data = json.loads(row['data']) if row else {
                'draft': StudentPage().model_dump(), 'published': None,
            }
            updated = change(data)
            stamp = now()
            db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?) ON CONFLICT(id) '
                       'DO UPDATE SET data=excluded.data,updated=excluded.updated',
                       (_page_id(owner), 'student_page', owner, encode(updated), stamp, stamp))
        return updated

    def resources(fields, owner):
        result = {}
        for kind in ('document', 'portfolio'):
            rows = []
            for ident in fields.get(kind + '_ids', []):
                item = store.get(ident, kind)
                if item is None:
                    raise HTTPException(422, '选中的资料或作品不存在，请重新选择')
                if item['owner'] != owner:
                    raise HTTPException(403, '只能发布自己上传的资料或作品')
                rows.append({'id': ident, 'name': item['data'].get('name', '未命名'),
                             'url': f'/api/documents/{ident}' if kind == 'document'
                             else f'/api/portfolio/{ident}/file',
                             **({'mime': item['data'].get('mime', 'application/octet-stream')}
                                if kind == 'portfolio' else {})})
            result['documents' if kind == 'document' else 'portfolio'] = rows
        return result

    def avatar_url(owner, avatar_id):
        return f'/api/students/{owner}/avatar?version={avatar_id}' if avatar_id else None

    def result(owner, data):
        draft = data['draft']
        return {'draft': {**StudentPage.model_validate({key: value for key, value in draft.items()
                         if key in StudentPage.model_fields}).model_dump(),
                         'avatar_url': avatar_url(owner, draft.get('avatar_id'))},
                'published': public_snapshot(owner, data['published']) if data.get('published') else None}

    def public_snapshot(owner, snapshot):
        fields = StudentPage.model_validate({key: value for key, value in snapshot.items()
                                            if key in StudentPage.model_fields}).model_dump()
        return {**fields, 'id': owner, 'published_at': snapshot['published_at'],
                'avatar_url': avatar_url(owner, snapshot.get('avatar_id')),
                **resources(fields, owner)}

    @app.get('/api/me/page')
    def my_page(current=Depends(user)):
        student(current)
        return result(current['id'], page_data(current['id']))

    @app.put('/api/me/page')
    def save_page(payload: StudentPage, current=Depends(user)):
        student(current)
        fields = payload.model_dump()
        resources(fields, current['id'])

        def save(data):
            return {**data, 'draft': {**fields, 'avatar_id': data['draft'].get('avatar_id')}}

        return result(current['id'], update_page(current['id'], save))

    @app.post('/api/me/page/publish')
    def publish_page(current=Depends(user)):
        student(current)

        def publish(data):
            draft = data['draft']
            if not draft.get('display_name', '').strip():
                raise HTTPException(422, '请填写希望在主页展示的姓名')
            resources(draft, current['id'])
            return {**data, 'published': {**draft, 'published_at': now()}}

        published = update_page(current['id'], publish)
        store.audit(current['id'], 'publish_student_page', current['id'])
        return result(current['id'], published)

    @app.delete('/api/me/page/publish')
    def withdraw_page(current=Depends(user)):
        student(current)
        data = update_page(current['id'], lambda value: {**value, 'published': None})
        store.audit(current['id'], 'withdraw_student_page', current['id'])
        return result(current['id'], data)

    @app.get('/api/students')
    def students(current=Depends(user)):
        return [public_snapshot(item['owner'], item['data']['published'])
                for item in store.list('student_page') if item['data'].get('published')]

    @app.get('/api/students/{student_id}')
    def student_page(student_id: str, current=Depends(user)):
        published = page_data(student_id).get('published')
        if not published:
            raise HTTPException(404, '学生尚未发布主页')
        return public_snapshot(student_id, published)

    @app.post('/api/me/avatar')
    async def upload_avatar(file: UploadFile = File(...), current=Depends(user)):
        student(current)
        content = await file.read(3 * 1024 * 1024 + 1)
        suffix = Path(file.filename or '').suffix.lower()
        if not content or len(content) > 3 * 1024 * 1024 or suffix not in {'.png', '.jpg', '.jpeg', '.webp'}:
            raise HTTPException(422, '头像支持 PNG、JPG、WEBP，最大3MB')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(content)) as source:
                    if source.format not in {'PNG', 'JPEG', 'WEBP'} or source.width * source.height > 16_000_000:
                        raise ValueError('图片尺寸或格式不支持')
                    source.load()
                    image = source.convert('RGBA')
                    image.thumbnail((1024, 1024))
                    # 创建新图去除源图的EXIF、文本等元数据。
                    clean = Image.new('RGBA', image.size)
                    clean.paste(image)
                    output = BytesIO()
                    clean.save(output, format='PNG')
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
                Image.DecompressionBombWarning):
            raise HTTPException(422, '头像文件损坏、格式不支持或图片尺寸过大') from None
        ident = uid()
        folder = store.root / 'avatars'
        folder.mkdir(exist_ok=True)
        (folder / (ident + '.png')).write_bytes(output.getvalue())
        store.save('student_avatar', current['id'], {'format': 'png'}, ident)

        def save_avatar(data):
            return {**data, 'draft': {**data['draft'], 'avatar_id': ident}}

        update_page(current['id'], save_avatar)
        return {'avatar_url': avatar_url(current['id'], ident)}

    @app.get('/api/students/{student_id}/avatar')
    def avatar(student_id: str, version: str | None = None, current=Depends(user)):
        data = page_data(student_id)
        snapshot = data['draft'] if current['id'] == student_id else data.get('published')
        ident = version or (snapshot or {}).get('avatar_id')
        # 所有者可以核对仍在发布的旧头像；他人只访问当前发布的版本。
        allowed = {snapshot.get('avatar_id')} if snapshot else set()
        if current['id'] == student_id and data.get('published'):
            allowed.add(data['published'].get('avatar_id'))
        if not ident or ident not in allowed:
            raise HTTPException(404, '头像尚未公开或不存在')
        item = store.get(ident, 'student_avatar')
        if item is None or item['owner'] != student_id:
            raise HTTPException(404, '头像不存在')
        path = store.root / 'avatars' / (ident + '.png')
        if not path.is_file():
            raise HTTPException(404, '头像不存在')
        return FileResponse(path, media_type='image/png', headers={'Cache-Control': 'no-store'})
