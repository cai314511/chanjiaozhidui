from typing import Literal

from pydantic import Field, model_validator

from backend.schemas import Model


class Source(Model):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(default="", max_length=1000)
    reference: str = Field(default="", max_length=500)
    collected_at: str
    method: Literal["official_bundle", "authorized_public", "internal_aggregate"]
    license_basis: str = Field(min_length=5, max_length=2000)
    research_permitted: bool
    contains_personal_data: bool
    redaction_reviewed: bool = False
    split: Literal["development", "evaluation"] = "development"
    scope: str = Field(min_length=1, max_length=500)


class Skill(Model):
    name: str = Field(min_length=1, max_length=100)
    level: float = Field(ge=1, le=5)
    weight: float = Field(default=1, gt=0, le=100)


class Recruitment(Model):
    record_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    industry: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    region: str = Field(min_length=1, max_length=100)
    month: str
    salary_min: float | None = Field(default=None, ge=0, le=1000000)
    salary_max: float | None = Field(default=None, ge=0, le=1000000)
    verified_headcount: int | None = Field(default=None, ge=0, le=1000000)
    headcount_evidence: str = Field(default="", max_length=1000)
    skills: list[Skill] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        from backend.governance import month
        self.month = month(self.month)
        if (self.salary_min is None) != (self.salary_max is None):
            raise ValueError("薪资必须同时给出上下限或同时缺失")
        if self.salary_min is not None and self.salary_min > self.salary_max:
            raise ValueError("薪资区间上下限顺序错误")
        if self.verified_headcount is not None and not self.headcount_evidence.strip():
            raise ValueError("核实招聘人数必须附人数口径与证据")
        if len({s.name for s in self.skills}) != len(self.skills):
            raise ValueError("同条招聘记录技能重复")
        return self


class Employment(Model):
    program_code: str = Field(min_length=1, max_length=100)
    year: int = Field(ge=1990, le=2100)
    graduates: int = Field(ge=5, le=1000000)
    employed: int = Field(ge=0)
    related_employed: int | None = Field(default=None, ge=0)
    average_salary: float | None = Field(default=None, ge=0, le=1000000)
    salary_sample: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid(self):
        if self.employed > self.graduates or self.related_employed is not None and self.related_employed > self.employed:
            raise ValueError("就业人数或对口人数超出统计范围")
        if self.salary_sample > self.employed:
            raise ValueError("薪资样本不能超过就业人数")
        if self.average_salary is not None and self.salary_sample < 5:
            raise ValueError("平均起薪至少需要5个匿名汇总样本")
        return self


class Policy(Model):
    title: str = Field(min_length=1, max_length=300)
    issuing_body: str = Field(min_length=1, max_length=200)
    month: str
    topic: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=30000)


class Dataset(Model):
    source_id: str
    kind: Literal["recruitment", "employment", "policy"]
    records: list[dict] = Field(min_length=1, max_length=20000)


class Observation(Model):
    level: float = Field(ge=0, le=5)
    sample_count: int = Field(ge=5)
    evidence: str = Field(min_length=1, max_length=1000)


class BaselineCourse(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    credits: float = Field(ge=0, le=100)
    hours: float = Field(ge=0, le=10000)
    category: Literal["general", "professional"]
    protected: bool = False
    teacher_hours: float = Field(ge=0, le=100000)
    lab_hours: float = Field(ge=0, le=100000)
    prerequisites: list[str] = Field(default_factory=list, max_length=100)


class ProgramConstraints(Model):
    credits_min: float = Field(ge=0, le=1000)
    credits_max: float = Field(ge=0, le=1000)
    hours_min: float = Field(ge=0, le=100000)
    hours_max: float = Field(ge=0, le=100000)
    general_credits_min: float = Field(ge=0, le=1000)
    professional_credits_min: float = Field(ge=0, le=1000)
    teacher_hours_max: float = Field(ge=0, le=1e8)
    lab_hours_max: float = Field(ge=0, le=1e8)
    budget: float = Field(ge=0, le=1e10)

    @model_validator(mode="after")
    def valid(self):
        if self.credits_min > self.credits_max or self.hours_min > self.hours_max:
            raise ValueError("培养方案约束上下限错误")
        return self


class Direction(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    job_category: str = Field(min_length=1, max_length=100)
    capacity: int = Field(ge=0, le=100000)
    min_grade: float = Field(ge=0, le=100)
    course_ids: list[str] = Field(min_length=1, max_length=100)


class CohortGroup(Model):
    id: str = Field(min_length=1, max_length=100)
    count: int = Field(ge=5, le=100000)
    grade: float = Field(ge=0, le=100, description='同意愿匿名分组的最低成绩或成绩分箱下界，不能以平均成绩代替资格条件')
    preferences: list[str] = Field(min_length=1, max_length=100)


class Program(Model):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    region: str = Field(min_length=1, max_length=100)
    current_seats: int = Field(ge=1, le=100000)
    completion_rate: float = Field(gt=0, le=1)
    pipeline_graduates: list[int] = Field(min_length=3, max_length=3)
    current_direction_counts: dict[str, int] = Field(min_length=1, max_length=100, description='岗位类别名称为键，不能使用方向ID')
    skills: dict[str, Observation] = Field(min_length=1, max_length=100)
    courses: list[BaselineCourse] = Field(min_length=1, max_length=200)
    constraints: ProgramConstraints
    directions: list[Direction] = Field(min_length=1, max_length=30)
    groups: list[CohortGroup] = Field(min_length=1, max_length=500)
    split_timing: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid(self):
        for values in (self.pipeline_graduates, list(self.current_direction_counts.values())):
            if any(v < 0 for v in values):
                raise ValueError("培养规模不能为负")
        if any(0 < v < 5 for v in self.current_direction_counts.values()):
            raise ValueError("方向汇总小于5人的单元请合并或省略")
        if sum(self.current_direction_counts.values()) <= 0:
            raise ValueError('当前培养方向人数合计必须大于零，不能用空规模计算方向差距')
        for values in ([c.id for c in self.courses], [d.id for d in self.directions], [d.job_category for d in self.directions], [g.id for g in self.groups]):
            if len(values) != len(set(values)):
                raise ValueError("课程、方向、岗位对应或匿名分组标识重复")
        ids = {d.id for d in self.directions}
        categories = {d.job_category for d in self.directions}
        if any(key in ids and key not in categories for key in self.current_direction_counts):
            raise ValueError('当前培养方向人数必须按岗位类别名称填写，不能使用方向ID')
        if any(set(g.preferences) - ids or len(g.preferences) != len(set(g.preferences)) for g in self.groups):
            raise ValueError("分组意愿包含未知或重复方向")
        return self


class Action(Model):
    id: str = Field(min_length=1, max_length=100)
    kind: Literal["add", "delete", "modify", "merge"]
    reason: str = Field(min_length=1, max_length=2000)
    remove_ids: list[str] = Field(default_factory=list, max_length=30)
    add_courses: list[BaselineCourse] = Field(default_factory=list, max_length=30)
    cost: float = Field(ge=0, le=1e10)
    skill_delta: dict[str, float] = Field(max_length=100)
    evidence: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def valid(self):
        if any(not -5 <= value <= 5 for value in self.skill_delta.values()):
            raise ValueError("能力变化范围为-5至5")
        valid_shape = {'add': not self.remove_ids and bool(self.add_courses),
                       'delete': bool(self.remove_ids) and not self.add_courses,
                       'modify': len(self.remove_ids) == len(self.add_courses) == 1,
                       'merge': len(self.remove_ids) >= 2 and len(self.add_courses) == 1}
        if not valid_shape[self.kind] or len(self.remove_ids) != len(set(self.remove_ids)):
            raise ValueError("课程动作的移除和新增结构不符合动作类型")
        return self


class AdmissionsPolicy(Model):
    target_rate: float = Field(default=.85, gt=0, le=1)
    deadband: float = Field(default=.03, ge=0, le=.2)
    gain: float = Field(default=.5, gt=0, le=2)
    max_change: float = Field(default=.1, gt=0, le=.3)
    min_seats: int = Field(ge=1)
    max_seats: int = Field(ge=1)
    cycle_years: int = Field(default=1, ge=1, le=4)

    @model_validator(mode="after")
    def valid(self):
        if self.min_seats > self.max_seats:
            raise ValueError("招生上下限错误")
        return self


class Scenario(Model):
    name: Literal["乐观", "基准", "悲观"]
    demand_growth: float = Field(ge=-.5, le=.5)
    salary_growth: float = Field(ge=-.3, le=.3)
    skill_gain_factor: float = Field(ge=0, le=1.5)
    probability: float = Field(ge=0, le=1)


class DecisionCase(Model):
    title: str = Field(min_length=1, max_length=200)
    recruitment_id: str
    employment_id: str | None = None
    policy_ids: list[str] = Field(default_factory=list, max_length=20)
    program: Program
    actions: list[Action] = Field(max_length=50)
    admissions: AdmissionsPolicy
    scenarios: list[Scenario] = Field(min_length=3, max_length=3)
    skill_employment_elasticity: float = Field(default=0, ge=0, le=1)
    skill_salary_elasticity: float = Field(default=0, ge=0, le=1)
    implementation_lag: int = Field(default=4, ge=1, le=4)
    assumptions: str = Field(min_length=5, max_length=5000)
    market_scope_confirmed: bool = False
    annual_demand_confirmed: bool = False
    max_rounds: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def valid(self):
        if {s.name for s in self.scenarios} != {'乐观', '基准', '悲观'} or abs(sum(s.probability for s in self.scenarios) - 1) > 1e-8:
            raise ValueError("必须包含三种不同情景，主观情景概率之和为1")
        if not self.admissions.min_seats <= self.program.current_seats <= self.admissions.max_seats:
            raise ValueError("当前招生规模超出控制器上下限")
        if len({a.id for a in self.actions}) != len(self.actions):
            raise ValueError("课程动作标识重复")
        return self
