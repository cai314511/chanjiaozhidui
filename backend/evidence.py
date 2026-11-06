"""本机比赛资料的可复算处理与只读研究接口。"""

import csv
import hashlib
import math
import re
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import median

from fastapi import Depends, HTTPException, Query

from backend.governance import redact
from backend.store import encode, now


BUNDLE_ID = 'competition-evidence-v1'
SHARED_OWNER = 'competition-reference'
SKILLS = {
    'Python': r'(?<![a-z0-9])python(?![a-z0-9])', 'SQL': r'(?<![a-z0-9])(?:sql|mysql|postgresql)(?![a-z0-9])',
    'Java': r'(?<![a-z0-9])java(?![a-z0-9])', 'C++': r'c\+\+', '机器学习': r'机器学习|machine learning',
    '深度学习': r'深度学习|deep learning', '大模型': r'大模型|\bLLM\b|生成式',
    '自然语言处理': r'自然语言|\bNLP\b', '数据分析': r'数据分析|数据挖掘',
    '产品设计': r'产品设计|产品原型|原型设计|需求分析', '风控': r'风控|风险模型|风险建模',
    '量化研究': r'量化|交易策略', '云计算': r'云计算|云原生|kubernetes',
    '沟通协作': r'沟通|协作|团队合作', '算法': r'算法',
}
PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in SKILLS.items()}
EVIDENCE_TERMS = re.compile(r'人工智能|金融科技|数字金融|数字经济|产教|人才培养|本科毕业生|月收入|就业率|机器学习|大模型|课程|专业调整')


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_text(text, company=''):
    text = str(text or '').replace('\x00', '')
    if company:
        text = text.replace(company, '[企业已泛化]')
    text = re.sub(r'(?:联系人|联系老师|姓名|联系地址|详细地址|联系邮箱|邮箱|电话|手机|微信|QQ)\s*[：:]\s*[^；;\n。]{1,120}', '[联系信息已移除]', text)
    return redact(text).strip()


def salary_interval(low, high):
    try:
        low, high = float(low), float(high)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and 0 < v <= 1_000_000 for v in (low, high)) or low > high:
        return None
    return [round(low, 2), round(high, 2)]


def classify(title, industry):
    if re.search(r'人工智能|机器学习|深度学习|算法|大模型|自然语言|计算机视觉|机器人|(?<![a-z])AI(?:GC)?(?![a-z])|AI产品|AI工程|AI应用|智能产品', title, re.I):
        return 'AI产品'
    if re.search(r'金融科技|量化|数字金融|金融产品|风控模型|风险模型|支付产品|信贷模型', title):
        return '金融科技'
    if re.search(r'金融|银行|保险|证券|资本市场|货币', industry) and re.search(r'数据|科技|开发|软件|系统|产品|风控|信息技术|测试', title):
        return '金融科技'
    return None


def build_recruitment(paths):
    jobs, sources = {}, []
    scanned = matched = duplicates = invalid_dates = 0
    for path in paths:
        path = Path(path)
        source_id = hashlib.sha256(path.name.encode()).hexdigest()[:20]
        source = {'id': source_id, 'name': path.name, 'sha256': sha256_file(path),
                  'scanned_rows': 0, 'matched_rows': 0, 'period': '2026年，文件内实际月份见统计'}
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            required = {'招聘岗位', '工作城市', '最低月薪', '最高月薪', '职位描述', '招聘发布日期'}
            if not required <= set(reader.fieldnames or []):
                raise ValueError(f'{path.name}缺少必要字段：{sorted(required - set(reader.fieldnames or []))}')
            previous_line = 1
            for row in reader:
                line = previous_line + 1
                previous_line = reader.line_num
                scanned += 1
                source['scanned_rows'] += 1
                industry = classify(row['招聘岗位'], row.get('上市公司行业', ''))
                if not industry:
                    continue
                try:
                    published = date.fromisoformat(row['招聘发布日期'].strip()[:10])
                    month = published.strftime('%Y-%m')
                except ValueError:
                    invalid_dates += 1
                    continue
                matched += 1
                source['matched_rows'] += 1
                company = row.get('企业名称', '')
                description = safe_text(row['职位描述'], company)
                job = {'title': safe_text(row['招聘岗位'], company), 'city': safe_text(row['工作城市']),
                       'industry': industry, 'month': month,
                       'salary': salary_interval(row['最低月薪'], row['最高月薪']),
                       'education': safe_text(row.get('学历要求')), 'experience': safe_text(row.get('要求经验')),
                       'description': description, 'skills': [name for name, pattern in PATTERNS.items() if pattern.search(description)],
                       'headcount': None}
                # 企业与完整日期只参与内部摘要，避免把独立公告误合并；不写入共享正文。
                fingerprint = hashlib.sha256(encode([company, published.isoformat(), job]).encode()).hexdigest()
                provenance = {'source_id': source_id, 'file': path.name, 'line': line}
                if fingerprint in jobs:
                    duplicates += 1
                    jobs[fingerprint]['provenance'].append(provenance)
                else:
                    jobs[fingerprint] = {'id': fingerprint[:24], **job, 'provenance': [provenance]}
        sources.append(source)
    return {'jobs': sorted(jobs.values(), key=lambda j: (j['month'], j['id']), reverse=True),
            'sources': sources, 'scanned_rows': scanned, 'matched_rows': matched,
            'duplicate_rows': duplicates, 'invalid_dates': invalid_dates,
            'method': '岗位标题关键词及金融行业×技术岗位规则筛选；技能为正文关键词命中，不代表等级。同企业、同原始发布日期且脱敏岗位内容相同才合并；企业和日级日期仅参与内部摘要，页面按月份展示并保留全部出处。',
            'scope': '两份2026年招聘CSV的相关岗位；公告条数不等于招聘人数。不同数据包有覆盖重叠，未推算市场总需求。'}


def recruitment_stats(jobs):
    salaries = [(j['salary'][0] + j['salary'][1]) / 2 for j in jobs if j['salary']]
    counts = lambda key: [{'name': name, 'count': count} for name, count in Counter(j[key] or '未注明' for j in jobs).most_common()]
    return {'total': len(jobs), 'salary_sample': len(salaries),
            'salary_midpoint_median': round(median(salaries), 2) if salaries else None,
            'cities': counts('city'), 'industries': counts('industry'), 'months': sorted(counts('month'), key=lambda v: v['name']),
            'skills': [{'name': name, 'count': count} for name, count in Counter(s for j in jobs for s in j['skills']).most_common()],
            'salary_basis': '人民币元/月；双边有效报价区间中点的中位数，未按薪资月数折算年包；不等于毕业生实际收入。'}


def extract_reference(path, data_root):
    import fitz
    from docx import Document

    path, data_root = Path(path), Path(data_root)
    relative = path.relative_to(data_root).as_posix()
    blocks = []
    total = 0
    if path.suffix.lower() == '.docx':
        document = Document(path)
        candidates = [(f'段落{i + 1}', p.text) for i, p in enumerate(document.paragraphs)]
        candidates += [(f'表格{t + 1}第{i + 1}行', ' | '.join(c.text for c in row.cells))
                       for t, table in enumerate(document.tables) for i, row in enumerate(table.rows)]
    elif path.suffix.lower() == '.pdf':
        with fitz.open(path) as document:
            total = len(document)
            candidates = [(f'PDF第{i + 1}页', page.get_text()) for i, page in enumerate(document)]
    else:
        raise ValueError('研究证据仅处理PDF与DOCX')
    characters = sum(len(text.strip()) for _, text in candidates)
    for location, text in candidates:
        text = safe_text(text)
        match = EVIDENCE_TERMS.search(text)
        if match:
            start = max(0, match.start() - 150)
            excerpt = text[start:start + 1800]
            blocks.append({'location': location, 'text': excerpt, 'excerpt': len(excerpt) < len(text)})
    if '本科生就业报告' in relative:
        kind, status = '就业报告', '已提取' if blocks else '正文编码或扫描问题，待OCR'
    elif path.suffix.lower() == '.docx' and '报考专业分析' in relative:
        kind, status = '产业指南', '已提取；汇编观点供研究核对'
    else:
        kind, status = '政策文件', '已提取' if blocks else '无可检索正文，待OCR'
    if total and blocks:
        readable_pages = sum(len(re.findall(r'[\u4e00-\u9fff]', text)) > 30 for _, text in candidates)
        if readable_pages < total * .5:
            status = '部分文字已提取，其余页面待OCR'
    return {'id': hashlib.sha256(relative.encode()).hexdigest()[:24], 'title': path.stem,
            'kind': kind, 'path': relative, 'sha256': sha256_file(path), 'pages': total or None,
            'characters': characters, 'blocks': blocks, 'status': status,
            'basis': '用户提供的比赛资料；保留文内表述和原始统计口径。出版年与毕业届别分别阅读；未填补缺失的样本人数或能力等级。'}


def publish_bundle(store, bundle):
    # 单事务替换本导入器的固定记录，个人资料和业务记录不变。
    data = {**bundle, 'summary': recruitment_stats(bundle['recruitment']['jobs'])}
    stamp = now()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',
                   (BUNDLE_ID, 'competition_evidence', SHARED_OWNER, encode(data), stamp, stamp))
        db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',
                   (SHARED_OWNER, 'publish_local_competition_evidence', BUNDLE_ID, stamp))


def attach_evidence(app, store, user):
    def bundle():
        item = store.get(BUNDLE_ID, 'competition_evidence')
        if not item or item['owner'] != SHARED_OWNER:
            return None
        return item['data']

    @app.get('/api/evidence/summary')
    def summary(current=Depends(user)):
        data = bundle()
        if not data:
            return {'ready': False}
        return {'ready': True, 'created_at': data['created_at'], 'scope': data['scope'],
                'statistics': data['summary'],
                'processing': {k: v for k, v in data['recruitment'].items() if k != 'jobs'},
                'document_count': len(data['documents']),
                'document_kinds': dict(Counter(d['kind'] for d in data['documents'])),
                'inventory': data['inventory']}

    @app.get('/api/evidence/jobs')
    def jobs(q: str = Query('', max_length=100), city: str = Query('', max_length=100),
             industry: str = Query('', max_length=20), page: int = Query(1, ge=1), current=Depends(user)):
        data = bundle()
        rows = data['recruitment']['jobs'] if data else []
        rows = [j for j in rows if (not city or (j['city'] or '未注明') == city) and (not industry or j['industry'] == industry)
                and (not q or q.casefold() in (j['title'] + j['description']).casefold())]
        start = (page - 1) * 20
        return {'total': len(rows), 'page': page, 'page_size': 20, 'items': rows[start:start + 20]}

    @app.get('/api/evidence/documents')
    def documents(q: str = Query('', max_length=100), kind: str = Query('', max_length=30), current=Depends(user)):
        data = bundle()
        rows = data['documents'] if data else []
        found = []
        for row in rows:
            if kind and row['kind'] != kind:
                continue
            matches = [b for b in row['blocks'] if not q or q.casefold() in b['text'].casefold()]
            if q and q.casefold() not in row['title'].casefold() and not matches:
                continue
            found.append({k: v for k, v in row.items() if k != 'blocks'} | {'matches': matches[:2], 'block_count': len(row['blocks'])})
        return found

    @app.get('/api/evidence/documents/{ident}')
    def document(ident: str, current=Depends(user)):
        data = bundle()
        result = next((d for d in data['documents'] if d['id'] == ident), None) if data else None
        if result is None:
            raise HTTPException(404, '未找到已接入的研究证据')
        return result
