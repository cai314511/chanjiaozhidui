"""全行业本地招聘目录、企业档案与学生收藏；历史公告不进入发布动态。"""

import csv
import hashlib
import json
import re
import threading
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.evidence import safe_text, salary_interval, sha256_file
from backend.store import encode, now


CATALOG_ID = 'market-catalog-v1'
CATALOG_OWNER = 'local-market-import'
_CACHE = {}
_VIEW_CACHE = {}
_CACHE_LOCK = threading.RLock()

# 宽泛归类只引用原始行业字段；没有字段或同名企业证据时保留“未分类”。
TRACK_RULES = [
    ('金融服务', r'金融|资本市场|保险|货币'),
    ('软件与信息服务', r'软件|信息技术|互联网|电信|广播电视和卫星'),
    ('电子与半导体', r'计算机|通信和其他电子|仪器仪表'),
    ('生物医药', r'医药|卫生'),
    ('汽车与交通装备', r'汽车|铁路、船舶|航空航天'),
    ('机械与智能制造', r'专用设备|通用设备|电气机械'),
    ('能源与公用事业', r'电力|热力|燃气|水的生产|煤炭|石油|天然气'),
    ('材料与化工', r'化学|橡胶|塑料|金属|矿|纤维|石油加工'),
    ('建筑与房地产', r'建筑|房地产|土木工程'),
    ('消费与零售', r'批发|零售|食品|饮料|家具|纺织|服装|皮革|烟草|造纸|木材'),
    ('交通与物流', r'运输|仓储|装卸|邮政'),
    ('农业', r'农业|林业|畜牧|渔业|农、林、牧、渔'),
    ('文化传媒', r'新闻|出版|文化|体育|娱乐|电影|录音|广播'),
    ('教育', r'教育'),
    ('环保与公共服务', r'生态|环境|水利|公共设施|社会工作'),
    ('专业与商务服务', r'专业技术|研究和试验|商务|租赁|科技推广'),
    ('住宿与餐饮', r'住宿|餐饮'),
]

# 环境选择决定主要方向；兴趣和任务只作次级加分，映射结果仍须存在于目录。
EXPLORATION_OPTIONS = {
    'environment': {
        '金融与商业': {'金融服务': 100, '专业与商务服务': 65, '消费与零售': 60},
        '医疗与健康': {'生物医药': 100},
        '科技研发': {'软件与信息服务': 100, '电子与半导体': 95, '专业与商务服务': 60},
        '制造与新能源': {'机械与智能制造': 100, '能源与公用事业': 95, '汽车与交通装备': 90, '材料与化工': 85},
        '文化与服务': {'文化传媒': 100, '教育': 85, '专业与商务服务': 80, '住宿与餐饮': 75},
    },
    'interests': {
        '技术与创造': {'软件与信息服务': 24, '电子与半导体': 24, '机械与智能制造': 20},
        '商业与管理': {'金融服务': 24, '专业与商务服务': 24, '消费与零售': 20},
        '人与服务': {'教育': 24, '专业与商务服务': 20, '住宿与餐饮': 20, '生物医药': 18},
        '艺术与表达': {'文化传媒': 24, '教育': 18},
        '科学与健康': {'生物医药': 24, '材料与化工': 20, '专业与商务服务': 18},
    },
    'tasks': {
        '写代码与做产品': {'软件与信息服务': 18, '电子与半导体': 12},
        '分析数据和规律': {'金融服务': 18, '软件与信息服务': 18, '专业与商务服务': 15, '电子与半导体': 10},
        '设计制作与动手': {'机械与智能制造': 18, '汽车与交通装备': 18, '电子与半导体': 15, '文化传媒': 15},
        '沟通策划与组织': {'专业与商务服务': 18, '文化传媒': 18, '消费与零售': 15, '教育': 12},
        '研究实验与探索': {'生物医药': 18, '材料与化工': 18, '专业与商务服务': 18, '电子与半导体': 12},
    },
}


def normalized_company(name):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(name or ''))).casefold()


def company_id(name):
    return hashlib.sha256(normalized_company(name).encode()).hexdigest()[:24]


def _tracks(industries):
    result = set()
    for industry in industries:
        matches = [track for track, rule in TRACK_RULES if re.search(rule, industry)]
        result.update(matches or [industry])
    return sorted(result) or ['未分类']


def build_market(paths, samples_per_company=2):
    """统计所有行和企业，保留每企业近期样本及完整岗位标题索引。"""
    if not 1 <= samples_per_company <= 8:
        raise ValueError('每企业历史样本数须为1至8')
    paths = [Path(path) for path in paths]
    industry_map = {}
    industry_sources = {}
    sources = []
    # 独立第一遍使缺行业文件不依赖输入顺序地引用同名企业行业证据。
    for path in paths:
        source = {'id': hashlib.sha256(path.name.encode()).hexdigest()[:20],
                  'name': path.name, 'sha256': sha256_file(path), 'rows': 0}
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            required = {'企业名称', '招聘岗位', '工作城市', '最低月薪', '最高月薪', '职位描述', '招聘发布日期'}
            if not required <= set(reader.fieldnames or []):
                raise ValueError(f'{path.name}缺少必要字段：{sorted(required - set(reader.fieldnames or []))}')
            previous_line = 1
            for row in reader:
                line, previous_line = previous_line + 1, reader.line_num
                source['rows'] += 1
                industry = safe_text(row.get('上市公司行业', '')).strip()
                if industry and row['企业名称'].strip():
                    key = normalized_company(row['企业名称'])
                    industry_map.setdefault(key, set()).add(industry)
                    industry_sources.setdefault(key, {}).setdefault((industry, path.name),
                        {'industry': industry, 'file': path.name, 'line': line})
        sources.append(source)
    companies = {}
    fingerprints = {}
    duplicates = unnamed = 0
    for path, source in zip(paths, sources):
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            previous_line = 1
            for row in reader:
                line, previous_line = previous_line + 1, reader.line_num
                name = safe_text(row['企业名称']).strip()
                if not name:
                    unnamed += 1
                    continue
                key = normalized_company(name)
                company = companies.setdefault(key, {
                    'id': company_id(name), 'name': name,
                    'tracks': _tracks(industry_map.get(key, set())),
                    'raw_industries': sorted(industry_map.get(key, set())),
                    'industry_evidence': list(industry_sources.get(key, {}).values()),
                    'sources': [], 'history_count': 0, 'historical_jobs': [], 'search_terms': set(),
                })
                if source['name'] not in company['sources']:
                    company['sources'].append(source['name'])
                title = safe_text(row['招聘岗位'])[:180]
                company['search_terms'].add(title)
                try:
                    published = date.fromisoformat(row['招聘发布日期'].strip()[:10]).isoformat()
                except ValueError:
                    published = ''
                salary = salary_interval(row['最低月薪'], row['最高月薪'])
                city = safe_text(row['工作城市'])[:80]
                fingerprint = hashlib.sha256(encode([key, title, city, salary, published, row['职位描述']]).encode()).hexdigest()
                seen = fingerprints.setdefault(key, set())
                if fingerprint in seen:
                    duplicates += 1
                    continue
                seen.add(fingerprint)
                company['history_count'] += 1
                sample = {'id': fingerprint[:24], 'title': title, 'city': city, 'salary': salary,
                          'published': published, 'company_id': company['id'], 'company': name,
                          'tracks': company['tracks'], 'type': 'historical',
                          'source': {'file': source['name'], 'line': line, 'source_id': source['id']},
                          'industry_source': '原始行业字段或标准化全名相同企业的原始行业字段' if company['raw_industries'] else '缺少行业证据',
                          'education': safe_text(row.get('学历要求', ''))[:80],
                          'description': safe_text(row['职位描述'])[:240]}
                samples = company['historical_jobs']
                if len(samples) < samples_per_company or (published, sample['id']) > (samples[-1]['published'], samples[-1]['id']):
                    samples.append(sample)
                    samples.sort(key=lambda job: (job['published'], job['id']), reverse=True)
                    del samples[samples_per_company:]
    for company in companies.values():
        company['search_terms'] = sorted(company['search_terms'])
    return {'version': 1, 'created_at': now(), 'sources': sources,
            'scanned_rows': sum(source['rows'] for source in sources), 'duplicate_rows': duplicates,
            'unnamed_rows': unnamed, 'samples_per_company': samples_per_company,
            'companies': sorted(companies.values(), key=lambda company: company['name']),
            'scope': '用户提供的本地招聘CSV历史公告；完整企业目录、全量标题检索与每企业近期公告样本。',
            'method': '行业来自原始上市公司行业字段；按标准化企业全名精确引用同名企业证据，再按行业关键词作宽泛赛道归类。没有证据标未分类。未按公司简称、集团关系或岗位名称推断行业。重复公告依据企业、岗位、城市、日期、薪资及原始正文摘要去重。'}


def publish_market(store, bundle):
    stamp = now()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT kind,owner FROM entities WHERE id=?', (CATALOG_ID,)).fetchone()
        if previous and (previous['kind'] != 'market_catalog' or previous['owner'] != CATALOG_OWNER):
            raise ValueError('目录固定ID已被其他实体使用')
        db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',
                   (CATALOG_ID, 'market_catalog', CATALOG_OWNER, encode(bundle), stamp, stamp))
        db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',
                   (CATALOG_OWNER, 'import_local_market', CATALOG_ID, stamp))


def get_catalog(store):
    key = str(store.path.resolve())
    with store.connect() as db:
        row = db.execute('SELECT updated FROM entities WHERE id=? AND kind=? AND owner=?',
                         (CATALOG_ID, 'market_catalog', CATALOG_OWNER)).fetchone()
    stamp = row['updated'] if row else None
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == stamp:
            return cached[1]
        item = store.get(CATALOG_ID, 'market_catalog') if stamp else None
        result = item['data'] if item and item['owner'] == CATALOG_OWNER else {'companies': [], 'sources': []}
        _CACHE[key] = (stamp, result)
        return result


def _market_view(store):
    key = str(store.path.resolve())
    with store.connect() as db:
        rows = db.execute("SELECT kind,COUNT(*) AS n,MAX(updated) AS stamp FROM entities WHERE kind IN ('market_catalog','company_profile','job') GROUP BY kind").fetchall()
    version = tuple((row['kind'], row['n'], row['stamp']) for row in rows)
    with _CACHE_LOCK:
        cached = _VIEW_CACHE.get(key)
        if cached and cached[0] == version:
            return cached[1]
        catalog = get_catalog(store)
        companies = {item['id']: {**item, 'registered': False, 'live_count': 0, 'description': ''}
                     for item in catalog['companies']}
        profiles = {}
        for item in store.list('company_profile'):
            profile = item['data']
            if not profile.get('name', '').strip():
                continue
            profiles[item['owner']] = profile
            ident = company_id(profile['name'])
            company = companies.setdefault(ident, {'id': ident, 'name': profile['name'], 'tracks': [],
                'sources': [], 'history_count': 0, 'historical_jobs': [], 'raw_industries': [],
                'search_terms': [], 'live_count': 0})
            company['registered'] = True
            company['description'] = profile.get('description', '')
            company['tracks'] = sorted(set(company['tracks'] + profile.get('tracks', [])))
        jobs = []
        for item in store.list('job'):
            data = item['data']
            if data.get('deleted') or data.get('closed') or data.get('status') in {'draft', 'paused', 'closed', 'archived'}:
                continue
            profile = profiles.get(item['owner'], {})
            name = profile.get('name') or data.get('company', '')
            if not name.strip():
                continue
            ident = company_id(name)
            company = companies.setdefault(ident, {'id': ident, 'name': name, 'tracks': [], 'sources': [],
                'history_count': 0, 'historical_jobs': [], 'raw_industries': [], 'search_terms': [],
                'registered': True, 'live_count': 0, 'description': ''})
            company['registered'] = True
            industry = str(data.get('industry') or '').strip()
            tracks = sorted(set([industry, *_tracks([industry])])) if industry else profile.get('tracks', [])
            company['tracks'] = sorted(set(company['tracks'] + tracks)) or ['未分类']
            company['live_count'] += 1
            jobs.append({'id': item['id'], 'title': data.get('title', ''), 'city': data.get('city', ''),
                         'salary': salary_interval(data.get('salary_min'), data.get('salary_max')),
                         'company_id': ident, 'company': name, 'tracks': tracks or company['tracks'],
                         'type': 'live', 'published': item['created'], 'updated': item['updated'],
                         'description': safe_text(data.get('description', ''))[:500]})
        for company in companies.values():
            company['tracks'] = company['tracks'] or ['未分类']
            company['_search'] = '\n'.join([company['name'], *company['tracks'], *company.get('raw_industries', []),
                                           *company.get('search_terms', [])]).casefold()
        jobs.sort(key=lambda job: (job['published'], job['id']), reverse=True)
        tracks = Counter(track for company in companies.values() for track in company['tracks'])
        result = {'companies': companies, 'jobs': jobs, 'tracks': tracks, 'catalog': catalog}
        _VIEW_CACHE[key] = (version, result)
        return result


def _public_company(company):
    from backend.company_logos import logo_fields
    return {key: value for key, value in company.items() if key not in {'historical_jobs', 'search_terms', '_search'}} | logo_fields(company['id'])


class MarketModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class CompanyProfile(MarketModel):
    name: str = Field(min_length=1, max_length=160)
    tracks: list[str] = Field(min_length=1, max_length=20)
    description: str = Field(default='', max_length=3000)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('企业名称不能为空')
        return value

    @field_validator('tracks')
    @classmethod
    def clean_tracks(cls, value):
        cleaned = list(dict.fromkeys(track.strip() for track in value))
        if any(not track or len(track) > 100 for track in cleaned):
            raise ValueError('赛道名称须为1至100个字符')
        return cleaned


class Favorite(MarketModel):
    type: Literal['company', 'track']
    target_id: str = Field(min_length=1, max_length=160)


class Recommendation(MarketModel):
    answers: dict = Field(default_factory=dict, max_length=30)
    text: str = Field(default='', max_length=4000)

    @field_validator('answers')
    @classmethod
    def bounded_answers(cls, value):
        if len(encode(value)) > 12000:
            raise ValueError('探索回答内容过长')
        return value


class Exploration(Recommendation):
    seen: bool = False


def _private_id(kind, owner, *parts):
    return kind + '-' + hashlib.sha256(encode([owner, *parts]).encode()).hexdigest()[:32]


def attach_market(app, store, user):
    def student(current):
        if current['role'] != 'student':
            raise HTTPException(403, '此功能仅供学生账号使用')

    def employer(current):
        if current['role'] != 'employer':
            raise HTTPException(403, '此功能仅供企业账号使用')

    @app.get('/api/market/tracks')
    def tracks():
        return [{'name': name, 'count': count} for name, count in sorted(_market_view(store)['tracks'].items(), key=lambda item: (-item[1], item[0]))]

    @app.get('/api/market/search')
    def search(q: str = Query('', max_length=120), track: str = Query('', max_length=100),
               page: int = Query(1, ge=1, le=100000), page_size: int = Query(20, ge=1, le=50), current=Depends(user)):
        view = _market_view(store)
        query = q.strip().casefold()
        matched_live = [job for job in view['jobs'] if (not track or track in job['tracks']) and
                        (not query or query in (job['title'] + job['company'] + ''.join(job['tracks'])).casefold())]
        live_companies = {job['company_id'] for job in matched_live}
        companies = [company for company in view['companies'].values() if (not track or track in company['tracks']) and
                     (not query or query in company['_search'] or company['id'] in live_companies)]
        companies.sort(key=lambda company: (-int(company['registered']), -company['live_count'], company['name']))
        historical = [job for company in companies for job in company['historical_jobs'] if
                      not query or query in (job['title'] + job['company'] + ''.join(job['tracks'])).casefold()]
        jobs = matched_live + sorted(historical, key=lambda job: (job['published'], job['id']), reverse=True)
        start = (page - 1) * page_size
        return {'ready': bool(view['catalog'].get('created_at')), 'companies': [_public_company(company) for company in companies[start:start + page_size]],
                'jobs': jobs[start:start + page_size], 'total_companies': len(companies), 'total_jobs': len(jobs),
                'page': page, 'page_size': page_size,
                'history_basis': '企业目录及岗位标题全量检索；历史公告明细为每企业近期样本，history_count为去重后全量公告数。',
                'scanned_rows': view['catalog'].get('scanned_rows', 0)}

    @app.get('/api/market/companies/{ident}')
    def company(ident: str, current=Depends(user)):
        view = _market_view(store)
        result = view['companies'].get(ident)
        if not result:
            raise HTTPException(404, '未找到此企业')
        return {**_public_company(result), 'jobs': [job for job in view['jobs'] if job['company_id'] == ident],
                'historical_jobs': result['historical_jobs']}

    @app.get('/api/company/profile')
    def profile(current=Depends(user)):
        employer(current)
        rows = store.list('company_profile', current['id'])
        return rows[0]['data'] if rows else {'name': current['name'], 'tracks': [], 'description': ''}

    @app.put('/api/company/profile')
    def save_profile(payload: CompanyProfile, current=Depends(user)):
        employer(current)
        rows = store.list('company_profile', current['id'])
        ident = rows[0]['id'] if rows else _private_id('company-profile', current['id'])
        data = payload.model_dump()
        store.save('company_profile', current['id'], data, ident)
        return data

    @app.get('/api/me/favorites')
    def favorites(current=Depends(user)):
        student(current)
        return [{'id': item['id'], **item['data']} for item in store.list('market_favorite', current['id'])]

    @app.post('/api/me/favorites')
    @app.put('/api/me/favorites')
    def save_favorite(payload: Favorite, current=Depends(user)):
        student(current)
        view = _market_view(store)
        if payload.type == 'company':
            company = view['companies'].get(payload.target_id)
            if not company:
                raise HTTPException(404, '未找到此企业')
            name = company['name']
        else:
            if payload.target_id not in view['tracks']:
                raise HTTPException(404, '未找到此赛道')
            name = payload.target_id
        data = {**payload.model_dump(), 'name': name}
        ident = _private_id('favorite', current['id'], payload.type, payload.target_id)
        store.save('market_favorite', current['id'], data, ident)
        return {'id': ident, **data}

    @app.delete('/api/me/favorites/{kind}/{target_id:path}')
    def delete_favorite(kind: Literal['company', 'track'], target_id: str, current=Depends(user)):
        student(current)
        ident = _private_id('favorite', current['id'], kind, target_id)
        with store.connect() as db:
            db.execute('DELETE FROM entities WHERE id=? AND kind=? AND owner=?', (ident, 'market_favorite', current['id']))
        return {'ok': True}

    @app.get('/api/me/feed')
    def feed(page: int = Query(1, ge=1, le=100000), current=Depends(user)):
        student(current)
        saved = [item['data'] for item in store.list('market_favorite', current['id'])]
        companies = {item['target_id'] for item in saved if item['type'] == 'company'}
        tracks = {item['target_id'] for item in saved if item['type'] == 'track'}
        jobs = [job for job in _market_view(store)['jobs'] if job['company_id'] in companies or tracks.intersection(job['tracks'])]
        start = (page - 1) * 30
        return {'jobs': jobs[start:start + 30], 'total': len(jobs), 'page': page, 'page_size': 30,
                'basis': '仅展示真实平台岗位的发布时间；本地历史招聘资料不作为新发布动态。'}

    @app.get('/api/me/exploration')
    def exploration(current=Depends(user)):
        student(current)
        rows = store.list('market_exploration', current['id'])
        return rows[0]['data'] if rows else {'seen': False, 'answers': {}, 'text': ''}

    @app.put('/api/me/exploration')
    def save_exploration(payload: Exploration, current=Depends(user)):
        student(current)
        data = payload.model_dump()
        store.save('market_exploration', current['id'], data, _private_id('exploration', current['id']))
        return data

    @app.post('/api/market/recommend')
    def recommend(payload: Recommendation, current=Depends(user)):
        student(current)
        view = _market_view(store)
        answer_text = encode(payload.answers).casefold() + ' ' + payload.text.casefold()
        terms = set(re.findall(r'[a-zA-Z][a-zA-Z0-9+#]{1,25}|[\u4e00-\u9fff]{2,12}', answer_text))
        chinese = re.findall(r'[\u4e00-\u9fff]{2,}', answer_text)
        terms.update(run[index:index + 2] for run in chinese for index in range(len(run) - 1))
        ranked = []
        for track, count in view['tracks'].items():
            if track == '未分类':
                continue
            track_terms = {term for term in terms if term in track.casefold()}
            score = min(18, 12 * int(track.casefold() in answer_text) + 3 * len(track_terms))
            selections = {}
            reasons = []
            for group, options in EXPLORATION_OPTIONS.items():
                values = payload.answers.get(group, [])
                values = [values] if isinstance(values, str) else values
                if not isinstance(values, list):
                    continue
                matched = [value for value in values if isinstance(value, str) and track in options.get(value, {})]
                if matched:
                    score += max(options[value][track] for value in matched)
                    selections[group] = matched
                    label = {'environment': '工作环境', 'interests': '兴趣', 'tasks': '任务偏好'}[group]
                    reasons.append(label + '选择“' + '、'.join(matched) + '”对应' + track)
            examples = []
            fallback_examples = []
            sampled_jobs = matched_jobs = 0
            title_terms = set()
            for company in view['companies'].values():
                if track not in company['tracks']:
                    continue
                for job in company['historical_jobs']:
                    sampled_jobs += 1
                    example = {'company': company['name'], 'title': job['title'], 'source': job['source']}
                    if len(fallback_examples) < 2:
                        fallback_examples.append(example)
                    hits = sorted(term for term in terms if term in job['title'].casefold())
                    if hits:
                        matched_jobs += 1
                        title_terms.update(hits)
                        if len(examples) < 2:
                            examples.append(example)
            history_score = round(8 * matched_jobs / sampled_jobs, 3) if sampled_jobs else 0
            score = round(score + history_score, 3)
            if track_terms:
                reasons.append('回答包含赛道词项“' + '、'.join(sorted(track_terms)) + '”')
            if matched_jobs:
                reasons.append(f'本地{sampled_jobs}条岗位样本中{matched_jobs}条标题匹配回答词项')
            ranked.append({'track': track, 'score': score, 'company_count': count,
                           'reason': '；'.join(reasons) if reasons else '本地目录可探索方向，按企业覆盖数补充',
                           'evidence': {'matched_terms': sorted(track_terms | title_terms), 'examples': examples or fallback_examples,
                                        'selections': selections, 'sample_jobs': sampled_jobs,
                                        'matched_sample_jobs': matched_jobs, 'history_score': history_score,
                                        'company_count': count, 'source': '本地全行业招聘目录及平台企业档案'}})
        ranked.sort(key=lambda item: (-item['score'], -item['company_count'], item['track']))
        return {'recommendations': ranked[:5],
                'basis': ('依据目录已有赛道推荐：工作环境选择优先，兴趣与任务偏好作次级匹配；历史标题按样本命中比例加分且最多8分。属于资料检索提示，不是职业测评结论。'
                          if ranked else '本地目录暂无可支持的赛道，请先接入招聘目录或企业档案。')}
