import copy
import math
from graphlib import CycleError, TopologicalSorter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from backend.solver import milp
from scipy.stats import binomtest, fisher_exact, linregress


VERSION = 'decision-2'


def wilson_interval(successes, total):
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError('比例区间要求有效成功数及样本量')
    result = binomtest(int(successes), int(total)).proportion_ci(method='wilson')
    return round(float(result.low), 6), round(float(result.high), 6)


def direction_gap(demand, supply):
    d, s = sum(demand.values()), sum(supply.values())
    if not d or not s:
        return None
    return round(.5 * sum(abs(demand.get(k, 0) / d - supply.get(k, 0) / s)
                            for k in set(demand) | set(supply)), 6)


def admissions_step(seats, employment_rate, policy):
    error = employment_rate - policy['target_rate']
    if abs(error) <= policy['deadband']:
        return max(policy['min_seats'], min(policy['max_seats'], seats))
    change = max(-policy['max_change'], min(policy['max_change'], policy['gain'] * error))
    result = round(seats * (1 + change))
    result = max(math.ceil(seats * (1-policy['max_change'])), min(math.floor(seats * (1+policy['max_change'])), result))
    # 四舍五入可能使小规模专业不发生变化，这种状态应由稳定性检测如实报告。
    return max(policy['min_seats'], min(policy['max_seats'], result))


def split_students(directions, groups):
    if len({d['job_category'] for d in directions}) != len(directions):
        raise ValueError('培养方向与岗位类别必须一一对应')
    pairs = [(i, j, group['preferences'].index(direction['id']))
             for i, group in enumerate(groups) for j, direction in enumerate(directions)
             if direction['id'] in group['preferences'] and group['grade'] >= direction['min_grade']]
    if not pairs:
        return {'allocated': 0, 'unallocated': sum(g['count'] for g in groups),
                'direction_counts': {d['id']: 0 for d in directions}, 'allocation': []}
    priority = (len(directions) + 1) * sum(g['count'] for g in groups) + 1
    objective = [-priority + rank for _, _, rank in pairs]
    rows = [[int(i == k) for i, _, _ in pairs] for k in range(len(groups))]
    rows += [[int(j == k) for _, j, _ in pairs] for k in range(len(directions))]
    caps = [g['count'] for g in groups] + [d['capacity'] for d in directions]
    result = milp(np.array(objective), integrality=np.ones(len(pairs)), bounds=Bounds(0, np.inf),
                  constraints=LinearConstraint(np.array(rows), 0, np.array(caps)), options={'time_limit': 10})
    if not result.success:
        raise ValueError('方向分流未完成：' + result.message)
    allocation = [{'group_id': groups[i]['id'], 'direction_id': directions[j]['id'], 'count': int(round(result.x[k])),
                   'preference_rank': rank + 1} for k, (i, j, rank) in enumerate(pairs) if result.x[k] > .5]
    counts = {d['id']: sum(a['count'] for a in allocation if a['direction_id'] == d['id']) for d in directions}
    total = sum(counts.values())
    return {'allocated': total, 'unallocated': sum(g['count'] for g in groups) - total,
            'direction_counts': counts, 'allocation': allocation,
            'basis': '匿名分组的整数流分配；组内个体分配仍需本人确认'}


def validate_program(program, actions):
    baseline = {c['id']: c for c in program['courses']}
    final = copy.deepcopy(baseline)
    violations, removed, additions = [], set(), {}
    changes = []
    for action in actions:
        for ident in action['remove_ids']:
            if ident not in baseline or ident in removed:
                violations.append('移除未知或重复课程：' + ident)
                continue
            old = baseline[ident]
            replacement = next((c for c in action['add_courses'] if c['id'] == ident), None)
            if old.get('protected') and (replacement is None or not replacement.get('protected') or
                   replacement['name'] != old['name'] or replacement['hours'] < old['hours'] or replacement['credits'] < old['credits']):
                violations.append('受保护课程不得删除、改名或减少学时学分：' + old['name'])
            removed.add(ident)
            final.pop(ident, None)
        for course in action['add_courses']:
            ident = course['id']
            if ident in additions or ident in baseline and ident not in action['remove_ids']:
                violations.append('新增课程标识冲突：' + ident)
            additions[ident] = course
        changes.append({'action_id': action['id'], 'kind': action['kind'], 'reason': action.get('reason', ''),
                        'removed': [baseline[i] for i in action['remove_ids'] if i in baseline],
                        'added': action['add_courses'], 'evidence': action.get('evidence', '')})
    final.update(additions)
    courses = list(final.values())
    totals = {key: sum(c[key] for c in courses) for key in ('credits', 'hours', 'teacher_hours', 'lab_hours')}
    totals['general_credits'] = sum(c['credits'] for c in courses if c['category'] == 'general')
    totals['professional_credits'] = sum(c['credits'] for c in courses if c['category'] == 'professional')
    totals['cost'] = sum(a['cost'] for a in actions)
    limits = program['constraints']
    for key, label in (('credits', '总学分'), ('hours', '总学时')):
        if not limits[key + '_min'] - 1e-8 <= totals[key] <= limits[key + '_max'] + 1e-8:
            violations.append(label + '不满足培养方案范围')
    for key, limit, label in (('general_credits', 'general_credits_min', '通识学分'), ('professional_credits', 'professional_credits_min', '专业学分')):
        if totals[key] < limits[limit] - 1e-8:
            violations.append(label + '低于最低要求')
    for key, limit, label in (('teacher_hours', 'teacher_hours_max', '师资课时'), ('lab_hours', 'lab_hours_max', '实验室课时'), ('cost', 'budget', '调整预算')):
        if totals[key] > limits[limit] + 1e-8:
            violations.append(label + '超出上限')
    for course in courses:
        if set(course.get('prerequisites', [])) - set(final):
            violations.append('先修课程缺失：' + course['name'])
    try:
        list(TopologicalSorter({c['id']: set(c.get('prerequisites', [])) for c in courses}).static_order())
    except CycleError:
        violations.append('课程先修关系存在循环')
    for direction in program.get('directions', []):
        if set(direction['course_ids']) - set(final):
            violations.append('方向配套课程不完整：' + direction['name'])
    return {'feasible': not violations, 'violations': violations, 'courses': courses, 'totals': totals, 'changes': changes}


def demand_profile(recruitment):
    reference_year = max((int(r['month'][:4]) for r in recruitment), default=None)
    all_postings = len(recruitment)
    recruitment = [r for r in recruitment if int(r['month'][:4]) == reference_year]
    skills, categories = {}, {}
    known_headcount = 0
    complete = True
    for row in recruitment:
        count = row.get('verified_headcount')
        complete = complete and count is not None
        if count is not None:
            known_headcount += count
        categories[row['category']] = categories.get(row['category'], 0) + 1
        for skill in row['skills']:
            bucket = skills.setdefault(skill['name'], {'level_sum': 0, 'weight': 0, 'observations': 0})
            bucket['level_sum'] += skill['level'] * skill['weight']
            bucket['weight'] += skill['weight']
            bucket['observations'] += 1
    targets = {name: {'target': v['level_sum'] / v['weight'], 'weight': v['weight'], 'observations': v['observations']}
               for name, v in skills.items()}
    return {'skills': targets, 'category_postings': categories, 'verified_headcount': known_headcount if complete else None,
            'known_headcount_subtotal': known_headcount, 'postings': len(recruitment), 'postings_all_years': all_postings,
            'reference_year': reference_year, 'observed_months': sorted({r['month'] for r in recruitment})}


def structural_score(targets, skills):
    unknown = sorted(set(targets) - set(skills))
    if unknown:
        return {'score': None, 'missing_skills': unknown}
    total = sum(r['weight'] for r in targets.values())
    if not total:
        return {'score': None, 'missing_skills': []}
    details = [{'skill': name, 'target': r['target'], 'supply': skills[name]['level'],
                'gap': max(0, r['target'] - skills[name]['level']), 'weight': r['weight'] / total,
                'sample_count': skills[name]['sample_count'], 'evidence': skills[name]['evidence']}
               for name, r in targets.items()]
    score = 100 * sum(d['weight'] * min(1, d['supply'] / d['target']) for d in details)
    return {'score': round(score, 6), 'missing_skills': [], 'details': details}


def diagnostics(recruitment, employment, program):
    demand = demand_profile(recruitment)
    skill = structural_score(demand['skills'], program['skills'])
    history = sorted([r for r in employment if r['program_code'] == program['code']], key=lambda r: r['year'])
    last = history[-1] if history else None
    scale = None
    if last and demand['verified_headcount'] is not None:
        scale = {'graduates': last['graduates'], 'verified_vacancies': demand['verified_headcount'],
                 'supply_year': last['year'], 'demand_year': demand['reference_year'],
                 'time_alignment': '跨年度比较时沿用最近观测供给规模到招聘参考年度，须由使用者确认范围可比',
                 'supply_minus_demand': last['graduates'] - demand['verified_headcount'],
                 'supply_demand_ratio': last['graduates'] / demand['verified_headcount'] if demand['verified_headcount'] else None}
    statistics = {'employment_interval': wilson_interval(last['employed'], last['graduates']) if last else None,
                  'trend': None, 'first_last_fisher_p': None, 'salary_outlier_years': [],
                  'interpretation': '统计描述与相关性分析；不将其解释为课程调整的因果效应'}
    if len(history) >= 3:
        regression = linregress([r['year'] for r in history], [r['employed'] / r['graduates'] for r in history])
        statistics['trend'] = {'annual_rate_change': float(regression.slope),
                               'p_value': float(regression.pvalue) if math.isfinite(regression.pvalue) else None,
                               'standard_error': float(regression.stderr) if math.isfinite(regression.stderr) else None}
    if len(history) >= 2:
        first = history[0]
        statistics['first_last_fisher_p'] = float(fisher_exact([[first['employed'], first['graduates'] - first['employed']],
                                                              [last['employed'], last['graduates'] - last['employed']]]).pvalue)
    salaries = [(r['year'], r['average_salary']) for r in history if r.get('average_salary') is not None]
    if len(salaries) >= 4:
        q1, q3 = np.quantile([s[1] for s in salaries], [.25, .75])
        spread = q3 - q1
        statistics['salary_outlier_years'] = [year for year, salary in salaries if salary < q1 - 1.5 * spread or salary > q3 + 1.5 * spread]
    return {'skills': skill, 'direction_gap': direction_gap(demand['category_postings'], program['current_direction_counts']),
            'direction_basis': '招聘公告类别分布与当前培养方向分布的总变差距离，数值范围0–1',
            'scale': scale, 'scale_missing': None if scale else '缺少同范围核实招聘人数或本专业就业汇总，公告数量不能代替招聘人数',
            'statistics': statistics, 'demand': demand, 'employment_history': history}


def select_actions(program, actions, targets, excluded):
    if not actions:
        return []
    n, names = len(actions), list(targets)
    baseline = {c['id']: c for c in program['courses']}
    limits = program['constraints']
    upper = np.ones(n + len(names))
    objective = [0.] * n + [-targets[s]['weight'] / targets[s]['target'] for s in names]
    for i, name in enumerate(names):
        upper[n + i] = targets[name]['target']
    rows, lo, hi = [], [], []

    def constrain(vector, minimum=-np.inf, maximum=np.inf):
        rows.append(vector + [0.] * len(names) if len(vector) == n else vector)
        lo.append(minimum)
        hi.append(maximum)

    def delta(action, key, category=None):
        old = [baseline[i] for i in action['remove_ids'] if i in baseline]
        return sum(c[key] for c in action['add_courses'] if category is None or c['category'] == category) - sum(c[key] for c in old if category is None or c['category'] == category)

    for j, action in enumerate(actions):
        if set(action['remove_ids']) - set(baseline):
            upper[j] = 0
        for ident in action['remove_ids']:
            old = baseline.get(ident)
            replacement = next((c for c in action['add_courses'] if c['id'] == ident), None)
            if old and old['protected'] and (not replacement or not replacement['protected'] or replacement['name'] != old['name'] or replacement['credits'] < old['credits'] or replacement['hours'] < old['hours']):
                upper[j] = 0
        if any(c['id'] in baseline and c['id'] not in action['remove_ids'] for c in action['add_courses']):
            upper[j] = 0
    for ident in baseline:
        constrain([float(ident in a['remove_ids']) for a in actions], maximum=1)
    all_ids = set(baseline) | {c['id'] for a in actions for c in a['add_courses']}

    def presence(ident):
        return [float(any(c['id'] == ident for c in a['add_courses'])) - float(ident in a['remove_ids']) for a in actions]

    for ident in all_ids:
        base = int(ident in baseline)
        constrain(presence(ident), minimum=-base, maximum=1-base)
    for key in ('credits', 'hours'):
        base = sum(c[key] for c in baseline.values())
        constrain([delta(a, key) for a in actions], limits[key+'_min'] - base, limits[key+'_max'] - base)
    for category in ('general', 'professional'):
        base = sum(c['credits'] for c in baseline.values() if c['category'] == category)
        constrain([delta(a, 'credits', category) for a in actions], limits[category+'_credits_min'] - base)
    for key in ('teacher_hours', 'lab_hours'):
        base = sum(c[key] for c in baseline.values())
        constrain([delta(a, key) for a in actions], maximum=limits[key+'_max'] - base)
    constrain([a['cost'] for a in actions], maximum=limits['budget'])
    for direction in program['directions']:
        for ident in direction['course_ids']:
            constrain(presence(ident), minimum=1-int(ident in baseline), maximum=1-int(ident in baseline))
    for ident, course in baseline.items():
        for prerequisite in course['prerequisites']:
            required = presence(prerequisite)
            old_exists = [-float(ident in a['remove_ids']) for a in actions]
            constrain([v - p for v, p in zip(old_exists, required)], maximum=int(prerequisite in baseline)-1)
    for j, action in enumerate(actions):
        for course in action['add_courses']:
            for prerequisite in course['prerequisites']:
                vector = [-v for v in presence(prerequisite)]
                vector[j] += 1
                constrain(vector, maximum=int(prerequisite in baseline))
    for i, name in enumerate(names):
        supply = program['skills'][name]['level']
        gains = [a['skill_delta'].get(name, 0) for a in actions]
        constrain(gains, minimum=-supply, maximum=5-supply)
        vector = [-g for g in gains] + [0.] * len(names)
        vector[n+i] = 1
        constrain(vector, maximum=supply)
    for selected in excluded:
        constrain([1. if i in selected else -1. for i in range(n)], maximum=len(selected)-1)
    result = milp(np.array(objective), integrality=[1]*n+[0]*len(names), bounds=Bounds(np.zeros(n+len(names)), upper),
                  constraints=LinearConstraint(np.array(rows), np.array(lo), np.array(hi)), options={'time_limit': 10})
    if result.status == 2:
        return None
    if not result.success:
        raise ValueError('课程调整优化未完成：' + result.message)
    return [i for i in range(n) if result.x[i] > .5]


def changed_skills(program, actions, factor=1):
    result = copy.deepcopy(program['skills'])
    for name in result:
        change = sum(a['skill_delta'].get(name, 0) for a in actions)
        # 悲观情景只折减正向收益，负向影响不会因情景折扣而变小。
        change = change * factor if change > 0 else change
        result[name]['level'] = max(0, min(5, result[name]['level'] + change))
    return result


def forecast(case, diagnosis, selected, include_sensitivity=True):
    history = diagnosis['employment_history']
    demand = diagnosis['demand']['verified_headcount']
    if not history or demand is None or not case['market_scope_confirmed'] or not case['annual_demand_confirmed']:
        return {'status': 'incomplete', 'reason': '需要就业基期、核实招聘人数及同地区同周期同市场范围确认', 'scenarios': []}
    last, program = history[-1], case['program']
    if diagnosis['demand']['reference_year'] < last['year']:
        return {'status': 'incomplete', 'reason': '招聘参考年度早于最新就业年度，请更新需求证据后推演', 'scenarios': []}
    capacity = min(last['graduates'], demand)
    if capacity < last['employed'] or capacity <= 0:
        return {'status': 'incomplete', 'reason': '招聘人数覆盖范围不能解释基期就业人数，请核对市场范围与人数口径', 'scenarios': []}
    p0 = last['employed'] / capacity
    interval = diagnosis['statistics']['employment_interval']
    conditional_interval = [min(1, p * last['graduates'] / capacity) for p in interval]
    baseline_score = diagnosis['skills']['score']
    if baseline_score is None:
        return {'status': 'incomplete', 'reason': '缺少有证据的培养技能等级', 'scenarios': []}
    resources = validate_program(program, selected)['totals']
    limits = program['constraints']
    capacity_limits = [case['admissions']['max_seats'], sum(d['capacity'] for d in program['directions'])]
    for key, bound in (('teacher_hours', 'teacher_hours_max'), ('lab_hours', 'lab_hours_max')):
        if resources[key] > 0:
            capacity_limits.append(math.floor(program['current_seats'] * limits[bound] / resources[key]))
    supported_max = min(capacity_limits)
    if supported_max < max(case['admissions']['min_seats'], math.ceil(program['current_seats']*(1-case['admissions']['max_change']))):
        return {'status': 'incomplete', 'reason': '方向或教学资源容量不能支持受幅度限制的招生过渡，请修改方案', 'scenarios': []}
    control = {**case['admissions'], 'max_seats': supported_max}
    scenarios = []
    origin_year = max(last['year'], diagnosis['demand']['reference_year'])
    for scenario in case['scenarios']:
        score = structural_score(diagnosis['demand']['skills'], changed_skills(program, selected, scenario['skill_gain_factor']))['score']
        improvement = (score - baseline_score) / 100
        paths = {}
        for name, adjusted in (('no_adjustment', False), ('adjustment', True)):
            seats = program['current_seats']
            if adjusted:
                seats = admissions_step(seats, last['employed'] / last['graduates'], control)
            intakes = [seats]
            rows = []
            for year in range(1, 13):
                graduates = program['pipeline_graduates'][year-1] if year < 4 else round(intakes[year-4] * program['completion_rate'])
                available = demand * (1 + scenario['demand_growth']) ** year
                effective = adjusted and year >= case['implementation_lag']
                shift = case['skill_employment_elasticity'] * improvement if effective else 0
                probability = max(0, min(1, p0 + shift))
                employed = min(graduates, available) * probability
                rate = employed / graduates if graduates else None
                salary = last.get('average_salary')
                if salary is not None:
                    salary *= (1 + scenario['salary_growth']) ** year
                    if effective:
                        salary *= max(0, 1 + case['skill_salary_elasticity'] * improvement)
                rate_bounds = [min(graduates, available) * max(0, min(1, p + shift)) / graduates for p in conditional_interval] if graduates else None
                if adjusted and year % control['cycle_years'] == 0 and rate is not None:
                    seats = admissions_step(seats, rate, control)
                rows.append({'year': origin_year + year, 'offset': year, 'graduates': graduates,
                             'demand': round(available, 3), 'employed': round(employed, 3),
                             'employment_rate': round(rate, 6) if rate is not None else None,
                             'employment_rate_interval': rate_bounds,
                             'salary': round(salary, 2) if salary is not None else None,
                             'skill_match': score if effective else baseline_score,
                             'admissions_issued': seats})
                intakes.append(seats)
            tail = intakes[-6:]
            changes = [tail[i+1] - tail[i] for i in range(len(tail)-1)]
            signs = [math.copysign(1, d) for d in changes if d]
            paths[name] = {'years': rows[:4], 'stability': {
                'horizon_years': 12, 'last_six_intakes': tail,
                'stable_in_last_five_steps': all(abs(d) <= 1 for d in changes),
                'direction_reversals': sum(signs[i] != signs[i-1] for i in range(1, len(signs))),
                'bounded': all(case['admissions']['min_seats'] <= x <= (supported_max if adjusted else case['admissions']['max_seats']) for x in intakes),
                'at_boundary': intakes[-1] in {control['min_seats'], control['max_seats']},
                'target_band_satisfied': rows[-1]['employment_rate'] is not None and abs(rows[-1]['employment_rate']-control['target_rate']) <= control['deadband']}}
        before, after = paths['no_adjustment']['years'][-1], paths['adjustment']['years'][-1]
        scenarios.append({'name': scenario['name'], 'assumptions': scenario, **paths,
                          'four_year_change': {key: round(after[key] - before[key], 6) if after[key] is not None and before[key] is not None else None
                                               for key in ('employed', 'employment_rate', 'salary', 'skill_match')}})
    sensitivity = []
    if include_sensitivity:
        for key in ('skill_employment_elasticity', 'skill_salary_elasticity'):
            current = case[key]
            trials = []
            for value in sorted({max(0, current-.1), min(1, current+.1)}):
                trial = forecast({**case, key: value}, diagnosis, selected, include_sensitivity=False)
                central = next(s for s in trial['scenarios'] if s['name'] == '基准')
                trials.append({'value': value, 'four_year_change': central['four_year_change']})
            sensitivity.append({'parameter': key, 'value': current, 'trials': trials,
                                'interpretation': '对显式情景系数上下扰动0.1并重新推演，未将系数称为因果估计'})
    return {'status': 'ready', 'scenarios': scenarios, 'sensitivity': sensitivity,
            'basis': '由基期就业校准的结构情景推演；三情景概率为使用者主观假设',
            'interval_basis': '95%基期Wilson抽样区间的传播，不包含结构模型误差；情景差异另列',
            'lag': case['implementation_lag'], 'admissions_delay_years': 4,
            'supported_admissions_max': supported_max,
            'capacity_assumption': '方向容量作为硬上限；师资和实验室课时按招生人数相对现有规模线性缩放的情景假设',
            'observed_employment_year': last['year'], 'projection_origin_year': origin_year,
            'time_alignment': '就业样本与招聘期不同时，沿用最近观测就业基准到推演起点，属于显式结构假设'}


def risks(program, selected, validation, projection, split):
    if not selected:
        return []
    totals, limits = validation['totals'], program['constraints']
    action_ids = [a['id'] for a in selected]
    base_hours = sum(c['hours'] for c in program['courses'])
    changed_hours = sum(abs(sum(c['hours'] for c in a['add_courses']) - sum(c['hours'] for c in program['courses'] if c['id'] in a['remove_ids'])) for a in selected)
    exposure = [
        ('师资短板', totals['teacher_hours'] / limits['teacher_hours_max'] if limits['teacher_hours_max'] else 0,
         '教学团队', '开课前一学期', '新增课程缺少可投入师资', '核验教师排课与专业背景，分配主讲及替补教师', '师资课时使用比例'),
        ('学生适应', changed_hours / base_hours if base_hours else 1,
         '专业负责人和学业导师', '分流前及每学期末', '课程变动带来学习负担及适应成本', '提供先修衔接、辅导与意愿复核，跟踪课程通过率', '变动学时/原总学时'),
        ('资源冲突', totals['lab_hours'] / limits['lab_hours_max'] if limits['lab_hours_max'] else 0,
         '实验室和教务排课部门', '排课前两个月', '新增实践与已有教学争用实验室时段', '核对设备和时段，建立冲突排课清单并落实校企实践资源', '实验室课时使用比例'),
    ]
    result = []
    for name, ratio, owner, deadline, consequence, response, indicator in exposure:
        grade = 3 if ratio > .85 else 2 if ratio > .6 else 1
        result.append({'risk': name, 'action_ids': action_ids, 'impact_population': '本专业受调整课程和方向影响的学生及教师',
                       'consequence': consequence, 'indicator': indicator, 'exposure': round(ratio, 4),
                       'likelihood_grade': grade, 'severity_grade': grade,
                       'assessment_basis': '按资源或学时暴露比例分档：超过85%为3，超过60%为2，其余为1；非统计发生概率',
                       'warning_threshold': .85, 'owner': owner, 'deadline': deadline, 'response': response})
    original_lab = sum(c['lab_hours'] for c in program['courses'])
    if totals['lab_hours'] <= original_lab:
        probability = sum(s['assumptions']['probability'] for s in projection.get('scenarios', []) if s['assumptions']['skill_gain_factor'] < 1)
        result[2] = {'risk': '能力改善未达预期', 'action_ids': action_ids, 'impact_population': '所选课程覆盖的后续学生',
                     'consequence': '录入的课程能力增益属于假设，实施效果可能低于培养目标',
                     'indicator': '技能增益折减情景的主观概率之和', 'exposure': probability if projection.get('scenarios') else None,
                     'likelihood_grade': 2, 'severity_grade': 2, 'assessment_basis': '依据录入增益假设及情景折减；未推断为实证发生频率',
                     'warning_threshold': 0, 'owner': '课程负责人和教学评价部门', 'deadline': '每学期课程考核后',
                     'response': '使用同一能力量规开展前后测，核验实践作业和雇主反馈，未达目标时修订课程内容'}
    if split['unallocated']:
        result.append({'risk': '方向分流受限', 'action_ids': action_ids, 'impact_population': '未分配到志愿方向的匿名学生组',
                       'consequence': '成绩门槛、意愿与容量不能同时满足', 'indicator': '未分配比例',
                       'exposure': split['unallocated'] / (split['allocated'] + split['unallocated']),
                       'likelihood_grade': 3, 'severity_grade': 2, 'assessment_basis': '当前模型已出现未分配结果',
                       'warning_threshold': 0, 'owner': '教务处和专业负责人', 'deadline': program['split_timing'],
                       'response': '开展二次志愿征询，调整有资源支持的方向容量并重新计算'})
    if projection['status'] == 'ready':
        exposure_probability = sum(s['assumptions']['probability'] for s in projection['scenarios'] if s['four_year_change']['employment_rate'] is not None and s['four_year_change']['employment_rate'] < 0)
        if exposure_probability:
            result.append({'risk': '就业改善未实现', 'action_ids': action_ids, 'impact_population': '调整方案影响的后续毕业生',
                           'consequence': '部分情景下四年后就业率低于不调整基线', 'indicator': '就业率下降情景的主观概率之和',
                           'exposure': exposure_probability, 'likelihood_grade': 3 if exposure_probability > .5 else 2,
                           'severity_grade': 3, 'assessment_basis': '情景概率由使用者设定，不是经验发生频率',
                           'warning_threshold': 0, 'owner': '招生就业部门', 'deadline': '每年度招生方案确定前',
                           'response': '复核需求覆盖和就业反馈，重新调整方向容量、课程及招生控制参数'})
    return result


def run_decision(case, recruitment, employment):
    program = case['program']
    recruitment = [r for r in recruitment if r['region'] == program['region']]
    diagnosis = diagnostics(recruitment, employment, program)
    if not case['annual_demand_confirmed'] or not case['market_scope_confirmed']:
        diagnosis['scale'] = None
        diagnosis['scale_missing'] = '尚未同时确认去重年度招聘人数和市场范围可比性，不能将招聘窗口快照与毕业生规模直接相比'
    elif diagnosis['employment_history'] and diagnosis['demand']['reference_year'] < diagnosis['employment_history'][-1]['year']:
        diagnosis['scale'] = None
        diagnosis['scale_missing'] = '招聘需求证据早于就业样本年度，暂不进行规模差距比较'
    baseline = validate_program(program, [])
    result = {'model': VERSION, 'diagnosis': diagnosis, 'baseline_program': baseline,
              'assumptions': case['assumptions'], 'rounds': [], 'best': None, 'status': 'incomplete'}
    if not recruitment or diagnosis['skills']['score'] is None:
        result['missing'] = ['同地区岗位数据或有证据的技能供给不足'] + diagnosis['skills']['missing_skills']
        return result
    excluded, candidates = [], []
    for iteration in range(case['max_rounds']):
        indices = select_actions(program, case['actions'], diagnosis['demand']['skills'], excluded)
        if indices is None:
            result['stop_reason'] = '候选动作中没有尚未评估的可行组合'
            break
        if not case['actions'] and iteration:
            break
        excluded.append(indices)
        selected = [case['actions'][i] for i in indices]
        check = validate_program(program, selected)
        adjusted = structural_score(diagnosis['demand']['skills'], changed_skills(program, selected))
        split = split_students(program['directions'], program['groups'])
        after_distribution = {d['job_category']: split['direction_counts'][d['id']] for d in program['directions']}
        after_distribution['未分流'] = split['unallocated']
        split['direction_gap_after'] = direction_gap(diagnosis['demand']['category_postings'], after_distribution)
        prediction = forecast(case, diagnosis, selected) if check['feasible'] else {'status': 'incomplete', 'reason': '培养方案硬约束未满足', 'scenarios': []}
        risk_rows = risks(program, selected, check, prediction, split)
        improvement = adjusted['score'] - diagnosis['skills']['score']
        viable = check['feasible'] and improvement >= -1e-8
        worst_employed = min((s['adjustment']['years'][-1]['employed'] for s in prediction['scenarios']), default=-1)
        ranking = (worst_employed, adjusted['score'], -check['totals']['cost'])
        reflections = list(check['violations'])
        if prediction['status'] != 'ready':
            reflections.append(prediction['reason'])
        if split['unallocated']:
            reflections.append('分流存在未分配学生，请检查容量、成绩门槛与意愿')
        if not selected or improvement <= 1e-8:
            reflections.append('该组合未产生正向技能结构改善')
        if not reflections:
            reflections.append('硬约束通过；下一轮排除本组合，检验其他组合的三情景表现和成本')
        candidate = {'iteration': iteration+1, 'action_ids': [a['id'] for a in selected], 'program': check,
                     'skills': adjusted, 'improvement': round(improvement, 6), 'split': split,
                     'forecast': prediction, 'risks': risk_rows, 'eligible': viable,
                     'reflection': reflections, 'next_step': '增加已评估组合的排除约束并重新求解'}
        result['rounds'].append(candidate)
        if viable and selected and improvement > 1e-8:
            candidates.append((ranking, candidate))
        if not case['actions']:
            break
    if candidates:
        result['best'] = max(candidates, key=lambda item: item[0])[1]
        result['status'] = 'ready' if result['best']['forecast']['status'] == 'ready' else 'partial'
    else:
        result['status'] = 'no_improving_plan'
    result.setdefault('stop_reason', '达到使用者设置的迭代轮数上限')
    result['selection_basis'] = '可行且技能改善的组合中，依次比较悲观情景四年就业人数、技能匹配度和较低成本；仅在已评估组合中比较'
    result['evaluation_limit'] = '预算、能力增益和情景参数是录入假设；不将模型推演解释为实际实施效果'
    return result
