from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def system():
    root = Path(__file__).resolve().parents[1] / "runtime" / "tests"
    root.mkdir(parents=True, exist_ok=True)
    import uuid
    folder = root / uuid.uuid4().hex
    folder.mkdir()
    app = create_app(folder)
    return app


def account(app, role, name):
    client = TestClient(app)
    response = client.post("/api/auth/register", json={"username": name, "password": "test-password-123",
                           "name": name, "role": role})
    assert response.status_code == 200, response.text
    return client


def job_data():
    return {"title": "AI产品经理", "industry": "AI产品", "city": "北京", "work_mode": "现场",
            "salary_min": 10000, "salary_max": 20000, "capacity": 1, "description": "负责产品设计与数据分析",
            "requirements": [{"skill": "产品设计", "target": 4, "weight": 80, "mandatory": False},
                             {"skill": "数据分析", "target": 4, "weight": 20, "mandatory": False}],
            "hard": {"majors": [], "schools": [], "languages": []},
            "training_cost": 1000, "mentor_hours": 10, "questions": []}


def test_profile_access_and_role_enforced(system):
    employer = account(system, "employer", "enterprise-one")
    student = account(system, "student", "student-one")
    assert employer.put("/api/profile", json={"major": "经济学"}).status_code == 403
    assert student.post("/api/jobs", json=job_data()).status_code == 403
    assert TestClient(system).get("/api/profile").status_code == 401


def test_weight_versions_preview_and_ownership(system):
    first = account(system, "employer", "employer-first")
    second = account(system, "employer", "employer-second")
    created = first.post("/api/jobs", json=job_data()).json()
    ident = created["id"]
    payload = {"version": 1, "weights": {"产品设计": 20, "数据分析": 80}}
    assert second.put(f"/api/jobs/{ident}/weights", json=payload).status_code == 403
    result = first.put(f"/api/jobs/{ident}/weights", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2
    assert first.put(f"/api/jobs/{ident}/weights", json=payload).status_code == 409
    assert len(first.get(f"/api/jobs/{ident}/versions").json()) == 2


def test_application_consent_revoked_immediately(system):
    employer = account(system, "employer", "company-consent")
    outsider = account(system, "employer", "company-outsider")
    student = account(system, "student", "student-consent")
    student.put("/api/profile", json={"major": "经济学", "abilities": {"产品设计": {"level": 4}}})
    ident = employer.post("/api/jobs", json=job_data()).json()["id"]
    assert student.post("/api/applications", json={"job_id": ident, "consent": False}).status_code == 422
    application = student.post("/api/applications", json={"job_id": ident, "consent": True}).json()
    aid = application["id"]
    assert outsider.get(f"/api/applications/{aid}").status_code == 403
    assert employer.get(f"/api/applications/{aid}").json()["profile"]["major"] == "经济学"
    assert student.post(f"/api/applications/{aid}/withdraw").status_code == 200
    assert employer.get(f"/api/applications/{aid}").status_code == 403


def test_university_cannot_read_individual_material(system):
    university = account(system, "university", "school-test")
    student = account(system, "student", "student-private")
    doc = student.post("/api/documents", files={"file": ("career.txt", "职业规划：AI产品".encode(), "text/plain")})
    assert doc.status_code == 200, doc.text
    ident = doc.json()["id"]
    assert university.get(f"/api/documents/{ident}").status_code == 403
    assert university.get("/api/university/insights").json()["suppressed"] is True


def test_review_creates_verified_scores_and_hard_gate(system):
    employer = account(system, "employer", "company-review")
    student = account(system, "student", "student-review")
    spec = job_data()
    spec["requirements"][0]["mandatory"] = True
    spec["questions"] = [{"id": "q1", "title": "设计产品验证方案", "kind": "scenario",
                           "skill": "产品设计", "rubric": "根据用户研究、指标和验证方法评分"}]
    jid = employer.post("/api/jobs", json=spec).json()["id"]
    aid = student.post("/api/applications", json={"job_id": jid, "consent": True}).json()["id"]
    student.post(f"/api/applications/{aid}/answers", json={"job_version": 1, "answers": {"q1": "先访谈用户，再设计可验证指标"}})
    revision = employer.get(f'/api/applications/{aid}').json()['revision']
    bad = employer.post(f"/api/applications/{aid}/review", json={"revision": revision, "abilities": {"产品设计": {"level": 5}}, "background": {}})
    assert bad.status_code == 422
    response = employer.post(f"/api/applications/{aid}/review", json={"revision": revision, "abilities": {
        "产品设计": {"level": 2, "evidence": "q1：提出访谈但缺少指标定义"}}, "background": {}})
    assert response.status_code == 200, response.text
    assert employer.get(f"/api/applications/{aid}").json()["match"]["status"] == "excluded"


def test_no_account_leak_and_bad_numbers_rejected(system):
    employer = account(system, "employer", "company-numeric")
    spec = job_data()
    spec["requirements"][0]["weight"] = -1
    assert employer.post("/api/jobs", json=spec).status_code == 422
    spec = job_data()
    spec["salary_max"] = 100
    assert employer.post("/api/jobs", json=spec).status_code == 422
    assert "password" not in str(employer.get("/api/auth/me").json())


def test_job_edit_versions_and_conflict(system):
    employer = account(system, "employer", "company-edit")
    outsider = account(system, "employer", "company-other")
    data = job_data()
    jid = employer.post('/api/jobs', json=data).json()['id']
    data['description'] = '更新工作内容与培养目标'
    assert outsider.put(f'/api/jobs/{jid}?version=1', json=data).status_code == 403
    response = employer.put(f'/api/jobs/{jid}?version=1', json=data)
    assert response.status_code == 200, response.text
    assert response.json()['version'] == 2
    assert employer.put(f'/api/jobs/{jid}?version=1', json=data).status_code == 409


def test_corrupt_document_returns_actionable_error(system):
    student = account(system, 'student', 'corrupt-document')
    response = student.post('/api/documents', files={'file': ('bad.docx', b'not-a-docx', 'application/octet-stream')})
    assert response.status_code == 422


def test_school_code_not_shared_and_profile_change_invalidates_review(system):
    university = account(system, 'university', 'university-code')
    code = university.get('/api/auth/me').json()['school_code']
    employer = account(system, 'employer', 'company-code')
    student = account(system, 'student', 'student-code')
    assert student.put('/api/profile', json={'major': '经济学', 'school_code': code}).status_code == 200
    data = job_data()
    data['questions'] = [{'id': 'q1', 'title': '给出设计方案', 'kind': 'text', 'skill': '产品设计', 'rubric': '按验证方案评价'}]
    jid = employer.post('/api/jobs', json=data).json()['id']
    aid = student.post('/api/applications', json={'job_id': jid, 'consent': True}).json()['id']
    shared = employer.get(f'/api/applications/{aid}').json()
    assert 'school_code' not in shared['profile']
    student.post(f'/api/applications/{aid}/answers', json={'job_version': 1, 'answers': {'q1': '给出用户研究和验证方案'}})
    revision = employer.get(f'/api/applications/{aid}').json()['revision']
    response = employer.post(f'/api/applications/{aid}/review', json={'revision': revision, 'abilities': {'产品设计': {'level': 4, 'evidence': 'q1：包含研究与验证'}}})
    assert response.status_code == 200
    reviewed = employer.get(f'/api/applications/{aid}').json()
    assert reviewed['review']['abilities']['产品设计']['level'] == 4
    assert 'employer' not in reviewed['match']
    student.put('/api/profile', json={'major': '金融学', 'school_code': code})
    assert employer.get(f'/api/applications/{aid}').json()['review'] is None


def test_school_aggregation_requires_five_per_skill(system):
    university = account(system, 'university', 'school-aggregate')
    code = university.get('/api/auth/me').json()['school_code']
    employer = account(system, 'employer', 'company-aggregate')
    employer.post('/api/jobs', json=job_data())
    for index in range(5):
        student = account(system, 'student', f'aggregate-{index}')
        student.put('/api/profile', json={'major': '经济学', 'school_code': code,
                    'abilities': {'产品设计': {'level': 2}, **({'数据分析': {'level': 3}} if index < 4 else {})}})
    result = university.get('/api/university/insights').json()
    assert result['suppressed'] is False
    assert [row['skill'] for row in result['skills']] == ['产品设计']
    assert result['skills'][0]['gap'] == 2
    assert all('owner' not in row for row in result['skills'])


def test_agent_history_respects_revoked_source_authorization(system):
    employer = account(system, 'employer', 'company-history')
    student = account(system, 'student', 'student-history')
    jid = employer.post('/api/jobs', json=job_data()).json()['id']
    aid = student.post('/api/applications', json={'job_id': jid, 'consent': True}).json()['id']
    owner = employer.get('/api/auth/me').json()['id']
    # 仅在隔离数据库构建已保存记录，检验真实读取权限，不声称调用过模型。
    system.state.store.save('agent_run', owner, {'status': 'completed', 'application_id': aid,
                            'document_ids': [], 'result': {'message': '隔离测试记录'}})
    assert len(employer.get('/api/agent/history').json()) == 1
    student.post(f'/api/applications/{aid}/withdraw')
    assert employer.get('/api/agent/history').json() == []


def test_answer_revision_retains_original_evidence_snapshot(system):
    employer = account(system, 'employer', 'company-snapshot')
    student = account(system, 'student', 'student-snapshot')
    spec = job_data()
    spec['questions'] = [{'id': 'q1', 'title': '设计验证方案', 'kind': 'text', 'skill': '产品设计', 'rubric': '看验证方法'}]
    jid = employer.post('/api/jobs', json=spec).json()['id']
    aid = student.post('/api/applications', json={'job_id': jid, 'consent': True}).json()['id']
    student.post(f'/api/applications/{aid}/answers', json={'job_version': 1, 'answers': {'q1': '原始回答：用户研究'}})
    revision = employer.get(f'/api/applications/{aid}').json()['revision']
    employer.post(f'/api/applications/{aid}/review', json={'revision': revision, 'abilities': {'产品设计': {'level': 3, 'evidence': 'q1：体现用户研究'}}})
    student.post(f'/api/applications/{aid}/answers', json={'job_version': 1, 'answers': {'q1': '修订回答：用户研究和指标验证'}})
    response = employer.get(f'/api/applications/{aid}/history')
    assert response.status_code == 200
    history = response.json()
    assert any(row['answers']['q1'] == '原始回答：用户研究' and row.get('review') for row in history)
    assert all(row['job_version'] == 1 for row in history)


def test_changed_question_cannot_reuse_old_answer(system):
    employer = account(system, 'employer', 'company-question-version')
    student = account(system, 'student', 'student-question-version')
    spec = job_data()
    spec['questions'] = [{'id': 'q1', 'title': '设计产品方案', 'kind': 'text', 'skill': '产品设计', 'rubric': '评价产品方法'}]
    jid = employer.post('/api/jobs', json=spec).json()['id']
    aid = student.post('/api/applications', json={'job_id': jid, 'consent': True}).json()['id']
    assert student.post(f'/api/applications/{aid}/answers', json={'job_version': 1, 'answers': {'q1': '产品设计回答'}}).status_code == 200
    spec['questions'][0].update(skill='数据分析', title='完成数据分析', rubric='评价数据方法')
    assert employer.put(f'/api/jobs/{jid}?version=1', json=spec).status_code == 200
    result = employer.get(f'/api/applications/{aid}').json()
    assert result['answers'] == {}
    stale = student.post(f'/api/applications/{aid}/answers', json={'job_version': 1, 'answers': {'q1': '旧页面回答'}})
    assert stale.status_code == 409
