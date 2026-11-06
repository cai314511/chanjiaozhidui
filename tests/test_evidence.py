import json

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.evidence import build_recruitment, publish_bundle, salary_interval
from backend.store import Store


def test_salary_units_unknown_and_reversed_are_not_invented():
    assert salary_interval('8000.0', '15000.0') == [8000, 15000]
    assert salary_interval('', '15000') is None
    assert salary_interval('面议', '') is None
    assert salary_interval('15000', '8000') is None
    assert salary_interval('nan', '10000') is None


def test_non_ai_english_titles_do_not_match_by_substring():
    from backend.evidence import classify

    assert classify('Retail Manager', '') is None
    assert classify('AI产品经理', '') == 'AI产品'
    assert classify('数据分析师', '货币金融服务') == '金融科技'


def test_real_csv_pipeline_preserves_provenance_and_deduplicates(tmp_path):
    import csv

    paths = []
    row = {'企业名称': '内部企业甲', '招聘岗位': 'AI产品经理', '工作城市': '北京',
           '最低月薪': '10000', '最高月薪': '20000', '职位描述': '熟悉Python和SQL。联系人：张三；13812345678 test@example.com 内部企业甲',
           '招聘发布日期': '2026-03-01', '学历要求': '本科', '要求经验': '无需经验', '招聘人数': ''}
    for name in ['上市公司', '应届生']:
        path = tmp_path / (name + '.csv')
        with path.open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
            writer.writerow({**row, '招聘岗位': '餐厅服务员'})
        paths.append(path)
    result = build_recruitment(paths)
    assert result['scanned_rows'] == 4
    assert result['matched_rows'] == 2
    assert result['duplicate_rows'] == 1
    assert len(result['jobs']) == 1
    job = result['jobs'][0]
    assert len(job['provenance']) == 2
    assert job['month'] == '2026-03'
    assert job['salary'] == [10000, 20000]
    assert job['skills'] == ['Python', 'SQL']
    assert 'level' not in json.dumps(job)
    assert job['headcount'] is None
    serialized = json.dumps(result, ensure_ascii=False)
    for secret in ['内部企业甲', '13812345678', 'test@example.com', '张三']:
        assert secret not in serialized


def test_bundle_is_atomic_idempotent_and_requires_login(tmp_path):
    store = Store(tmp_path)
    bundle = {'version': 1, 'created_at': '2026-11-05', 'recruitment': {'jobs': [], 'scanned_rows': 0},
              'documents': [], 'inventory': [], 'scope': '隔离验收资料'}
    publish_bundle(store, bundle)
    publish_bundle(store, bundle)
    private = store.save('document', 'other-owner', {'name': '其他账号私有资料', 'blocks': [{'text': 'private-secret'}]})
    assert len(store.list('competition_evidence')) == 1
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/evidence/summary').status_code == 401
        response = client.post('/api/auth/register', json={'username': 'evidence-student', 'password': 'test-password-123', 'name': '隔离学生', 'role': 'student'})
        assert response.status_code == 200
        assert client.get('/api/evidence/summary').status_code == 200
        assert client.get('/api/evidence/jobs').json()['total'] == 0
        assert client.get('/api/evidence/documents/../../private').status_code in {404, 422}
        assert client.get('/api/evidence/documents/missing').status_code == 404
        assert client.get('/api/evidence/documents/' + private).status_code == 404
        assert 'private-secret' not in client.get('/api/evidence/documents').text
        assert client.get('/api/health').json()['name'] == '智链产教'


def test_unsearchable_pdf_is_not_reported_as_extracted(tmp_path):
    import fitz
    from backend.evidence import extract_reference

    folder = tmp_path / '本科生就业报告'
    folder.mkdir()
    path = folder / '隔离编码异常.pdf'
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), 'Unreadable encoded report')
        document.save(path)
    reference = extract_reference(path, tmp_path)
    assert reference['blocks'] == []
    assert '待OCR' in reference['status']


def test_same_text_from_distinct_employers_or_dates_is_not_merged(tmp_path):
    import csv

    path = tmp_path / '独立公告.csv'
    common = {'企业名称': '机构甲', '招聘岗位': 'AI产品经理', '工作城市': '北京',
              '最低月薪': '10000', '最高月薪': '20000', '职位描述': '熟悉Python', '招聘发布日期': '2026-03-01'}
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(common))
        writer.writeheader()
        writer.writerows([common, {**common, '企业名称': '机构乙'}, {**common, '招聘发布日期': '2026-03-02'}])
    result = build_recruitment([path])
    assert len(result['jobs']) == 3
    assert result['duplicate_rows'] == 0
    assert '机构甲' not in json.dumps(result, ensure_ascii=False)
