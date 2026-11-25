"""企业招聘分配快照的可分享表格，仅包含执行计划所需的字段。"""
from io import BytesIO
from urllib.parse import quote

from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


RESOURCES = {'salary': '月度薪资（元）', 'training': '培训（元）', 'mentor': '导师（课时）'}


def plan_workbook(item, stale, visible, visible_offers):
    plan = item['data']
    book = Workbook()
    book.remove(book.active)

    def sheet(name, headings, rows, widths):
        tab = book.create_sheet(name)
        tab.append(headings)
        for row in rows:
            tab.append(row)
            for cell in tab[tab.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                    cell.alignment = Alignment(vertical='top', wrap_text=True)
        for cell in tab[1]:
            cell.fill = PatternFill('solid', fgColor='235B52')
            cell.font = Font(color='FFFFFF', bold=True)
        for index, width in enumerate(widths, 1):
            tab.column_dimensions[get_column_letter(index)].width = width
        tab.freeze_panes = 'A2'
        tab.auto_filter.ref = tab.dimensions

    usage = plan['result']['used']
    status = '超预算，未做新增分配' if plan.get('status') == 'overcommitted' else '已计算'
    total = plan.get('budget_scope') == 'total'
    sheet('招聘总览', ('项目', '记录', '可新增', '新增建议', '合计占用'), [
        ('招聘计划', f"v{plan['version']}"),
        ('保存时间', item['created']),
        ('数据与岗位版本', '已变化，请重算后执行' if stale else '当前版本'),
        ('预算口径', '企业总预算' if total else '历史新增预算'),
        ('状态', status),
        ('建议入选人数', len(plan['result']['selected'])),
        ('执行方式', '先核对名单，再通过站内发出正式意向。'),
        *((label, plan['budget'][key], plan.get('remaining_budget', {}).get(key), usage[key],
           plan.get('total_used', {}).get(key)) for key, label in RESOURCES.items()),
    ], (24, 51, 18, 18, 18))
    jobs = {job['id']: job for job in plan['jobs']}
    selected, pending = [], []
    for candidate in plan['candidates']:
        if candidate['application_id'] not in visible:
            pending.append(('已撤回投递', candidate['job_title'], candidate['job_version'], '投递授权已撤回'))
            continue
        reasons = '；'.join(candidate['reasons'])
        gaps = '；'.join(f"{row['skill']} {row['gap'] if row['gap'] is not None else '待核实'}"
                        for row in candidate['skill_gaps'])
        row = (candidate['student_name'], candidate['job_title'], candidate['job_version'])
        if candidate['selected']:
            job = jobs[candidate['job_id']]
            selected.append((*row, candidate.get('match_score'), job['salary_max'], job.get('training_cost', 0),
                             job.get('mentor_hours', 0), gaps))
        else:
            pending.append((*row, reasons, gaps))
    sheet('建议名单', ('候选人', '岗位', '岗位版本', '核验匹配分', *RESOURCES.values(), '技能缺口（级）'),
          selected, (21, 32, 13, 15, 20, 15, 15, 52))
    sheet('待办与未入选', ('候选人', '岗位', '岗位版本', '待办或未入选原因', '技能缺口（级）'),
          pending, (21, 32, 13, 55, 52))
    sheet('岗位名额', ('岗位', '岗位版本', '计算前可用名额', '建议人数', '建议分配后剩余'),
          ((job['title'], job['version'], job['capacity'], count, job['capacity'] - count)
           for job in jobs.values() for count in
           (sum(c['selected'] and c['job_id'] == job['id'] for c in plan['candidates']),)),
          (35, 13, 20, 14, 20))
    sheet('既有承诺', ('候选人', '岗位', '原岗位版本', '状态', *RESOURCES.values()),
          ((record['student_name'] if record['offer_id'] in visible_offers else '授权已变更',
            record['job_title'], record['job_version'],
            '已录用' if record['status'] == 'hired' else '已接受意向',
            *(record['resources'][key] for key in RESOURCES)) for record in plan.get('commitments', [])),
          (21, 32, 15, 17, 20, 15, 15))
    stream = BytesIO()
    book.save(stream)
    name = quote(f"招聘计划-v{plan['version']}.xlsx")
    return Response(stream.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{name}"})
