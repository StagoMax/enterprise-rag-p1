"""多格式文档准入（P1.1）：解析、结构化、表格分流与降级记录。

按 docs/02 的技术选型：Docling 为主解析器；Docling 缺失或对某个文件失败时降级到
内置的零依赖抽取器（OOXML/HTML/Markdown 直读，PDF 走 pypdf/pypdfium2）；扫描件走
OCR 兜底（PaddleOCR 为主，RapidOCR 次选，全部延迟导入）。

设计约束：
- 解析失败一律作为数据记录在 ParsedDocument 上，不向调用方抛异常。
- 表格与正文分离：正文只保留散文，表格结构化保存，便于单独写入关系库。
- 锚点必须可复现（同输入同锚点，且与文件路径无关），因为引用链依赖它。
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ElementTree
import zipfile
from collections.abc import Iterable
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from enterprise_rag.models import DocumentInput, DocumentStatus

_WS = re.compile(r"[ \t 　]+")
_BLANK_RUN = re.compile(r"\n{3,}")
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+){0,5})[.、)\s]\s*\S")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_MD_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")
_STYLE_LEVEL = re.compile(r"(\d)\s*$")

# 单独成行的页码/页眉页脚样板：裸页码、"Page 3 of 10"、"第 3 页 共 10 页"。
_PAGE_LABEL = re.compile(
    r"^(?:"
    r"[\s\-–—_|]*\d{1,4}[\s\-–—_|]*"
    r"|page\s*\d{1,4}(?:\s*(?:of|/|-)\s*\d{1,4})?"
    r"|第\s*\d{1,4}\s*页(?:\s*[,，/]?\s*共?\s*\d{1,4}\s*页)?"
    r"|\d{1,4}\s*/\s*\d{1,4}"
    r")$",
    re.IGNORECASE,
)
_BOILERPLATE_HINT = re.compile(
    r"(内部资料|请勿外传|保密|机密|版权所有|all rights reserved|confidential|proprietary)",
    re.IGNORECASE,
)

# PDF 每页平均可抽取字符数低于该阈值时判定为扫描件/图片型 PDF。
_MIN_PDF_CHARS_PER_PAGE = 24

# 页眉页脚候选只在每页首尾若干行中寻找，避免误删正文。
_EDGE_LINES = 3
_HEADER_FOOTER_MIN_PAGES = 2
_HEADER_FOOTER_RATIO = 0.6
_HEADER_FOOTER_MAX_CHARS = 120

_OOXML_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

_SUFFIX_FORMATS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".htm": "html",
    ".html": "html",
    ".xhtml": "html",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
}

SUPPORTED_SUFFIXES = frozenset(_SUFFIX_FORMATS)


class BlockKind(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"


class ParseBackend(StrEnum):
    DOCLING = "docling"
    FALLBACK = "fallback"
    OCR = "ocr"
    NONE = "none"


class ParsedBlock(BaseModel):
    kind: BlockKind
    text: str
    anchor: str
    order: int
    page: int | None = None
    section: str | None = None
    heading_path: list[str] = Field(default_factory=list)


class ParsedTable(BaseModel):
    """结构化表格：与正文分离，供关系库单独落库。"""

    anchor: str
    order: int
    rows: list[list[str]] = Field(default_factory=list)
    page: int | None = None
    section: str | None = None
    caption: str | None = None

    @property
    def header(self) -> list[str]:
        return self.rows[0] if self.rows else []

    @property
    def row_count(self) -> int:
        return max(len(self.rows) - 1, 0)

    def to_markdown(self) -> str:
        if not self.rows:
            return ""
        width = max(len(row) for row in self.rows)
        lines: list[str] = []
        for index, row in enumerate(self.rows):
            padded = [*row, *[""] * (width - len(row))]
            lines.append("| " + " | ".join(padded) + " |")
            if index == 0:
                lines.append("| " + " | ".join(["---"] * width) + " |")
        return "\n".join(lines)

    def stub_line(self) -> str:
        """正文中的表格占位行：只留锚点与表头，不把表格摊平进散文。"""
        label = self.caption or "表格"
        header = " / ".join(part for part in self.header if part)
        suffix = f"（表头：{header}）" if header else ""
        return f"[表格 {self.anchor}] {label}{suffix}，共 {self.row_count} 行数据。"


class ParsedDocument(BaseModel):
    source_path: str
    source_name: str
    doc_format: str
    backend: ParseBackend = ParseBackend.NONE
    text: str = ""
    blocks: list[ParsedBlock] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    page_count: int = 0
    title: str | None = None
    needs_ocr: bool = False
    ocr_applied: bool = False
    failed: bool = False
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    suppressed_lines: list[str] = Field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return self.failed or self.backend is not ParseBackend.DOCLING

    @property
    def has_prose(self) -> bool:
        return bool(self.text.strip())

    def anchors(self) -> list[str]:
        return [block.anchor for block in self.blocks] + [table.anchor for table in self.tables]


def _normalize(text: str) -> str:
    return _WS.sub(" ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def build_anchor(kind: BlockKind, page: int | None, order: int, text: str) -> str:
    """确定性锚点：只由 (类型, 页, 序号, 归一化文本) 决定，不含路径或时间。"""
    digest = hashlib.sha256(_normalize(text).encode("utf-8")).hexdigest()[:10]
    return f"p{page if page else 0}:{kind.value}:{order}:{digest}"


class _SectionTracker:
    """按标题层级推导章节号；标题自带编号时以文档自身编号为准。"""

    def __init__(self) -> None:
        self._counters: list[int] = []
        self._path: list[str] = []

    def enter_heading(self, level: int, text: str) -> None:
        level = max(1, min(level, 6))
        explicit = _NUMBERED_HEADING.match(text)
        if explicit:
            self._counters = [int(part) for part in explicit.group(1).split(".")]
        else:
            del self._counters[level:]
            while len(self._counters) < level:
                self._counters.append(0)
            self._counters[level - 1] += 1
        del self._path[level - 1 :]
        self._path.append(text)

    @property
    def section(self) -> str | None:
        if not self._counters:
            return None
        return ".".join(str(part) for part in self._counters)

    @property
    def path(self) -> list[str]:
        return list(self._path)


def _looks_like_heading(line: str) -> bool:
    if len(line) > 80 or line.endswith(("。", ".", "！", "!", "?", "？", "；", ";", "，", ",")):
        return False
    return bool(_NUMBERED_HEADING.match(line))


def suppress_header_footer(pages: list[str]) -> tuple[list[str], list[str]]:
    """删除跨页重复的页眉/页脚与纯页码行，返回清洗后的页文本与被删内容。"""
    occurrences: dict[str, int] = {}
    for page in pages:
        lines = [line.strip() for line in page.splitlines()]
        edges = {
            line
            for line in lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]
            if line and len(line) <= _HEADER_FOOTER_MAX_CHARS
        }
        for line in edges:
            occurrences[line] = occurrences.get(line, 0) + 1

    multi_page = len(pages) >= _HEADER_FOOTER_MIN_PAGES
    threshold = max(_HEADER_FOOTER_MIN_PAGES, round(len(pages) * _HEADER_FOOTER_RATIO + 0.4))
    repeated = {line for line, count in occurrences.items() if count >= threshold}

    suppressed: set[str] = set()
    cleaned: list[str] = []
    for page in pages:
        lines = page.splitlines()
        keep: list[str] = []
        for index, raw in enumerate(lines):
            line = raw.strip()
            in_edge = index < _EDGE_LINES or index >= len(lines) - _EDGE_LINES
            boilerplate = (
                multi_page
                and len(line) <= _HEADER_FOOTER_MAX_CHARS
                and _BOILERPLATE_HINT.search(line) is not None
            )
            if line and in_edge and (_PAGE_LABEL.match(line) or line in repeated or boilerplate):
                suppressed.add(line)
                continue
            keep.append(raw)
        cleaned.append("\n".join(keep))
    return cleaned, sorted(suppressed)


class _Accumulator:
    """把 (类型, 文本, 页) 累积成块与表格，并统一分配锚点与章节号。"""

    def __init__(self) -> None:
        self.blocks: list[ParsedBlock] = []
        self.tables: list[ParsedTable] = []
        self._sections = _SectionTracker()

    def add_text(self, kind: BlockKind, text: str, page: int | None, *, level: int = 1) -> None:
        normalized = _normalize(text)
        if not normalized:
            return
        if kind is BlockKind.HEADING:
            self._sections.enter_heading(level, normalized)
        order = len(self.blocks)
        self.blocks.append(
            ParsedBlock(
                kind=kind,
                text=normalized,
                anchor=build_anchor(kind, page, order, normalized),
                order=order,
                page=page,
                section=self._sections.section,
                heading_path=self._sections.path,
            )
        )

    def add_table(self, rows: list[list[str]], page: int | None, caption: str | None) -> None:
        grid = [[_normalize(cell) for cell in row] for row in rows]
        grid = [row for row in grid if any(row)]
        if not grid:
            return
        order = len(self.tables)
        flattened = "\n".join("\t".join(row) for row in grid)
        self.tables.append(
            ParsedTable(
                anchor=build_anchor(BlockKind.TABLE, page, order, flattened),
                order=order,
                rows=grid,
                page=page,
                section=self._sections.section,
                caption=_normalize(caption) if isinstance(caption, str) and caption else None,
            )
        )

    def prose(self) -> str:
        joined = "\n\n".join(block.text for block in self.blocks)
        return _BLANK_RUN.sub("\n\n", joined).strip()

    def first_heading(self) -> str | None:
        for block in self.blocks:
            if block.kind is BlockKind.HEADING:
                return block.text
        return None


def _ingest_plain_lines(accumulator: _Accumulator, pages: list[str], *, paged: bool) -> None:
    """把纯文本页切成标题/列表/段落块。"""
    for index, page_text in enumerate(pages, start=1):
        page = index if paged else None
        buffer: list[str] = []
        for raw in page_text.splitlines():
            line = raw.strip()
            heading = _MD_HEADING.match(raw)
            is_list = bool(line) and bool(_MD_LIST.match(raw))
            is_heading = bool(line) and not is_list and _looks_like_heading(line)
            if (not line or heading or is_list or is_heading) and buffer:
                accumulator.add_text(BlockKind.PARAGRAPH, " ".join(buffer), page)
                buffer = []
            if not line:
                continue
            if heading:
                accumulator.add_text(
                    BlockKind.HEADING, heading.group(2), page, level=len(heading.group(1))
                )
            elif is_list:
                accumulator.add_text(BlockKind.LIST, line, page)
            elif is_heading:
                numbering = _NUMBERED_HEADING.match(line)
                level = len(numbering.group(1).split(".")) if numbering else 1
                accumulator.add_text(BlockKind.HEADING, line, page, level=level)
            else:
                buffer.append(line)
        if buffer:
            accumulator.add_text(BlockKind.PARAGRAPH, " ".join(buffer), page)


def _rapidocr_torch() -> Any:
    """用 torch 后端构造 RapidOCR。

    本机 onnxruntime 的 DLL 初始化失败（WinError 1114 一类），而 RapidOCR 支持
    torch 引擎；项目为了 Nemotron 本来就装了 CUDA 版 torch，因此这是零新增重依赖的
    可用路径。实测能完整识别出扫描页文字。
    """
    from rapidocr import RapidOCR
    from rapidocr.utils.typings import EngineType

    return RapidOCR(
        params={
            "Det.engine_type": EngineType.TORCH,
            "Cls.engine_type": EngineType.TORCH,
            "Rec.engine_type": EngineType.TORCH,
        }
    )


def _load_ocr_reader() -> tuple[Any | None, str]:
    """按 docs/02 的顺序尝试 OCR 引擎；全部不可用时只返回原因。"""
    reasons: list[str] = []
    candidates: tuple[tuple[str, Any], ...] = (
        ("paddleocr", lambda: __import__("paddleocr", fromlist=["PaddleOCR"]).PaddleOCR(lang="ch")),
        ("rapidocr(torch)", _rapidocr_torch),
        (
            "rapidocr_onnxruntime",
            lambda: __import__(
                "rapidocr_onnxruntime", fromlist=["RapidOCR"]
            ).RapidOCR(),
        ),
        ("rapidocr", lambda: __import__("rapidocr", fromlist=["RapidOCR"]).RapidOCR()),
    )
    for label, factory in candidates:
        try:
            return factory(), ""
        except Exception as error:  # noqa: BLE001
            reasons.append(f"{label} 不可用({type(error).__name__}: {error})")
    return None, "；".join(reasons)


def _recognize(reader: Any, image: Any) -> str:
    """归一化各 OCR 引擎的返回结构。

    覆盖 PaddleOCR 2.x（嵌套 [box, (text, score)]）、PaddleOCR 3.x（dict 里的
    rec_texts）、RapidOCR 1.x（(detections, elapse) 元组）与 RapidOCR 3.x
    （带 txts 属性的结果对象）。
    """
    result = reader.ocr(image) if hasattr(reader, "ocr") else reader(image)
    return "\n".join(_recognized_lines(result))


def _recognized_lines(result: Any) -> list[str]:
    if result is None:
        return []
    texts = getattr(result, "txts", None)
    if texts is not None:
        return [str(text) for text in texts]
    if isinstance(result, dict):
        return [str(text) for text in result.get("rec_texts", [])]
    if isinstance(result, tuple):
        return _recognized_lines(result[0]) if result else []
    if not isinstance(result, list):
        return []
    lines: list[str] = []
    for entry in result:
        if isinstance(entry, str):
            lines.append(entry)
        elif isinstance(entry, dict | tuple) or getattr(entry, "txts", None) is not None:
            lines.extend(_recognized_lines(entry))
        elif isinstance(entry, list):
            second = entry[1] if len(entry) >= 2 else None
            if isinstance(second, list | tuple) and second and isinstance(second[0], str):
                lines.append(second[0])  # PaddleOCR 2.x: [box, (text, score)]
            elif isinstance(second, str):
                lines.append(second)  # RapidOCR 1.x: [box, text, score]
            else:
                lines.extend(_recognized_lines(entry))
    return lines


def ocr_pdf_pages(path: Path, *, scale: float = 2.0) -> tuple[list[str], list[str]]:
    """渲染 PDF 页并 OCR。依赖缺失或失败时返回原因而不抛异常。"""
    try:
        import pypdfium2
    except Exception as error:
        return [], [f"OCR 跳过：缺少 PDF 渲染依赖 pypdfium2({error})"]
    try:
        import numpy
    except Exception as error:
        return [], [f"OCR 跳过：缺少 numpy({error})"]
    reader, reason = _load_ocr_reader()
    if reader is None:
        return [], [f"OCR 跳过：{reason}"]

    texts: list[str] = []
    try:
        document = pypdfium2.PdfDocument(str(path))
        for index in range(len(document)):
            bitmap = document[index].render(scale=scale)
            texts.append(_recognize(reader, numpy.asarray(bitmap.to_pil().convert("RGB"))))
    except Exception as error:
        return texts, [f"OCR 执行失败：{type(error).__name__}: {error}"]
    return texts, []


def _ooxml_text(node: ElementTree.Element, tag: str) -> str:
    return "".join(part.text or "" for part in node.iter(tag))


def _docx_block_kind(paragraph: ElementTree.Element) -> tuple[BlockKind, int]:
    style = paragraph.find("w:pPr/w:pStyle", _OOXML_NS)
    name = (style.get(f"{{{_OOXML_NS['w']}}}val") or "") if style is not None else ""
    lowered = name.lower()
    if lowered.startswith(("heading", "title")) or name.startswith("标题"):
        match = _STYLE_LEVEL.search(name)
        return BlockKind.HEADING, int(match.group(1)) if match else 1
    if (
        paragraph.find("w:pPr/w:numPr", _OOXML_NS) is not None
        or lowered.startswith("list")
        or name.startswith("列表")
    ):
        return BlockKind.LIST, 1
    return BlockKind.PARAGRAPH, 1


def _extract_docx(path: Path, accumulator: _Accumulator) -> int:
    with zipfile.ZipFile(path) as bundle:
        root = ElementTree.fromstring(bundle.read("word/document.xml"))
    body = root.find("w:body", _OOXML_NS)
    if body is None:
        return 0
    text_tag = f"{{{_OOXML_NS['w']}}}t"
    for child in body:
        if child.tag == f"{{{_OOXML_NS['w']}}}p":
            kind, level = _docx_block_kind(child)
            accumulator.add_text(kind, _ooxml_text(child, text_tag), None, level=level)
        elif child.tag == f"{{{_OOXML_NS['w']}}}tbl":
            rows = [
                [_ooxml_text(cell, text_tag) for cell in row.findall("w:tc", _OOXML_NS)]
                for row in child.findall("w:tr", _OOXML_NS)
            ]
            accumulator.add_table(rows, None, accumulator.first_heading())
    return 1


def _pptx_shape_text(shape: ElementTree.Element) -> str:
    paragraphs = [
        _ooxml_text(paragraph, f"{{{_OOXML_NS['a']}}}t").strip()
        for paragraph in shape.iter(f"{{{_OOXML_NS['a']}}}p")
    ]
    return "\n".join(part for part in paragraphs if part)


def _extract_pptx(path: Path, accumulator: _Accumulator) -> int:
    with zipfile.ZipFile(path) as bundle:
        names = sorted(
            (name for name in bundle.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
            key=lambda name: int(re.findall(r"\d+", name)[-1]),
        )
        for slide_number, name in enumerate(names, start=1):
            root = ElementTree.fromstring(bundle.read(name))
            # 只从 p:sp 取正文，表格在 graphicFrame 里，因此不会混入散文。
            for shape in root.iter(f"{{{_OOXML_NS['p']}}}sp"):
                placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", _OOXML_NS)
                is_title = placeholder is not None and "title" in (placeholder.get("type") or "")
                text = _pptx_shape_text(shape)
                if not text:
                    continue
                if is_title:
                    accumulator.add_text(BlockKind.HEADING, text, slide_number, level=1)
                    continue
                for line in text.splitlines():
                    kind = BlockKind.LIST if _MD_LIST.match(line) else BlockKind.PARAGRAPH
                    accumulator.add_text(kind, line, slide_number)
            for table in root.iter(f"{{{_OOXML_NS['a']}}}tbl"):
                rows = [
                    [
                        _ooxml_text(cell, f"{{{_OOXML_NS['a']}}}t")
                        for cell in row.findall("a:tc", _OOXML_NS)
                    ]
                    for row in table.findall("a:tr", _OOXML_NS)
                ]
                accumulator.add_table(rows, slide_number, accumulator.first_heading())
    return len(names)


def _xlsx_shared_strings(bundle: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in bundle.namelist():
        return []
    root = ElementTree.fromstring(bundle.read("xl/sharedStrings.xml"))
    return [_ooxml_text(item, f"{{{_OOXML_NS['x']}}}t") for item in root.findall("x:si", _OOXML_NS)]


def _xlsx_sheets(bundle: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ElementTree.fromstring(bundle.read("xl/workbook.xml"))
    relations = ElementTree.fromstring(bundle.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relation.get("Id"): relation.get("Target", "")
        for relation in relations.findall("pr:Relationship", _OOXML_NS)
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall("x:sheets/x:sheet", _OOXML_NS):
        target = targets.get(sheet.get(f"{{{_OOXML_NS['r']}}}id"), "").lstrip("/")
        if not target:
            continue
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        sheets.append((sheet.get("name") or "sheet", target))
    return sheets


def _xlsx_cell_value(cell: ElementTree.Element, shared: list[str]) -> str:
    if cell.get("t") == "inlineStr":
        return _ooxml_text(cell, f"{{{_OOXML_NS['x']}}}t")
    value = cell.find("x:v", _OOXML_NS)
    if value is None or value.text is None:
        return ""
    if cell.get("t") == "s":
        index = int(value.text)
        return shared[index] if 0 <= index < len(shared) else ""
    return value.text


def _extract_xlsx(path: Path, accumulator: _Accumulator) -> int:
    with zipfile.ZipFile(path) as bundle:
        shared = _xlsx_shared_strings(bundle)
        sheets = _xlsx_sheets(bundle)
        available = set(bundle.namelist())
        for sheet_number, (name, target) in enumerate(sheets, start=1):
            if target not in available:
                continue
            root = ElementTree.fromstring(bundle.read(target))
            # 工作表名作为标题块保证正文有可检索上下文；数据行只进表格。
            accumulator.add_text(BlockKind.HEADING, name, sheet_number, level=1)
            rows = [
                [_xlsx_cell_value(cell, shared) for cell in row.findall("x:c", _OOXML_NS)]
                for row in root.findall("x:sheetData/x:row", _OOXML_NS)
            ]
            accumulator.add_table(rows, sheet_number, name)
    return len(sheets)


class _HtmlCollector(HTMLParser):
    """把 HTML 折叠成标题/段落/列表/表格事件流，并丢掉脚本、样式与页眉页脚容器。"""

    _SKIP = frozenset({"script", "style", "noscript", "template", "svg"})
    _BOILERPLATE = frozenset({"header", "footer", "nav", "aside"})
    _BLOCK = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, Any]] = []
        self.title: str | None = None
        self.dropped: list[str] = []
        self._skip_depth = 0
        self._boilerplate_depth = 0
        self._buffer: list[str] = []
        self._current: str | None = None
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BOILERPLATE:
            self._flush()
            self._boilerplate_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "table":
            self._flush()
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._buffer.clear()
            self._current = "cell"
        elif tag in self._BLOCK:
            self._flush()
            self._current = tag
        elif tag == "br":
            self._buffer.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BOILERPLATE:
            dropped = _normalize("".join(self._buffer))
            if dropped:
                self.dropped.append(dropped)
            self._buffer.clear()
            self._current = None
            self._boilerplate_depth = max(0, self._boilerplate_depth - 1)
        elif tag == "title":
            self.title = _normalize("".join(self._buffer)) or None
            self._buffer.clear()
            self._in_title = False
        elif tag in {"td", "th"} and self._row is not None:
            self._row.append(_normalize("".join(self._buffer)))
            self._buffer.clear()
            self._current = None
        elif tag == "tr" and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table:
                self.events.append(("table", self._table))
            self._table = None
        elif tag == self._current:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._boilerplate_depth:
            self._buffer.append(data)
            return
        if self._in_title or self._current is not None:
            self._buffer.append(data)

    def _flush(self) -> None:
        text = _normalize("".join(self._buffer))
        self._buffer.clear()
        tag, self._current = self._current, None
        if not text or tag is None or tag == "cell":
            return
        if tag[0] == "h" and tag[1:].isdigit():
            self.events.append(("heading", (int(tag[1:]), text)))
        elif tag == "li":
            self.events.append(("list", text))
        else:
            self.events.append(("paragraph", text))

    def close(self) -> None:
        super().close()
        self._flush()


def _extract_html(path: Path, accumulator: _Accumulator) -> tuple[int, str | None, list[str]]:
    collector = _HtmlCollector()
    collector.feed(path.read_text(encoding="utf-8", errors="replace"))
    collector.close()
    for kind, payload in collector.events:
        if kind == "heading":
            level, text = payload
            accumulator.add_text(BlockKind.HEADING, text, None, level=level)
        elif kind == "list":
            accumulator.add_text(BlockKind.LIST, payload, None)
        elif kind == "table":
            accumulator.add_table(payload, None, accumulator.first_heading())
        else:
            accumulator.add_text(BlockKind.PARAGRAPH, payload, None)
    return 1, collector.title, sorted(set(collector.dropped))


def _read_pdf_pages(path: Path) -> tuple[list[str], list[str]]:
    """按 pypdf -> pypdfium2 顺序抽取每页文本；两者都缺失时返回原因。"""
    reasons: list[str] = []
    try:
        from pypdf import PdfReader
    except Exception as error:
        reasons.append(f"pypdf 不可用({error})")
    else:
        try:
            return [page.extract_text() or "" for page in PdfReader(str(path)).pages], []
        except Exception as error:
            return [], [f"pypdf 解析 PDF 失败：{type(error).__name__}: {error}"]
    try:
        import pypdfium2
    except Exception as error:
        reasons.append(f"pypdfium2 不可用({error})")
        return [], [f"缺少 PDF 文本抽取依赖：{'；'.join(reasons)}"]
    try:
        document = pypdfium2.PdfDocument(str(path))
        return [
            document[index].get_textpage().get_text_range() for index in range(len(document))
        ], []
    except Exception as error:
        return [], [f"pypdfium2 解析 PDF 失败：{type(error).__name__}: {error}"]


@runtime_checkable
class DocumentParser(Protocol):
    def supports(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> ParsedDocument: ...


def detect_format(path: Path) -> str | None:
    return _SUFFIX_FORMATS.get(path.suffix.lower())


def _docling_import_error() -> str:
    try:
        import docling.document_converter  # noqa: F401
    except Exception as error:
        return f"docling 不可用({type(error).__name__}: {error})，降级到内置抽取器"
    return ""


class DoclingDocumentParser:
    """Docling 为主、内置抽取器兜底、扫描件走 OCR 的统一解析器。

    覆盖 PDF / DOCX / PPTX / XLSX / HTML / Markdown（含纯文本）。
    """

    def __init__(
        self,
        *,
        prefer_docling: bool = True,
        enable_ocr: bool = True,
        suppress_boilerplate: bool = True,
    ) -> None:
        self._prefer_docling = prefer_docling
        self._enable_ocr = enable_ocr
        self._suppress_boilerplate = suppress_boilerplate
        self._converter: Any | None = None

    def supports(self, path: Path) -> bool:
        return detect_format(path) is not None

    def parse(self, path: Path) -> ParsedDocument:
        doc_format = detect_format(path)
        result = ParsedDocument(
            source_path=str(path),
            source_name=path.name,
            doc_format=doc_format or (path.suffix.lower().lstrip(".") or "unknown"),
        )
        if doc_format is None:
            result.failed = True
            result.error = f"不受支持的文件类型：{path.suffix or path.name}"
            return result
        if not path.is_file():
            result.failed = True
            result.error = f"文件不存在或不是普通文件：{path}"
            return result

        if self._prefer_docling:
            reason = _docling_import_error()
            if reason:
                result.warnings.append(reason)
            elif self._parse_with_docling(path, result):
                return result

        self._parse_with_fallback(path, doc_format, result)
        return result

    def _converter_instance(self) -> Any:
        if self._converter is None:
            from docling.document_converter import DocumentConverter

            self._converter = DocumentConverter()
        return self._converter

    def _parse_with_docling(self, path: Path, result: ParsedDocument) -> bool:
        accumulator = _Accumulator()
        try:
            document = self._converter_instance().convert(str(path)).document
            _collect_docling_items(document, accumulator)
        except Exception as error:
            # Docling 失败必须降级并记录原因，而不是把异常抛给调用方。
            result.warnings.append(
                f"docling 解析失败，降级到内置抽取器：{type(error).__name__}: {error}"
            )
            return False
        if not accumulator.blocks and not accumulator.tables:
            result.warnings.append("docling 未产出任何块，降级到内置抽取器")
            return False

        result.backend = ParseBackend.DOCLING
        result.blocks = accumulator.blocks
        result.tables = accumulator.tables
        result.text = accumulator.prose()
        result.title = accumulator.first_heading()
        pages = {block.page for block in accumulator.blocks if block.page}
        result.page_count = max(pages) if pages else 1
        if result.doc_format == "pdf" and _is_scanned_density(result.text, result.page_count):
            result.needs_ocr = True
            self._route_to_ocr(path, result)
        return True

    def _parse_with_fallback(self, path: Path, doc_format: str, result: ParsedDocument) -> None:
        accumulator = _Accumulator()
        try:
            if doc_format == "docx":
                result.page_count = _extract_docx(path, accumulator)
            elif doc_format == "pptx":
                result.page_count = _extract_pptx(path, accumulator)
            elif doc_format == "xlsx":
                result.page_count = _extract_xlsx(path, accumulator)
            elif doc_format == "html":
                result.page_count, result.title, result.suppressed_lines = _extract_html(
                    path, accumulator
                )
            elif doc_format == "pdf":
                self._fallback_pdf(path, accumulator, result)
            else:
                pages = [path.read_text(encoding="utf-8", errors="replace")]
                if self._suppress_boilerplate:
                    pages, result.suppressed_lines = suppress_header_footer(pages)
                _ingest_plain_lines(accumulator, pages, paged=False)
                result.page_count = 1
        except Exception as error:
            # 单文件失败作为数据返回，批量准入不因一个坏文件中断。
            result.failed = True
            result.backend = ParseBackend.NONE
            result.error = f"内置抽取器解析失败：{type(error).__name__}: {error}"
            return

        if result.backend is not ParseBackend.OCR:
            result.backend = ParseBackend.FALLBACK
        result.blocks = accumulator.blocks
        result.tables = accumulator.tables
        result.text = accumulator.prose()
        result.title = result.title or accumulator.first_heading()
        if not result.blocks and not result.tables and not result.needs_ocr:
            result.failed = True
            result.error = "未能从文件中抽取到任何文本或表格"

    def _fallback_pdf(self, path: Path, accumulator: _Accumulator, result: ParsedDocument) -> None:
        pages, warnings = _read_pdf_pages(path)
        result.warnings.extend(warnings)
        result.page_count = len(pages)
        if not pages or _is_scanned_density("".join(pages), len(pages)):
            result.needs_ocr = True
            self._route_to_ocr(path, result, accumulator)
            if result.ocr_applied or not pages:
                return
        if self._suppress_boilerplate:
            pages, result.suppressed_lines = suppress_header_footer(pages)
        _ingest_plain_lines(accumulator, pages, paged=True)

    def _route_to_ocr(
        self,
        path: Path,
        result: ParsedDocument,
        accumulator: _Accumulator | None = None,
    ) -> None:
        if not self._enable_ocr:
            result.warnings.append("检测到扫描件/图片型 PDF，但 OCR 已被禁用")
            return
        pages, warnings = ocr_pdf_pages(path)
        result.warnings.extend(warnings)
        if not any(page.strip() for page in pages):
            result.warnings.append("检测到扫描件/图片型 PDF，OCR 未产出文本，需补装 OCR 依赖")
            return
        if self._suppress_boilerplate:
            pages, result.suppressed_lines = suppress_header_footer(pages)
        target = accumulator if accumulator is not None else _Accumulator()
        _ingest_plain_lines(target, pages, paged=True)
        result.ocr_applied = True
        result.backend = ParseBackend.OCR
        result.page_count = max(result.page_count, len(pages))
        if accumulator is None:
            result.blocks = target.blocks
            result.tables = target.tables
            result.text = target.prose()


def _is_scanned_density(text: str, page_count: int) -> bool:
    return len(_WS.sub("", text).strip()) / max(page_count, 1) < _MIN_PDF_CHARS_PER_PAGE


def _docling_label(item: Any) -> str:
    label = getattr(item, "label", None)
    return str(getattr(label, "value", label) or "").lower()


def _docling_page(item: Any) -> int | None:
    for provenance in getattr(item, "prov", None) or []:
        page = getattr(provenance, "page_no", None)
        if isinstance(page, int):
            return page
    return None


def _docling_table_rows(item: Any) -> list[list[str]]:
    data = getattr(item, "data", None)
    grid = getattr(data, "grid", None)
    if grid:
        return [[str(getattr(cell, "text", "") or "") for cell in row] for row in grid]
    cells = getattr(data, "table_cells", None) or []
    rows: dict[int, dict[int, str]] = {}
    for cell in cells:
        row_index = int(getattr(cell, "start_row_offset_idx", 0) or 0)
        column_index = int(getattr(cell, "start_col_offset_idx", 0) or 0)
        rows.setdefault(row_index, {})[column_index] = str(getattr(cell, "text", "") or "")
    ordered: list[list[str]] = []
    for row_index in sorted(rows):
        columns = rows[row_index]
        ordered.append([columns.get(index, "") for index in range(max(columns) + 1)])
    return ordered


def _docling_caption(item: Any, document: Any) -> str | None:
    """docling-core 的 caption_text 是方法而非属性，两种形态都要能取到文本。"""
    caption = getattr(item, "caption_text", None)
    if callable(caption):
        try:
            caption = caption(document)
        except Exception:
            return None
    return caption if isinstance(caption, str) and caption.strip() else None


def _collect_docling_items(document: Any, accumulator: _Accumulator) -> None:
    """遍历 Docling 文档树，页眉/页脚/脚注直接丢弃，表格单独收集。"""
    table_ids = {id(table) for table in getattr(document, "tables", None) or []}
    for item, level in document.iterate_items():
        page = _docling_page(item)
        label = _docling_label(item)
        if id(item) in table_ids or label == "table":
            accumulator.add_table(
                _docling_table_rows(item), page, _docling_caption(item, document)
            )
            continue
        if label in {"page_header", "page_footer", "footnote"}:
            continue
        text = str(getattr(item, "text", "") or "")
        if not text.strip():
            continue
        if label in {"section_header", "title"}:
            accumulator.add_text(BlockKind.HEADING, text, page, level=max(1, int(level or 1)))
        elif label in {"list_item", "list"}:
            accumulator.add_text(BlockKind.LIST, text, page)
        else:
            accumulator.add_text(BlockKind.PARAGRAPH, text, page)


_DEFAULT_PARSER = DoclingDocumentParser()


def parse_document(path: Path, *, parser: DocumentParser | None = None) -> ParsedDocument:
    return (parser or _DEFAULT_PARSER).parse(path)


def parse_documents(
    paths: Iterable[Path], *, parser: DocumentParser | None = None
) -> list[ParsedDocument]:
    """批量解析：单文件失败只体现在该条结果的 failed/error 上。"""
    active = parser or _DEFAULT_PARSER
    return [active.parse(path) for path in paths]


def to_document_input(
    parsed: ParsedDocument,
    *,
    document_id: str,
    owner: str,
    business_class: str,
    allowed_roles: Iterable[str],
    title: str | None = None,
    sensitivity: str = "internal",
    version: str = "1.0",
    status: DocumentStatus = DocumentStatus.ACTIVE,
    source_uri: str | None = None,
    include_tables: bool = False,
    table_stubs: bool = True,
) -> DocumentInput:
    """把解析结果转成仓库既有的 DocumentInput，元数据契约保持不变。

    默认只索引散文：表格留给关系库（include_tables=False），正文里仅保留带锚点的
    表格占位行（table_stubs=True），这样引用仍能指回具体表格。
    """
    if parsed.failed:
        raise ValueError(f"无法索引解析失败的文档：{parsed.error}")

    sections = [parsed.text] if parsed.text.strip() else []
    if include_tables:
        sections.extend(table.to_markdown() for table in parsed.tables)
    elif table_stubs:
        sections.extend(table.stub_line() for table in parsed.tables)
    content = _BLANK_RUN.sub("\n\n", "\n\n".join(part for part in sections if part.strip())).strip()
    if not content:
        raise ValueError(f"解析结果没有可索引内容：{parsed.source_name}")

    resolved_title = title or parsed.title or Path(parsed.source_name).stem
    if source_uri is None:
        source_uri = Path(parsed.source_path).resolve().as_uri()
    return DocumentInput(
        document_id=document_id,
        title=resolved_title[:300],
        content=content,
        owner=owner,
        business_class=business_class,
        sensitivity=sensitivity,
        allowed_roles=set(allowed_roles),
        version=version,
        status=status,
        source_uri=source_uri,
    )
