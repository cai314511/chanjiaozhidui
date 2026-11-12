"""比赛招聘数据字典的共用读取、枚举映射和公告身份规则。"""

import csv
import hashlib
import json
import math
import re
import unicodedata
from datetime import date
from pathlib import Path


REQUIRED = {'企业名称', '招聘岗位', '工作城市', '最低月薪', '最高月薪', '职位描述', '招聘发布日期'}
EDUCATION = {
    '不限': '学历不限', '无学历要求': '学历不限', '学历不限': '学历不限',
    '中技/中专': '中专/中技', '中专/中技': '中专/中技',
    '专科': '大专', '大学专科': '大专', '大专': '大专',
    '大学本科': '本科', '本科': '本科', '硕士研究生': '硕士', '硕士': '硕士',
    '博士研究生': '博士', '博士': '博士',
}
EXPERIENCE = {
    '不限': '经验不限', '经验不限': '经验不限', '工作经验不限': '经验不限',
    '无经验': '无经验', '无工作经验': '无经验', '无需经验': '无经验',
    '应届生': '应届毕业生', '应届毕业生': '应届毕业生',
    '在校生/应届生': '在校生/应届毕业生',
}
EMPLOYMENT = {'全职': '全职', '全职工作': '全职', '兼职': '兼职', '实习': '实习',
              '实习生': '实习', '校园': '校园招聘', '校招': '校园招聘', '校园招聘': '校园招聘'}
RAW_FIELDS = {'education': '学历要求', 'experience': '要求经验', 'headcount': '招聘人数',
              'recruitment_category': '招聘类别', 'primary_category': '初级分类'}


def read_recruitment(path):
    """UTF-8 BOM、按列名读取；返回原始字符串及物理起始行，拒绝残缺行。"""
    path = Path(path)
    # csv 的限制是进程级，保持单调放宽，避免导入器相互缩小上限。
    csv.field_size_limit(max(csv.field_size_limit(), 16 * 1024 * 1024))
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle, strict=True)
        line = 1
        try:
            fields = next(reader, [])
            if not REQUIRED <= set(fields):
                raise ValueError(f'{path.name}缺少必要字段：{sorted(REQUIRED - set(fields))}')
            if len(fields) != len(set(fields)):
                raise ValueError(f'{path.name}包含重复列名')
            while True:
                line = reader.line_num + 1
                values = next(reader, None)
                if values is None:
                    break
                if not values:
                    continue
                if len(values) != len(fields):
                    raise ValueError(f'{path.name}第{line}行列数与表头不一致')
                yield line, dict(zip(fields, values))
        except csv.Error as exc:
            raise ValueError(f'{path.name}第{line}行CSV解析失败：{exc}') from exc


def salary_interval(low, high):
    try:
        low, high = float(low), float(high)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and 0 < v <= 1_000_000 for v in (low, high)) or low > high:
        return None
    return [round(low, 2), round(high, 2)]


def _text(value):
    return str(value or '').strip()


def _integer(value):
    text = _text(value)
    return int(text.split('.')[0]) if re.fullmatch(r'[0-9]+(?:\.0+)?', text) else None


def _salary_key(value):
    text = _text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    if number == 0:
        return None
    return round(number, 2) if math.isfinite(number) and 0 < number <= 1_000_000 else text


def _day(value, key, issues):
    text = _text(value)
    if not text:
        return ''
    if re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', text):
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            pass
    issues.append(key + '_invalid_date')
    return ''


def _year(raw, parsed_date, key, issues):
    year = _integer(raw)
    if _text(raw) and (year is None or not 1 <= year <= 9999):
        issues.append(key + '_invalid_year')
        year = None
    if parsed_date:
        actual = int(parsed_date[:4])
        if year is not None and year != actual:
            issues.append(key + '_year_mismatch')
        return actual
    return year


def normalize_recruitment(row):
    issues = []
    raw = {name: _text(row.get(field)) for name, field in RAW_FIELDS.items()}
    education = EDUCATION.get(raw['education'], raw['education'])
    exp = re.sub(r'\s+', '', raw['experience'])
    experience = EXPERIENCE.get(exp, exp)
    match = re.fullmatch(r'([0-9]+)年(?:及以上|以上)', exp)
    if match:
        experience = match[1] + '年及以上'
    # 不把“经验不限”“无经验”“应届毕业生”合成同一资格条件。
    types = sorted({EMPLOYMENT[value] for value in
                    (raw['recruitment_category'], raw['primary_category']) if value in EMPLOYMENT})
    headcount = _integer(re.sub(r'\s*人$', '', raw['headcount']).strip())
    headcount = headcount if headcount is not None and headcount > 0 else None
    stock = _text(row.get('关联股票代码'))
    if stock and re.fullmatch(r'[0-9]{1,6}', stock):
        stock = stock.zfill(6)
    elif stock:
        issues.append('invalid_stock_code')
        stock = ''
    published = _day(row.get('招聘发布日期'), 'published', issues)
    ended = _day(row.get('招聘结束日期'), 'ended', issues)
    if published and ended and ended < published:
        issues.append('end_before_publication')
    return {'education': education, 'experience': experience, 'headcount': headcount,
            'employment_type': '、'.join(types),
            'recruitment_category': '' if raw['recruitment_category'] in EMPLOYMENT else raw['recruitment_category'],
            'primary_category': '' if raw['primary_category'] in EMPLOYMENT else raw['primary_category'],
            'published': published, 'ended': ended,
            'published_year': _year(row.get('招聘发布年份'), published, 'published', issues),
            'ended_year': _year(row.get('招聘结束年份'), ended, 'ended', issues),
            'stock_code': stock, 'raw_requirements': raw, 'issues': issues}


def recruitment_fingerprint(row, normalized):
    """同法人名称、日期、岗位内容与资格条件才合并；渠道信息不作身份键。"""
    name = re.sub(r'\s+', '', unicodedata.normalize('NFKC', row['企业名称'])).casefold()
    salary = salary_interval(row['最低月薪'], row['最高月薪'])
    # 不把两个不同的单边报价或异常报价都变成 null 后误合并。
    salary_key = salary or [_salary_key(row['最低月薪']), _salary_key(row['最高月薪'])]
    payload = [name, _text(row['招聘岗位']), _text(row['工作城市']), _text(row.get('工作区域')),
               _text(row.get('工作地点')),
               salary_key, normalized['published'] or _text(row['招聘发布日期']),
               normalized['ended'] or _text(row.get('招聘结束日期')), row['职位描述'],
               normalized['education'], normalized['experience'], normalized['employment_type'],
               normalized['recruitment_category'], normalized['primary_category'],
               normalized['headcount'] if normalized['headcount'] is not None else normalized['raw_requirements']['headcount']]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
