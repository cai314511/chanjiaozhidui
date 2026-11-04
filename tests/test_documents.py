import hashlib
import io

import pytest
from docx import Document
from openpyxl import Workbook

from backend.documents import extract


def test_docx_extract_keeps_paragraph_and_table_evidence():
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph('培养目标：能够独立完成产品需求分析')
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = '课程'
    table.cell(0, 1).text = '产品设计'
    document.save(stream)
    content = stream.getvalue()
    result = extract('培养方案.docx', content)
    assert result['sha256'] == hashlib.sha256(content).hexdigest()
    assert result['blocks'][0]['location'] == '段落1'
    assert result['blocks'][1]['text'] == '课程 | 产品设计'


def test_xlsx_extract_preserves_sheet_and_row():
    book = Workbook()
    book.active.title = '岗位证据'
    book.active.append(['岗位', '技能'])
    book.active.append(['AI产品经理', '需求分析'])
    stream = io.BytesIO()
    book.save(stream)
    result = extract('岗位.xlsx', stream.getvalue())
    assert result['blocks'][1]['location'] == '岗位证据第2行'
    assert result['blocks'][1]['text'] == 'AI产品经理 | 需求分析'


def test_csv_quoted_newline_uses_mature_csv_reader():
    result = extract('岗位.csv', '岗位,要求\n产品经理,"用户研究\n指标验证"'.encode())
    assert result['blocks'][1]['text'] == '产品经理 | 用户研究\n指标验证'


def test_unsupported_format_rejected():
    with pytest.raises(ValueError):
        extract('秘密.exe', b'content')
