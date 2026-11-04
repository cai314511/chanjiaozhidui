import pytest

from backend.governance import month, redact, validate_source


def test_month_granularity():
    assert month('2026-10-23') == '2026-10'
    assert month('2026-10') == '2026-10'
    with pytest.raises(ValueError):
        month('2026-15')


def test_redaction_removes_structured_and_embedded_identifiers():
    result = redact({'name': '隔离测试姓名', 'company': '隔离测试企业', 'text': '联系13800138000或student@example.com'})
    assert '隔离测试姓名' not in str(result)
    assert '隔离测试企业' not in str(result)
    assert '13800138000' not in str(result)
    assert 'student@example.com' not in str(result)


def test_source_requires_permission_and_no_personal_collection():
    source = {'title': '测试来源声明', 'url': 'https://example.org/data', 'collected_at': '2026-11-03',
              'method': 'official_bundle', 'license_basis': '隔离测试用途声明', 'research_permitted': True,
              'contains_personal_data': False, 'split': 'development'}
    assert validate_source(source)['split'] == 'development'
    with pytest.raises(ValueError):
        validate_source({**source, 'research_permitted': False})
    with pytest.raises(ValueError):
        validate_source({**source, 'contains_personal_data': True})
