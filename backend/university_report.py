"""本校培养诊断的报告视图；复用已保存的决策结果，不补造预测。"""
from collections import defaultdict
import copy

from fastapi import Depends, HTTPException
from pydantic import BaseModel

from backend.competition_api import public_result
from backend.decision import changed_skills, structural_score, validate_program, run_decision
from backend.store import now
from backend.job_state import active_job
from backend.university_report_metadata import check_report_versions, report_source_versions


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


def constraint_checks(program, actions):
    """候选只供定位冲突，按真实课程校验给出超限差额。"""
    rows = []
    if not program:
        return rows
    for action in actions:
        check = validate_program(program, [action])
        resources = []
        for key, limit, label, unit in [('cost', 'budget', '调整预算', '元'),
                                       ('teacher_hours', 'teacher_hours_max', '师资课时', '课时'),
                                       ('lab_hours', 'lab_hours_max', '实验室课时', '课时')]:
            used, maximum = check['totals'][key], program['constraints'][limit]
            resources.append({'id': key, 'label': label, 'used': used, 'limit': maximum,
                              'unit': unit, 'shortfall': max(0, used - maximum)})
        rows.append({'action_id': action['id'], 'name': action.get('reason', action['id']),
                     'feasible': check['feasible'], 'violations': check['violations'], 'resources': resources})
    return rows


def calculation_state(run, result, checks):
    if not run:
        return {'state': 'not_calculated', 'label': '尚未测算', 'missing': [],
                'reason': '连接课程、岗位目标与资源上限后，确认并生成一次测算。'}
    if result.get('best'):
        if result.get('status') == 'partial':
            return {'state': 'missing_inputs', 'label': '课程方案可行，预测输入待补',
                    'missing': [result['best']['forecast'].get('reason', '四年情景输入待补')],
                    'reason': '已保存通过课程约束的改善方案；四年结果需补齐预测依据。'}
        return {'state': 'success', 'label': '已找到可行改善方案', 'missing': [],
                'reason': '所列推荐已通过本轮培养方案约束，并产生正向技能结构改善。'}
    if result.get('status') == 'incomplete':
        return {'state': 'missing_inputs', 'label': '测算输入待补', 'missing': result.get('missing', []),
                'reason': '缺少可比较的岗位目标或能力证据，尚未生成推荐。'}
    infeasible = not result.get('rounds') or all(not row['program']['feasible'] for row in result.get('rounds', []))
    return {'state': 'infeasible' if infeasible else 'no_improvement',
            'label': '当前约束下无可行方案' if infeasible else '当前候选未产生改善', 'missing': [],
            'reason': '检查下列真实约束冲突并调整资源或课程。' if infeasible else '保留原方案；修改候选课程与已确认增益后重新测算。'}


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
    catalog = (run['data'].get('catalog_snapshot') if run else None) or (catalogs[0]['data'] if catalogs else {'courses': [], 'sources': []})
    departments = defaultdict(int)
    for course in catalog['courses']:
        for department in course.get('departments', []) or ['未注明院系']:
            departments[department] += 1
    checks = constraint_checks(program, proposals) if run and not best else []
    actions = copy.deepcopy(adjusted['changes']) if adjusted else []
    for action in actions:
        original = next((a for a in proposals if a['id'] == action['action_id']), {})
        action.update({'cost': original.get('cost'), 'skill_delta': original.get('skill_delta', {}),
                       'status': '已通过约束测算', 'teaching_plan': original.get('teaching_plan')})
    return public_result({
        'generated_at': now(), 'program': program, 'metrics': metrics,
        'calculation': calculation_state(run, result, checks), 'constraint_checks': checks,
        'version_check': check_report_versions(store, owner, run) if run else {'stale': False, 'changes': [], 'unknown': [], 'token': None},
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
    improved = result.get('benefit', 0) > 1e-8
    selected = [c for c in inputs['courses'] if c['id'] in result['selected']] if improved else []
    teaching_actions = {action['id']: action for action in inputs.get('teaching_actions', [])}
    courses = [{
        'id': c['id'], 'name': c['name'], 'credits': c['credits'],
        'hours': None, 'prerequisites': [],
    } for c in selected]
    catalogs = store.list('university_course_catalog', owner)
    catalog = saved['data'].get('catalog_snapshot') or (catalogs[0]['data'] if catalogs else {'courses': [], 'sources': []})
    reason = '简版优化已保存资源组合与剩余缺口；未提供能力基线、完整专业课程及就业和需求情景，四年预测待补充。'
    resource_labels = [('cost', '调整预算', '元'), ('credits', '新增学分', '学分'),
                       ('teacher_hours', '师资课时', '课时'), ('lab_hours', '实验室课时', '课时'),
                       ('study_hours', '学生新增学习时间', '课时'), ('months', '完成期限', '月')]
    checks = []
    if not improved:
        for course in inputs['courses']:
            resources = [{'id': key, 'label': label, 'unit': unit, 'used': course[key],
                          'limit': inputs['limits'][key], 'shortfall': max(0, course[key] - inputs['limits'][key])}
                         for key, label, unit in resource_labels]
            violations = [row['label'] + '超出上限' for row in resources if row['shortfall'] > 0]
            checks.append({'action_id': course['id'], 'name': course['name'], 'feasible': not violations,
                           'violations': violations, 'resources': resources})
    infeasible = bool(checks) and all(not check['feasible'] for check in checks) and any(inputs['gaps'].values())
    calculation = {'state': 'success' if improved else 'infeasible' if infeasible else 'no_improvement',
                   'label': '已找到可行改善组合' if improved else '当前资源下没有可行候选' if infeasible else '当前候选未产生改善',
                   'missing': [], 'reason': reason}
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
        'calculation': calculation,
        'constraint_checks': checks, 'version_check': check_report_versions(store, owner, saved),
        'skills': [{'name': name, 'target': None, 'before': None, 'after': None, 'count': None,
                    'gap_before': gap, 'gap_after': result['remaining'][name]}
                   for name, gap in inputs['gaps'].items()],
        'scenarios': [{'name': name, 'emoji': emoji, 'description': description, 'assumptions': None,
                       'years': [], 'skill_levels': {}, 'coverage_after': None, 'match_after': None}
                      for name, emoji, description in SCENARIOS],
        'forecast_status': 'incomplete', 'forecast_reason': reason, 'forecast_basis': None,
        'implementation_lag': None, 'admissions_delay_years': None,
        'metrics_scope': '已保存培养方案优化的输入与结果快照', 'sample_count': None,
        'actions': [{'action_id': c['id'], 'kind': 'modify' if teaching_actions.get(c['id'], {}).get('kind') == 'enhance' else 'add',
                     'reason': teaching_actions.get(c['id'], {}).get('name', '在本轮资源上限内选中的培养候选'),
                     'removed': [], 'added': [course],
                     'evidence': teaching_actions.get(c['id'], {}).get('evidence') or result.get('assumption', '录入的情景假设'),
                     'cost': c['cost'], 'skill_delta': c['gains'], 'status': '已通过简版资源约束测算',
                     'teaching_plan': c.get('teaching_plan')}
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

    @app.post('/api/university/report/recalculate')
    def recalculate(payload: ReportRecalculation, current=Depends(user)):
        if current['role'] != 'university':
            raise HTTPException(403, '仅高校账号可重新测算本校报告')
        if payload.confirmed is not True:
            raise HTTPException(422, '请先确认输入差异，再生成新的测算记录')
        saved = owned_result(store, current['id'], payload.run_id, 'decision_run')
        versions = check_report_versions(store, current['id'], saved)
        if payload.versions_token != versions['token']:
            raise HTTPException(409, '输入在确认后再次变化，请刷新差异并重新确认')
        if any(change['id'] in {'catalog', 'profile', 'workspace'} for change in versions['changes']):
            raise HTTPException(422, '课程库或本校配置已变更，请先在培养向导确认课程、资源与动作并生成新方案')
        case_id = saved['data'].get('case_id')
        if not case_id:
            raise HTTPException(422, '该历史记录没有关联方案，请在方案页面保存新方案后测算')
        case = owned_result(store, current['id'], case_id, 'decision_case')['data']
        inputs = []
        for ident, kind in [(case['recruitment_id'], 'recruitment'),
                            *([(case['employment_id'], 'employment')] if case.get('employment_id') else []),
                            *[(ident, 'policy') for ident in case.get('policy_ids', [])]]:
            item = owned_result(store, current['id'], ident, 'research_dataset')
            if item['data']['kind'] != kind or item['data'].get('split') == 'evaluation':
                raise HTTPException(422, '输入数据类型错误或属于封存评测集')
            inputs.append(item)
        recruitment = inputs[0]['data']['records']
        employment = next((item['data']['records'] for item in inputs if item['data']['kind'] == 'employment'), [])
        try:
            result = run_decision(case, recruitment, employment)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        provenance = [{'dataset_id': item['id'], 'sha256': item['data']['sha256'],
                       'source': item['data']['source_snapshot'], 'processing': item['data']['processing']}
                      for item in inputs]
        data = {'case_id': case_id, 'case': case, 'result': result, 'provenance': provenance,
                'source_versions': report_source_versions(store, current['id'], case, provenance),
                'supersedes_run_id': saved['id'], 'confirmed_versions_token': payload.versions_token}
        if check_report_versions(store, current['id'], saved)['token'] != payload.versions_token:
            raise HTTPException(409, '测算期间输入发生变化，请刷新差异并重新确认')
        catalogs = store.list('university_course_catalog', current['id'])
        data['catalog_snapshot'] = catalogs[0]['data'] if catalogs else None
        ident = store.save('decision_run', current['id'], data)
        store.audit(current['id'], 'recalculate_university_report', ident)
        return {'id': ident, 'supersedes_run_id': saved['id']}


class ReportRecalculation(BaseModel):
    run_id: str
    versions_token: str
    confirmed: bool = False
