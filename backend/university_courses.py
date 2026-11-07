"""本校课程与教务导出资料；只处理用户明确提供的字段。"""
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, UploadFile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from lxml.etree import XMLSyntaxError
from pypdf.errors import PdfReadError
from backend.documents import extract, MAX_SIZE
from backend.store import now

ALIASES={'code':['code','课程代码','课程编码'],'name':['name','课程名称'],'credits':['credits','学分'],
         'hours':['hours','总学时','学时'],'skills':['skills','能力标签','对应技能']}


def normalize_course(row):
    result={key:next((row[a] for a in aliases if a in row and row[a] is not None),'') for key,aliases in ALIASES.items()}
    if not str(result['name']).strip():
        raise ValueError('每行需填写课程名称')
    result['name']=str(result['name']).strip()[:200]
    result['code']=str(result['code']).strip() or hashlib.sha256(result['name'].encode()).hexdigest()[:16]
    for key in ['credits','hours']:
        if result[key]=='':
            result[key]=None
        else:
            result[key]=float(result[key])
            if not math.isfinite(result[key]) or not 0<=result[key]<=10000:
                raise ValueError('学分和学时须为0至10000的有效数值，缺失请留空')
    skills=result['skills']
    if isinstance(skills,str):
        skills=json.loads(skills) if skills.strip().startswith('[') else re.split('[,，;；、\n]',skills)
    if not isinstance(skills,list) or any(not isinstance(s,str) for s in skills):
        raise ValueError('能力标签应为文字列表')
    result['skills']=list(dict.fromkeys(s.strip()[:100] for s in skills if s.strip()))
    return result


def attach_university_courses(app,store,user):
    def school(current):
        if current['role']!='university':
            raise HTTPException(403,'仅高校账号可管理本校课程资料')

    @app.get('/api/university/courses')
    def courses(current=Depends(user)):
        school(current)
        rows=store.list('university_course_catalog',current['id'])
        return rows[0]['data'] if rows else {'courses':[],'sources':[]}

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
        try:
            if suffix=='.csv':
                rows=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
            elif suffix=='.json':
                payload=json.loads(content)
                rows=payload if isinstance(payload,list) else payload.get('courses',payload.get('program',{}).get('courses',[]))
            elif suffix=='.xlsx':
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    if sum(i.file_size for i in archive.infolist())>60*1024*1024:
                        raise ValueError('教务表解压体积过大，请分批导入')
                book=load_workbook(io.BytesIO(content),read_only=True,data_only=True)
                try:
                    iterator=book.active.iter_rows(values_only=True);headers=[str(v or '').strip() for v in next(iterator)]
                    rows=[]
                    for values in iterator:
                        if len(rows)>=2000:raise ValueError('每批最多2000门课程')
                        if any(v is not None for v in values):rows.append(dict(zip(headers,values)))
                finally:book.close()
            else:
                raise ValueError('支持CSV、XLSX、JSON、PDF、DOCX、TXT')
            if not isinstance(rows,list) or not 1<=len(rows)<=2000:raise ValueError('每批需包含1至2000门课程')
            parsed=[normalize_course(row) for row in rows]
            if len({c['code'] for c in parsed})!=len(parsed):raise ValueError('同批课程代码重复，请先核对')
        except (ValueError,TypeError,KeyError,AttributeError,StopIteration,zipfile.BadZipFile,InvalidFileException,XMLSyntaxError,csv.Error):
            raise HTTPException(422,'课程文件无效：请核对课程名称、课程代码、学分、总学时、能力标签；CSV使用UTF-8。') from None
        # 同校目录合并在写事务中完成，避免并发导入丢失先前课程。
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT data FROM entities WHERE id=?",('university-courses:'+current['id'],)).fetchone()
            previous=json.loads(row['data']) if row else {'courses':[],'sources':[]}
            merged={c['code']:c for c in previous['courses']}
            for c in parsed:merged[c['code']]={**c,'source':source}
            sources=previous['sources']
            if not any(s['sha256']==source['sha256'] for s in sources):sources=[*sources,source]
            from backend.store import encode
            stamp=now();ident='university-courses:'+current['id']
            db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',
                (ident,'university_course_catalog',current['id'],encode({'courses':list(merged.values()),'sources':sources}),stamp,stamp))
        return {'imported_courses':len(parsed),'total_courses':len(merged),'message':'本校课程已校验并导入，可用于课程覆盖分析及候选方案填写。'}
