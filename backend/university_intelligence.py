"""高校需求观察：全量历史公告聚合、站内岗位及本校匿名学生数据。"""

import math
import threading
from collections import Counter, defaultdict
from pathlib import Path

from fastapi import Depends, HTTPException, Query

from backend.evidence import PATTERNS, safe_text, sha256_file
from backend.recruitment_data import normalize_recruitment, read_recruitment, recruitment_fingerprint
from backend.market import EXPLORATION_OPTIONS, TRACK_RULES, _tracks, company_id, normalized_company
from backend.store import encode, now


DEMAND_ID = 'demand-observatory-v1'
DEMAND_OWNER = 'local-demand-import'
MINIMUM_STUDENTS = 5
_CACHE = {}
_LOCK = threading.RLock()


def build_demand(paths):
    """扫描全量CSV，按公告摘要跨文件去重，不读取市场目录的岗位样本。"""
    paths = [Path(path) for path in paths]
    industries, sources = defaultdict(set), []
    for path in paths:
        source = {'name': path.name, 'sha256': sha256_file(path), 'scanned_rows': 0}
        for _, row in read_recruitment(path):
            source['scanned_rows'] += 1
            industry = safe_text(row.get('上市公司行业', '')).strip()
            if row['企业名称'].strip() and industry:
                industries[normalized_company(row['企业名称'])].add(industry)
        sources.append(source)
    groups, seen = {}, set()
    duplicate_rows = invalid_dates = unnamed_rows = 0
    dates = []
    quality = Counter()
    for path in paths:
        for _, row in read_recruitment(path):
            name = safe_text(row['企业名称']).strip()
            if not name:
                unnamed_rows += 1
                continue
            title, city = safe_text(row['招聘岗位'])[:180], safe_text(row['工作城市'])[:80] or '未注明'
            key = normalized_company(name)
            normalized = normalize_recruitment(row)
            quality.update(normalized['issues'])
            published = normalized['published']
            fingerprint = recruitment_fingerprint(row, normalized)
            if fingerprint in seen:
                duplicate_rows += 1
                continue
            seen.add(fingerprint)
            if published:
                dates.append(published)
            else:
                invalid_dates += 1
            month = published[:7] if published else '日期未注明'
            tracks = tuple(_tracks(industries.get(key, set())))
            group = groups.setdefault((month, city, tracks), {'month': month, 'city': city, 'tracks': list(tracks),
                'postings': 0, 'skills': Counter(), 'companies': set()})
            group['postings'] += 1
            group['companies'].add(company_id(name))
            text = title + '\n' + row['职位描述']
            group['skills'].update(skill for skill, pattern in PATTERNS.items() if pattern.search(text))
    built_at = now()
    for group in groups.values():
        group['skills'] = dict(group['skills'])
        group['companies'] = sorted(group['companies'])
    return {'version': 1, 'groups': list(groups.values()),
            'history_period': f'{min(dates)} 至 {max(dates)}' if dates else '未接入有效日期的历史公告',
            'source_meta': {'ready': True, 'sources': sources, 'scanned_rows': sum(source['scanned_rows'] for source in sources),
                'deduplicated_postings': len(seen), 'duplicate_rows': duplicate_rows, 'invalid_dates': invalid_dates,
                'unnamed_rows': unnamed_rows, 'built_at': built_at, 'quality_issues': dict(quality)},
            'method': '全量CSV按企业全名、岗位、城市区域、薪资、完整日期、原始正文和标准化资格条件去重；关联上市公司行业及同名招聘主体证据仅作宽泛赛道参考，不认定发布法人行业，缺证据保留未分类。技能为标题或正文词项命中，每公告每技能最多计一次。'}


def publish_demand(store, bundle):
    stamp = now()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = db.execute('SELECT kind,owner FROM entities WHERE id=?', (DEMAND_ID,)).fetchone()
        if previous and (previous['kind'] != 'demand_observatory' or previous['owner'] != DEMAND_OWNER):
            raise ValueError('需求观察固定ID已被其他实体使用')
        db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated=excluded.updated',
                   (DEMAND_ID, 'demand_observatory', DEMAND_OWNER, encode(bundle), stamp, stamp))
        db.execute('INSERT INTO audit(actor,action,target,created) VALUES(?,?,?,?)',
                   (DEMAND_OWNER, 'import_full_local_demand', DEMAND_ID, stamp))


def get_demand(store):
    key = str(store.path.resolve())
    with store.connect() as db:
        item = db.execute('SELECT updated FROM entities WHERE id=? AND kind=? AND owner=?',
                          (DEMAND_ID, 'demand_observatory', DEMAND_OWNER)).fetchone()
    version = item['updated'] if item else None
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and cached[0] == version:
            return cached[1]
        item = store.get(DEMAND_ID, 'demand_observatory') if version else None
        result = item['data'] if item and item['owner'] == DEMAND_OWNER else {
            'groups': [], 'history_period': '尚未接入全量历史公告',
            'source_meta': {'ready': False, 'sources': [], 'scanned_rows': 0, 'deduplicated_postings': 0,
                            'duplicate_rows': 0, 'invalid_dates': 0, 'built_at': None}}
        _CACHE[key] = (version, result)
        return result


def _canonical_skill(name):
    name = str(name or '').strip()
    for skill, pattern in PATTERNS.items():
        if name.casefold() == skill.casefold() or pattern.fullmatch(name):
            return skill
    return name


def _level(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value) if 0 <= value <= 5 else None


def _courses(store, school_id):
    catalogs = store.list('university_course_catalog', school_id)
    if catalogs:
        courses = catalogs[0]['data'].get('courses', [])
        mapping = {}
    else:
        profiles = store.list('university_profile', school_id)
        program = profiles[0]['data'].get('program', {}) if profiles else {}
        courses = program.get('courses', [])
        mapping = program.get('course_skill_mapping', {})
    if not courses:
        return None
    counts = Counter()
    for course in courses:
        skills = course.get('skills') or mapping.get(course.get('id', course.get('code', '')))
        if not isinstance(skills, (list, dict)) or not skills:
            return None
        names = {_canonical_skill(skill) for skill in skills if isinstance(skill, str) and skill.strip()}
        if not names:
            return None
        counts.update(names)
    return counts


def _student_aggregates(store, school_id, available_tracks):
    available_tracks = available_tracks | {name for name, _ in TRACK_RULES}
    with store.connect() as db:
        valid_students = {row['id'] for row in db.execute("SELECT id FROM users WHERE role='student'")}
    profiles = {}
    for item in store.list('profile'):
        if item['owner'] not in profiles and item['owner'] in valid_students:
            profiles[item['owner']] = item['data']
    profiles = {owner: data for owner, data in profiles.items() if data.get('school_id') == school_id}
    if len(profiles) < MINIMUM_STUDENTS:
        return None, {}, Counter()
    explorations = {}
    for item in store.list('market_exploration'):
        if item['owner'] in profiles and item['owner'] not in explorations:
            explorations[item['owner']] = item['data']
    abilities, goals = defaultdict(list), Counter()
    for owner, profile in profiles.items():
        for skill, observation in profile.get('abilities', {}).items():
            value = _level(observation.get('level')) if isinstance(observation, dict) else None
            if value is not None and skill.strip():
                abilities[_canonical_skill(skill)].append(value)
        person_goals = set()
        for industry in profile.get('preferences', {}).get('industries', []):
            if isinstance(industry, str):
                person_goals.update(track for track in [industry, *_tracks([industry])] if track in available_tracks)
        career = str(profile.get('career', ''))
        person_goals.update(track for track in available_tracks if track != '未分类' and track in career)
        person_goals.update(track for track in _tracks([career]) if track != '未分类' and track in available_tracks)
        exploration = explorations.get(owner, {})
        values = exploration.get('answers', {}).get('environment', [])
        values = [values] if isinstance(values, str) else values
        if isinstance(values, list):
            for selection in values:
                if not isinstance(selection, str):
                    continue
                mapping = EXPLORATION_OPTIONS['environment'].get(selection, {})
                if mapping:
                    maximum = max(mapping.values())
                    person_goals.update(track for track, weight in mapping.items() if weight == maximum and track in available_tracks)
        goals.update(person_goals)
    return len(profiles), abilities, Counter({name: count for name, count in goals.items() if count >= MINIMUM_STUDENTS})


def attach_university_intelligence(app, store, user):
    @app.get('/api/university/intelligence')
    def intelligence(track: str = Query('', max_length=100), city: str = Query('', max_length=100), current=Depends(user)):
        if current['role'] != 'university':
            raise HTTPException(403, '此功能仅供高校账号使用')
        demand = get_demand(store)
        all_groups = demand['groups']
        available_tracks = {value for group in all_groups for value in group['tracks']}
        available_cities = {group['city'] for group in all_groups}
        groups = [group for group in all_groups if (not track or track in group['tracks']) and (not city or city == group['city'])]
        historical = Counter()
        sectors, trend, links = Counter(), Counter(), Counter()
        companies = set()
        for group in groups:
            companies.update(group['companies'])
            historical.update(group['skills'])
            trend[group['month']] += group['postings']
            for sector in group['tracks']:
                sectors[sector] += group['postings']
                for skill, count in group['skills'].items():
                    links[(sector, skill)] += count
        live_skills, targets = Counter(), defaultdict(list)
        live_count = 0
        profiles = {item['owner']: item['data'] for item in reversed(store.list('company_profile'))}
        for item in store.list('job'):
            data = item['data']
            if data.get('deleted') or data.get('closed') or data.get('status') in {'draft', 'paused', 'closed', 'archived'}:
                continue
            company = profiles.get(item['owner'], {}).get('name') or data.get('company', '')
            industry = str(data.get('industry') or '').strip()
            tracks = set([industry, *_tracks([industry])]) if industry else set(profiles.get(item['owner'], {}).get('tracks', []) or ['未分类'])
            job_city = str(data.get('city', '')).strip() or '未注明'
            available_tracks.update(tracks)
            available_cities.add(job_city)
            if track and track not in tracks or city and job_city != city:
                continue
            live_count += 1
            if company:
                companies.add(company_id(company))
            text = str(data.get('title', '')) + '\n' + str(data.get('description', ''))
            skills = {skill for skill, pattern in PATTERNS.items() if pattern.search(text)}
            job_targets = defaultdict(list)
            for requirement in data.get('requirements', []):
                skill = _canonical_skill(requirement.get('skill'))
                if not skill:
                    continue
                skills.add(skill)
                value = _level(requirement.get('target'))
                if value is not None:
                    job_targets[skill].append(value)
            live_skills.update(skills)
            for skill, values in job_targets.items():
                targets[skill].append(sum(values) / len(values))
        available_tracks.discard('')
        student_count, abilities, goals = _student_aggregates(store, current['id'], available_tracks)
        course_counts = _courses(store, current['id'])
        skill_names = set(historical) | set(live_skills) | {skill for skill, values in abilities.items() if len(values) >= MINIMUM_STUDENTS}
        skills = []
        for skill in skill_names:
            values = abilities.get(skill, [])
            count = len(values) if len(values) >= MINIMUM_STUDENTS else None
            student_level = round(sum(values) / len(values), 3) if count else None
            target_level = round(sum(targets[skill]) / len(targets[skill]), 3) if targets.get(skill) else None
            gap = round(max(0, target_level - student_level), 3) if student_level is not None and target_level is not None else None
            skills.append({'name': skill, 'postings': historical[skill], 'live_postings': live_skills[skill],
                'student_count': count, 'student_level': student_level, 'target_level': target_level, 'gap': gap})
        skills.sort(key=lambda row: (-row['postings'], -row['live_postings'], row['name']))
        return {'generated_at': now(), 'history_period': demand['history_period'], 'source_meta': demand['source_meta'],
            'filters': {'tracks': sorted(available_tracks), 'cities': sorted(available_cities)},
            'applied_filters': {'track': track, 'city': city},
            'summary': {'historical_postings': sum(group['postings'] for group in groups), 'live_postings': live_count,
                        'companies': len(companies), 'student_count': student_count},
            'student_suppressed': student_count is None, 'student_minimum': MINIMUM_STUDENTS,
            'trend': [{'month': month, 'postings': count} for month, count in sorted(trend.items())],
            'sectors': [{'name': name, 'postings': count} for name, count in sectors.most_common()], 'skills': skills,
            'student_goals': [{'name': name, 'count': count} for name, count in goals.most_common()],
            'coverage': [{'skill': row['name'], 'course_count': course_counts[row['name']] if course_counts is not None else None} for row in skills],
            'links': [{'source': '赛道：' + sector, 'target': '技能：' + skill, 'value': count} for (sector, skill), count in links.most_common()],
            'notes': ['历史需求来自已导入招聘CSV全量去重统计，实际期间见历史观察期；未使用企业近期样本推算市场。',
                '历史赛道参考关联上市公司行业及同名招聘主体证据，不认定发布法人行业或工商行业编码。',
                '平台岗位为当前站内已发布岗位，每次请求重新读取；未接入外部实时招聘数据。',
                '公告条数不是招聘人数；多赛道公告分别计入各赛道，赛道数不可直接相加为公告总数。',
                '历史技能为词项出现频次，未从招聘正文推断能力等级。目标等级只来自真实站内岗位的显式能力要求。',
                '学生统计仅包含school_id关联本校的学生账号；总样本或单技能、单目标不足5人时抑制对应数据。学生自述能力不代表全校总体。',
                '赛道和城市筛选历史公告及站内岗位，本校匿名学生汇总保持全校授权样本口径。',
                '能力差值为岗位目标等级减本校能力均值的非负差，仅双方均有数据且该技能本校至少5样本时计算，不是市场绝对缺员人数。',
                '课程覆盖仅据本校显式课程技能映射计算；缺课程或映射时为null，未用课程标题猜测覆盖。']}
