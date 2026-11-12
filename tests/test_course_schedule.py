"""全校教务课表的多校区、教学班归并与原子校验。"""
import io

from openpyxl import Workbook, load_workbook

from tests.test_university_courses import school_system


def workbook_bytes(sheets):
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    content = io.BytesIO()
    book.save(content)
    return content.getvalue()


def upload(client, content):
    return client.post('/api/university/materials/import', files={
        'file': ('全校课表.xlsx', content,
                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
    }, data={'kind': 'teaching'})


def test_all_sheets_title_rows_and_teaching_sections_are_merged(school_system):
    _, client = school_system
    header = ['学年', '学期', '校区名称', '开课学院', '课程代码', '课程', '学分', '教学班']
    content = workbook_bytes({
        '校区一': [['全校开课课表'], [], header,
                  ['2026-2027', '1', '校区一', '经济学院', '00101', '计量经济学', '3.0', '班01'],
                  ['2026-2027', '1', '校区一', '经济学院', '00101', '计量经济学', '3', '班02']],
        '校区二': [header,
                  ['2026-2027', '1', '校区二', '经济学院', '00101', '计量经济学', 3, '班03'],
                  ['2026-2027', '1', '校区二', '统计学院', '00102', '统计实践', 2, '班04']],
        '说明': [['本表包含两个校区']],
    })
    response = upload(client, content)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['imported_courses'] == 2
    assert result['recognition']['data_rows'] == 4
    assert result['recognition']['merged_rows'] == 2
    courses = client.get('/api/university/courses').json()['courses']
    first = next(c for c in courses if c['code'] == '00101')
    assert first['credits'] == 3
    assert first['hours'] is None
    assert first['skills'] == []
    assert first['campuses'] == ['校区一', '校区二']
    assert first['section_count'] == 3
    assert upload(client, content).status_code == 200
    assert len(client.get('/api/university/courses').json()['courses']) == 2
    exported = client.get('/api/university/courses/export')
    assert exported.status_code == 200
    book = load_workbook(io.BytesIO(exported.content), data_only=False)
    assert book.active.max_row == 3
    assert book.active['A2'].value == '00101'


def test_conflicting_credits_reject_whole_workbook(school_system):
    _, client = school_system
    header = ['课程代码', '课程名称', '学分']
    response = upload(client, workbook_bytes({'A': [header, ['C1', '课程一', 3]],
                                               'B': [header, ['C1', '课程一', 4]]}))
    assert response.status_code == 422
    assert 'B' in response.json()['detail']
    assert '学分' in response.json()['detail']
    assert client.get('/api/university/courses').json()['courses'] == []


def test_repeated_headers_blank_rows_and_formula_text_export(school_system):
    _, client = school_system
    header = ['课程编号', '课名', '学分', '总课时']
    response = upload(client, workbook_bytes({'课程': [header, ['C1', '=测试课程', 2, 32],
                                                       header, [], ['C2', '数据实践', 3, 48]]}))
    # 字符串公式没有缓存，不能被当成空白行静默跳过。
    assert response.status_code == 422
    response = client.post('/api/university/materials/import', files={
        'file': ('课程.csv', '课程代码,课程名称,学分\nC1,=测试课程,2\n'.encode(), 'text/csv'),
    })
    assert response.status_code == 200
    book = load_workbook(io.BytesIO(client.get('/api/university/courses/export').content))
    assert book.active['B2'].data_type == 's'
    assert book.active['B2'].value == '=测试课程'


def test_reimport_schedule_preserves_confirmed_fields_missing_from_export(school_system):
    _, client = school_system
    original = '课程代码,课程名称,学分,总学时,能力标签\nC1,数据实践,3,48,Python\n'.encode()
    assert client.post('/api/university/materials/import', files={
        'file': ('课程映射.csv', original, 'text/csv'),
    }).status_code == 200
    content = workbook_bytes({'课表': [['课程代码', '课程', '学分'], ['C1', '数据实践', 3]]})
    assert upload(client, content).status_code == 200
    course = client.get('/api/university/courses').json()['courses'][0]
    assert course['hours'] == 48
    assert course['skills'] == ['Python']
    assert course['field_sources']['hours']['name'] == '课程映射.csv'


def test_repeated_headers_and_blank_lines_do_not_become_courses(school_system):
    _, client = school_system
    header = ['课程编号', '课名', '学分', '总课时']
    content = workbook_bytes({'课程': [header, ['C1', '数据实践', 3, 48], header,
                                          [], ['C2', '统计学', 2, 32]]})
    result = upload(client, content)
    assert result.status_code == 200, result.text
    assert result.json()['imported_courses'] == 2


def test_numeric_course_codes_keep_excel_leading_zero_format(school_system):
    _, client = school_system
    book = Workbook()
    book.active.append(['课程代码', '课程', '学分'])
    book.active.append([123, '数据实践', 3])
    book.active['A2'].number_format = '0000000'
    content = io.BytesIO()
    book.save(content)
    assert upload(client, content.getvalue()).status_code == 200
    assert client.get('/api/university/courses').json()['courses'][0]['code'] == '0000123'


def test_uncalculated_formula_in_credit_field_is_not_silently_missing(school_system):
    _, client = school_system
    content = workbook_bytes({'课程': [['课程代码', '课程', '学分'], ['C1', '数据实践', '=1+2']]})
    response = upload(client, content)
    assert response.status_code == 422
    assert '公式' in response.json()['detail']
    assert client.get('/api/university/courses').json()['courses'] == []


def test_export_reimport_preserves_metadata_lists_and_section_counts(school_system):
    _, client = school_system
    header = ['课程代码', '课程名称', '学分', '校区名称', '开课学院', '教学班', '课程性质']
    content = workbook_bytes({'一': [header, ['C1', '数据实践', 3, '校区一', '学院一', '班一', '必修课']],
                              '二': [header, ['C1', '数据实践', 3, '校区二', '学院二', '班二', '选修课']]})
    assert upload(client, content).status_code == 200
    before = client.get('/api/university/courses').json()['courses'][0]
    assert upload(client, client.get('/api/university/courses/export').content).status_code == 200
    after = client.get('/api/university/courses').json()['courses'][0]
    for key in ('campuses', 'departments', 'section_count', 'categories'):
        assert after[key] == before[key]


def test_generic_course_title_does_not_override_real_header(school_system):
    _, client = school_system
    content = workbook_bytes({'教务表': [['课程'], ['2026年全校开课清单'],
                                          ['课程代码', '课程名称', '学分'], ['C1', '计量经济学', 3]]})
    response = upload(client, content)
    assert response.status_code == 200, response.text
    courses = client.get('/api/university/courses').json()['courses']
    assert len(courses) == 1
    assert courses[0]['code'] == 'C1'
    assert courses[0]['name'] == '计量经济学'
    assert courses[0]['credits'] == 3
