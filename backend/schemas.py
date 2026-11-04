from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Account(Model):
    username: str = Field(min_length=3, max_length=60, pattern=r"^[a-zA-Z0-9_.@-]+$")
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    role: Literal["employer", "student", "university"]


class Login(Model):
    username: str
    password: str


class Requirement(Model):
    skill: str = Field(min_length=1, max_length=60)
    target: float = Field(default=3, ge=1, le=5)
    weight: float = Field(default=1, ge=0, le=100)
    mandatory: bool = False
    category: str = "专业能力"


class Question(Model):
    id: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=4000)
    kind: Literal["text", "voice", "scenario"] = "text"
    skill: str = Field(min_length=1, max_length=60)
    rubric: str = Field(min_length=1, max_length=4000)


class Hard(Model):
    majors: list[str] = Field(default_factory=list, max_length=30)
    schools: list[str] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=list, max_length=30)


class Job(Model):
    title: str = Field(min_length=1, max_length=120)
    industry: Literal["AI产品", "金融科技"]
    city: str = Field(min_length=1, max_length=40)
    work_mode: Literal["现场", "混合", "远程"] = "现场"
    salary_min: float = Field(ge=0, le=1000000)
    salary_max: float = Field(ge=0, le=1000000)
    capacity: int = Field(ge=1, le=10000)
    description: str = Field(min_length=1, max_length=30000)
    training_cost: float = Field(default=0, ge=0, le=1e8)
    mentor_hours: float = Field(default=0, ge=0, le=10000)
    requirements: list[Requirement] = Field(min_length=1, max_length=50)
    questions: list[Question] = Field(default_factory=list, max_length=30)
    hard: Hard = Field(default_factory=Hard)

    @model_validator(mode="after")
    def valid(self):
        if self.salary_min > self.salary_max:
            raise ValueError("薪资下限不能大于上限")
        names = [r.skill for r in self.requirements]
        if len(set(names)) != len(names) or not sum(r.weight for r in self.requirements):
            raise ValueError("技能不能重复，权重之和必须大于零")
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("题目标识不能重复")
        if any(q.skill not in names for q in self.questions):
            raise ValueError("测评技能必须属于岗位能力要求")
        return self


class Ability(Model):
    level: float = Field(ge=0, le=5)
    evidence: str = Field(default="", max_length=4000)


class Preferences(Model):
    salary_target: float = Field(default=0, ge=0, le=1000000)
    cities: list[str] = Field(default_factory=list, max_length=30)
    industries: list[str] = Field(default_factory=list, max_length=10)
    work_modes: list[str] = Field(default_factory=list, max_length=3)
    goals: list[str] = Field(default_factory=list, max_length=50)
    salary_hard: bool = False
    city_hard: bool = False
    weights: dict[str, float] = Field(default_factory=lambda: {"salary": 25, "city": 20, "industry": 20, "work_mode": 10, "development": 25})

    @model_validator(mode="after")
    def valid(self):
        from backend.matching import normalized
        normalized(self.weights)
        if set(self.weights) - {"salary", "city", "industry", "work_mode", "development"}:
            raise ValueError("未知偏好维度")
        return self


class LearningResources(Model):
    budget: float = Field(default=0, ge=0, le=1e8)
    study_hours: float = Field(default=0, ge=0, le=100000)
    months: float = Field(default=0, ge=0, le=120)


class Profile(Model):
    major: str = Field(default="", max_length=100)
    school_name: str = Field(default="", max_length=100)
    school_code: str = Field(default="", max_length=80)
    language: str = Field(default="", max_length=100)
    career: str = Field(default="", max_length=10000)
    experience: str = Field(default="", max_length=10000)
    abilities: dict[str, Ability] = Field(default_factory=dict, max_length=100)
    preferences: Preferences = Field(default_factory=Preferences)
    resources: LearningResources = Field(default_factory=LearningResources)


class Weights(Model):
    version: int = Field(ge=1)
    weights: dict[str, float] = Field(max_length=50)


class Apply(Model):
    job_id: str
    consent: Literal[True]
    document_ids: list[str] = Field(default_factory=list, max_length=20)
    portfolio_ids: list[str] = Field(default_factory=list, max_length=20)


class Answers(Model):
    job_version: int = Field(ge=1)
    answers: dict[str, str] = Field(max_length=30)
    audio_ids: list[str] = Field(default_factory=list, max_length=10)


class Review(Model):
    revision: str = Field(min_length=1, max_length=80)
    abilities: dict[str, Ability] = Field(max_length=50)
    background: dict[str, bool] = Field(default_factory=dict)


class Choice(Model):
    chosen: bool


class Budget(Model):
    salary: float = Field(ge=0, le=1e10)
    training: float = Field(ge=0, le=1e10)
    mentor: float = Field(ge=0, le=1e8)


class AgentRequest(Model):
    message: str = Field(min_length=1, max_length=12000)
    document_ids: list[str] = Field(default_factory=list, max_length=5)
    application_id: str | None = None
    job_id: str | None = None
    mode: Literal["chat", "job", "profile", "assessment", "curriculum"] = "chat"
    send_documents: bool = False


class Course(Model):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    cost: float = Field(ge=0, le=1e10)
    credits: float = Field(ge=0, le=1000)
    teacher_hours: float = Field(ge=0, le=100000)
    lab_hours: float = Field(ge=0, le=100000)
    study_hours: float = Field(ge=0, le=100000)
    months: float = Field(ge=0, le=120)
    gains: dict[str, float] = Field(max_length=100)


class Limits(Model):
    cost: float = Field(ge=0, le=1e10)
    credits: float = Field(ge=0, le=1000)
    teacher_hours: float = Field(ge=0, le=100000)
    lab_hours: float = Field(ge=0, le=100000)
    study_hours: float = Field(ge=0, le=100000)
    months: float = Field(ge=0, le=120)


class Optimize(Model):
    gaps: dict[str, float] = Field(max_length=100)
    weights: dict[str, float] = Field(max_length=100)
    courses: list[Course] = Field(max_length=100)
    limits: Limits


class ArchiveImport(Model):
    archive: str = Field(max_length=200)
    member: str = Field(max_length=1000)
