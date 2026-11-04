import hashlib
import json
import re
from datetime import date
from urllib.parse import urlsplit


IDENTIFIERS = [
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    re.compile(r"(?<!\d)0\d{2,3}[- ]?\d{7,8}(?!\d)"),
    re.compile(r"(?:详细地址|家庭住址|住址|联系地址)[：:][^\n；;]{3,100}"),
    re.compile(r"(?:姓名|学生姓名|联系人|企业名称|公司名称|学号)[：:]\s*[^\n，。；;]{1,80}"),
]
SENSITIVE_KEYS = {"company", "company_name", "employer_name", "contact", "phone", "email", "address",
                  "username", "school_code", "school_id", "owner", "student_id", "reviewer", "actor",
                  "企业名称", "公司名称", "姓名", "联系人", "联系方式", "联系电话", "详细地址", "身份证", "学号"}
SAFE_NAME_PATHS = {"skills", "courses", "directions", "actions", "add_courses"}


def month(value):
    value = str(value).strip()
    if len(value) not in {7, 10}:
        raise ValueError("日期应为YYYY-MM或YYYY-MM-DD")
    parsed = date.fromisoformat(value + '-01' if len(value) == 7 else value)
    return parsed.strftime('%Y-%m')


def contains_identifiers(text):
    return any(pattern.search(str(text)) for pattern in IDENTIFIERS)


def redact(value, path=()):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            sensitive = key in SENSITIVE_KEYS or key == 'name' and not set(path) & SAFE_NAME_PATHS
            result[key] = '[已泛化]' if sensitive else redact(item, (*path, key))
        return result
    if isinstance(value, list):
        return [redact(item, path) for item in value]
    if isinstance(value, str):
        for pattern in IDENTIFIERS:
            value = pattern.sub('[已脱敏]', value)
        return value
    return value


def validate_source(source):
    if not source.get('research_permitted'):
        raise ValueError('来源许可未确认允许研究分析，不能进入参赛研究数据域')
    if source.get('contains_personal_data'):
        raise ValueError('参赛研究数据不得采集含个人信息的记录，请先在合法来源完成脱敏')
    if not str(source.get('license_basis', '')).strip():
        raise ValueError('缺少来源许可及使用权限依据')
    date.fromisoformat(source['collected_at'])
    url = source.get('url', '')
    if url:
        parts = urlsplit(url)
        if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
            raise ValueError('公开来源地址必须为无凭证的HTTPS地址')
    elif not source.get('reference'):
        raise ValueError('来源必须有公开地址或官方数据包定位')
    if source.get('method') == 'authorized_public' and not url:
        raise ValueError('公开采集数据必须登记公开来源地址')
    if contains_identifiers(json.dumps(source, ensure_ascii=False)):
        raise ValueError('来源登记含可识别联系方式或个人标识，请清除后登记')
    return source


def clean_records(kind, records):
    from backend.competition_schemas import Employment, Policy, Recruitment
    model = {'recruitment': Recruitment, 'employment': Employment, 'policy': Policy}[kind]
    seen, clean, removed, duplicates = set(), [], 0, 0
    employment_keys, record_ids, probable = set(), {}, {}
    for row in records:
        removed += sum(key in SENSITIVE_KEYS for key in row)
        filtered = {key: value for key, value in row.items() if key not in SENSITIVE_KEYS}
        if contains_identifiers(json.dumps(filtered, ensure_ascii=False)):
            raise ValueError('发现可识别联系方式或个人标识，停止导入；请先完成来源数据脱敏')
        result = model.model_validate(filtered).model_dump()
        if kind == 'policy':
            result['month'] = month(result['month'])
        canonical = result
        digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if digest in seen:
            duplicates += 1
            continue
        if kind == 'recruitment':
            if result['record_id'] in record_ids:
                raise ValueError('同一招聘记录标识对应不同内容，请核对重复发布和更新关系')
            record_ids[result['record_id']] = digest
            identity_free = {key: value for key, value in result.items() if key != 'record_id'}
            group = hashlib.sha256(json.dumps(identity_free, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            probable[group] = probable.get(group, 0) + 1
        if kind == 'employment':
            key = (result['program_code'], result['year'])
            if key in employment_keys:
                raise ValueError('同一专业同一年份有不同就业汇总记录，请先核对统计口径')
            employment_keys.add(key)
        seen.add(digest)
        clean.append(result)
    return clean, {'input_count': len(records), 'retained_count': len(clean), 'duplicates_removed': duplicates,
                   'identifier_columns_removed': removed, 'date_granularity': 'year' if kind == 'employment' else 'month',
                   'salary_format': {'recruitment': 'interval', 'employment': 'mean_with_sample_count', 'policy': 'not_applicable'}[kind], 'human_redaction_review_required': True,
                   'possible_duplicate_groups': sum(v > 1 for v in probable.values()),
                   'dedup_basis': '只自动移除完全重复记录；内容相同但记录标识不同的公告保留并标记人工复核'}


def model_gateway(message, context, names=()):
    if contains_identifiers(message):
        raise ValueError('问题中含联系方式、身份证或详细地址，请移除后发送')
    def known_identifiers(value):
        if isinstance(value, str):
            for name in names:
                if name and len(name) >= 2:
                    value = value.replace(name, '[身份已泛化]')
            return value
        if isinstance(value, dict):
            return {key: known_identifiers(item) for key, item in value.items()}
        if isinstance(value, list):
            return [known_identifiers(item) for item in value]
        return value
    message = known_identifiers(message)
    sanitized = known_identifiers(redact(context))
    # 个人学校名称不影响能力分析，向外部模型发送时统一泛化。
    def visit(item):
        if isinstance(item, dict):
            return {key: '[院校已泛化]' if key == 'school_name' else visit(value) for key, value in item.items()}
        if isinstance(item, list):
            return [visit(value) for value in item]
        return item
    return message, visit(sanitized)


def check_model_output(result):
    text = json.dumps(result, ensure_ascii=False)
    if contains_identifiers(text):
        raise ValueError('模型结果含可识别个人信息，已阻止展示，请缩小任务范围后重试')
    result['content_review'] = {'identifier_check': 'passed', 'human_review': 'required',
                                'scope': '规则扫描不能替代人工内容与事实审核'}
    return result
