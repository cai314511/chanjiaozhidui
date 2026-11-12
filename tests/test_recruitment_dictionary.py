"""字典契约：真实 CSV 读取、跨表清洗及三个消费者的统计结果。"""

import csv

import pytest

from backend.evidence import build_recruitment
from backend.market import build_market
from backend.university_intelligence import build_demand


def write_rows(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def base_row():
    return {'企业名称': '隔离企业', '招聘岗位': 'AI算法工程师', '工作城市': '北京',
            '最低月薪': '0.0', '最高月薪': '', '职位描述': 'Python开发',
            '招聘发布日期': '2026-03-01 ', '招聘结束日期': '2026-03-31 ',
            '招聘发布年份': '2026.0', '招聘结束年份': '2026.0',
            '学历要求': '中技/中专', '要求经验': '无工作经验', '招聘人数': '1 人',
            '招聘类别': '制药/生物工程', '初级分类': '全职', '来源': '平台59'}


@pytest.mark.parametrize('builder', [build_recruitment, build_market, build_demand])
def test_long_quoted_description_and_physical_source_lines(tmp_path, builder):
    long_row = {**base_row(), '职位描述': 'Python,"引号"\n' + '长正文' * 50000}
    path = write_rows(tmp_path / 'long.csv', [long_row, base_row()])
    result = builder([path])
    if builder is build_recruitment:
        assert result['scanned_rows'] == 2
        assert sorted(j['provenance'][0]['line'] for j in result['jobs']) == [2, 4]
    elif builder is build_market:
        assert result['companies'][0]['history_count'] == 2
        assert sorted(j['source']['line'] for j in result['companies'][0]['historical_jobs']) == [2, 4]
    else:
        assert result['source_meta']['deduplicated_postings'] == 2


@pytest.mark.parametrize('builder', [build_recruitment, build_market, build_demand])
def test_different_requirements_are_distinct_but_synonyms_deduplicate(tmp_path, builder):
    row = base_row()
    rows = [row, {**row, '学历要求': '中专/中技', '要求经验': '无经验', '招聘人数': '1'},
            {**row, '学历要求': '本科'}, {**row, '要求经验': '1-3年'},
            {**row, '招聘人数': '2人'}, {**row, '初级分类': '实习'}]
    result = builder([write_rows(tmp_path / 'requirements.csv', rows)])
    if builder is build_recruitment:
        assert len(result['jobs']) == 5
        assert result['duplicate_rows'] == 1
        original = next(j for j in result['jobs'] if len(j['provenance']) == 2)
        assert original['education'] == '中专/中技'
        assert original['experience'] == '无经验'
        assert original['headcount'] == 1
        assert original['employment_type'] == '全职'
        assert original['salary'] is None
        assert original['headcount_verified'] is False
        assert original['raw_requirements']['education'] == '中技/中专'
    elif builder is build_market:
        assert result['companies'][0]['history_count'] == 5
        assert result['duplicate_rows'] == 1
    else:
        assert result['source_meta']['deduplicated_postings'] == 5
        assert result['source_meta']['duplicate_rows'] == 1


def test_normalization_retains_identifiers_unknowns_and_year_issues():
    from backend.recruitment_data import normalize_recruitment

    result = normalize_recruitment({**base_row(), '关联股票代码': '2714',
        '统一社会信用代码': '00123456789012345X', '所属地区编码': '010001',
        '招聘发布年份': '2025.0', '招聘结束年份': '', '学历要求': '专升本待核',
        '要求经验': '1 年以上'})
    assert result['stock_code'] == '002714'
    assert result['published'] == '2026-03-01'
    assert result['ended'] == '2026-03-31'
    assert result['published_year'] == result['ended_year'] == 2026
    assert 'published_year_mismatch' in result['issues']
    assert result['education'] == '专升本待核'
    assert result['experience'] == '1年及以上'
    assert result['employment_type'] == '全职'
    assert result['recruitment_category'] == '制药/生物工程'


@pytest.mark.parametrize(('raw', 'expected'), [('若干', None), ('', None), ('3 人', 3),
    ('2.0', 2), ('1-3人', None), ('0', None), ('nan', None), ('-1', None)])
def test_headcount_is_planned_and_never_invented(raw, expected):
    from backend.recruitment_data import normalize_recruitment

    result = normalize_recruitment({**base_row(), '招聘人数': raw})
    assert result['headcount'] == expected


@pytest.mark.parametrize('builder', [build_recruitment, build_market, build_demand])
def test_invalid_date_suffix_is_not_silently_truncated(tmp_path, builder):
    path = write_rows(tmp_path / 'date.csv', [{**base_row(), '招聘发布日期': '2026-03-01无效'}])
    result = builder([path])
    if builder is build_recruitment:
        assert result['jobs'] == []
        assert result['invalid_dates'] == 1
    elif builder is build_market:
        assert result['companies'][0]['historical_jobs'][0]['published'] == ''
    else:
        assert result['groups'][0]['month'] == '日期未注明'
        assert result['source_meta']['invalid_dates'] == 1


def test_full_table_and_year_table_map_by_header_not_position(tmp_path):
    from backend.recruitment_data import read_recruitment, normalize_recruitment

    fields = ['企业名称', '股票简称', '关联股票代码', '与上市公司关系', '上市公司行业',
              '招聘发布年份', '招聘结束年份', '招聘岗位', '工作城市', '工作区域', '最低月薪',
              '最高月薪', '职位描述', '学历要求', '要求经验', '招聘人数', '招聘类别', '初级分类',
              '来源平台', '公司地点', '工作地点', '招聘发布日期', '招聘结束日期', '来源']
    row = {field: base_row().get(field, '') for field in fields}
    row.update({'来源平台': '马克数据网', '关联股票代码': '1'})
    full = write_rows(tmp_path / 'full.csv', [dict(reversed(list(row.items())))])
    yearly = write_rows(tmp_path / 'year.csv', [{key: value for key, value in row.items() if key != '来源平台'}])
    graduate = write_rows(tmp_path / 'graduate.csv', [{key: value for key, value in row.items()
        if key not in {'股票简称', '关联股票代码', '与上市公司关系', '上市公司行业'}}])
    _, loaded = next(read_recruitment(full))
    assert loaded['来源'] == '平台59'
    assert loaded['来源平台'] == '马克数据网'
    assert normalize_recruitment(loaded)['stock_code'] == '000001'
    assert next(read_recruitment(yearly))[1]['来源'] == '平台59'
    graduate_row = next(read_recruitment(graduate))[1]
    assert len(loaded) == 24
    assert len(next(read_recruitment(yearly))[1]) == 23
    assert len(graduate_row) == 20
    assert graduate_row['来源'] == '平台59'
    assert normalize_recruitment(graduate_row)['stock_code'] == ''


def test_reader_keeps_credit_and_administrative_codes_as_strings(tmp_path):
    from backend.recruitment_data import read_recruitment

    path = write_rows(tmp_path / 'identifiers.csv', [{**base_row(),
        '统一社会信用代码': '00123456789012345X', '所属地区编码': '010001'}])
    row = next(read_recruitment(path))[1]
    assert row['统一社会信用代码'] == '00123456789012345X'
    assert row['所属地区编码'] == '010001'


def test_malformed_csv_reports_file_and_row(tmp_path):
    path = write_rows(tmp_path / 'malformed.csv', [base_row()])
    with path.open('a', encoding='utf-8') as handle:
        handle.write('short,row\n')
    with pytest.raises(ValueError, match=r'malformed.csv.*第3行列数'):
        build_market([path])


def test_blank_lines_do_not_shift_physical_provenance(tmp_path):
    path = tmp_path / 'blank.csv'
    row = base_row()
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        handle.write('\n')
        writer.writerow(row)
    job = build_recruitment([path])['jobs'][0]
    assert job['provenance'][0]['line'] == 3


@pytest.mark.parametrize('builder', [build_recruitment, build_market, build_demand])
def test_same_city_different_workplace_postings_are_retained(tmp_path, builder):
    path = write_rows(tmp_path / 'workplaces.csv', [
        {**base_row(), '工作地点': '北京甲园区'}, {**base_row(), '工作地点': '北京乙园区'}])
    result = builder([path])
    if builder is build_recruitment:
        assert len(result['jobs']) == 2
    elif builder is build_market:
        assert result['companies'][0]['history_count'] == 2
    else:
        assert result['source_meta']['deduplicated_postings'] == 2


@pytest.mark.parametrize('builder', [build_recruitment, build_market, build_demand])
def test_zero_and_empty_salary_are_equivalent_unknown_quotes(tmp_path, builder):
    path = write_rows(tmp_path / 'unknown-salary.csv', [base_row(), {**base_row(), '最低月薪': ''}])
    result = builder([path])
    if builder is build_recruitment:
        assert len(result['jobs']) == 1
        assert result['jobs'][0]['salary'] is None
    elif builder is build_market:
        assert result['companies'][0]['history_count'] == 1
    else:
        assert result['source_meta']['deduplicated_postings'] == 1
