import pytest

from backend.decision import admissions_step, direction_gap, split_students, validate_program, wilson_interval


def test_direction_gap_is_zero_for_same_distribution():
    assert direction_gap({'产品': 60, '数据': 40}, {'产品': 30, '数据': 20}) == 0
    assert direction_gap({'产品': 100}, {'数据': 100}) == 1


def test_feedback_deadband_and_bounded_adjustment():
    policy = {'target_rate': .85, 'deadband': .03, 'gain': 1, 'max_change': .1, 'min_seats': 50, 'max_seats': 200}
    assert admissions_step(100, .86, policy) == 100
    assert admissions_step(100, .5, policy) == 90
    assert admissions_step(50, .5, policy) == 50
    assert admissions_step(200, 1, policy) == 200


def test_wilson_interval_uses_real_sample_size():
    lo, hi = wilson_interval(80, 100)
    assert lo == pytest.approx(.7112, abs=.0001)
    assert hi == pytest.approx(.8666, abs=.0001)


def test_split_respects_grades_capacity_and_preferences():
    directions = [{'id': 'a', 'name': '产品', 'job_category': '产品经理', 'capacity': 5, 'min_grade': 70, 'course_ids': ['c']},
                  {'id': 'b', 'name': '数据', 'job_category': '数据分析师', 'capacity': 5, 'min_grade': 80, 'course_ids': ['c']}]
    groups = [{'id': 'g1', 'count': 5, 'grade': 85, 'preferences': ['a', 'b']},
              {'id': 'g2', 'count': 5, 'grade': 75, 'preferences': ['a']}]
    result = split_students(directions, groups)
    assert result['allocated'] == 10
    assert result['direction_counts'] == {'a': 5, 'b': 5}


def test_protected_course_and_credit_requirements_fail_fast():
    program = {'courses': [{'id': 'c', 'name': '必修课程', 'credits': 3, 'hours': 48, 'category': 'professional',
                             'protected': True, 'teacher_hours': 48, 'lab_hours': 0, 'prerequisites': []}],
               'constraints': {'credits_min': 3, 'credits_max': 5, 'hours_min': 48, 'hours_max': 80,
                               'general_credits_min': 0, 'professional_credits_min': 3,
                               'teacher_hours_max': 80, 'lab_hours_max': 40, 'budget': 1000}}
    result = validate_program(program, [{'id': 'del', 'kind': 'delete', 'remove_ids': ['c'], 'add_courses': [], 'cost': 0, 'skill_delta': {}}])
    assert result['feasible'] is False
    assert any('受保护' in error for error in result['violations'])


def test_small_enrollment_cannot_exceed_percentage_limit_by_rounding():
    policy = {'target_rate': .85, 'deadband': .03, 'gain': 1, 'max_change': .1, 'min_seats': 1, 'max_seats': 100}
    assert admissions_step(5, .1, policy) == 5


def decision_input():
    # 仅用于隔离单元测试，不作为官方数据或产品预置结果。
    from backend.competition_schemas import DecisionCase
    course = {'id': 'c', 'name': '基础课程', 'credits': 3, 'hours': 48, 'category': 'professional',
              'protected': True, 'teacher_hours': 48, 'lab_hours': 0, 'prerequisites': []}
    case = {'title': '隔离测试决策', 'recruitment_id': 'test', 'employment_id': 'employment',
            'program': {'code': 'test-code', 'name': '测试专业', 'region': '北京', 'current_seats': 100,
                        'completion_rate': 1, 'pipeline_graduates': [100, 100, 100],
                        'current_direction_counts': {'产品经理': 100},
                        'skills': {'产品设计': {'level': 2, 'sample_count': 100, 'evidence': '隔离测试能力评估'}},
                        'courses': [course], 'constraints': {'credits_min': 3, 'credits_max': 8, 'hours_min': 48,
                        'hours_max': 120, 'general_credits_min': 0, 'professional_credits_min': 3,
                        'teacher_hours_max': 120, 'lab_hours_max': 50, 'budget': 10000},
                        'directions': [{'id': 'd', 'name': '产品方向', 'job_category': '产品经理', 'capacity': 100,
                                        'min_grade': 60, 'course_ids': ['c']}],
                        'groups': [{'id': 'g', 'count': 100, 'grade': 80, 'preferences': ['d']}], 'split_timing': '大二第二学期'},
            'actions': [{'id': 'a', 'kind': 'add', 'reason': '填补能力缺口', 'remove_ids': [],
                         'add_courses': [{**course, 'id': 'new', 'name': '产品实践', 'protected': False, 'credits': 2, 'hours': 32, 'teacher_hours': 32, 'lab_hours': 20}],
                         'cost': 5000, 'skill_delta': {'产品设计': 2}, 'evidence': '课程目标的测试假设'}],
            'admissions': {'min_seats': 80, 'max_seats': 120},
            'scenarios': [{'name': name, 'demand_growth': growth, 'salary_growth': growth,
                           'skill_gain_factor': factor, 'probability': probability}
                          for name, growth, factor, probability in [('乐观', .05, 1.1, .2), ('基准', 0, 1, .6), ('悲观', -.05, .7, .2)]],
            'assumptions': '隔离测试的已知结构输入，所有系数为测试假设', 'market_scope_confirmed': True, 'annual_demand_confirmed': True,
            'skill_employment_elasticity': .2, 'implementation_lag': 4}
    recruitment = [{'record_id': 'j', 'title': '测试岗位', 'category': '产品经理', 'region': '北京',
                    'industry': 'AI产品', 'month': '2026-10', 'verified_headcount': 120,
                    'headcount_evidence': '测试口径', 'skills': [{'name': '产品设计', 'level': 4, 'weight': 1}]}]
    employment = [{'program_code': 'test-code', 'year': 2025, 'graduates': 100, 'employed': 80,
                   'average_salary': 10000, 'salary_sample': 80}]
    return DecisionCase.model_validate(case).model_dump(), recruitment, employment


def test_four_year_delay_and_counterfactual_are_computed():
    from backend.decision import run_decision
    case, recruitment, employment = decision_input()
    result = run_decision(case, recruitment, employment)
    assert result['best']['action_ids'] == ['a']
    base = next(s for s in result['best']['forecast']['scenarios'] if s['name'] == '基准')
    assert base['adjustment']['years'][0]['employment_rate'] == base['no_adjustment']['years'][0]['employment_rate']
    assert base['adjustment']['years'][3]['skill_match'] == 100
    assert base['four_year_change']['employment_rate'] == pytest.approx(.1)
    assert len(result['best']['risks']) >= 3
    assert result['rounds'][0]['reflection']


def test_missing_headcount_does_not_turn_postings_into_people():
    from backend.decision import run_decision
    case, recruitment, employment = decision_input()
    recruitment[0]['verified_headcount'] = None
    result = run_decision(case, recruitment, employment)
    assert result['diagnosis']['scale'] is None
    assert result['best']['forecast']['status'] == 'incomplete'
    assert result['status'] == 'partial'


def test_historical_headcounts_not_added_to_current_demand():
    from backend.decision import run_decision
    case, recruitment, employment = decision_input()
    recruitment.append({**recruitment[0], 'record_id': 'older', 'month': '2020-10'})
    result = run_decision(case, recruitment, employment)
    assert result['diagnosis']['demand']['verified_headcount'] == 120
    assert result['diagnosis']['scale']['supply_minus_demand'] == -20


def test_direction_id_cannot_be_mistaken_for_job_category():
    from backend.competition_schemas import DecisionCase
    case, _, _ = decision_input()
    case['program']['current_direction_counts'] = {'d': 100}
    with pytest.raises(ValueError):
        DecisionCase.model_validate(case)


def test_unconfirmed_market_scope_does_not_produce_scale_gap():
    from backend.decision import run_decision
    case, recruitment, employment = decision_input()
    case['market_scope_confirmed'] = False
    result = run_decision(case, recruitment, employment)
    assert result['diagnosis']['scale'] is None
    assert result['best']['forecast']['status'] == 'incomplete'


def test_admissions_forecast_obeys_direction_and_resource_capacity():
    from backend.decision import run_decision
    case, recruitment, employment = decision_input()
    result = run_decision(case, recruitment, employment)
    forecast = result['best']['forecast']
    assert forecast['supported_admissions_max'] == 100
    for scenario in forecast['scenarios']:
        assert max(scenario['adjustment']['stability']['last_six_intakes']) <= 100
        assert scenario['adjustment']['stability']['bounded']
