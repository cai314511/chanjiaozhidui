import csv
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.store import Store, now


def fixture_csvs(tmp_path):
    base = {'企业名称': '农业公司', '招聘岗位': '数据研究员', '上市公司行业': '农业',
            '工作城市': '北京', '最低月薪': '8000', '最高月薪': '10000',
            '职位描述': '熟悉Python、SQL和数据分析。联系人：王老师；13812345678',
            '招聘发布日期': '2026-01-02'}
    listed = [base, {**base, '招聘岗位': '算法工程师', '职位描述': 'Python机器学习', '招聘发布日期': '2026-02-01'},
              {**base, '企业名称': '医药公司', '上市公司行业': '医药制造业', '工作城市': '上海', '职位描述': 'SQL数据分析'}]
    graduate = [{key: value for key, value in base.items() if key != '上市公司行业'},
                {**base, '企业名称': '未知企业', '上市公司行业': '', '职位描述': '沟通协作'}]
    paths = []
    for name, rows in [('listed.csv', listed), ('graduate.csv', graduate)]:
        path = tmp_path / name
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(base))
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
    return paths


def client_for(store):
    from backend.university_intelligence import attach_university_intelligence
    app = FastAPI()

    def user(request: Request):
        role = request.headers.get('x-role')
        if not role:
            raise HTTPException(401, '请登录')
        return {'id': request.headers.get('x-user', 'school1'), 'role': role}

    attach_university_intelligence(app, store, user)
    return TestClient(app)


def add_student(store, ident, school='school1', skill='Python', level=2):
    with store.connect() as db:
        db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',
                   (ident, ident, '不应公开姓名' + ident, 'student', '', '', '', now()))
    store.save('profile', ident, {'school_id': school, 'career': '希望从事农业研究',
               'preferences': {'industries': ['农业']}, 'abilities': {skill: {'level': level, 'evidence': '私有能力证据'}}})
    store.save('market_exploration', ident, {'seen': True, 'answers': {'environment': ['金融与商业']}, 'text': '不应公开自由文字'})


def test_full_csv_aggregation_deduplicates_and_retains_every_posting(tmp_path):
    from backend.university_intelligence import build_demand
    bundle = build_demand(fixture_csvs(tmp_path))
    assert bundle['source_meta']['scanned_rows'] == 5
    assert bundle['source_meta']['deduplicated_postings'] == 4
    assert bundle['source_meta']['duplicate_rows'] == 1
    assert sum(group['postings'] for group in bundle['groups']) == 4
    agriculture = [group for group in bundle['groups'] if '农业' in group['tracks']]
    assert sum(group['postings'] for group in agriculture) == 2
    assert sum(group['skills'].get('Python', 0) for group in agriculture) == 2
    assert any(group['tracks'] == ['未分类'] for group in bundle['groups'])
    serialized = json.dumps(bundle, ensure_ascii=False)
    assert '王老师' not in serialized
    assert '13812345678' not in serialized
    assert '职位描述' not in serialized


def test_university_permissions_filters_and_live_updates_do_not_invent_levels(tmp_path):
    from backend.university_intelligence import build_demand, publish_demand
    store = Store(tmp_path / 'db')
    publish_demand(store, build_demand(fixture_csvs(tmp_path)))
    headers = {'x-role': 'university'}
    with client_for(store) as client:
        assert client.get('/api/university/intelligence').status_code == 401
        assert client.get('/api/university/intelligence', headers={'x-role': 'student'}).status_code == 403
        response = client.get('/api/university/intelligence', headers=headers).json()
        assert response['summary']['historical_postings'] == 4
        assert response['summary']['live_postings'] == 0
        python = next(skill for skill in response['skills'] if skill['name'] == 'Python')
        assert python['postings'] == 2
        assert python['student_level'] is python['target_level'] is python['gap'] is None
        assert all(row['course_count'] is None for row in response['coverage'])
        assert client.get('/api/university/intelligence?track=农业&city=北京', headers=headers).json()['summary']['historical_postings'] == 2
        job_id = store.save('job', 'employer1', {'company': '农业公司', 'industry': '农业', 'city': '北京',
                            'title': 'Python工程师', 'description': 'Python开发', 'requirements': [{'skill': 'Python', 'target': 4}]})
        updated = client.get('/api/university/intelligence?track=农业', headers=headers).json()
        assert updated['summary']['live_postings'] == 1
        python = next(skill for skill in updated['skills'] if skill['name'] == 'Python')
        assert python['target_level'] == 4
        assert python['gap'] is None
        store.save('job', 'employer1', {'company': '农业公司', 'industry': '农业', 'city': '北京',
                   'title': 'Python工程师', 'requirements': [{'skill': 'Python', 'target': 3}]}, job_id)
        assert next(row for row in client.get('/api/university/intelligence', headers=headers).json()['skills'] if row['name'] == 'Python')['target_level'] == 3


def test_school_aggregates_suppress_small_groups_and_exclude_other_schools(tmp_path):
    from backend.university_intelligence import build_demand, publish_demand
    store = Store(tmp_path / 'db')
    publish_demand(store, build_demand(fixture_csvs(tmp_path)))
    store.save('job', 'employer1', {'company': '农业公司', 'industry': '农业', 'city': '北京',
               'title': 'Python岗位', 'requirements': [{'skill': 'Python', 'target': 4}]})
    for index in range(4):
        add_student(store, 'student' + str(index))
        profile = store.list('profile', 'student' + str(index))[0]
        data = profile['data']
        data['abilities']['SQL'] = {'level': 3, 'evidence': '少量技能自述'}
        data['preferences']['industries'].append('生物医药')
        store.save('profile', profile['owner'], data, profile['id'])
    for index in range(6):
        add_student(store, 'outsider' + str(index), school='other-school', level=5)
    headers = {'x-role': 'university'}
    with client_for(store) as client:
        suppressed = client.get('/api/university/intelligence', headers=headers).json()
        assert suppressed['student_suppressed'] is True
        assert suppressed['summary']['student_count'] is None
        assert suppressed['student_goals'] == []
        assert all(row['student_count'] is None and row['student_level'] is None for row in suppressed['skills'])
        add_student(store, 'student4')
        visible = client.get('/api/university/intelligence', headers=headers).json()
        assert visible['summary']['student_count'] == 5
        python = next(row for row in visible['skills'] if row['name'] == 'Python')
        assert python['student_count'] == 5
        assert python['student_level'] == 2
        assert python['gap'] == 2
        sql = next(row for row in visible['skills'] if row['name'] == 'SQL')
        assert sql['student_count'] is sql['student_level'] is sql['gap'] is None
        assert {row['name'] for row in visible['student_goals']} == {'农业', '金融服务'}
        assert all(row['count'] == 5 for row in visible['student_goals'])
        serialized = json.dumps(visible, ensure_ascii=False)
        for secret in ['student0', 'outsider', '不应公开姓名', '私有能力证据', '不应公开自由文字']:
            assert secret not in serialized


def test_course_mapping_and_independent_publish_preserve_private_data(tmp_path):
    from backend.university_intelligence import build_demand, publish_demand
    store = Store(tmp_path / 'db')
    private = store.save('document', 'private-owner', {'text': 'private-data'})
    bundle = build_demand(fixture_csvs(tmp_path))
    publish_demand(store, bundle)
    publish_demand(store, bundle)
    store.save('university_profile', 'school1', {'program': {'courses': [
        {'id': 'python', 'name': '程序设计', 'skills': ['Python']},
        {'id': 'database', 'name': '数据库', 'skills': ['SQL']},
    ]}})
    with client_for(store) as client:
        response = client.get('/api/university/intelligence', headers={'x-role': 'university'}).json()
    counts = {row['skill']: row['course_count'] for row in response['coverage']}
    assert counts['Python'] == counts['SQL'] == 1
    assert counts['沟通协作'] == 0
    store.save('university_course_catalog', 'school1', {'courses': [
        {'code': 'imported', 'name': '未标注技能课程', 'skills': []},
    ]})
    with client_for(store) as client:
        assert all(row['course_count'] is None for row in client.get('/api/university/intelligence', headers={'x-role': 'university'}).json()['coverage'])
        publish_demand(store, {**bundle, 'groups': []})
        assert client.get('/api/university/intelligence', headers={'x-role': 'university'}).json()['summary']['historical_postings'] == 0
    assert len(store.list('demand_observatory')) == 1
    assert store.get(private)['data']['text'] == 'private-data'
