import hashlib
import json
import secrets
import sqlite3
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from lxml.etree import XMLSyntaxError
from openpyxl.utils.exceptions import InvalidFileException
from pypdf.errors import PdfReadError

from backend import schemas as s
from backend.documents import MAX_SIZE, extract
from backend.matching import allocate, match, normalized, optimize_courses
from backend.store import Store, check_password, encode, now, password_hash, uid
from backend.presentation import public_product, parameter_question, PARAMETER_REPLY


ROOT = Path(__file__).resolve().parents[1]


def create_app(data_root=None, enable_demo=True):
    app = FastAPI(title="智链产教", docs_url="/api/docs", redoc_url=None)
    store = Store(Path(data_root) if data_root else ROOT / "data" / "private")
    app.state.store = store
    if data_root is None:
        from backend.reference_data import import_reference
        import_reference(store)
    attempts = {}

    @app.middleware("http")
    async def security(request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            if urlsplit(origin).netloc != request.headers.get("host"):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "请求来源不匹配"}, status_code=403)
        response = await call_next(request)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and response.status_code < 400 and getattr(request.state, 'administrator', None):
            store.audit(request.state.administrator, 'workspace:' + request.method + ':' + request.url.path, request.state.workspace)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api") else "no-cache"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        return response

    def limited(request):
        key = request.client.host if request.client else "local"
        current = time.monotonic()
        history = [t for t in attempts.get(key, []) if current - t < 60]
        if len(history) >= 30:
            raise HTTPException(429, "尝试过于频繁，请稍后重试")
        attempts[key] = history + [current]

    def public_user(row):
        return {key: row[key] for key in ("id", "username", "name", "role", "school_code")}

    def user(request: Request):
        from backend.administration import principal
        row, token = principal(store, request)
        actor = row
        with store.connect() as db:
            context = db.execute('SELECT target_id FROM admin_contexts WHERE token=?', (token,)).fetchone() if actor['role'] == 'admin' else None
            if context:
                row = db.execute('SELECT * FROM users WHERE id=?', (context['target_id'],)).fetchone()
                if row is None:
                    raise HTTPException(409, '工作空间账号已不存在，请返回管理入口')
        result = public_user(row)
        expected = request.headers.get('X-Workspace-ID')
        if expected and expected != row['id'] and not request.url.path.startswith('/api/auth/'):
            raise HTTPException(409, '工作空间已切换，请刷新页面后继续')
        if context:
            result['administrator'] = {'id': actor['id'], 'name': actor['name']}
            request.state.administrator = actor['id']
            request.state.workspace = row['id']
        return result

    from backend.administration import attach_administration
    attach_administration(app, store, user, public_user)

    def role(current, required):
        if current["role"] not in required:
            raise HTTPException(403, "当前身份没有此操作权限")

    def entity(ident, kind=None):
        result = store.get(ident, kind)
        if result is None:
            raise HTTPException(404, "记录不存在")
        return result

    def owned(ident, current, kind=None):
        item = entity(ident, kind)
        if item["owner"] != current["id"]:
            raise HTTPException(403, "只能访问自己的记录")
        return item

    def flat(item):
        return {**item["data"], "id": item["id"], "owner": item["owner"], "created": item["created"]}

    def get_profile(student_id):
        rows = store.list("profile", student_id)
        return rows[0]["data"] if rows else s.Profile().model_dump()

    def application_access(ident, current):
        item = entity(ident, "application")
        job = entity(item["data"]["job_id"], "job")
        if current["id"] != item["owner"]:
            if current["role"] != "employer" or job["owner"] != current["id"] or item["data"].get("withdrawn"):
                raise HTTPException(403, "没有当前投递的访问授权")
        return item, job

    def snapshot_application(db, item, job_data, actor, reason):
        previous = item["data"]
        if previous.get("answers") or previous.get("review"):
            data = {"application_id": item["id"], "answers": previous.get("answers", {}),
                    "audio_ids": previous.get("audio_ids", []), "review": previous.get("review"),
                    "job_version": previous.get("answers_job_version", job_data["version"]), "questions": previous.get("answer_questions", job_data["questions"]),
                    "actor": actor, "reason": reason, "saved_at": now()}
            stamp = now()
            db.execute("INSERT INTO entities VALUES(?,?,?,?,?,?)", (uid(), "application_history", item["owner"], encode(data), stamp, stamp))

    def revise_application(item, current, changes, reason, require_current=False, job_version=None):
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM entities WHERE id=?", (item["id"],)).fetchone()
            latest = {**dict(row), "data": json.loads(row["data"])}
            if latest["data"].get("withdrawn") and reason != "withdraw":
                raise HTTPException(409, "投递已撤回，不能继续修改")
            if require_current and latest["updated"] != item["updated"]:
                raise HTTPException(409, "测评记录已变化，请重新载入后复核")
            job_row = db.execute("SELECT data FROM entities WHERE id=?", (latest["data"]["job_id"],)).fetchone()
            if job_version is not None and json.loads(job_row["data"])["version"] != job_version:
                raise HTTPException(409, "岗位版本已变化，请重新打开测评页面")
            snapshot_application(db, latest, json.loads(job_row["data"]), current["id"], reason)
            updated = {**latest["data"], **changes}
            db.execute("UPDATE entities SET data=?,updated=? WHERE id=?", (encode(updated), now(), item["id"]))
        return updated

    def application_result(item, job):
        profile = get_profile(item["owner"])
        review = item["data"].get("review")
        score = match(flat(job), profile, [review] if review else [])
        shared_profile = {key: value for key, value in profile.items() if key not in {"school_code", "school_id"}}
        return {**flat(item), "revision": item["updated"], "job": flat(job), "profile": shared_profile, "match": score}

    def document_access(ident, current):
        document = entity(ident, "document")
        if document["owner"] == current["id"]:
            return document
        from backend.student_space import published_resource
        if published_resource(store, document['owner'], ident, 'document'):
            return document
        if current["role"] == "employer":
            for item in store.list("application", document["owner"]):
                if not item["data"].get("withdrawn") and ident in item["data"].get("document_ids", []):
                    if entity(item["data"]["job_id"], "job")["owner"] == current["id"]:
                        return document
        raise HTTPException(403, "没有资料访问授权")

    def session(response, user_id):
        token = secrets.token_urlsafe(40)
        with store.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, time.time() + 43200))
        response.set_cookie("chanzhi_session", token, httponly=True, samesite="strict", max_age=43200)

    @app.post("/api/auth/register")
    def register(payload: s.Account, request: Request, response: Response):
        limited(request)
        ident, salt = uid(), secrets.token_hex(16)
        code = secrets.token_urlsafe(10) if payload.role == "university" else ""
        try:
            with store.connect() as db:
                db.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?,?)", (ident, payload.username.lower(), payload.name, payload.role, salt, password_hash(payload.password, salt), code, now()))
                if payload.role == 'employer':
                    stamp = now()
                    db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?)', (uid(), 'company_profile', ident,
                        encode({'name': payload.name, 'tracks': payload.company_tracks, 'description': ''}), stamp, stamp))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "账号已存在")
        session(response, ident)
        store.audit(ident, "register", ident)
        return {"id": ident, "username": payload.username, "name": payload.name, "role": payload.role, "school_code": code}

    @app.post("/api/auth/login")
    def login(payload: s.Login, request: Request, response: Response):
        limited(request)
        with store.connect() as db:
            row = db.execute("SELECT * FROM users WHERE username=?", (payload.username.lower(),)).fetchone()
        if row is None or not check_password(payload.password, row["salt"], row["hash"]):
            raise HTTPException(401, "账号或密码错误")
        session(response, row["id"])
        return public_user(row)

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        token = request.cookies.get("chanzhi_session", "")
        with store.connect() as db:
            db.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.encode()).hexdigest(),))
            db.execute('DELETE FROM admin_contexts WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))
        response.delete_cookie("chanzhi_session")
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(current=Depends(user)):
        return current

    @app.get("/api/health")
    def health():
        from backend.agent import configuration
        config = configuration()
        return {"status": "ok", "name": "智链产教", "model_version": "matching-1", "agent_configured": bool(config["key"]), "agent_model": config["model"]}

    @app.get("/api/profile")
    def profile(current=Depends(user)):
        role(current, ["student"])
        return public_product(get_profile(current["id"]))

    @app.put("/api/profile")
    def save_profile(payload: s.Profile, current=Depends(user)):
        role(current, ["student"])
        data = payload.model_dump()
        if payload.school_code:
            with store.connect() as db:
                school = db.execute("SELECT id,name FROM users WHERE school_code=? AND role='university'", (payload.school_code,)).fetchone()
            if school is None:
                raise HTTPException(422, "高校入校码不存在")
            data["school_id"] = school["id"]
        else:
            data["school_id"] = ""
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id FROM entities WHERE kind='profile' AND owner=?", (current["id"],)).fetchone()
            stamp = now()
            if row:
                db.execute("UPDATE entities SET data=?,updated=? WHERE id=?", (encode(data), stamp, row["id"]))
            else:
                db.execute("INSERT INTO entities VALUES(?,?,?,?,?,?)", (uid(), "profile", current["id"], encode(data), stamp, stamp))
            applications = db.execute("SELECT * FROM entities WHERE kind='application' AND owner=?", (current["id"],)).fetchall()
            for row in applications:
                detail = json.loads(row["data"])
                if detail.get("review"):
                    job_row = db.execute("SELECT data FROM entities WHERE id=?", (detail["job_id"],)).fetchone()
                    snapshot_application(db, {**dict(row), "data": detail}, json.loads(job_row["data"]), current["id"], "profile_changed")
                db.execute("UPDATE entities SET data=?,updated=? WHERE id=?", (encode({**detail, "review": None}), stamp, row["id"]))
        store.audit(current["id"], "save_profile", current["id"])
        return public_product(data)

    @app.get("/api/jobs")
    def jobs(current=Depends(user)):
        rows = [flat(item) for item in store.list("job")]
        if current['role']=='employer':
            rows=[j for j in rows if j['owner']==current['id']]
        else:
            rows=[j for j in rows if j.get('status','published')=='published']
        for job in rows:
            job['priorities'] = job.get('priorities', {r['skill']: '重点关注' for r in job['requirements']})
        return public_product(rows)

    @app.post("/api/jobs")
    def create_job(payload: s.Job, current=Depends(user)):
        role(current, ["employer"])
        companies=store.list('company_profile',current['id'])
        company=companies[0]['data'].get('name',current['name']) if companies else current['name']
        data = {**payload.model_dump(), "company": company, "version": 1, "status":"published"}
        ident = store.save("job", current["id"], data)
        with store.connect() as db:
            db.execute("INSERT INTO job_versions VALUES(?,?,?,?)", (ident, 1, encode(data), now()))
        return public_product(flat(entity(ident)))

    @app.put("/api/jobs/{ident}")
    def edit_job(ident: str, payload: s.Job, version: int, current=Depends(user)):
        role(current, ["employer"])
        owned(ident, current, "job")
        data = {**payload.model_dump(), "company": current["name"], "version": version + 1}
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM entities WHERE id=?", (ident,)).fetchone()
            if json.loads(row["data"])["version"] != version:
                raise HTTPException(409, "岗位已更新，请重新载入后修改")
            original_data=json.loads(row['data'])
            data['company']=original_data.get('company',current['name'])
            data['status']=original_data.get('status','published')
            previous = {r['skill']: r for r in json.loads(row['data'])['requirements']}
            previous_priorities = json.loads(row['data']).get('priorities', {})
            data['priorities'] = {r['skill']: previous_priorities.get(r['skill'], '重点关注') for r in data['requirements']}
            for requirement, original in zip(data['requirements'], payload.requirements):
                if requirement['skill'] in previous:
                    for key in ('weight', 'target'):
                        if key not in original.model_fields_set:
                            requirement[key] = previous[requirement['skill']][key]
            db.execute("UPDATE entities SET data=?,updated=? WHERE id=?", (encode(data), now(), ident))
            db.execute("INSERT INTO job_versions VALUES(?,?,?,?)", (ident, data["version"], encode(data), now()))
            for application in db.execute("SELECT id,owner,data FROM entities WHERE kind='application'").fetchall():
                detail = json.loads(application["data"])
                if detail["job_id"] == ident and not detail.get("withdrawn"):
                    snapshot_application(db, {"id": application["id"], "owner": application["owner"], "data": detail}, json.loads(row["data"]), current["id"], "job_changed")
                    old_questions = {q["id"]: q for q in json.loads(row["data"])["questions"]}
                    unchanged = {q["id"] for q in data["questions"] if old_questions.get(q["id"]) == q}
                    detail["answers"] = {qid: answer for qid, answer in detail.get("answers", {}).items() if qid in unchanged}
                    if any(qid not in unchanged for qid in old_questions):
                        detail["audio_ids"] = []
                    detail.update(review=None, student_chosen=False, employer_chosen=False, job_changed=True)
                    db.execute("UPDATE entities SET data=?,updated=? WHERE id=?", (encode(detail), now(), application["id"]))
        store.audit(current["id"], "edit_job", ident)
        return public_product(flat(entity(ident)))

    def updated_weights(ident, payload, current, save, priorities=None):
        job = owned(ident, current, "job")
        data = job["data"]
        if payload.version != data["version"]:
            raise HTTPException(409, "权重已更新，请重新载入后调整")
        if set(payload.weights) != {r["skill"] for r in data["requirements"]}:
            raise HTTPException(422, "权重维度必须与岗位能力完全一致")
        try:
            normalized(payload.weights)
            if any(v > 100 for v in payload.weights.values()):
                raise ValueError("单项权重范围为0–100")
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        data["requirements"] = [{**r, "weight": payload.weights[r["skill"]]} for r in data["requirements"]]
        if priorities is not None:
            data['priorities'] = priorities
        if save:
            data["version"] += 1
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                latest = db.execute("SELECT data FROM entities WHERE id=?", (ident,)).fetchone()
                if json.loads(latest["data"])["version"] != payload.version:
                    raise HTTPException(409, "权重被其他会话更新，请重新载入")
                latest_data=json.loads(latest['data'])
                data['status']=latest_data.get('status','published')
                data['company']=latest_data.get('company',data['company'])
                db.execute("UPDATE entities SET data=?,updated=? WHERE id=?", (encode(data), now(), ident))
                db.execute("INSERT INTO job_versions VALUES(?,?,?,?)", (ident, data["version"], encode(data), now()))
            store.audit(current["id"], "weights_version", ident)
        rankings = []
        for item in store.list("application"):
            if item["data"]["job_id"] == ident and not item["data"].get("withdrawn"):
                result = application_result(item, {**job, "data": data})
                rankings.append({"id": item["id"], "student_id": item["owner"], "match": result["match"]})
        rankings.sort(key=lambda row: (row["match"]["status"] != "excluded", row["match"]["provisional"]), reverse=True)
        return {**data, "id": ident, "rankings": rankings}

    @app.put("/api/jobs/{ident}/weights")
    def weights(ident: str, payload: s.Weights, current=Depends(user)):
        return public_product(updated_weights(ident, payload, current, True))

    @app.post("/api/jobs/{ident}/preview")
    def preview(ident: str, payload: s.Weights, current=Depends(user)):
        return public_product(updated_weights(ident, payload, current, False))

    @app.get("/api/jobs/{ident}/versions")
    def versions(ident: str, current=Depends(user)):
        owned(ident, current, "job")
        with store.connect() as db:
            rows = db.execute("SELECT version,data,created FROM job_versions WHERE job_id=? ORDER BY version DESC", (ident,)).fetchall()
        return public_product([{"version": r["version"], "data": json.loads(r["data"]), "created": r["created"]} for r in rows])

    @app.get("/api/jobs/{ident}/match")
    def own_match(ident: str, current=Depends(user)):
        role(current, ["student"])
        job = entity(ident, "job")
        reviews = [a["data"]["review"] for a in store.list("application", current["id"]) if a["data"]["job_id"] == ident and not a["data"].get("withdrawn") and a["data"].get("review")]
        return public_product(match(flat(job), get_profile(current["id"]), reviews))

    @app.post("/api/applications")
    def apply(payload: s.Apply, current=Depends(user)):
        role(current, ["student"])
        target=entity(payload.job_id, "job")
        if target['data'].get('status','published')!='published':
            raise HTTPException(409,'该岗位暂不接受新的投递')
        for doc_id in payload.document_ids:
            owned(doc_id, current, "document")
        for ident in payload.portfolio_ids:
            owned(ident, current, 'portfolio')
        ident, stamp = uid(), now()
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT data FROM entities WHERE kind='application' AND owner=?", (current["id"],)).fetchall()
            if any(json.loads(row["data"])["job_id"] == payload.job_id and not json.loads(row["data"]).get("withdrawn") for row in existing):
                raise HTTPException(409, "已投递该岗位")
            data = {**payload.model_dump(), "withdrawn": False, "student_chosen": True, "employer_chosen": False, "answers": {}, "audio_ids": []}
            db.execute("INSERT INTO entities VALUES(?,?,?,?,?,?)", (ident, "application", current["id"], encode(data), stamp, stamp))
        store.audit(current["id"], "consent_apply", ident)
        return flat(entity(ident))

    @app.get("/api/applications")
    def applications(current=Depends(user)):
        role(current, ["student", "employer"])
        results = []
        for item in store.list("application"):
            if item["data"].get("withdrawn"):
                continue
            job = entity(item["data"]["job_id"], "job")
            if item["owner"] == current["id"] or job["owner"] == current["id"]:
                results.append(application_result(item, job))
        return public_product(results)

    @app.get("/api/applications/{ident}")
    def application(ident: str, current=Depends(user)):
        item, job = application_access(ident, current)
        if item["data"].get("withdrawn"):
            return {"id": ident, "withdrawn": True}
        return public_product(application_result(item, job))

    @app.post("/api/applications/{ident}/withdraw")
    def withdraw(ident: str, current=Depends(user)):
        item = owned(ident, current, "application")
        revise_application(item, current, {"withdrawn": True, "student_chosen": False, "employer_chosen": False}, "withdraw")
        store.audit(current["id"], "withdraw_consent", ident)
        return {"ok": True}

    @app.post("/api/applications/{ident}/choice")
    def choice(ident: str, payload: s.Choice, current=Depends(user)):
        item, job = application_access(ident, current)
        if item["data"].get("withdrawn"):
            raise HTTPException(409, "投递已撤回")
        key = "student_chosen" if item["owner"] == current["id"] else "employer_chosen"
        data = revise_application(item, current, {key: payload.chosen}, "choice")
        return {"mutual": data["student_chosen"] and data["employer_chosen"], key: payload.chosen}

    @app.post("/api/applications/{ident}/answers")
    def answers(ident: str, payload: s.Answers, current=Depends(user)):
        item = owned(ident, current, "application")
        if item["data"].get("withdrawn"):
            raise HTTPException(409, "投递已撤回")
        job = entity(item["data"]["job_id"], "job")["data"]
        if payload.job_version != job["version"]:
            raise HTTPException(409, "岗位版本已变化，请重新打开测评页面")
        if set(payload.answers) - {q["id"] for q in job["questions"]}:
            raise HTTPException(422, "回答包含不存在的题目")
        if any(not answer.strip() or len(answer) > 15000 for answer in payload.answers.values()):
            raise HTTPException(422, "回答不能为空或超过15000字符")
        for audio_id in payload.audio_ids:
            owned(audio_id, current, "audio")
        revise_application(item, current, {**payload.model_dump(), "answers_job_version": payload.job_version, "answer_questions": job["questions"], "review": None, "submitted": now()}, "answer_changed", job_version=payload.job_version)
        return {"ok": True, "review_invalidated": True}

    @app.post("/api/applications/{ident}/review")
    def review(ident: str, payload: s.Review, current=Depends(user)):
        item, job = application_access(ident, current)
        if job["owner"] != current["id"]:
            raise HTTPException(403, "只能由岗位企业复核")
        if payload.revision != item["updated"]:
            raise HTTPException(409, "画像或测评已更新，请重新载入后复核")
        questions = {q["id"]: q for q in job["data"]["questions"]}
        valid_skills = {r["skill"] for r in job["data"]["requirements"]}
        for skill, observation in payload.abilities.items():
            if skill not in valid_skills:
                raise HTTPException(422, "复核能力不属于岗位")
            references = [qid for qid, q in questions.items() if q["skill"] == skill and qid in observation.evidence and item["data"].get("answers", {}).get(qid)]
            if not references:
                raise HTTPException(422, "复核必须引用已作答且关联该能力的题目标识")
        if set(payload.background) - {"majors", "schools", "languages"}:
            raise HTTPException(422, "未知背景条件")
        if any(payload.background.values()) and not item["data"].get("document_ids"):
            raise HTTPException(422, "核验背景需要学生授权的证明资料")
        revise_application(item, current, {"review": {**payload.model_dump(), "reviewed": True, "reviewer": current["id"], "reviewed_at": now()}}, "assessment_reviewed", require_current=True)
        store.audit(current["id"], "review_assessment", ident)
        return {"ok": True}

    @app.get("/api/applications/{ident}/history")
    def assessment_history(ident: str, current=Depends(user)):
        item, job = application_access(ident, current)
        return [flat(row) for row in store.list("application_history") if row["data"]["application_id"] == ident]

    @app.post("/api/employer/allocate")
    def allocation(payload: s.Budget, current=Depends(user)):
        role(current, ["employer"])
        job_map = {j["id"]: flat(j) for j in store.list("job", current["id"])}
        pairs = []
        for item in store.list("application"):
            job_id = item["data"]["job_id"]
            if job_id in job_map and not item["data"].get("withdrawn"):
                result = application_result(item, entity(job_id, "job"))
                pairs.append({"application_id": item["id"], "job_id": job_id, "student_id": item["owner"], "status": result["match"]["status"], "lower": result["match"]["lower"], "mutual": item["data"].get("student_chosen") and item["data"].get("employer_chosen")})
        return allocate(pairs, job_map, payload.model_dump())

    @app.post("/api/documents")
    async def upload(file: UploadFile = File(...), current=Depends(user)):
        content = await file.read(MAX_SIZE + 1)
        if len(content) > MAX_SIZE:
            raise HTTPException(413, "文档不得超过12MB")
        try:
            data = extract(file.filename or "", content)
        except (zipfile.BadZipFile, XMLSyntaxError, PdfReadError, InvalidFileException, KeyError):
            raise HTTPException(422, "文件损坏、加密或格式不完整，请检查原文件") from None
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(422, str(exc))
        ident = uid()
        folder = store.root / "files"
        folder.mkdir(exist_ok=True)
        (folder / ident).write_bytes(content)
        data["uploaded_at"] = now()
        store.save("document", current["id"], data, ident)
        return flat(entity(ident))

    @app.get("/api/documents")
    def documents(current=Depends(user)):
        return [{k: v for k, v in flat(d).items() if k != "blocks"} for d in store.list("document", current["id"])]

    @app.get("/api/documents/{ident}")
    def document(ident: str, current=Depends(user)):
        return flat(document_access(ident, current))

    @app.get("/api/documents/{ident}/download")
    def download(ident: str, current=Depends(user)):
        item = document_access(ident, current)
        if item['data'].get('url'):
            return Response('\n\n'.join(b['text'] for b in item['data']['blocks']), media_type='text/plain; charset=utf-8')
        return FileResponse(store.root / "files" / ident, filename=item["data"]["name"], media_type="application/octet-stream")

    @app.post("/api/audio")
    async def audio(file: UploadFile = File(...), current=Depends(user)):
        role(current, ["student"])
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".webm", ".wav", ".mp3", ".m4a", ".ogg"}:
            raise HTTPException(422, "不支持的音频格式")
        content = await file.read(MAX_SIZE + 1)
        if not content or len(content) > MAX_SIZE:
            raise HTTPException(413, "音频为空或超过12MB")
        ident = uid()
        folder = store.root / "audio"
        folder.mkdir(exist_ok=True)
        (folder / ident).write_bytes(content)
        store.save("audio", current["id"], {"name": Path(file.filename).name, "sha256": hashlib.sha256(content).hexdigest()}, ident)
        return {"id": ident}

    @app.get("/api/audio/{ident}")
    def get_audio(ident: str, current=Depends(user)):
        audio_item = entity(ident, "audio")
        permitted = audio_item["owner"] == current["id"]
        if not permitted and current["role"] == "employer":
            permitted = any(not a["data"].get("withdrawn") and ident in a["data"].get("audio_ids", []) and entity(a["data"]["job_id"], "job")["owner"] == current["id"] for a in store.list("application", audio_item["owner"]))
        if not permitted:
            raise HTTPException(403, "没有音频访问授权")
        return FileResponse(store.root / "audio" / ident, filename=audio_item["data"]["name"])

    @app.get("/api/university/insights")
    def insights(current=Depends(user)):
        role(current, ["university"])
        profiles = [p for p in store.list("profile") if p["data"].get("school_id") == current["id"]]
        if len(profiles) < 5:
            return {"suppressed": True, "minimum": 5, "message": "本校授权样本不足5人，暂不展示能力统计"}
        needs, supplies = {}, {}
        for job in store.list("job"):
            for req in job["data"]["requirements"]:
                needs.setdefault(req["skill"], []).append(req["target"])
        for p in profiles:
            for skill, obs in p["data"].get("abilities", {}).items():
                supplies.setdefault(skill, []).append(obs["level"])
        rows = []
        for skill, targets in needs.items():
            levels = supplies.get(skill, [])
            if len(levels) < 5:
                continue
            target, level = sum(targets) / len(targets), sum(levels) / len(levels)
            rows.append({"skill": skill, "target": round(target, 3), "supply": round(level, 3), "gap": round(max(0, target - level), 3), "count": len(levels)})
        return {"suppressed": False, "sample_count": len(profiles), "skills": rows,
                "basis": "本校学生自述能力与站内发布岗位的描述性汇总；不代表全校或行业总体"}

    @app.post("/api/university/optimize")
    def optimize(payload: s.Optimize, current=Depends(user)):
        role(current, ["university"])
        try:
            result = optimize_courses(payload.gaps, payload.weights, [c.model_dump() for c in payload.courses], payload.limits.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        ident = store.save("optimization", current["id"], {"input": payload.model_dump(), "result": result})
        return public_product({"id": ident, **result})

    @app.get("/api/university/plans")
    def plans(current=Depends(user)):
        role(current, ["university"])
        return [flat(p) for p in store.list("optimization", current["id"])]

    @app.post("/api/student/optimize")
    def student_optimize(payload: s.Optimize, current=Depends(user)):
        role(current, ["student"])
        profile = get_profile(current["id"])
        resources = profile.get("resources", s.LearningResources().model_dump())
        limits = payload.limits.model_dump()
        for limit, resource in (("cost", "budget"), ("study_hours", "study_hours"), ("months", "months")):
            limits[limit] = min(limits[limit], resources[resource])
        try:
            result = optimize_courses(payload.gaps, payload.weights, [c.model_dump() for c in payload.courses], limits)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        ident = store.save("learning_plan", current["id"], {"input": {**payload.model_dump(), "limits": limits}, "result": result})
        return {"id": ident, **result}

    @app.get("/api/student/plans")
    def student_plans(current=Depends(user)):
        role(current, ["student"])
        return [flat(p) for p in store.list("learning_plan", current["id"])]

    @app.get("/api/data/status")
    def data_status(current=Depends(user)):
        candidates = list((ROOT.parent).glob("*数据.zip*")) + list((ROOT.parent).glob("政策文件.zip*"))
        return [{"name": p.name, "bytes": p.stat().st_size, "status": "下载中" if p.name.endswith(".downloading") else "待导入", "readable": p.suffix.lower() == ".zip"} for p in candidates]

    def archive_path(name):
        candidates = {p.name: p for p in ROOT.parent.glob("*.zip") if p.name in {"产业数据.zip", "就业数据.zip", "政策文件.zip"}}
        if name not in candidates:
            raise HTTPException(404, "压缩包不存在或尚未下载完成")
        return candidates[name]

    @app.get("/api/data/archive")
    def archive_members(name: str, current=Depends(user)):
        from backend.documents import ALLOWED
        with zipfile.ZipFile(archive_path(name)) as archive:
            members = [item for item in archive.infolist() if not item.is_dir() and Path(item.filename).suffix.lower() in ALLOWED]
            return {"total": len(members), "members": [{"name": item.filename, "bytes": item.file_size, "importable": item.file_size <= MAX_SIZE and not item.flag_bits & 1} for item in members[:1000]], "shown": min(len(members), 1000)}

    @app.post("/api/data/import")
    def import_archive(payload: s.ArchiveImport, current=Depends(user)):
        with zipfile.ZipFile(archive_path(payload.archive)) as archive:
            try:
                info = archive.getinfo(payload.member)
            except KeyError:
                raise HTTPException(404, "压缩包内文件不存在")
            if info.file_size > MAX_SIZE or info.flag_bits & 1:
                raise HTTPException(422, "文件超过12MB或已加密，请在本地拆分后上传")
            with archive.open(info) as source:
                content = source.read(MAX_SIZE + 1)
        try:
            data = extract(Path(payload.member).name, content)
        except (zipfile.BadZipFile, XMLSyntaxError, PdfReadError, InvalidFileException, KeyError):
            raise HTTPException(422, "文件损坏、加密或格式不完整，请检查原文件") from None
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(422, str(exc))
        ident = uid()
        folder = store.root / "files"
        folder.mkdir(exist_ok=True)
        (folder / ident).write_bytes(content)
        data.update(source_archive=payload.archive, source_member=payload.member, uploaded_at=now())
        store.save("document", current["id"], data, ident)
        return flat(entity(ident))

    @app.post("/api/agent/run")
    def agent_run(payload: s.AgentRequest, current=Depends(user)):
        from backend.agent import run_agent
        from backend.agent import AgentError
        if parameter_question(payload.message):
            return {"message": PARAMETER_REPLY, "draft": None, "trace": [], "model": "系统说明", "elapsed": 0}
        documents = []
        if payload.document_ids and not payload.send_documents:
            raise HTTPException(422, "请确认将所选正文发送至DeepSeek")
        for ident in payload.document_ids:
            documents.append(flat(document_access(ident, current)))
        context = {"role": current["role"], "documents": documents, "mode": payload.mode}
        if current["role"] == "student":
            context["profile"] = get_profile(current["id"])
        if payload.application_id:
            item, job = application_access(payload.application_id, current)
            if item["data"].get("withdrawn"):
                raise HTTPException(403, "投递已撤回")
            context["application"] = application_result(item, job)
        if payload.job_id:
            context["job"] = flat(entity(payload.job_id, "job"))
        if current["role"] == "university":
            context["insights"] = insights(current)
        from backend.governance import check_model_output, model_gateway
        try:
            safe_message, context = model_gateway(payload.message, public_product(context), (current['name'], current['username']))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        try:
            result = run_agent(safe_message, context)
            result = check_model_output(result)
        except AgentError as exc:
            store.save("agent_run", current["id"], {"status": "failed", "error": str(exc), "mode": payload.mode})
            raise HTTPException(502, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        if payload.application_id:
            application_access(payload.application_id, current)
        for ident in payload.document_ids:
            document_access(ident, current)
        ident = store.save("agent_run", current["id"], {"status": "completed", "mode": payload.mode, "application_id": payload.application_id, "document_ids": payload.document_ids, "result": result})
        return public_product({"id": ident, **result})

    @app.get("/api/agent/history")
    def agent_history(current=Depends(user)):
        visible = []
        for item in store.list("agent_run", current["id"]):
            try:
                if item["data"].get("application_id"):
                    application_access(item["data"]["application_id"], current)
                for doc_id in item["data"].get("document_ids", []):
                    document_access(doc_id, current)
            except HTTPException as exc:
                if exc.status_code in {403, 404}:
                    continue
                raise
            visible.append(flat(item))
        return public_product(visible[:20])

    from backend.competition_api import attach_competition
    attach_competition(app, store, user, role, owned, entity, flat)
    from backend.evidence import attach_evidence
    attach_evidence(app, store, user)
    from backend.student_space import attach_student_space
    attach_student_space(app, store, user)
    from backend.market import attach_market
    attach_market(app, store, user)
    from backend.company_logos import attach_company_logos
    attach_company_logos(app)
    from backend.university_courses import attach_university_courses
    attach_university_courses(app, store, user)
    from backend.university_intelligence import attach_university_intelligence
    attach_university_intelligence(app, store, user)
    from backend.university_report import attach_university_report
    attach_university_report(app, store, user)
    from backend.experience_api import attach_experience
    attach_experience(app, store, user, role, owned, entity, flat, application_access, agent_run, updated_weights)
    from backend.recruiting import attach_recruiting
    attach_recruiting(app, store, user, flat, application_result)
    if enable_demo:
        from backend.demo import DemoRouter
        app.add_middleware(DemoRouter, root=store.root / 'demo', factory=create_app)

    app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "web" / "index.html")

    return app
