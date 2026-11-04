import math

import pytest

from backend.matching import ability_score, allocate, bilateral, match, optimize_courses, preference_score


def test_weights_reverse_candidate_order():
    requirements = [{"skill": "产品设计", "target": 5, "weight": 80},
                    {"skill": "Python", "target": 5, "weight": 20}]
    first = {"产品设计": {"level": 5, "verified": True}, "Python": {"level": 1, "verified": True}}
    second = {"产品设计": {"level": 1, "verified": True}, "Python": {"level": 5, "verified": True}}
    assert ability_score(requirements, first)["lower"] == 84
    assert ability_score(requirements, second)["lower"] == 36
    requirements[0]["weight"], requirements[1]["weight"] = 20, 80
    assert ability_score(requirements, first)["lower"] == 36
    assert ability_score(requirements, second)["lower"] == 84


def test_unknown_evidence_is_interval_not_certified_full_score():
    result = ability_score([{"skill": "责任感", "target": 4, "weight": 10}],
                           {"责任感": {"level": 5, "verified": False}})
    assert result["lower"] == 0
    assert result["upper"] == 100
    assert result["coverage"] == 0
    assert result["provisional"] == 100


def test_surplus_cannot_cancel_gap():
    result = ability_score([{"skill": "A", "target": 2, "weight": 1},
                            {"skill": "B", "target": 5, "weight": 1}],
                           {"A": {"level": 5, "verified": True}, "B": {"level": 1, "verified": True}})
    assert result["lower"] == 60


@pytest.mark.parametrize("weight", [-1, math.nan, math.inf])
def test_invalid_weight_rejected(weight):
    with pytest.raises(ValueError):
        ability_score([{"skill": "A", "target": 3, "weight": weight}], {})


def test_zero_sum_rejected():
    with pytest.raises(ValueError):
        ability_score([{"skill": "A", "target": 3, "weight": 0}], {})


def test_duplicate_skills_rejected():
    with pytest.raises(ValueError):
        ability_score([{"skill": "A", "target": 3, "weight": 1}] * 2, {})


def test_bilateral_penalizes_one_sided_match():
    assert bilateral(100, 25) == 40
    assert bilateral(0, 0) == 0


def test_student_preferences_are_independent():
    job = {"salary_max": 12000, "city": "北京", "industry": "AI产品", "work_mode": "现场",
           "requirements": [{"skill": "产品设计"}]}
    prefs = {"salary_target": 24000, "cities": ["上海"], "industries": ["AI产品"],
             "work_modes": [], "goals": [], "weights": {"salary": 2, "city": 1}}
    result = preference_score(job, prefs)
    assert result["score"] == pytest.approx(100 / 3, abs=0.01)


def test_course_optimizer_respects_all_resources_and_saturates_gain():
    courses = [
        {"id": "a", "name": "产品实训", "cost": 10, "credits": 2, "teacher_hours": 3,
         "lab_hours": 1, "study_hours": 4, "months": 2, "gains": {"产品": 2}},
        {"id": "b", "name": "产品项目", "cost": 10, "credits": 2, "teacher_hours": 3,
         "lab_hours": 1, "study_hours": 4, "months": 2, "gains": {"产品": 2}},
        {"id": "c", "name": "数据实践", "cost": 10, "credits": 2, "teacher_hours": 3,
         "lab_hours": 1, "study_hours": 4, "months": 2, "gains": {"数据": 1}},
    ]
    limits = {"cost": 20, "credits": 4, "teacher_hours": 6, "lab_hours": 2,
              "study_hours": 8, "months": 2}
    result = optimize_courses({"产品": 2, "数据": 1}, {"产品": 1, "数据": 1}, courses, limits)
    assert len(result["selected"]) == 2
    assert "c" in result["selected"]
    assert result["benefit"] == 3
    assert result["used"]["cost"] == 20


def test_course_exceeding_deadline_excluded():
    course = {"id": "a", "name": "长期课程", "cost": 0, "credits": 0, "teacher_hours": 0,
              "lab_hours": 0, "study_hours": 0, "months": 5, "gains": {"A": 1}}
    result = optimize_courses({"A": 1}, {"A": 1}, [course],
                              {"cost": 0, "credits": 0, "teacher_hours": 0, "lab_hours": 0,
                               "study_hours": 0, "months": 2})
    assert result["selected"] == []


def test_zero_weight_does_not_hide_mandatory_failure():
    job = {'salary_max': 10000, 'city': '北京', 'industry': 'AI产品', 'work_mode': '现场',
           'requirements': [{'skill': '合规', 'target': 4, 'weight': 0, 'mandatory': True},
                            {'skill': '产品', 'target': 5, 'weight': 100}], 'hard': {}}
    review = {'reviewed': True, 'abilities': {'合规': {'level': 1}, '产品': {'level': 5}}}
    result = match(job, {'preferences': {}}, [review])
    assert result['employer']['lower'] == 100
    assert result['status'] == 'excluded'


def test_weight_scale_invariance():
    abilities = {'A': {'level': 2, 'verified': True}, 'B': {'level': 4, 'verified': True}}
    one = ability_score([{'skill': 'A', 'target': 4, 'weight': 3}, {'skill': 'B', 'target': 4, 'weight': 1}], abilities)
    two = ability_score([{'skill': 'A', 'target': 4, 'weight': 30}, {'skill': 'B', 'target': 4, 'weight': 10}], abilities)
    assert one['lower'] == two['lower'] == 62.5


def test_recruitment_optimizer_obeys_student_capacity_and_budget():
    jobs = {'a': {'capacity': 1, 'salary_max': 10, 'training_cost': 3, 'mentor_hours': 2},
            'b': {'capacity': 1, 'salary_max': 10, 'training_cost': 3, 'mentor_hours': 2}}
    pairs = [{'application_id': 'one', 'student_id': 's1', 'job_id': 'a', 'lower': 90, 'status': 'eligible', 'mutual': True},
             {'application_id': 'two', 'student_id': 's1', 'job_id': 'b', 'lower': 80, 'status': 'eligible', 'mutual': True},
             {'application_id': 'three', 'student_id': 's2', 'job_id': 'b', 'lower': 70, 'status': 'eligible', 'mutual': True},
             {'application_id': 'four', 'student_id': 's3', 'job_id': 'b', 'lower': 100, 'status': 'pending', 'mutual': True}]
    result = allocate(pairs, jobs, {'salary': 20, 'training': 6, 'mentor': 4})
    assert set(result['selected']) == {'one', 'three'}
    result = allocate(pairs, jobs, {'salary': 10, 'training': 6, 'mentor': 4})
    assert result['selected'] == ['one']


def test_tiny_positive_weight_still_requires_verified_evidence():
    job = {'salary_max': 10000, 'city': '北京', 'industry': 'AI产品', 'work_mode': '现场',
           'requirements': [{'skill': 'A', 'target': 4, 'weight': 100},
                            {'skill': 'B', 'target': 4, 'weight': 0.000001}]}
    result = match(job, {'preferences': {}}, [{'reviewed': True, 'abilities': {'A': {'level': 4}}}])
    assert result['status'] == 'pending'
