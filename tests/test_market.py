import csv
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.store import Store


def write_csv(path, rows):
    fields = sorted({key for row in rows for key in row})
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def make_bundle(tmp_path):
    from backend.market import build_market
    base = {'企业名称': '甲公司', '招聘岗位': '农业技术员', '上市公司行业': '农业',
            '工作城市': '北京', '最低月薪': '8000', '最高月薪': '10000',
            '职位描述': '岗位介绍。联系人：张三；13812345678 test@example.com',
            '招聘发布日期': '2026-01-02'}
    listed = write_csv(tmp_path / 'listed.csv', [base, {**base, '招聘岗位': '植物研究员'},
                       {**base, '企业名称': '乙公司', '上市公司行业': '医药制造业'}])
    graduate = write_csv(tmp_path / 'graduate.csv', [
        {key: value for key, value in base.items() if key != '上市公司行业'},
        {**base, '企业名称': '未知公司', '上市公司行业': '', '招聘类别': 'Python'}])
    return build_market([listed, graduate], samples_per_company=1)


def client_for(store):
    from backend.market import attach_market
    app = FastAPI()

    def user(request: Request):
        role = request.headers.get('x-role')
        if not role:
            raise HTTPException(401, '请登录')
        return {'id': request.headers.get('x-user', 'student1'), 'role': role, 'name': '企业账号'}

    attach_market(app, store, user)
    return TestClient(app)


def test_full_catalog_keeps_industry_provenance_company_names_and_unknown(tmp_path):
    from backend.market import company_id
    bundle = make_bundle(tmp_path)
    assert bundle['scanned_rows'] == 5
    companies = {row['name']: row for row in bundle['companies']}
    assert len(companies) == 3
    assert companies['甲公司']['history_count'] == 2  # 重复公告只计一次
    assert companies['甲公司']['tracks'] == ['农业']
    assert companies['未知公司']['tracks'] == ['未分类']
    assert companies['甲公司']['raw_industries'] == ['农业']
    assert companies['甲公司']['industry_evidence'][0]['file'] == 'listed.csv'
    assert companies['甲公司']['id'] == company_id(' 甲公司 ')
    assert company_id('甲公司') != company_id('甲集团公司')
    assert len(companies['甲公司']['historical_jobs']) == 1
    assert '植物研究员' in companies['甲公司']['search_terms']
    serialized = json.dumps(bundle, ensure_ascii=False)
    assert '甲公司' in serialized
    for private in ['张三', '13812345678', 'test@example.com']:
        assert private not in serialized


def test_catalog_cache_invalidates_and_publish_preserves_other_entities(tmp_path):
    from backend.market import get_catalog, publish_market
    store = Store(tmp_path / 'db')
    private = store.save('document', 'other', {'secret': 'preserved'})
    bundle = make_bundle(tmp_path)
    publish_market(store, bundle)
    assert len(get_catalog(store)['companies']) == 3
    publish_market(store, {**bundle, 'companies': []})
    assert get_catalog(store)['companies'] == []
    assert store.get(private)['data']['secret'] == 'preserved'
    assert len(store.list('market_catalog')) == 1


def test_favorites_feed_only_live_jobs_and_owner_isolation(tmp_path):
    from backend.market import company_id, publish_market
    store = Store(tmp_path / 'db')
    publish_market(store, make_bundle(tmp_path))
    with client_for(store) as client:
        assert client.get('/api/market/tracks').status_code == 200
        assert client.get('/api/market/search').status_code == 401
        student = {'x-role': 'student'}
        company = {'x-role': 'employer', 'x-user': 'employer1'}
        assert client.put('/api/company/profile', headers=student, json={'name': '甲公司', 'tracks': ['农业']}).status_code == 403
        assert client.put('/api/company/profile', headers=company, json={'name': '甲公司', 'tracks': ['农业', '生物医药'], 'description': '企业介绍'}).status_code == 200
        ident = company_id('甲公司')
        response = client.post('/api/me/favorites', headers=student, json={'type': 'company', 'target_id': ident})
        assert response.status_code == 200
        assert client.get('/api/me/feed', headers=student).json()['jobs'] == []
        job = store.save('job', 'employer1', {'title': '新发布农技岗位', 'industry': '农业', 'city': '北京', 'salary_min': 9000, 'salary_max': 12000, 'company': '旧账号名'})
        feed = client.get('/api/me/feed', headers=student).json()
        assert [item['id'] for item in feed['jobs']] == [job]
        assert feed['jobs'][0]['type'] == 'live'
        track_student = {'x-role': 'student', 'x-user': 'track-student'}
        assert client.post('/api/me/favorites', headers=track_student, json={'type': 'track', 'target_id': '生物医药'}).status_code == 200
        assert client.get('/api/me/feed', headers=track_student).json()['jobs'] == []
        job_data = store.get(job)['data']
        store.save('job', 'employer1', {**job_data, 'industry': '生物医药'}, job)
        assert client.get('/api/me/feed', headers=track_student).json()['jobs'][0]['id'] == job
        detail = client.get('/api/market/companies/' + ident, headers=student).json()
        assert detail['registered'] is True
        assert detail['live_count'] == 1
        assert len(detail['historical_jobs']) == 1
        assert set(detail['tracks']) == {'农业', '生物医药'}
        assert client.put('/api/company/profile', headers=company, json={'name': '更名企业', 'tracks': ['农业']}).status_code == 200
        moved = client.get('/api/market/companies/' + company_id('更名企业'), headers=student).json()
        assert moved['jobs'][0]['company'] == '更名企业'
        assert moved['jobs'][0]['company_id'] == company_id('更名企业')
        assert client.get('/api/market/companies/' + ident, headers=student).json()['live_count'] == 0
        assert client.get('/api/me/favorites', headers={**student, 'x-user': 'other'}).json() == []
        assert client.post('/api/me/favorites', headers=student, json={'type': 'company', 'target_id': 'missing'}).status_code == 404
        assert client.delete('/api/me/favorites/company/' + ident, headers=student).status_code == 200
        assert client.get('/api/me/feed', headers=student).json()['jobs'] == []


def test_search_covers_unsampled_titles_and_validates_inputs_and_recommendations(tmp_path):
    from backend.market import publish_market
    store = Store(tmp_path / 'db')
    publish_market(store, make_bundle(tmp_path))
    with client_for(store) as client:
        headers = {'x-role': 'student'}
        results = client.get('/api/market/search?q=植物研究员', headers=headers).json()
        assert results['total_companies'] == 1
        assert results['companies'][0]['name'] == '甲公司'
        assert client.get('/api/market/search?page_size=10000', headers=headers).status_code == 422
        response = client.post('/api/market/recommend', headers=headers, json={'answers': {'interest': ['医药', '农业']}, 'text': '希望从事农业研究'})
        assert response.status_code == 200
        recommendations = response.json()['recommendations']
        assert recommendations[0]['track'] == '农业'
        available = {item['name'] for item in client.get('/api/market/tracks', headers=headers).json()}
        assert all(item['track'] in available for item in recommendations)
        assert all(item['evidence'] for item in recommendations)
        assert client.put('/api/me/exploration', headers=headers, json={'seen': True, 'answers': {'interest': ['农业']}}).status_code == 200
        assert client.get('/api/me/exploration', headers=headers).json()['seen'] is True
        assert client.get('/api/me/exploration', headers={'x-role': 'employer'}).status_code == 403


def test_ninety_character_registered_track_can_be_searched_and_saved(tmp_path):
    from backend.app import create_app

    track = '跨领域自定义赛道长名称' * 8 + '方向'
    assert len(track) == 90
    with TestClient(create_app(tmp_path / 'registered-track')) as client:
        registration = client.post('/api/auth/register', json={
            'username': 'long-track-employer', 'password': 'test-password-123',
            'name': '长赛道企业', 'role': 'employer', 'company_tracks': [track],
        })
        assert registration.status_code == 200
        search = client.get('/api/market/search', params={'track': track})
        saved = client.put('/api/company/profile', json={
            'name': '长赛道企业', 'tracks': [track], 'description': '自填赛道',
        })
        assert (search.status_code, saved.status_code) == (200, 200)
        assert search.json()['total_companies'] == 1
        assert search.json()['companies'][0]['tracks'] == [track]
        assert saved.json()['tracks'] == [track]
        assert client.get('/api/market/search', params={'track': '长' * 101}).status_code == 422
        assert client.put('/api/company/profile', json={'name': '长赛道企业', 'tracks': ['长' * 101]}).status_code == 422


def test_search_paginates_all_jobs_when_one_company_has_multiple_job_pages(tmp_path):
    store = Store(tmp_path / 'pagination')
    store.save('company_profile', 'employer1', {'name': '多岗位企业', 'tracks': ['农业'], 'description': ''})
    job_ids = {store.save('job', 'employer1', {
        'title': f'农业岗位{index}', 'industry': '农业', 'city': '北京',
        'salary_min': 8000, 'salary_max': 12000, 'company': '多岗位企业',
    }) for index in range(7)}
    with client_for(store) as client:
        pages = [client.get('/api/market/search', headers={'x-role': 'student'},
                            params={'track': '农业', 'page': page, 'page_size': 2}).json()
                 for page in range(1, 5)]
    assert all(page['total_companies'] == 1 and page['total_jobs'] == 7 for page in pages)
    assert [len(page['companies']) for page in pages] == [1, 0, 0, 0]
    assert [len(page['jobs']) for page in pages] == [2, 2, 2, 1]
    collected = [job['id'] for page in pages for job in page['jobs']]
    assert len(collected) == len(set(collected)) == 7
    assert set(collected) == job_ids


def test_custom_track_with_slash_can_be_favorited_and_removed(tmp_path):
    from urllib.parse import quote

    store = Store(tmp_path / 'slash-track')
    store.save('company_profile', 'employer1', {
        'name': '自填赛道企业', 'tracks': ['AI/产品'], 'description': '',
    })
    headers = {'x-role': 'student'}
    with client_for(store) as client:
        saved = client.post('/api/me/favorites', headers=headers,
                            json={'type': 'track', 'target_id': 'AI/产品'})
        assert saved.status_code == 200
        assert client.get('/api/me/favorites', headers=headers).json()[0]['target_id'] == 'AI/产品'
        removed = client.delete('/api/me/favorites/track/' + quote('AI/产品', safe=''), headers=headers)
        assert removed.status_code == 200
        assert client.get('/api/me/favorites', headers=headers).json() == []


def test_recommendation_prioritizes_selected_environment_over_industry_size(tmp_path):
    from backend.market import company_id, publish_market

    companies = []
    for track, size, title in [('电子与半导体', 80, '商业数据分析与管理'),
                               ('金融服务', 1, '银行运营'),
                               ('生物医药', 1, '医药研发')]:
        for index in range(size):
            name = f'{track}企业{index}'
            companies.append({
                'id': company_id(name), 'name': name, 'tracks': [track],
                'sources': ['失衡行业样本.csv'], 'history_count': 1,
                'search_terms': [title], 'raw_industries': [track],
                'historical_jobs': [{'title': title, 'source': {'file': '失衡行业样本.csv', 'line': index + 2}}],
            })
    store = Store(tmp_path / 'imbalanced-recommendation')
    publish_market(store, {'created_at': '2026-11-06', 'companies': companies, 'sources': []})
    headers = {'x-role': 'student'}
    with client_for(store) as client:
        response = client.post('/api/market/recommend', headers=headers, json={'answers': {
            'interests': ['商业与管理'], 'tasks': ['分析数据和规律'], 'environment': ['金融与商业'],
        }})
        recommendations = response.json()['recommendations']
        assert recommendations[0]['track'] == '金融服务'
        assert '金融与商业' in recommendations[0]['reason']
        assert recommendations[0]['evidence']['examples'][0]['source']['file'] == '失衡行业样本.csv'
        assert {row['track'] for row in recommendations} <= {'金融服务', '电子与半导体', '生物医药'}
        healthcare = client.post('/api/market/recommend', headers=headers, json={'answers': {
            'interests': ['商业与管理'], 'tasks': ['分析数据和规律'], 'environment': ['医疗与健康'],
        }}).json()['recommendations']
        assert healthcare[0]['track'] == '生物医药'
