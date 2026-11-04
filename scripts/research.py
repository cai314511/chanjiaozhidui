import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.competition_api import public_result, report_markdown
from backend.competition_schemas import DecisionCase, Source
from backend.decision import run_decision
from backend.governance import clean_records, validate_source


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def records_from_file(path, mapping):
    path = Path(path)
    if path.suffix.lower() == '.json':
        data = read_json(path)
        rows = data.get('records', []) if isinstance(data, dict) else data
    elif path.suffix.lower() == '.csv':
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
    elif path.suffix.lower() == '.xlsx':
        book = load_workbook(path, read_only=True, data_only=True)
        iterator = book.active.iter_rows(values_only=True)
        header = next(iterator)
        if len(set(header)) != len(header):
            raise ValueError('表头重复')
        rows = [dict(zip(header, values)) for values in iterator]
        book.close()
    else:
        raise ValueError('支持JSON、CSV和XLSX')
    if len(rows) > 20000:
        raise ValueError('单批最多20000条，请按完整记录和统计范围拆分；禁止将部分样本当作完整年度需求')
    result = []
    for row in rows:
        renamed = {mapping.get(key, key): value for key, value in row.items() if value is not None and value != ''}
        if len(renamed) != len([v for v in row.values() if v is not None and v != '']):
            raise ValueError('字段映射导致同名列冲突')
        if isinstance(renamed.get('skills'), str):
            renamed['skills'] = json.loads(renamed['skills'])
        result.append(renamed)
    return result


def normalize(args):
    source = validate_source(Source.model_validate(read_json(args.source)).model_dump())
    if not source['redaction_reviewed']:
        raise ValueError('需要操作者完成来源脱敏审核声明')
    mapping = read_json(args.mapping) if args.mapping else {}
    rows, processing = clean_records(args.kind, records_from_file(args.input, mapping))
    package = {'source': source, 'kind': args.kind, 'records': rows, 'processing': processing,
               'sha256': hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(package, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'retained': len(rows), 'output': str(target.resolve())}, ensure_ascii=False))


def package(path, kind):
    data = read_json(path)
    source = validate_source(Source.model_validate(data['source']).model_dump())
    if source['split'] != 'development':
        raise ValueError('独立评测集不能用于生成或选择方案')
    if data['kind'] != kind or not source['redaction_reviewed']:
        raise ValueError('数据类型不符或尚未完成脱敏审核')
    rows, processing = clean_records(kind, data['records'])
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if data.get('sha256') and data['sha256'] != digest:
        raise ValueError('数据指纹不一致，源文件可能已经变化')
    return rows, {'source': source, 'processing': processing, 'sha256': digest}


def analyze(args):
    case = DecisionCase.model_validate(read_json(args.case)).model_dump()
    recruitment, rec_source = package(args.recruitment, 'recruitment')
    employment, emp_source = package(args.employment, 'employment') if args.employment else ([], None)
    result = run_decision(case, recruitment, employment)
    run = {'case': case, 'result': result, 'provenance': [rec_source] + ([emp_source] if emp_source else [])}
    target = Path(args.output)
    target.mkdir(parents=True, exist_ok=True)
    (target/'result.json').write_text(json.dumps(public_result(run), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (target/'report.md').write_text(report_markdown(run), encoding='utf-8')
    print(json.dumps({'status': result['status'], 'rounds': len(result['rounds']), 'output': str(target.resolve())}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description='产教智对可复核数据处理与专业决策；默认本地计算，不调用外部模型')
    commands = parser.add_subparsers(dest='command', required=True)
    normalize_parser = commands.add_parser('normalize', help='校验来源、映射字段并规范化')
    normalize_parser.add_argument('--source', required=True)
    normalize_parser.add_argument('--kind', choices=['recruitment', 'employment', 'policy'], required=True)
    normalize_parser.add_argument('--input', required=True)
    normalize_parser.add_argument('--mapping')
    normalize_parser.add_argument('--output', required=True)
    analyze_parser = commands.add_parser('analyze', help='重算固定输入的方案与四年情景')
    analyze_parser.add_argument('--case', required=True)
    analyze_parser.add_argument('--recruitment', required=True)
    analyze_parser.add_argument('--employment')
    analyze_parser.add_argument('--output', required=True)
    args = parser.parse_args()
    (normalize if args.command == 'normalize' else analyze)(args)


if __name__ == '__main__':
    main()
