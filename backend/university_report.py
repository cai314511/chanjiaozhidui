"""本校培养诊断的报告视图；复用已保存的决策结果，不补造预测。"""
from collections import defaultdict

from fastapi import Depends, HTTPException

from backend.competition_api import public_result
from backend.decision import changed_skills, structural_score, validate_program
from backend.store import now
from backend.job_state import active_job


SCENARIOS = [
    ('乐观', '🌤️', '产业需求增长，校企合作顺利'),
    ('基准', '🧭', '按照正常培养调整节奏实施'),
    ('悲观', '🌧️', '岗位需求下降，教学资源受限'),
]


def coverage(skills, targets):
    if not targets or set(targets) - set(skills):
        return None
    return round(100 * sum(skills[name]['level'] >= target['target']
                           for name, target in targets.items()) / len(targets), 3)


def owned_result(store, owner, ident, kind):
    item = store.get(ident, kind)
    if item is None:
        raise HTTPException(404, '所选测算记录不存在')
    if item['owner'] != owner:
        raise HTTPException(403, '仅可读取本校测算记录')
    return item


def build_report(store, owner, run_id=None, optimization_id=None):
    if run_id is not None and optimization_id is not None:
        raise HTTPException(422, '请仅选择一次专业决策或培养方案优化')
    if optimization_id is not None:
        return optimization_report(store, owner, owned_result(store, owner, optimization_id, 'optimization'))
    profiles = store.list('university_profile', owner)
    program = profiles[0]['data']['program'] if profiles else None
    proposals = profiles[0]['data'].get('actions', []) if profiles else []
    runs = store.list('decision_run', owner)
    run = owned_result(store, owner, run_id, 'decision_run') if run_id is not None else (runs[0] if runs else None)
    result = run['data']['result'] if run else {}
    case = run['data']['case'] if run else {}
    if case:
        program = case['program']
        proposals = case['actions']
    best = result.get('best')
    diagnosis = result.get('diagnosis', {})
    targets = diagnosis.get('demand', {}).get('skills', {})
    skills = dict(program.get('skills', {})) if program else {}
    sample_count = None
    if not run:
        observations = defaultdict(list)
        students = set()
        for item in store.list('profile'):
            if item['data'].get('school_id') != owner:
                continue
            students.add(item['owner'])
            for name, observation in item['data'].get('abilities', {}).items():
                observations[name].append(observation['level'])
        sample_count = len(students) if len(students) >= 5 else None
        skills = {name: {'level': sum(values) / len(values), 'sample_count': len(values),
                         'evidence': '本校至少5名学生的能力自述均值'}
                  for name, values in observations.items() if len(values) >= 5}
        levels = defaultdict(list)
        for item in store.list('job'):
            job = item['data']
            if not active_job(job):
                continue
            for requirement in job.get('requirements', []):
                levels[requirement['skill']].append(requirement['target'])
        targets = {name: {'target': sum(values) / len(values), 'weight': len(values)}
                   for name, values in levels.items()}
    selected = [action for action in proposals if best and action['id'] in best['action_ids']]
    base_assumption = next((scenario for scenario in case.get('scenarios', []) if scenario['name'] == '基准'), {})
    after_skills = changed_skills({**program, 'skills': skills}, selected,
                                  base_assumption.get('skill_gain_factor', 1)) if program and best else None
    before_match = structural_score(targets, skills)['score']
    after_match = structural_score(targets, after_skills)['score'] if after_skills is not None else None
    before_coverage = coverage(skills, targets)
    after_coverage = coverage(after_skills, targets) if after_skills is not None else None
    history = diagnosis.get('employment_history', [])
    last = history[-1] if history else None
    related = round(last['related_employed'] / last['graduates'] * 100, 3) if last and last.get('related_employed') is not None else None
    forecast = best.get('forecast', {}) if best else {}
    scenarios = []
    for name, emoji, description in SCENARIOS:
        saved = next((s for s in forecast.get('scenarios', []) if s['name'] == name), None)
        assumption = next((s for s in case.get('scenarios', []) if s['name'] == name), None)
        years = []
        if saved:
            for before, after in zip(saved['no_adjustment']['years'], saved['adjustment']['years']):
                years.append({'year': after['year'], 'offset': after['offset'],
                              'match_before': before['skill_match'], 'match_after': after['skill_match'],
                              'employment_before': before['employment_rate'], 'employment_after': after['employment_rate'],
                              'admissions_before': before['admissions_issued'], 'admissions_after': after['admissions_issued'],
                              'demand': after['demand'], 'graduates': after['graduates']})
        effective = bool(years) and forecast.get('lag', 4) <= 4
        scenario_skills = changed_skills(program, selected, assumption['skill_gain_factor']) if effective else None
        scenarios.append({'name': name, 'emoji': emoji, 'description': description,
                          'assumptions': assumption, 'years': years,
                          'skill_levels': {name: observation['level'] for name, observation in scenario_skills.items()} if scenario_skills is not None else {},
                          'coverage_after': coverage(scenario_skills, targets) if scenario_skills is not None else None,
                          'match_after': years[-1]['match_after'] if years else None})
    base = next(s for s in scenarios if s['name'] == '基准')
    baseline = result.get('baseline_program') or (validate_program(program, []) if program else None)
    adjusted = best.get('program') if best else None
    metrics = [
        {'id': 'match', 'label': '专业与岗位匹配度', 'before': before_match, 'after': after_match, 'unit': '%',
         'note': '岗位目标与培养能力等级的结构匹配；存在未评估技能时不生成总分。'},
        {'id': 'coverage', 'label': '学生技能覆盖程度', 'before': before_coverage, 'after': after_coverage, 'unit': '%',
         'note': '达到岗位目标等级的技能项占比，基于本校汇总；不代表达标学生比例。'},
        {'id': 'related', 'label': '毕业生专业对口率', 'before': related, 'after': None, 'unit': '%',
         'note': (f'{last["year"]}届对口就业人数 ÷ 毕业生人数；调整后需毕业跟踪数据。' if related is not None else '补充本专业毕业生总数及对口就业人数；就业率另行展示。')},
        {'id': 'enrollment', 'label': '招生规模适配度', 'before': program['current_seats'] if program else None,
         'after': base['years'][-1]['admissions_after'] if base['years'] else None, 'unit': '人',
         'note': (f'四年招生情景；教学资源支持上限 {forecast["supported_admissions_max"]} 人。' if forecast.get('supported_admissions_max') is not None else '当前招生规模；调整值需同范围核实需求与教学容量。')},
        {'id': 'cost', 'label': '培养方案实施成本', 'before': 0 if program else None,
         'after': adjusted['totals']['cost'] if adjusted else None, 'unit': '元',
         'note': '本轮课程调整的新增投入；当前方案的日常教学经费不在该口径内。'},
    ]
    resources = []
    if program:
        for key, limit, label, unit in [('cost', 'budget', '调整预算', '元'),
                                       ('teacher_hours', 'teacher_hours_max', '师资课时', '课时'),
                                       ('lab_hours', 'lab_hours_max', '实验室课时', '课时')]:
            resources.append({'id': key, 'label': label, 'unit': unit,
                              'before': baseline['totals'][key] if baseline else None,
                              'after': adjusted['totals'][key] if adjusted else None,
                              'limit': program['constraints'][limit]})
    catalogs = store.list('university_course_catalog', owner)
    catalog = catalogs[0]['data'] if catalogs else {'courses': [], 'sources': []}
    departments = defaultdict(int)
    for course in catalog['courses']:
        for department in course.get('departments', []) or ['未注明院系']:
            departments[department] += 1
    actions = adjusted['changes'] if adjusted else [
        {'action_id': action['id'], 'kind': action['kind'], 'reason': action['reason'],
         'removed': [c for c in program['courses'] if c['id'] in action['remove_ids']],
         'added': action['add_courses'], 'evidence': action['evidence']} for action in proposals
    ]
    for action in actions:
        original = next((a for a in proposals if a['id'] == action['action_id']), {})
        action.update({'cost': original.get('cost'), 'skill_delta': original.get('skill_delta', {}),
                       'status': '已通过约束测算' if best else '待测算候选建议'})
    return public_result({
        'generated_at': now(), 'program': program, 'metrics': metrics,
        'student_skills': [{'name': name, 'level': observation['level'], 'count': observation['sample_count']}
                           for name, observation in skills.items() if observation['sample_count'] >= 5],
        'skills': [
            {'name': name, 'target': target['target'], 'before': skills.get(name, {}).get('level'),
             'after': after_skills.get(name, {}).get('level') if after_skills is not None else None,
             'count': skills.get(name, {}).get('sample_count')} for name, target in targets.items()],
        'scenarios': scenarios, 'forecast_status': forecast.get('status', 'incomplete'),
        'forecast_reason': forecast.get('reason', '先在专业调整决策中补齐岗位需求、就业基期及三情景参数，并保存一次测算。'),
        'forecast_basis': forecast.get('basis'), 'implementation_lag': forecast.get('lag'),
        'admissions_delay_years': forecast.get('admissions_delay_years'),
        'metrics_scope': '已保存专业决策的证据快照' if run else '当前平台岗位与本校授权学生汇总',
        'sample_count': sample_count, 'actions': actions, 'resources': resources,
        'courses_before': program['courses'] if program else [],
        'courses_after': adjusted['courses'] if adjusted else [],
        'feasible': adjusted['feasible'] if adjusted else None,
        'source': {'run_id': run['id'] if run else None, 'optimization_id': None,
                   'case_id': run['data'].get('case_id') if run else None, 'title': case.get('title'),
                   'created_at': run['created'] if run else None,
                   'assumptions': case.get('assumptions'),
                   'provenance': run['data'].get('provenance', []) if run else []},
        'catalog': {'total': len(catalog['courses']), 'sources': catalog['sources'],
                    'mapped': sum(bool(course['skills']) for course in catalog['courses']),
                    'missing_hours': sum(course['hours'] is None for course in catalog['courses']),
                    'departments': [{'name': key, 'count': value} for key, value in sorted(departments.items(), key=lambda r: -r[1])]}
    })


def optimization_report(store, owner, saved):
    """仅展示简版真实输入与资源解，不推导缺失的能力基线或课程学时。"""
    inputs, result = saved['data']['input'], saved['data']['result']
    selected = [c for c in inputs['courses'] if c['id'] in result['selected']]
    courses = [{
        'id': c['id'], 'name': c['name'], 'credits': c['credits'],
        'hours': None, 'prerequisites': [],
    } for c in selected]
    catalogs = store.list('university_course_catalog', owner)
    catalog = catalogs[0]['data'] if catalogs else {'courses': [], 'sources': []}
    reason = '简版优化已保存资源组合与剩余缺口；未提供能力基线、完整专业课程及就业和需求情景，四年预测待补充。'
    resource_labels = [('cost', '调整预算', '元'), ('credits', '新增学分', '学分'),
                       ('teacher_hours', '师资课时', '课时'), ('lab_hours', '实验室课时', '课时'),
                       ('study_hours', '学生新增学习时间', '课时'), ('months', '完成期限', '月')]
    metrics = [
        {'id': key, 'label': label, 'before': None,
         'after': result['used']['cost'] if key == 'cost' else None, 'unit': unit,
         'note': '本轮新增投入；原有教学经费未知。' if key == 'cost' else '简版优化未提供该指标所需基线。'}
        for key, label, unit in [('match', '专业与岗位匹配度', '%'), ('coverage', '学生技能覆盖程度', '%'),
                                 ('related', '毕业生专业对口率', '%'), ('enrollment', '招生规模适配度', '人'),
                                 ('cost', '培养方案实施成本', '元')]
    ]
    return public_result({
        'generated_at': now(), 'program': None, 'metrics': metrics, 'student_skills': [],
        'skills': [{'name': name, 'target': None, 'before': None, 'after': None, 'count': None,
                    'gap_before': gap, 'gap_after': result['remaining'][name]}
                   for name, gap in inputs['gaps'].items()],
        'scenarios': [{'name': name, 'emoji': emoji, 'description': description, 'assumptions': None,
                       'years': [], 'skill_levels': {}, 'coverage_after': None, 'match_after': None}
                      for name, emoji, description in SCENARIOS],
        'forecast_status': 'incomplete', 'forecast_reason': reason, 'forecast_basis': None,
        'implementation_lag': None, 'admissions_delay_years': None,
        'metrics_scope': '已保存培养方案优化的输入与结果快照', 'sample_count': None,
        'actions': [{'action_id': c['id'], 'kind': 'add', 'reason': '在本轮资源上限内选中的培养候选',
                     'removed': [], 'added': [course], 'evidence': result.get('assumption', '录入的情景假设'),
                     'cost': c['cost'], 'skill_delta': c['gains'], 'status': '已通过简版资源约束测算'}
                    for c, course in zip(selected, courses)],
        'resources': [{'id': key, 'label': label, 'unit': unit, 'before': None,
                       'after': max((c['months'] for c in selected), default=0) if key == 'months' else result['used'][key],
                       'limit': inputs['limits'][key]} for key, label, unit in resource_labels],
        'courses_before': [], 'courses_after': courses, 'feasible': bool(selected),
        'source': {'run_id': None, 'optimization_id': saved['id'], 'case_id': None,
                   'title': '培养方案优化 · ' + '、'.join(c['name'] for c in selected) if selected else '培养方案优化 · 无正收益组合',
                   'created_at': saved['created'], 'assumptions': result.get('assumption'),
                   'input': inputs, 'provenance': []},
        'catalog': {'total': len(catalog['courses']), 'sources': catalog['sources'],
                    'mapped': sum(bool(c.get('skills')) for c in catalog['courses']),
                    'missing_hours': sum(c.get('hours') is None for c in catalog['courses']), 'departments': []},
    })


def attach_university_report(app, store, user):
    @app.get('/api/university/report')
    def report(run_id: str | None = None, optimization_id: str | None = None, current=Depends(user)):
        if current['role'] != 'university':
            raise HTTPException(403, '仅高校账号可读取本校培养诊断报告')
        return build_report(store, current['id'], run_id, optimization_id)
