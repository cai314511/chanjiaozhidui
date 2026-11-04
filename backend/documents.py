import csv
import hashlib
import io
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader


ALLOWED = {".txt", ".md", ".csv", ".docx", ".pdf", ".xlsx"}
MAX_SIZE = 12 * 1024 * 1024


def extract(name, content):
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED:
        raise ValueError("支持 TXT、MD、CSV、DOCX、PDF、XLSX")
    if len(content) > MAX_SIZE:
        raise ValueError("文档不得超过12MB")
    blocks = []
    if suffix in {".txt", ".md", ".csv"}:
        text = content.decode("utf-8-sig")
        lines = list(csv.reader(io.StringIO(text))) if suffix == ".csv" else [[line] for line in text.splitlines()]
        blocks = [{"location": f"第{i+1}行", "text": " | ".join(row)} for i, row in enumerate(lines) if any(row)]
    elif suffix == ".docx":
        import zipfile
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 60 * 1024 * 1024:
                raise ValueError("DOCX解压体积过大")
        document = Document(io.BytesIO(content))
        blocks = [{"location": f"段落{i+1}", "text": p.text} for i, p in enumerate(document.paragraphs) if p.text.strip()]
        blocks += [{"location": f"表格{j+1}第{i+1}行", "text": " | ".join(c.text for c in row.cells)}
                   for j, table in enumerate(document.tables) for i, row in enumerate(table.rows)]
    elif suffix == ".pdf":
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > 300:
            raise ValueError("单次上传PDF最多300页")
        blocks = [{"location": f"第{i+1}页", "text": page.extract_text() or ""} for i, page in enumerate(reader.pages)]
    else:
        import zipfile
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > 60 * 1024 * 1024:
                raise ValueError("XLSX解压体积过大")
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        for sheet in workbook:
            for i, row in enumerate(sheet.iter_rows(values_only=True)):
                if len(blocks) >= 10000:
                    raise ValueError("单次上传最多读取10000行，请拆分资料")
                blocks.append({"location": f"{sheet.title}第{i+1}行", "text": " | ".join(str(v) if v is not None else "" for v in row)})
        workbook.close()
    blocks = [b for b in blocks if b["text"].strip()]
    if not blocks:
        raise ValueError("未提取到文字；扫描版PDF请先进行OCR")
    if sum(len(b["text"]) for b in blocks) > 500000:
        raise ValueError("正文超过50万字符，请拆分资料")
    return {"name": Path(name).name, "sha256": hashlib.sha256(content).hexdigest(), "blocks": blocks,
            "characters": sum(len(b["text"]) for b in blocks)}
