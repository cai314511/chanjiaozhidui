import math

import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from backend.solver import milp


RESOURCES = ("cost", "credits", "teacher_hours", "lab_hours", "study_hours")


def number(value, minimum=0, maximum=float("inf")):
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError("数值超出范围或包含非有限数值")
    return result


def normalized(weights):
    values = {key: number(value) for key, value in weights.items()}
    total = sum(values.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("至少保留一项正权重")
    return {key: value / total for key, value in values.items()}


def ability_score(requirements, abilities):
    if not requirements or len({r["skill"] for r in requirements}) != len(requirements):
        raise ValueError("能力要求不能为空或重复")
    weights = normalized({r["skill"]: r["weight"] for r in requirements})
    lower = upper = provisional = coverage = 0.0
    rows = []
    for requirement in requirements:
        skill = requirement["skill"]
        target = number(requirement["target"], 1, 5)
        observation = abilities.get(skill, {})
        level = observation.get("level")
        utility = min(1, number(level, 0, 5) / target) if level is not None else 0
        verified = observation.get("verified") is True and level is not None
        weight = weights[skill]
        lo, hi = (utility, utility) if verified else (0, 1)
        lower += weight * lo
        upper += weight * hi
        provisional += weight * utility
        coverage += weight * int(verified)
        rows.append({"skill": skill, "target": target, "level": level,
                     "weight": round(weight, 8), "raw_weight": requirement["weight"],
                     "verified": verified, "contribution": round(100 * weight * lo, 4),
                     "gap": round(max(0, target - float(level)), 4) if level is not None else None,
                     "evidence": observation.get("evidence", ""),
                     "source": observation.get("source", "自述 / 待核实")})
    return {"lower": round(lower * 100, 4), "upper": round(upper * 100, 4),
            "provisional": round(provisional * 100, 4), "coverage": round(coverage * 100, 4),
            "details": rows, "model": "matching-1"}


def bilateral(employer, student):
    employer, student = number(employer, 0, 100), number(student, 0, 100)
    return round(2 * employer * student / (employer + student), 4) if employer + student else 0


def preference_score(job, preferences):
    target = number(preferences.get("salary_target", 0))
    goals = preferences.get("goals", [])
    offered = {r["skill"] for r in job.get("requirements", [])}
    utilities = {
        "salary": min(1, number(job["salary_max"]) / target) if target else 1,
        "city": float(not preferences.get("cities") or job["city"] in preferences["cities"]),
        "industry": float(not preferences.get("industries") or job["industry"] in preferences["industries"]),
        "work_mode": float(not preferences.get("work_modes") or job["work_mode"] in preferences["work_modes"]),
        "development": len(set(goals) & offered) / len(set(goals)) if goals else 1,
    }
    weights = normalized(preferences.get("weights", {key: 1 for key in utilities}))
    if set(weights) - set(utilities):
        raise ValueError("未知偏好维度")
    return {"score": round(100 * sum(weights[k] * utilities[k] for k in weights), 4),
            "details": [{"dimension": k, "weight": weights[k], "utility": utilities[k]}
                        for k in weights]}


def hard_gates(job, profile, abilities, verified_background=None):
    gates = []
    background = verified_background or {}
    for field, label in (("majors", "专业"), ("schools", "院校"), ("languages", "语言")):
        allowed = job.get("hard", {}).get(field, [])
        if not allowed:
            continue
        actual = profile.get({"majors": "major", "schools": "school_name", "languages": "language"}[field], "")
        state = "pass" if actual in allowed else "fail" if actual else "pending"
        if state == "pass" and not background.get(field):
            state = "pending"
        gates.append({"label": label, "status": state, "required": allowed, "actual": actual})
    for req in job["requirements"]:
        if req.get("mandatory"):
            obs = abilities.get(req["skill"], {})
            state = "pending"
            if obs.get("verified") and obs.get("level") is not None:
                state = "pass" if obs["level"] >= req["target"] else "fail"
            gates.append({"label": req["skill"], "status": state, "required": req["target"],
                          "actual": obs.get("level")})
    prefs = profile.get("preferences", {})
    if prefs.get("salary_hard"):
        gates.append({"label": "学生薪资底线", "status": "pass" if job["salary_max"] >= prefs.get("salary_target", 0) else "fail"})
    if prefs.get("city_hard") and prefs.get("cities"):
        gates.append({"label": "学生城市要求", "status": "pass" if job["city"] in prefs["cities"] else "fail"})
    return gates


def match(job, profile, assessments=None):
    abilities = {k: {**v, "verified": False} for k, v in profile.get("abilities", {}).items()}
    background = {}
    for assessment in assessments or []:
        if assessment.get("reviewed"):
            abilities.update({k: {**v, "verified": True, "source": "企业已复核测评"}
                              for k, v in assessment.get("abilities", {}).items()})
            background.update(assessment.get("background", {}))
    employer = ability_score(job["requirements"], abilities)
    student = preference_score(job, profile.get("preferences", {}))
    gates = hard_gates(job, profile, abilities, background)
    complete = all(d["verified"] for d in employer["details"] if d["raw_weight"] > 0)
    status = "excluded" if any(g["status"] == "fail" for g in gates) else "pending" if any(g["status"] == "pending" for g in gates) or not complete else "eligible"
    sensitivity = []
    for row in employer["details"]:
        changed = [{**r, "weight": r["weight"] + sum(x["weight"] for x in job["requirements"]) * .1}
                   if r["skill"] == row["skill"] else r for r in job["requirements"]]
        sensitivity.append({"skill": row["skill"], "delta": round(ability_score(changed, abilities)["provisional"] - employer["provisional"], 4)})
    return {"employer": employer, "student": student, "gates": gates, "status": status,
            "lower": bilateral(employer["lower"], student["score"]),
            "upper": bilateral(employer["upper"], student["score"]),
            "provisional": bilateral(employer["provisional"], student["score"]),
            "weight_version": job.get("version", 1), "sensitivity": sensitivity}


def optimize_courses(gaps, weights, courses, limits):
    if not gaps or not courses:
        return {"selected": [], "benefit": 0, "used": {k: 0 for k in RESOURCES}, "remaining": gaps}
    if len(courses) > 100 or len(gaps) > 100:
        raise ValueError("单次优化最多100个方案和100项技能")
    if len({c["id"] for c in courses}) != len(courses):
        raise ValueError("方案标识重复")
    skills = list(gaps)
    n, m = len(courses), len(skills)
    gap = np.array([number(gaps[s], 0, 5) for s in skills])
    objective = np.array([0.0] * n + [-number(weights.get(s, 1)) for s in skills])
    if not any(objective):
        raise ValueError("收益权重不能全部为零")
    upper = np.concatenate([np.ones(n), gap])
    for j, course in enumerate(courses):
        if number(course["months"]) > number(limits["months"]):
            upper[j] = 0
        for value in course["gains"].values():
            number(value, 0, 5)
    rows, bounds = [], []
    for resource in RESOURCES:
        rows.append([number(c[resource]) for c in courses] + [0] * m)
        bounds.append(number(limits[resource]))
    for i, skill in enumerate(skills):
        row = [-number(c["gains"].get(skill, 0), 0, 5) for c in courses] + [0] * m
        row[n + i] = 1
        rows.append(row)
        bounds.append(0)
    result = milp(objective, integrality=[1] * n + [0] * m,
                  bounds=Bounds(np.zeros(n + m), upper),
                  constraints=LinearConstraint(np.array(rows), -np.inf, np.array(bounds)),
                  options={"time_limit": 10})
    if not result.success:
        raise ValueError("资源优化未完成：" + result.message)
    selected = [c for j, c in enumerate(courses) if result.x[j] > .5]
    remaining = {s: round(max(0, gaps[s] - sum(c["gains"].get(s, 0) for c in selected)), 4) for s in skills}
    return {"selected": [c["id"] for c in selected], "benefit": round(-result.fun, 4),
            "used": {k: sum(c[k] for c in selected) for k in RESOURCES}, "remaining": remaining,
            "assumption": "方案增益与成本为录入的情景假设"}


def allocate(pairs, jobs, budget):
    pairs = [p for p in pairs if p["status"] == "eligible" and p.get("mutual")]
    if not pairs:
        return {"selected": [], "used": {"salary": 0, "training": 0, "mentor": 0}}
    if len(pairs) > 2000:
        raise ValueError("单次分配最多2000个候选对")
    rows, upper = [], []
    for student in {p["student_id"] for p in pairs}:
        rows.append([int(p["student_id"] == student) for p in pairs])
        upper.append(1)
    for job_id, job in jobs.items():
        rows.append([int(p["job_id"] == job_id) for p in pairs])
        upper.append(number(job["capacity"], 0))
    used_vectors = {}
    for key, field in (("salary", "salary_max"), ("training", "training_cost"), ("mentor", "mentor_hours")):
        vector = [number(jobs[p["job_id"]][field]) for p in pairs]
        rows.append(vector)
        upper.append(number(budget[key]))
        used_vectors[key] = vector
    scores = [number(p["lower"], 0, 100) for p in pairs]
    result = milp(-np.array(scores), integrality=np.ones(len(pairs)),
                  bounds=Bounds(0, 1), constraints=LinearConstraint(np.array(rows), -np.inf, np.array(upper)),
                  options={"time_limit": 10})
    if not result.success:
        raise ValueError("招聘分配未完成：" + result.message)
    indices = [i for i, x in enumerate(result.x) if x > .5]
    return {"selected": [pairs[i]["application_id"] for i in indices],
            "used": {k: sum(v[i] for i in indices) for k, v in used_vectors.items()}}
