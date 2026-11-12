"""将教务导出的多工作表课表归并为课程，不推算缺失的学时或能力。"""
import hashlib
import io
import json
import math
import re
import zipfile

from openpyxl import load_workbook


MAX_COURSES = 10000
MAX_ROWS = 30000
ALIASES = {
    'code': ['code', '课程代码', '课程编码', '课程编号', '课程序号'],
    'name': ['name', '课程名称', '课程', '课名', '课程中文名称'],
    'credits': ['credits', '学分', '课程学分'],
    'hours': ['hours', '总学时', '学时', '总课时', '课程总学时'],
    'skills': ['skills', '能力标签', '对应技能'],
    'department': ['开课学院', '开课院系', '开课单位', '院系'],
    'campus': ['校区名称', '校区'],
    'academic_year': ['学年'],
    'semester': ['学期'],
    'section': ['教学班', '教学班号', '教学班编号'],
    'section_count': ['教学班数'],
    'category': ['课程性质', '课程类别'],
}
MULTI_FIELDS = {'department': 'departments', 'campus': 'campuses',
                'academic_year': 'academic_years', 'semester': 'semesters',
                'category': 'categories'}


def header_key(value):
    return re.sub(r'\s+', '', str(value or '')).strip().lower()


LOOKUP = {header_key(alias): key for key, aliases in ALIASES.items() for alias in aliases}


def detect_header(sheet):
    """优先选字段完整的表头，避免把“课程”标题当成单列表头。"""
    candidate = None
    for index, values in enumerate(sheet.iter_rows(max_row=30, values_only=True), 1):
        if len(values) > 200:
            raise ValueError(f'工作表“{sheet.title}”第{index}行超过200列')
        keys = [LOOKUP.get(header_key(value)) for value in values]
        if 'name' not in keys:
            continue
        score = len({key for key in keys if key})
        if candidate is None or score > candidate[0]:
            candidate = (score, index, keys)
    if candidate is None:
        return None, None
    _, index, keys = candidate
    useful = [key for key in keys if key]
    if len(useful) != len(set(useful)):
        raise ValueError(f'工作表“{sheet.title}”第{index}行含重复课程字段')
    return keys, index


def normalize_course(row):
    if not isinstance(row, dict):
        raise ValueError('课程记录必须是对象')
    fields = {LOOKUP.get(header_key(key), key): value for key, value in row.items()}
    name = str(fields.get('name') or '').strip()
    if not name:
        raise ValueError('缺少课程名称；若使用公式，请先在Excel中计算并另存为值')
    if len(name) > 200:
        raise ValueError('课程名称不能超过200字')
    code = str(fields.get('code') if fields.get('code') is not None else '').strip()
    result = {'code': code or hashlib.sha256(name.encode()).hexdigest()[:16], 'name': name}
    for key in ('credits', 'hours'):
        value = fields.get(key)
        if value is None or str(value).strip() in {'', '-', '—', '未提供'}:
            result[key] = None
        else:
            try:
                value = float(value)
            except (ValueError, TypeError):
                raise ValueError(f'{"学分" if key == "credits" else "总学时"}不是有效数值') from None
            if isinstance(fields[key], bool) or not math.isfinite(value) or not 0 <= value <= 10000:
                raise ValueError('学分和学时须为0至10000的有效数值，缺失请留空')
            result[key] = value
    skills = fields.get('skills') or []
    if isinstance(skills, str):
        skills = json.loads(skills) if skills.strip().startswith('[') else re.split('[,，;；、\n]', skills)
    if not isinstance(skills, list) or any(not isinstance(skill, str) for skill in skills):
        raise ValueError('能力标签应为文字列表')
    result['skills'] = list(dict.fromkeys(skill.strip()[:100] for skill in skills if skill.strip()))
    return result


def parse_schedule(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sum(item.file_size for item in archive.infolist()) > 60 * 1024 * 1024:
            raise ValueError('教务表解压体积超过60MB，请分批导入')
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    cached_book = None
    courses, sections, reported_sections, sheets, skipped = {}, {}, {}, [], []
    data_rows = scanned = 0
    try:
        cached_book = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
        for sheet in book:
            if sheet.max_column and sheet.max_column > 200:
                raise ValueError(f'工作表“{sheet.title}”超过200列，请仅保留教务数据区域')
            sheet_rows = 0
            # 某些教务导出错误声明A1:A1；从实际XML流读取完整行。
            sheet.reset_dimensions()
            headers, header_row = detect_header(sheet)
            if headers is None:
                skipped.append({'name': sheet.title, 'reason': '前30行未找到课程名称表头'})
                continue
            cached_sheet = cached_book[sheet.title]
            cached_sheet.reset_dimensions()
            for index, (cells, cached) in enumerate(zip(sheet.iter_rows(), cached_sheet.iter_rows(values_only=True)), 1):
                values = tuple(cached[i] if cell.data_type == 'f' else cell.value
                               for i, cell in enumerate(cells))
                scanned += 1
                if scanned > MAX_ROWS + 3000:
                    raise ValueError('工作簿行数过多，请分批导入（最多30000条课程安排）')
                if len(values) > 200:
                    raise ValueError(f'工作表“{sheet.title}”第{index}行超过200列')
                if index <= header_row:
                    continue
                if not any(value is not None and str(value).strip() for value in values):
                    continue
                keys = [LOOKUP.get(header_key(value)) for value in values]
                if 'name' in keys and sum(key is not None for key in keys) >= 2:
                    continue  # 分页重复表头。
                fields = {key: value for key, value in zip(headers, values) if key}
                for column, key in enumerate(headers):
                    if not key or column >= len(cells):
                        continue
                    cell = cells[column]
                    if cell.data_type == 'f' and fields.get(key) is None:
                        raise ValueError(f'工作表“{sheet.title}”第{index}行：课程字段公式缺少计算值，请在Excel中重新计算并另存')
                    if key == 'code' and isinstance(cell.value, (int, float)):
                        format_code = cell.number_format
                        if re.fullmatch('0{2,30}', format_code) and float(cell.value).is_integer():
                            fields['code'] = str(int(cell.value)).zfill(len(format_code))
                if not any(fields.get(key) is not None and str(fields[key]).strip() for key in ('code', 'name')):
                    if any(fields.get(key) not in (None, '') for key in ('credits', 'hours', 'section')):
                        raise ValueError(f'工作表“{sheet.title}”第{index}行缺少课程名称或代码')
                    continue
                if str(fields.get('name') or '').strip() in {'合计', '总计', '小计'} and not fields.get('code'):
                    continue
                try:
                    course = normalize_course(fields)
                    existing = courses.get(course['code'])
                    if existing:
                        for key, label in (('name', '课程名称'), ('credits', '学分'), ('hours', '总学时')):
                            old, new = existing[key], course[key]
                            if old is not None and new is not None and old != new:
                                raise ValueError(f'课程代码{course["code"]}的{label}冲突，请核对后导入')
                            if old is None:
                                existing[key] = new
                        existing['skills'] = list(dict.fromkeys(existing['skills'] + course['skills']))
                    else:
                        if len(courses) >= MAX_COURSES:
                            raise ValueError('每批最多10000门不同课程')
                        existing = courses[course['code']] = {**course, 'source_sheets': []}
                    if sheet.title not in existing['source_sheets']:
                        existing['source_sheets'].append(sheet.title)
                    for field, target in MULTI_FIELDS.items():
                        existing.setdefault(target, [])
                        for value in re.split('[;；]', str(fields.get(field) or '')):
                            value = value.strip()
                            if value and value not in existing[target]:
                                existing[target].append(value)
                    section = str(fields.get('section') or '').strip()
                    if section:
                        section_id = (str(fields.get('academic_year') or ''),
                                      str(fields.get('semester') or ''), section)
                        sections.setdefault(course['code'], set()).add(section_id)
                    count = fields.get('section_count')
                    if count is not None and str(count).strip():
                        value = float(count)
                        if not math.isfinite(value) or not value.is_integer() or not 0 <= value <= MAX_ROWS:
                            raise ValueError('教学班数应为0至30000的整数')
                        previous_count = reported_sections.get(course['code'])
                        if previous_count is not None and previous_count != int(value):
                            raise ValueError(f'课程代码{course["code"]}的教学班数冲突')
                        reported_sections[course['code']] = int(value)
                    sheet_rows += 1
                    data_rows += 1
                    if data_rows > MAX_ROWS:
                        raise ValueError('每批最多30000条课程安排')
                except ValueError as exc:
                    raise ValueError(f'工作表“{sheet.title}”第{index}行：{exc}') from None
            sheets.append({'name': sheet.title, 'header_row': header_row, 'data_rows': sheet_rows,
                           'fields': list(dict.fromkeys(key for key in headers if key))})
    finally:
        book.close()
        if cached_book is not None:
            cached_book.close()
    if not courses:
        raise ValueError('未找到可识别课程；请提供含课程名称（或课程、课名）表头的教务清单')
    for code, course in courses.items():
        course['section_count'] = len(sections[code]) if code in sections else reported_sections.get(code)
    return list(courses.values()), {
        'sheets': sheets, 'skipped_sheets': skipped, 'data_rows': data_rows,
        'unique_courses': len(courses), 'merged_rows': data_rows - len(courses),
        'missing_hours': sum(course['hours'] is None for course in courses.values()),
        'missing_skills': sum(not course['skills'] for course in courses.values()),
    }
