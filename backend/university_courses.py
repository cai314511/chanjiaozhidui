"""本校课程与教务导出资料；只处理用户明确提供的字段。"""
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException
from lxml.etree import XMLSyntaxError
from pypdf.errors import PdfReadError
from backend.documents import extract, MAX_SIZE
from backend.store import now
from backend.course_import import normalize_course, parse_schedule, MAX_COURSES
from pydantic import BaseModel, Field, ConfigDict


class CourseRevision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: str = Field(min_length=1, max_length=100)
    hours: float | None = Field(default=None, ge=0, le=10000)
    skills: list[str] | None = Field(default=None, max_length=100)
    source_note: str = Field(min_length=1, max_length=2000)
    confirmed: bool


class CourseRevisions(BaseModel):
    revisions: list[CourseRevision] = Field(min_length=1, max_length=1000)

def attach_university_courses(app,store,user):
    def school(current):
        if current['role']!='university':
            raise HTTPException(403,'仅高校账号可管理本校课程资料')

    @app.get('/api/university/courses')
    def courses(current=Depends(user)):
        school(current)
        rows=store.list('university_course_catalog',current['id'])
        return rows[0]['data'] if rows else {'courses':[],'sources':[]}

    @app.patch('/api/university/courses')
    def revise_courses(payload: CourseRevisions, current=Depends(user)):
        school(current)
        from backend.store import encode
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            ident = 'university-courses:' + current['id']
            row = db.execute('SELECT data,owner,kind FROM entities WHERE id=?', (ident,)).fetchone()
            if not row or row['owner'] != current['id'] or row['kind'] != 'university_course_catalog':
                raise HTTPException(422, '请先导入本校课程库')
            catalog = json.loads(row['data'])
            courses = {c['code']: c for c in catalog['courses']}
            if len({r.code for r in payload.revisions}) != len(payload.revisions):
                raise HTTPException(422, '同批课程代码重复')
            for revision in payload.revisions:
                if revision.code not in courses:
                    raise HTTPException(422, '课程不存在：' + revision.code)
                course = courses[revision.code]
                if not revision.confirmed:
                    raise HTTPException(422, '请确认修订字段及其来源后保存')
                for key in ('hours', 'skills'):
                    if key not in revision.model_fields_set:
                        continue
                    value = getattr(revision, key)
                    if key == 'skills':
                        value = list(dict.fromkeys(s.strip() for s in value or [] if s.strip()))
                        if any(len(s) > 100 for s in value):
                            raise HTTPException(422, '能力标签不能超过100字')
                    course[key] = value
                    course.setdefault('field_confirmations', {})[key] = True
                    course.setdefault('field_sources', {})[key] = {
                        'kind': 'teacher_review', 'note': revision.source_note, 'confirmed_at': now()}
            db.execute('UPDATE entities SET data=?,updated=? WHERE id=?', (encode(catalog), now(), ident))
            db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',
                       (current['id'], 'confirm_course_fields', ident, now()))
        return {'updated_courses': len(payload.revisions), 'message': '已保存课程修订及确认来源'}

    @app.get('/api/university/courses/export')
    def export_courses(current=Depends(user)):
        school(current)
        rows=store.list('university_course_catalog',current['id'])
        catalog=rows[0]['data'] if rows else {'courses':[]}
        book=Workbook();sheet=book.active;sheet.title='本校课程库'
        sheet.append(['课程代码','课程名称','学分','总学时','能力标签','开课学院','校区','学年','学期','教学班数','来源文件','课程性质'])
        for course in catalog['courses']:
            sheet.append([course['code'],course['name'],course['credits'],course['hours'],';'.join(course['skills']),
                          '；'.join(course.get('departments',[])),'；'.join(course.get('campuses',[])),
                          '；'.join(course.get('academic_years',[])),'；'.join(course.get('semesters',[])),
                          course.get('section_count'),course.get('source',{}).get('name',''),'；'.join(course.get('categories',[]))])
            # 用户提供的文本始终为字符串，避免导出为Excel公式。
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value,str):cell.data_type='s'
        for cell in sheet[1]:
            cell.fill=PatternFill('solid',fgColor='256F63');cell.font=Font(color='FFFFFF',bold=True)
        sheet.freeze_panes='C2';sheet.auto_filter.ref=sheet.dimensions
        for key,width in {'A':20,'B':36,'C':10,'D':12,'E':32,'F':28,'G':24,'H':20,'I':12,'J':12,'K':48,'L':24}.items():
            sheet.column_dimensions[key].width=width
        output=io.BytesIO();book.save(output);book.close()
        return Response(output.getvalue(),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition':'attachment; filename="university-courses.xlsx"'})

    @app.post('/api/university/materials/import')
    async def import_material(file:UploadFile=File(...),kind:str=Form('courses'),current=Depends(user)):
        school(current)
        if kind not in {'courses','program','teaching'}:
            raise HTTPException(422,'请选择课程、培养方案或教务导出')
        content=await file.read(MAX_SIZE+1)
        if not content or len(content)>MAX_SIZE:
            raise HTTPException(413,'单份资料需在12MB以内')
        name=Path(file.filename or '资料').name
        suffix=Path(name).suffix.lower()
        source={'name':name,'kind':kind,'sha256':hashlib.sha256(content).hexdigest(),'imported_at':now()}
        if suffix in {'.pdf','.docx','.txt','.md'}:
            try:
                data=extract(name,content)
            except (ValueError,UnicodeError,zipfile.BadZipFile,PdfReadError,KeyError,XMLSyntaxError) as exc:
                raise HTTPException(422,str(exc)) from None
            ident=hashlib.sha256((current['id']+kind+source['sha256']).encode()).hexdigest()[:24]
            store.save('document',current['id'],{**data,'university_material':kind},ident)
            folder=store.root/'files';folder.mkdir(exist_ok=True);(folder/ident).write_bytes(content)
            return {'document_id':ident,'imported_courses':0,'message':'已存入本校资料库。正文供核对，结构化课程请使用CSV、XLSX或JSON。'}
        recognition=None
        try:
            if suffix=='.csv':
                rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
                # 本校课程保留原有单字段边界，不依赖招聘导入放宽的进程级CSV设置。
                if any(len(str(value))>131072 for row in rows for value in (*row.keys(),*row.values())):
                    raise ValueError('课程CSV单字段过长，请检查导出内容')
            elif suffix=='.json':
                payload=json.loads(content)
                rows=payload if isinstance(payload,list) else payload.get('courses',payload.get('program',{}).get('courses',[]))
            elif suffix=='.xlsx':
                parsed,recognition=parse_schedule(content)
            else:
                raise ValueError('支持CSV、XLSX、JSON、PDF、DOCX、TXT')
            if suffix!='.xlsx':
                if not isinstance(rows,list) or not 1<=len(rows)<=MAX_COURSES:raise ValueError('每批需包含1至10000门课程')
                parsed=[normalize_course(row) for row in rows]
                if len({c['code'] for c in parsed})!=len(parsed):raise ValueError('同批课程代码重复，请先核对')
        except ValueError as exc:
            raise HTTPException(422,'课程文件无效：'+str(exc)) from None
        except (TypeError,KeyError,AttributeError,StopIteration,zipfile.BadZipFile,InvalidFileException,XMLSyntaxError,csv.Error):
            raise HTTPException(422,'课程文件无效：请核对课程名称、课程代码、学分、总学时、能力标签；CSV使用UTF-8。') from None
        # 同校目录合并在写事务中完成，避免并发导入丢失先前课程。
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT data FROM entities WHERE id=?",('university-courses:'+current['id'],)).fetchone()
            previous=json.loads(row['data']) if row else {'courses':[],'sources':[]}
            merged={c['code']:c for c in previous['courses']}
            for c in parsed:
                old=merged.get(c['code'],{})
                field_sources={**old.get('field_sources',{})}
                updated={**old,**c,'source':source}
                for key in ('credits','hours','skills'):
                    missing=c[key] is None or key=='skills' and not c[key]
                    if missing and old.get(key) is not None:
                        updated[key]=old[key]
                        field_sources.setdefault(key,old.get('source',source))
                    elif not missing:
                        field_sources[key]=source
                updated['field_sources']=field_sources
                merged[c['code']]=updated
            sources=previous['sources']
            if not any(s['sha256']==source['sha256'] for s in sources):sources=[*sources,source]
            from backend.store import encode
            stamp=now();ident='university-courses:'+current['id']
            db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',
                (ident,'university_course_catalog',current['id'],encode({'courses':list(merged.values()),'sources':sources}),stamp,stamp))
        return {'imported_courses':len(parsed),'total_courses':len(merged),'recognition':recognition,
                'message':f'已识别并导入本校数据库：{len(parsed)}门课程，课程库共{len(merged)}门。'}
