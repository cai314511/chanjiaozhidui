from concurrent.futures import ThreadPoolExecutor

from backend.app import create_app
from tests.test_api import account, job_data


def response_payload(client, kind, ident, action, **extra):
    item = next(i for i in client.get('/api/recruiting/workflow').json()[kind] if i['id'] == ident)
    return {'action': action, 'revision': item['revision'], **extra}


def setup_case(tmp_path):
    app = create_app(tmp_path / 'isolated')
    employer = account(app, 'employer', 'closure-company')
    students = [account(app, 'student', f'closure-student-{i}') for i in range(2)]
    spec = job_data()
    spec['questions'] = [{'id': 'q1', 'title': '产品设计方案', 'skill': '产品设计', 'rubric': '说明验证方法'},
                         {'id': 'q2', 'title': '数据分析方案', 'skill': '数据分析', 'rubric': '说明指标'}]
    job = employer.post('/api/jobs', json=spec).json()
    applications = [s.post('/api/applications', json={'job_id': job['id'], 'consent': True}).json()['id'] for s in students]
    return app, employer, students, job, applications


def test_invitation_confirmation_creates_shared_room_and_rejects_outsider(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    payload = {'starts_at': '2027-01-10T10:00:00+08:00', 'timezone': 'Asia/Shanghai', 'duration_minutes': 30, 'instructions': '准备项目介绍'}
    created = employer.post(f'/api/recruiting/applications/{aids[0]}/invitations', json=payload)
    assert created.status_code == 200, created.text
    invitation = created.json()
    assert students[1].post(f"/api/recruiting/invitations/{invitation['id']}/respond", json={'action': 'accept', 'revision': invitation['revision']}).status_code == 403
    accepted = students[0].post(f"/api/recruiting/invitations/{invitation['id']}/respond", json=response_payload(students[0], 'invitations', invitation['id'], 'accept'))
    assert accepted.status_code == 200, accepted.text
    room = accepted.json()['interview_id']
    assert employer.get('/api/interviews/' + room).status_code == 200
    assert students[0].get('/api/interviews/' + room).status_code == 200
    assert students[1].get('/api/interviews/' + room).status_code == 403
    assert employer.post(f"/api/recruiting/invitations/{invitation['id']}/respond", json=response_payload(employer, 'invitations', invitation['id'], 'cancel')).json()['status'] == 'cancelled'


def test_offer_acceptance_reserves_last_seat_atomically_and_release(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    offers = []
    for aid in aids:
        response = employer.post(f'/api/recruiting/applications/{aid}/offers', json={'message': '正式录用意向'})
        assert response.status_code == 200, response.text
        offers.append(response.json()['id'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(s.post, f'/api/recruiting/offers/{oid}/respond', json=response_payload(s, 'offers', oid, 'accept')) for s, oid in zip(students, offers)]
        responses = [f.result() for f in futures]
    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(i for i, r in enumerate(responses) if r.status_code == 200)
    assert employer.post(f'/api/recruiting/offers/{offers[winner]}/respond', json=response_payload(employer, 'offers', offers[winner], 'confirm')).json()['status'] == 'hired'
    assert employer.post(f'/api/recruiting/offers/{offers[winner]}/respond', json=response_payload(employer, 'offers', offers[winner], 'revoke')).json()['status'] == 'revoked'
    loser = 1 - winner
    assert students[loser].post(f'/api/recruiting/offers/{offers[loser]}/respond', json=response_payload(students[loser], 'offers', offers[loser], 'accept')).status_code == 200


def test_plan_versions_persist_staleness_and_comparison(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    budget = {'salary': 40000, 'training': 2000, 'mentor': 20}
    first = employer.post('/api/recruiting/plans', json=budget)
    assert first.status_code == 200, first.text
    assert first.json()['version'] == 1
    students[0].put('/api/profile', json={'career': '数据分析'})
    history = employer.get('/api/recruiting/plans').json()
    assert history[0]['stale'] is True
    second = employer.post('/api/recruiting/plans', json={**budget, 'salary': 20000}).json()
    assert second['version'] == 2
    compared = employer.get(f"/api/recruiting/plans/compare?left={first.json()['id']}&right={second['id']}")
    assert compared.status_code == 200
    assert compared.json()['left']['stale'] is True
    assert compared.json()['budget_changes']['salary'] == {'before': 40000.0, 'after': 20000.0}


def test_qualification_missing_self_report_and_verified():
    from backend.eligibility import qualification
    job = {'graduation_from': '2027-01', 'graduation_to': '2027-12', 'degrees': ['本科']}
    assert qualification(job, {})['status'] == 'pending'
    profile = {'graduation_month': '2027-06', 'degree': '本科'}
    assert qualification(job, profile)['status'] == 'pending'
    assert qualification(job, profile, {'graduation_month': True, 'degree': True})['status'] == 'eligible'
    assert qualification(job, {**profile, 'graduation_month': '2028-06'})['status'] == 'excluded'


def test_draft_publish_validation_capacity_withdraw_and_close(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    spec = job_data()
    spec['requirements'][0]['mandatory'] = True
    assert employer.post('/api/jobs', json=spec).status_code == 422
    draft = employer.post('/api/jobs', json={**spec, 'status': 'draft'})
    assert draft.status_code == 200, draft.text
    assert employer.post('/api/recruiting/jobs/'+draft.json()['id']+'/status', json={'status': 'published'}).status_code == 422
    offer = employer.post('/api/recruiting/applications/'+aids[0]+'/offers', json={'message': '录用意向'}).json()
    assert students[0].post('/api/recruiting/offers/'+offer['id']+'/respond', json=response_payload(students[0], 'offers', offer['id'], 'accept')).status_code == 200
    assert employer.post('/api/recruiting/offers/'+offer['id']+'/respond', json=response_payload(employer, 'offers', offer['id'], 'confirm')).status_code == 200
    assert students[0].post('/api/applications/'+aids[0]+'/withdraw').status_code == 200
    assert employer.get('/api/recruiting/workflow').json()['offers'][0]['status'] == 'revoked'
    other = employer.post('/api/recruiting/applications/'+aids[1]+'/offers', json={'message': '候补意向'}).json()
    assert employer.post('/api/recruiting/jobs/'+job['id']+'/status', json={'status': 'closed'}).status_code == 200
    assert students[1].post('/api/recruiting/offers/'+other['id']+'/respond', json=response_payload(students[1], 'offers', other['id'], 'accept')).status_code == 409


def test_reschedule_closes_old_room_and_timezone_is_validated(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    payload = {'starts_at': '2027-01-10T10:00:00+08:00', 'timezone': 'Asia/Shanghai', 'duration_minutes': 30}
    bad = {**payload, 'starts_at': '2027-01-10T10:00:00Z'}
    assert employer.post('/api/recruiting/applications/'+aids[0]+'/invitations', json=bad).status_code == 422
    invitation = employer.post('/api/recruiting/applications/'+aids[0]+'/invitations', json=payload).json()
    accepted = students[0].post('/api/recruiting/invitations/'+invitation['id']+'/respond', json=response_payload(students[0], 'invitations', invitation['id'], 'accept')).json()
    assert students[0].post('/api/recruiting/invitations/'+invitation['id']+'/respond', json=response_payload(students[0], 'invitations', invitation['id'], 'reschedule', proposal={**payload, 'starts_at': '2027-01-11T10:00:00+08:00'})).status_code == 200
    assert employer.get('/api/interviews/'+accepted['interview_id']).status_code == 403
    assert employer.post('/api/recruiting/invitations/'+invitation['id']+'/respond', json=response_payload(employer, 'invitations', invitation['id'], 'accept')).status_code == 200


def test_shrink_blocks_committed_seats_and_stale_offer_cannot_accept(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    spec = employer.get('/api/recruiting/jobs/'+job['id']+'/spec').json()
    payload = {key: value for key, value in spec.items() if key not in {'id', 'owner', 'occupied', 'company', 'version'}}
    payload['capacity'] = 2
    assert employer.put('/api/jobs/'+job['id']+'?version=1', json=payload).status_code == 200
    offers = [employer.post('/api/recruiting/applications/'+aid+'/offers', json={'message': '正式意向'}).json() for aid in aids]
    for student, offer in zip(students, offers):
        assert student.post('/api/recruiting/offers/'+offer['id']+'/respond', json=response_payload(student, 'offers', offer['id'], 'accept')).status_code == 200
    assert employer.put('/api/jobs/'+job['id']+'?version=2', json={**payload, 'capacity': 1}).status_code == 409
    assert employer.get('/api/recruiting/jobs/'+job['id']+'/spec').json()['occupied'] == 2
    plan = employer.post('/api/recruiting/plans', json={'salary': 100000, 'training': 10000, 'mentor': 100}).json()
    assert plan['result']['selected'] == []
    assert all('已有已接受' in c['reasons'][0] for c in plan['candidates'])


def test_workflow_permissions_duplicate_intents_and_stage_has_no_offer(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    assert employer.post('/api/recruiting/applications/'+aids[0]+'/stage', json={'stage': 'offer'}).status_code == 200
    assert employer.get('/api/recruiting/workflow').json()['offers'] == []
    assert students[0].post('/api/recruiting/applications/'+aids[0]+'/offers', json={'message': '非法发出'}).status_code == 403
    offer = employer.post('/api/recruiting/applications/'+aids[0]+'/offers', json={'message': '正式意向'}).json()
    assert employer.post('/api/recruiting/applications/'+aids[0]+'/offers', json={'message': '重复意向'}).status_code == 409
    assert students[1].post('/api/recruiting/offers/'+offer['id']+'/respond', json={'action': 'accept', 'revision': offer['revision']}).status_code == 403
    assert employer.post('/api/recruiting/offers/'+offer['id']+'/respond', json=response_payload(employer, 'offers', offer['id'], 'confirm')).status_code == 409


def test_workflow_stale_revision_rejected_and_elimination_blocks_accept(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    offer = employer.post('/api/recruiting/applications/'+aids[0]+'/offers', json={'message': '正式意向'}).json()
    response = students[0].post('/api/recruiting/offers/'+offer['id']+'/respond', json={'action': 'accept', 'revision': 'stale'})
    assert response.status_code == 409, response.text
    employer.post('/api/recruiting/applications/'+aids[0]+'/stage', json={'stage': 'declined'})
    assert students[0].post('/api/recruiting/offers/'+offer['id']+'/respond', json={'action': 'accept', 'revision': offer['revision']}).status_code == 409


def test_withdrawn_application_never_imports_current_profile_into_new_plan(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    assert students[0].post('/api/applications/'+aids[0]+'/withdraw').status_code == 200
    students[0].put('/api/profile', json={'career': '撤回后的新私密内容-不得披露'})
    plan = employer.post('/api/recruiting/plans', json={'salary': 100000, 'training': 10000, 'mentor': 100})
    assert plan.status_code == 200
    assert '撤回后的新私密内容' not in plan.text


def test_invitation_competing_reschedules_require_current_revision(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    proposal = {'starts_at': '2027-01-10T10:00:00+08:00', 'timezone': 'Asia/Shanghai', 'duration_minutes': 30}
    invitation = employer.post('/api/recruiting/applications/'+aids[0]+'/invitations', json=proposal).json()
    response = {'action': 'reschedule', 'revision': invitation['revision'], 'proposal': {**proposal, 'starts_at': '2027-01-11T10:00:00+08:00'}}
    assert students[0].post('/api/recruiting/invitations/'+invitation['id']+'/respond', json=response).status_code == 200
    response['proposal']['starts_at'] = '2027-01-12T10:00:00+08:00'
    assert employer.post('/api/recruiting/invitations/'+invitation['id']+'/respond', json=response).status_code == 409
    assert employer.get('/api/recruiting/workflow').json()['invitations'][0]['starts_at'].startswith('2027-01-11')


def test_job_version_change_requires_reissuing_formal_offer(tmp_path):
    app, employer, students, job, aids = setup_case(tmp_path)
    offer = employer.post('/api/recruiting/applications/'+aids[0]+'/offers', json={'message': '旧版本意向'}).json()
    response = employer.put('/api/jobs/'+job['id']+'/weights', json={'version': 1, 'weights': {'产品设计': 50, '数据分析': 50}})
    assert response.status_code == 200, response.text
    assert students[0].post('/api/recruiting/offers/'+offer['id']+'/respond', json={'action': 'accept', 'revision': offer['revision']}).status_code == 409
