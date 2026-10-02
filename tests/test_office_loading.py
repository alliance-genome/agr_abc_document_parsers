"""Tests for loading .xlsx / .docx through the Document loading API."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import pytest

from agr_abc_document_parsers import Document, emit_markdown
from agr_abc_document_parsers.models import _resolve_format_from_path

from .ooxml_helpers import build_xlsx

FIXTURES_DIR = Path(__file__).parent / "fixtures"
XLSX_FIXTURE = FIXTURES_DIR / "supplement_tables.xlsx"
DOCX_FIXTURE = FIXTURES_DIR / "supplement_methods.docx"


class TestFormatResolution:
    @pytest.mark.parametrize(
        "name, expected",
        [
            ("a.xlsx", "xlsx"),
            ("a.XLSX", "xlsx"),
            ("a.xlsm", "xlsx"),
            ("a.xlsx.gz", "xlsx"),
            ("a.docx", "docx"),
            ("a.docm", "docx"),
            ("a.docx.gz", "docx"),
            ("a.nxml.gz", "jats"),
            ("a.tei.gz", "tei"),
            ("a.md", "markdown"),
            ("a.gz", "auto"),
        ],
    )
    def test_extensions(self, name, expected):
        assert _resolve_format_from_path(Path(name)) == expected


class TestInMemoryLoading:
    def test_load_main_auto_detects_office_bytes(self):
        doc = Document().load_main(XLSX_FIXTURE.read_bytes(), title="Table S1")
        assert doc.source_format == "xlsx"
        assert doc.title == "Table S1"
        assert [s.heading for s in doc.sections] == ["Table S1", "Notes"]

    def test_load_main_explicit_format(self):
        doc = Document().load_main(DOCX_FIXTURE.read_bytes(), format="docx")
        assert doc.source_format == "docx"
        assert doc.title == "Supplementary Methods for Gene Study"

    def test_add_supplement_office_bytes(self):
        doc = Document(title="Main paper")
        doc.add_supplement(XLSX_FIXTURE.read_bytes(), title="Table S1")
        doc.add_supplement(gzip.compress(DOCX_FIXTURE.read_bytes()), title="Methods S1")
        assert [s.title for s in doc.supplements] == ["Table S1", "Methods S1"]
        assert [s.source_format for s in doc.supplements] == ["xlsx", "docx"]

    def test_add_supplements_mixed(self):
        doc = Document()
        doc.add_supplements([XLSX_FIXTURE.read_bytes(), "# Markdown supp\n\nText.\n"])
        assert doc.supplements[0].source_format == "xlsx"
        assert doc.supplements[1].title == "Markdown supp"

    def test_title_ignored_for_markdown(self):
        doc = Document().load_main("# MD Title\n\nText.\n", title="Ignored")
        assert doc.title == "MD Title"

    def test_wrong_explicit_format_raises(self):
        with pytest.raises(ValueError):
            Document().load_main(XLSX_FIXTURE.read_bytes(), format="docx")


class TestFileLoading:
    def test_load_main_file_defaults_title_to_stem(self, tmp_path):
        target = tmp_path / "Table_S1.xlsx"
        shutil.copy(XLSX_FIXTURE, target)
        doc = Document().load_main_file(target)
        assert doc.title == "Table_S1"
        assert doc.source_format == "xlsx"

    def test_load_main_file_gzipped_office(self, tmp_path):
        target = tmp_path / "Methods S2.docx.gz"
        target.write_bytes(gzip.compress(DOCX_FIXTURE.read_bytes()))
        doc = Document().load_main_file(target)
        assert doc.title == "Methods S2"
        assert "## Strains and culture" in emit_markdown(doc)

    def test_load_main_file_explicit_title(self, tmp_path):
        target = tmp_path / "x.docx"
        shutil.copy(DOCX_FIXTURE, target)
        assert Document().load_main_file(target, title="Given").title == "Given"

    def test_bare_gz_office_file_sniffed(self, tmp_path):
        target = tmp_path / "opaque.gz"
        target.write_bytes(gzip.compress(build_xlsx({"Sheet": "<row><c><v>5</v></c></row>"})))
        doc = Document().load_main_file(target)
        assert doc.source_format == "xlsx"
        assert doc.title == "opaque"
        assert doc.sections[0].heading == "Sheet"

    def test_add_supplement_files(self, tmp_path):
        a = tmp_path / "Table S1.xlsx"
        b = tmp_path / "Methods.docx"
        shutil.copy(XLSX_FIXTURE, a)
        shutil.copy(DOCX_FIXTURE, b)
        doc = Document(title="Main").add_supplement_files([a, b])
        assert [s.title for s in doc.supplements] == ["Table S1", "Methods"]

    def test_xml_files_unaffected_by_title_default(self, tmp_path):
        target = tmp_path / "paper.xml"
        target.write_bytes(
            b"<article><front><article-meta><title-group><article-title>JATS Title"
            b"</article-title></title-group></article-meta></front></article>"
        )
        assert Document().load_main_file(target).title == "JATS Title"
