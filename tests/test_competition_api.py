from tests.test_api import account, system
from tests.test_decision import decision_input


def source_data(split='development'):
    return {'title': '隔离测试来源', 'url': 'https://example.org/data', 'collected_at': '2026-11-03',
            'method': 'official_bundle', 'license_basis': '仅用于隔离测试的许可声明', 'research_permitted': True,
            'contains_personal_data': False, 'redaction_reviewed': True, 'split': split, 'scope': '北京测试专业对应的同周期市场'}


def prepare(client, split='development'):
    case, recruitment, employment = decision_input()
    source = client.post('/api/competition/sources', json=source_data(split))
    assert source.status_code == 200, source.text
    source_id = source.json()['id']
    jobs = client.post('/api/competition/datasets', json={'source_id': source_id, 'kind': 'recruitment', 'records': recruitment})
    assert jobs.status_code == 200, jobs.text
    feed = client.post('/api/competition/datasets', json={'source_id': source_id, 'kind': 'employment', 'records': employment})
    assert feed.status_code == 200, feed.text
    case['recruitment_id'], case['employment_id'] = jobs.json()['id'], feed.json()['id']
    return case


def test_research_requires_governed_sources_and_own_scope(system):
    uni = account(system, 'university', 'research-school')
    outsider = account(system, 'university', 'research-outsider')
    student = account(system, 'student', 'research-student')
    assert student.post('/api/competition/sources', json=source_data()).status_code == 403
    case = prepare(uni)
    response = uni.post('/api/competition/cases', json=case)
    assert response.status_code == 200, response.text
    cid = response.json()['id']
    assert outsider.post(f'/api/competition/cases/{cid}/run').status_code == 403
    run = uni.post(f'/api/competition/cases/{cid}/run')
    assert run.status_code == 200, run.text
    assert run.json()['result']['best']['action_ids'] == ['a']
    rid = run.json()['id']
    assert outsider.get(f'/api/competition/runs/{rid}').status_code == 403
    assert uni.get(f'/api/competition/runs/{rid}/export?format=json').status_code == 200


def test_evaluation_set_cannot_generate_or_select_plans(system):
    uni = account(system, 'university', 'evaluation-school')
    case = prepare(uni, 'evaluation')
    response = uni.post('/api/competition/cases', json=case)
    assert response.status_code == 422
    assert '评测' in response.json()['detail']


def test_personal_data_blocks_competition_ingestion(system):
    uni = account(system, 'university', 'sensitive-school')
    source = uni.post('/api/competition/sources', json=source_data()).json()
    _, jobs, _ = decision_input()
    jobs[0]['title'] = '联系13800138000'
    response = uni.post('/api/competition/datasets', json={'source_id': source['id'], 'kind': 'recruitment', 'records': jobs})
    assert response.status_code == 422


def test_case_without_source_is_never_silently_filled(system):
    uni = account(system, 'university', 'missing-source-school')
    case, _, _ = decision_input()
    assert uni.post('/api/competition/cases', json=case).status_code == 404


def test_public_suppression_removes_complementary_counts():
    from backend.competition_api import public_result
    result = public_result({'split': {'direction_counts': {'d': 98}, 'allocated': 98,
                                      'unallocated': 2, 'direction_gap_after': .02}})
    assert result['split']['direction_counts']['d'] == '已抑制'
    assert result['split']['direction_gap_after'] is None


def test_same_records_cannot_be_relabelled_as_independent_evaluation(system):
    uni = account(system, 'university', 'overlap-school')
    prepare(uni)
    source = uni.post('/api/competition/sources', json=source_data('evaluation')).json()
    _, jobs, _ = decision_input()
    jobs[0]['record_id'] = 'different-id-same-content'
    response = uni.post('/api/competition/datasets', json={'source_id': source['id'], 'kind': 'recruitment', 'records': jobs})
    assert response.status_code == 422
    assert '重叠' in response.json()['detail']
