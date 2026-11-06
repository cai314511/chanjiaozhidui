import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, File, Form, HTTPException, Response, UploadFile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from lxml.etree import XMLSyntaxError
from pydantic import ValidationError

from backend import competition_schemas as c
from backend.decision import VERSION, changed_skills, demand_profile, run_decision, structural_score
from backend.governance import clean_records, contains_identifiers, validate_source
from backend.store import encode, now, uid


RULES = [
    {'id': 'gap', 'page': 'PDF第3–4页', 'requirement': '技能结构、培养方向、规模匹配三维差距', 'evidence': 'diagnosis'},
    {'id': 'courses', 'page': 'PDF第3–4页', 'requirement': '课程增删改合并及具体学时变化，满足培养方案硬约束', 'evidence': 'best.program'},
    {'id': 'directions', 'page': 'PDF第4页', 'requirement': '方向岗位一一对应、分流时点、成绩意愿和容量', 'evidence': 'best.split'},
    {'id': 'admissions', 'page': 'PDF第4页', 'requirement': '招生调整阈值、周期、幅度及反馈稳定性', 'evidence': 'best.forecast'},
    {'id': 'validation', 'page': 'PDF第3–4页', 'requirement': '四年推演、反事实、三情景及不确定性', 'evidence': 'best.forecast'},
    {'id': 'risks', 'page': 'PDF第3–4页', 'requirement': '至少三个方案绑定风险及责任主体、期限和应对', 'evidence': 'best.risks'},
    {'id': 'iteration', 'page': 'PDF第2页', 'requirement': '生成、评估、反思、优化闭环', 'evidence': 'rounds'},
    {'id': 'governance', 'page': 'PDF第6–7页', 'requirement': '合法来源、脱敏、薪资区间、月份粒度、可复核处理', 'evidence': 'provenance'},
    {'id': 'materials', 'page': 'PDF第3–4页', 'requirement': 'PDF报告、数据支撑、≤5分钟视频、答辩PPT', 'evidence': 'submission_checklist'},
    {'id': 'onsite', 'page': 'PDF第6页', 'requirement': '外网API赛前报备联调，备份不得代替现场推演', 'evidence': 'submission_checklist'},
]


def public_result(value):
    result = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))

    def visit(item):
        if isinstance(item, dict):
            item.pop('allocation', None)
            small_remainder = isinstance(item.get('unallocated'), int) and 0 < item['unallocated'] < 5
            if 'direction_counts' in item and (small_remainder or any(isinstance(n, int) and 0 < n < 5 for n in item['direction_counts'].values())):
                item['direction_counts'] = {key: '已抑制' for key in item['direction_counts']}
                item['allocated'] = item['unallocated'] = '已抑制'
                item['direction_gap_after'] = None
            if isinstance(item.get('unallocated'), int) and 0 < item['unallocated'] < 5:
                item['allocated'] = item['unallocated'] = '已抑制'
            if item.get('risk') == '方向分流受限':
                item['exposure'] = None
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
    visit(result)
    return result


def report_markdown(run):
    result, case = public_result(run['result']), run['case']
    diagnosis, best = result['diagnosis'], result['best']
    lines = ['# ' + case['title'], '', '模型版本：' + result['model'], '',
             '## 数据与用途', '', '以下结果来自登记来源和显式方案假设。', '',
             '```json', json.dumps(run['provenance'], ensure_ascii=False, indent=2), '```', '',
             '## 现状三维差距', '', '```json', json.dumps(diagnosis, ensure_ascii=False, indent=2), '```', '',
             '## 培养调整方案', '']
    if best:
        for change in best['program']['changes']:
            lines += ['### ' + change['action_id'], change['reason'], '']
            lines += [f"移除或替换：{course['name']}，{course['hours']}学时，{course['credits']}学分。" for course in change['removed']]
            lines += [f"新增或替换后：{course['name']}，{course['hours']}学时，{course['credits']}学分。" for course in change['added']]
        lines += ['', '## 分流与效果验证', '', '```json', json.dumps({'split': best['split'], 'forecast': best['forecast']}, ensure_ascii=False, indent=2), '```', '',
                  '## 风险与应对', '', '```json', json.dumps(best['risks'], ensure_ascii=False, indent=2), '```']
    else:
        lines += ['尚无有证据支持的改善方案；缺失内容和约束见结果记录。']
    lines += ['', '## 迭代与假设', '', result['assumptions'], '', '```json',
              json.dumps([{'iteration': r['iteration'], 'actions': r['action_ids'], 'reflection': r['reflection']} for r in result['rounds']], ensure_ascii=False, indent=2), '```', '',
              '## 参赛材料状态', '', '本文件为可复核分析正文导出，PDF排版、视频及答辩PPT需按提交要求分别制作和验收。']
    return '\n'.join(lines)


def attach_competition(app, store, user, role, owned, entity, flat):
    def researcher(current):
        role(current, ['university'])

    def dataset(ident, current, kind=None, evaluation=False):
        item = owned(ident, current, 'research_dataset')
        data = item['data']
        if kind and data['kind'] != kind:
            raise HTTPException(422, '数据模块类型不匹配')
        if data['split'] == 'evaluation' and not evaluation:
            raise HTTPException(422, '标准评测集独立封存，只能评估已确定方案，不能参与生成与选择')
        return item

    def checked_case(payload, current):
        dataset(payload.recruitment_id, current, 'recruitment')
        if payload.employment_id:
            dataset(payload.employment_id, current, 'employment')
        for ident in payload.policy_ids:
            dataset(ident, current, 'policy')
        data = payload.model_dump()
        if contains_identifiers(json.dumps(data, ensure_ascii=False)):
            raise HTTPException(422, '参赛培养方案含联系方式或个人标识，请脱敏后提交')
        return data

    @app.get('/api/competition/status')
    def status(current=Depends(user)):
        researcher(current)
        sources = store.list('research_source', current['id'])
        datasets = store.list('research_dataset', current['id'])
        return {'sources': len(sources), 'datasets': len(datasets), 'cases': len(store.list('decision_case', current['id'])),
                'runs': len(store.list('decision_run', current['id'])), 'rules': RULES,
                'official_scoring_weights': None, 'model': VERSION,
                'submission_checklist': [
                    {'item': '方案报告PDF', 'status': '需根据真实数据排版并验收'},
                    {'item': '数据支撑及可运行分析脚本', 'status': '已提供脚本，真实数据结果随实际导入生成'},
                    {'item': '演示视频≤5分钟', 'status': '待录制及核验时长'},
                    {'item': '现场答辩PPT', 'status': '待制作'},
                    {'item': 'DeepSeek外网API报备与赛前联调', 'status': '待向主办方报备并取得联调结果'},
                    {'item': '本地备份与现场当场推演', 'status': '本地引擎可运行，现场演示待验收'}]}

    @app.post('/api/competition/sources')
    def create_source(payload: c.Source, current=Depends(user)):
        researcher(current)
        try:
            data = validate_source(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        data['declaration'] = '使用权限与脱敏审核由登记操作者声明，评审可核查依据'
        ident = store.save('research_source', current['id'], data)
        store.audit(current['id'], 'register_research_source', ident)
        return flat(entity(ident))

    @app.get('/api/competition/sources')
    def sources(current=Depends(user)):
        researcher(current)
        return [flat(item) for item in store.list('research_source', current['id'])]

    def import_records(payload, current, original_hash=None):
        source = owned(payload.source_id, current, 'research_source')['data']
        if not source['redaction_reviewed']:
            raise HTTPException(422, '来源尚未完成操作者脱敏审核声明')
        if len(json.dumps(payload.records, ensure_ascii=False)) > 20_000_000:
            raise HTTPException(413, '单批结构化数据超过20MB，请按完整记录分批导入')
        try:
            records, processing = clean_records(payload.kind, payload.records)
        except (ValueError, ValidationError) as exc:
            # 不返回包含原始输入的Pydantic错误，避免把个人信息带入页面或日志。
            message = '字段或口径校验未通过，请检查数据模板' if isinstance(exc, ValidationError) else str(exc)
            raise HTTPException(422, message)
        digest = hashlib.sha256(json.dumps(records, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        def fingerprints(rows):
            return {hashlib.sha256(json.dumps({key: value for key, value in row.items() if key != 'record_id'},
                                             ensure_ascii=False, sort_keys=True).encode()).hexdigest() for row in rows}
        record_hashes = fingerprints(records)
        data = {'source_id': payload.source_id, 'kind': payload.kind, 'records': records, 'split': source['split'],
                'processing': processing, 'sha256': digest, 'original_sha256': original_hash,
                'source_snapshot': source, 'immutable': True, 'record_fingerprints': sorted(record_hashes)}
        ident, stamp = uid(), now()
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute("SELECT data FROM entities WHERE kind='research_dataset' AND owner=?", (current['id'],)).fetchall()
            for row in existing:
                previous = json.loads(row['data'])
                if previous['kind'] == payload.kind and previous['split'] != source['split']:
                    if record_hashes & set(previous.get('record_fingerprints') or fingerprints(previous['records'])):
                        raise HTTPException(422, '开发数据与独立评测数据存在内容重叠，不能重新标记后作为独立验证')
            db.execute('INSERT INTO entities VALUES(?,?,?,?,?,?)', (ident, 'research_dataset', current['id'], encode(data), stamp, stamp))
        store.audit(current['id'], 'import_governed_dataset', ident)
        return {key: value for key, value in flat(entity(ident)).items() if key not in {'records', 'record_fingerprints'}}

    @app.post('/api/competition/datasets')
    def create_dataset(payload: c.Dataset, current=Depends(user)):
        researcher(current)
        return import_records(payload, current)

    @app.post('/api/competition/datasets/import')
    async def upload_dataset(source_id: str = Form(...), kind: str = Form(...), file: UploadFile = File(...), current=Depends(user)):
        researcher(current)
        content = await file.read(12 * 1024 * 1024 + 1)
        if len(content) > 12 * 1024 * 1024:
            raise HTTPException(413, '单份文件不超过12MB；大型来源请使用分析脚本分批导入')
        suffix = Path(file.filename or '').suffix.lower()
        try:
            if suffix == '.json':
                decoded = json.loads(content.decode('utf-8-sig'))
                records = decoded['records'] if isinstance(decoded, dict) else decoded
            elif suffix == '.csv':
                reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
                if reader.fieldnames is None or len(set(reader.fieldnames)) != len(reader.fieldnames):
                    raise ValueError('表头为空或重复')
                records = []
                for row in reader:
                    if len(records) >= 20000:
                        raise HTTPException(413, '单批最多20000行')
                    records.append(row)
            elif suffix == '.xlsx':
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    if sum(i.file_size for i in archive.infolist()) > 60 * 1024 * 1024:
                        raise HTTPException(413, 'XLSX解压体积过大，请拆分后导入')
                book = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
                rows = book.active.iter_rows(values_only=True)
                headers = next(rows)
                if len(set(headers)) != len(headers):
                    raise ValueError('表头重复')
                records = []
                for row in rows:
                    if len(records) >= 20000:
                        raise HTTPException(413, '单批最多20000行')
                    records.append(dict(zip(headers, row)))
                book.close()
            else:
                raise HTTPException(422, '结构化导入支持JSON、CSV或XLSX')
            for record in records:
                for key in list(record):
                    if record[key] == '' or record[key] is None:
                        record.pop(key)
                if isinstance(record.get('skills'), str):
                    record['skills'] = json.loads(record['skills'])
            payload = c.Dataset(source_id=source_id, kind=kind, records=records)
        except (ValueError, KeyError, TypeError, StopIteration, zipfile.BadZipFile, InvalidFileException, XMLSyntaxError, csv.Error):
            raise HTTPException(422, '结构化文件无效，请核对模板；skills列使用JSON数组') from None
        return import_records(payload, current, hashlib.sha256(content).hexdigest())

    @app.get('/api/competition/datasets')
    def datasets(current=Depends(user)):
        researcher(current)
        return [{key: value for key, value in flat(item).items() if key not in {'records', 'record_fingerprints'}} for item in store.list('research_dataset', current['id'])]

    @app.get('/api/competition/datasets/{ident}')
    def read_dataset(ident: str, current=Depends(user)):
        researcher(current)
        return flat(dataset(ident, current, evaluation=True))

    @app.post('/api/competition/cases')
    def create_case(payload: c.DecisionCase, current=Depends(user)):
        researcher(current)
        data = checked_case(payload, current)
        ident = store.save('decision_case', current['id'], data)
        return flat(entity(ident))

    @app.get('/api/competition/cases')
    def cases(current=Depends(user)):
        researcher(current)
        return [flat(item) for item in store.list('decision_case', current['id'])]

    @app.post('/api/competition/cases/{ident}/run')
    def execute_case(ident: str, current=Depends(user)):
        researcher(current)
        case = owned(ident, current, 'decision_case')['data']
        rec = dataset(case['recruitment_id'], current, 'recruitment')
        emp = dataset(case['employment_id'], current, 'employment') if case.get('employment_id') else None
        policies = [dataset(i, current, 'policy') for i in case.get('policy_ids', [])]
        try:
            result = run_decision(case, rec['data']['records'], emp['data']['records'] if emp else [])
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        provenance = [{'dataset_id': d['id'], 'sha256': d['data']['sha256'], 'source': d['data']['source_snapshot'],
                       'processing': d['data']['processing']} for d in [rec, *([emp] if emp else []), *policies]]
        data = {'case_id': ident, 'case': case, 'result': result, 'provenance': provenance,
                'policy_use': '政策作为定性证据附件；未将政策文本直接折算为招聘人数或预测系数'}
        run_id = store.save('decision_run', current['id'], data)
        store.audit(current['id'], 'run_professional_decision', run_id)
        return {'id': run_id, **public_result(data)}

    @app.get('/api/competition/runs')
    def runs(current=Depends(user)):
        researcher(current)
        return [{'id': item['id'], 'title': item['data']['case']['title'], 'created': item['created'],
                 'status': item['data']['result']['status']} for item in store.list('decision_run', current['id'])]

    @app.get('/api/competition/runs/{ident}')
    def run(ident: str, current=Depends(user)):
        researcher(current)
        return public_result(flat(owned(ident, current, 'decision_run')))

    @app.get('/api/competition/runs/{ident}/export')
    def export(ident: str, format: str = 'json', current=Depends(user)):
        researcher(current)
        data = owned(ident, current, 'decision_run')['data']
        if format == 'json':
            output, media = json.dumps(public_result(data), ensure_ascii=False, indent=2, allow_nan=False), 'application/json'
        elif format == 'md':
            output, media = report_markdown(data), 'text/markdown'
        elif format == 'csv':
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(['动作', '课程', '调整前学时', '调整后学时', '调整前学分', '调整后学分'])
            best = data['result']['best']
            for change in best['program']['changes'] if best else []:
                old = {course['id']: course for course in change['removed']}
                new = {course['id']: course for course in change['added']}
                for key in old.keys() | new.keys():
                    before, after = old.get(key, {}), new.get(key, {})
                    name = after.get('name', before.get('name', key))
                    if name.startswith(('=', '+', '-', '@')):
                        name = "'" + name
                    writer.writerow([change['kind'], name, before.get('hours', 0), after.get('hours', 0), before.get('credits', 0), after.get('credits', 0)])
            output, media = '\ufeff' + stream.getvalue(), 'text/csv'
        else:
            raise HTTPException(422, '支持json、csv和md导出')
        return Response(output, media_type=media, headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote('智链产教分析.' + format)})

    @app.post('/api/competition/runs/{ident}/evaluate/{dataset_id}')
    def evaluate(ident: str, dataset_id: str, current=Depends(user)):
        researcher(current)
        run_data = owned(ident, current, 'decision_run')['data']
        test = dataset(dataset_id, current, 'recruitment', evaluation=True)['data']
        if test['split'] != 'evaluation':
            raise HTTPException(422, '本入口仅接受独立评测集')
        best = run_data['result']['best']
        if not best:
            raise HTTPException(422, '没有已确定的改善方案可供独立评测')
        case = run_data['case']
        selected = [a for a in case['actions'] if a['id'] in best['action_ids']]
        records = [r for r in test['records'] if r['region'] == case['program']['region']]
        if not records:
            raise HTTPException(422, '评测集无对应地区记录')
        targets = demand_profile(records)['skills']
        result = {'frozen_run_id': ident, 'evaluation_dataset_id': dataset_id,
                  'before': structural_score(targets, case['program']['skills']),
                  'after': structural_score(targets, changed_skills(case['program'], selected)),
                  'scope': '固定方案在保留招聘证据上的结构匹配检验；不用于再次挑选方案'}
        evaluation_id = store.save('decision_evaluation', current['id'], result)
        return {'id': evaluation_id, **result}

    @app.get('/api/competition/templates/{name}')
    def template(name: str, current=Depends(user)):
        researcher(current)
        if name == 'program':
            template_file = Path(__file__).resolve().parents[1]/'docs'/'templates'/'program-input.json'
            return Response(template_file.read_text(encoding='utf-8'), media_type='application/json',
                            headers={'Content-Disposition': 'attachment; filename="program-input.json"'})
        schemas = {'case': c.DecisionCase, 'recruitment': c.Recruitment, 'employment': c.Employment, 'policy': c.Policy, 'source': c.Source}
        if name not in schemas:
            raise HTTPException(404, '模板不存在')
        body = {'description': '空白字段规范，不含真实或演示结果；按字段说明填写后导入', 'schema': schemas[name].model_json_schema()}
        return Response(json.dumps(body, ensure_ascii=False, indent=2), media_type='application/json',
                        headers={'Content-Disposition': 'attachment; filename="' + name + '.schema.json"'})
