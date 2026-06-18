"""
XLSX 明细报告输出模块。

为什么默认输出 xlsx：
- 报告里会出现 Java 注解、泛型、路径、中文说明等内容，xlsx 兼容性更好，也能固定列宽、冻结表头，适合作为正式报告查看；
- 这里不依赖 openpyxl/xlsxwriter，保证内网离线环境也能运行。

实现原则：
- 不引入 openpyxl、xlsxwriter 等第三方依赖，保证离线环境也能运行；
- 使用 Python 标准库 zipfile 直接生成最小可用 xlsx；
- 只负责展示，不参与扫描规则判断。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape


# 每列默认宽度。宽一点是为了打开报告时不用反复拖列宽。
DEFAULT_WIDTHS = [10, 34, 28, 52, 52, 30, 18, 14, 42, 10]


def _col_name(index: int) -> str:
    """把 1、2、3 转成 Excel 列名 A、B、C。"""
    name = ""
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _cell_xml(row_idx: int, col_idx: int, value, style_id: int = 0) -> str:
    """
    生成一个单元格 XML。

    这里统一使用 inlineStr 文本单元格，避免 Excel 把 @RequestBody、=xxx、+xxx
    之类内容识别成公式，也避免 sharedStrings 带来的额外复杂度。
    """
    ref = f"{_col_name(col_idx)}{row_idx}"
    text = "" if value is None else str(value)
    # Excel 单元格不允许控制字符，这里直接清理掉，避免文件打不开。
    safe_chars = []
    for ch in text:
        code = ord(ch)
        if code in (9, 10, 13) or code >= 32:
            # Unicode 代理区不是合法 XML 字符，也要过滤。
            if not (0xD800 <= code <= 0xDFFF):
                safe_chars.append(ch)
    text = "".join(safe_chars)
    text = escape(text)
    style_attr = f' s="{style_id}"' if style_id else ""
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{text}</t></is></c>'


def _worksheet_xml(rows: List[List[str]]) -> str:
    """生成工作表 XML，包含列宽、冻结表头、自动筛选和所有数据行。"""
    col_count = max((len(r) for r in rows), default=0)
    row_count = len(rows)

    cols = []
    for i in range(1, col_count + 1):
        width = DEFAULT_WIDTHS[i - 1] if i <= len(DEFAULT_WIDTHS) else 18
        cols.append(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>')

    sheet_rows = []
    for r_idx, row in enumerate(rows, start=1):
        style_id = 1 if r_idx == 1 else 0
        cells = []
        for c_idx in range(1, col_count + 1):
            value = row[c_idx - 1] if c_idx <= len(row) else ""
            cells.append(_cell_xml(r_idx, c_idx, value, style_id))
        sheet_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    dimension = f"A1:{_col_name(col_count)}{max(row_count, 1)}" if col_count else "A1"
    auto_filter = f'<autoFilter ref="A1:{_col_name(col_count)}{row_count}"/>' if row_count >= 1 and col_count else ""

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <dimension ref="{dimension}"/>
  <sheetViews>
    <sheetView workbookViewId="0">
      <pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>
    </sheetView>
  </sheetViews>
  <cols>{''.join(cols)}</cols>
  <sheetData>{''.join(sheet_rows)}</sheetData>
  {auto_filter}
</worksheet>'''


def _styles_xml() -> str:
    """生成最小样式：普通单元格 + 加粗表头。"""
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><name val="Calibri"/></font>
  </fonts>
  <fills count="1"><fill><patternFill patternType="none"/></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyFont="1"/>
    <xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def write_xlsx(rows: Iterable[Iterable], output_file: Path, sheet_name: str = "扫描明细") -> None:
    """
    写出 xlsx 文件。

    参数：
    - rows：二维数据，第一行为表头；
    - output_file：输出文件路径；
    - sheet_name：工作表名称，默认“扫描明细”。
    """
    output_file.parent.mkdir(parents=True, exist_ok=True)
    data = [["" if cell is None else str(cell) for cell in row] for row in rows]
    sheet_name = sheet_name[:31] or "扫描明细"

    with ZipFile(output_file, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>''')
        zf.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''')
        zf.writestr("xl/workbook.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets>
</workbook>''')
        zf.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>''')
        zf.writestr("xl/styles.xml", _styles_xml())
        zf.writestr("xl/worksheets/sheet1.xml", _worksheet_xml(data))
