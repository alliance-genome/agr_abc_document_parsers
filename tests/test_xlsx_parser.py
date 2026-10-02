"""Tests for the Excel (.xlsx) parser."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from agr_abc_document_parsers import emit_markdown, read_markdown, validate_markdown
from agr_abc_document_parsers.xlsx_parser import parse_xlsx

from .ooxml_helpers import build_docx, build_xlsx, styles_with_formats, zip_bytes

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES_DIR / "supplement_tables.xlsx"


def _rows(doc, section_idx: int = 0) -> list[list[str]]:
    return [[c.text for c in row] for row in doc.sections[section_idx].tables[0].rows]


# ---------------------------------------------------------------------------
# Real openpyxl-generated workbook
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def doc():
    return parse_xlsx(FIXTURE.read_bytes(), title="Supplementary Tables")


class TestFixtureWorkbook:
    def test_title_and_source_format(self, doc):
        assert doc.title == "Supplementary Tables"
        assert doc.source_format == "xlsx"

    def test_one_section_per_non_empty_sheet(self, doc):
        assert [s.heading for s in doc.sections] == ["Table S1", "Notes"]
        assert all(len(s.tables) == 1 for s in doc.sections)
        assert all(s.level == 1 for s in doc.sections)

    def test_header_row_flagged(self, doc):
        table = doc.sections[0].tables[0]
        assert all(c.is_header for c in table.rows[0])
        assert not any(c.is_header for c in table.rows[1])

    def test_empty_rows_and_columns_removed(self, doc):
        rows = _rows(doc)
        # Data started at B3 with an empty column D and an empty row 6.
        assert rows[0] == [
            "Gene",
            "Species",
            "Fold change",
            "p-value",
            "Significant",
            "Date assayed",
            "Notes",
        ]
        assert len(rows) == 5  # header, 2 data, Total, merged row

    def test_cell_value_rendering(self, doc):
        rows = _rows(doc)
        assert rows[1] == [
            "unc-54",
            "C. elegans",
            "2.5",
            "0.0001",
            "TRUE",
            "2024-03-15",
            "ratio | wild-type",
        ]
        # 0.1 + 0.2 -> "0.3" (15 significant digits), scientific notation kept,
        # datetime with a time component, embedded newline collapsed.
        assert rows[2] == [
            "daf-16",
            "C. elegans",
            "0.3",
            "1e-05",
            "FALSE",
            "2024-03-16 14:30:00",
            "multi line note",
        ]

    def test_formula_without_cached_value_is_blank(self, doc):
        rows = _rows(doc)
        assert rows[3][0] == "Total"
        assert rows[3][2] == ""  # =SUM(...) has no cached result in openpyxl output
        assert rows[3][3] == "3"

    def test_merged_cell_keeps_top_left_value(self, doc):
        rows = _rows(doc)
        assert rows[4][0] == "Merged header spanning B-D"
        assert rows[4][1:] == [""] * 6

    def test_markdown_output_is_valid_schema(self, doc):
        md = emit_markdown(doc)
        assert md.startswith("# Supplementary Tables\n\n## Table S1\n\n| Gene | Species |")
        assert (
            "| unc-54 | C. elegans | 2.5 | 0.0001 | TRUE | 2024-03-15 | ratio \\| wild-type |" in md
        )
        assert "## Notes" in md
        assert "## Empty" not in md
        result = validate_markdown(md)
        assert result.valid, result.errors
        assert result.warnings == []

    def test_markdown_round_trip(self, doc):
        back = read_markdown(emit_markdown(doc))
        assert back.title == "Supplementary Tables"
        assert [s.heading for s in back.sections] == ["Table S1", "Notes"]
        table = back.sections[0].tables[0]
        assert [c.text for c in table.rows[0]][:3] == ["Gene", "Species", "Fold change"]
        assert [c.text for c in table.rows[1]][-1] == "ratio | wild-type"

    def test_gzipped_input_accepted(self):
        doc = parse_xlsx(gzip.compress(FIXTURE.read_bytes()), title="GZ")
        assert [s.heading for s in doc.sections] == ["Table S1", "Notes"]


# ---------------------------------------------------------------------------
# Hand-built workbooks for edge cases
# ---------------------------------------------------------------------------


class TestCellTypes:
    def test_shared_inline_and_formula_strings(self):
        sheet = (
            '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
            '<row r="2"><c r="A2" t="inlineStr"><is><t>inline</t></is></c>'
            '<c r="B2" t="str"><f>CONCAT(A1,B1)</f><v>formula result</v></c></row>'
        )
        doc = parse_xlsx(build_xlsx({"S": sheet}, shared_strings=["alpha", "beta"]))
        assert _rows(doc) == [["alpha", "beta"], ["inline", "formula result"]]

    def test_rich_text_shared_string_runs_and_phonetics(self):
        sst_part = (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><r><t>unc-</t></r><r><rPr><i/></rPr><t>54</t></r>"
            '<rPh sb="0" eb="1"><t>IGNORED</t></rPh></si>'
            "</sst>"
        )
        sheet = '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1"><v>1</v></c></row>'
        data = build_xlsx(
            {"S": sheet}, shared_strings=["x"], extra_parts={"xl/sharedStrings.xml": sst_part}
        )
        assert _rows(parse_xlsx(data)) == [["unc-54", "1"]]

    def test_booleans_and_errors(self):
        sheet = (
            '<row r="1"><c r="A1" t="b"><v>1</v></c><c r="B1" t="b"><v>0</v></c>'
            '<c r="C1" t="e"><v>#N/A</v></c><c r="D1" t="e"><v>#DIV/0!</v></c></row>'
        )
        assert _rows(parse_xlsx(build_xlsx({"S": sheet}))) == [["TRUE", "FALSE", "#N/A", "#DIV/0!"]]

    def test_number_formatting(self):
        sheet = (
            '<row r="1"><c r="A1"><v>42</v></c><c r="B1"><v>42.0</v></c>'
            '<c r="C1"><v>0.30000000000000004</v></c><c r="D1"><v>1E-05</v></c>'
            '<c r="E1"><v>-7.5</v></c><c r="F1"><v>123456789012345680</v></c></row>'
        )
        rows = _rows(parse_xlsx(build_xlsx({"S": sheet})))
        assert rows == [["42", "42", "0.3", "1e-05", "-7.5", "123456789012345680"]]

    def test_iso_date_typed_cells(self):
        sheet = (
            '<row r="1"><c r="A1" t="d"><v>2024-03-15T00:00:00</v></c>'
            '<c r="B1" t="d"><v>2024-03-15T08:30:00</v></c></row>'
        )
        assert _rows(parse_xlsx(build_xlsx({"S": sheet}))) == [
            ["2024-03-15", "2024-03-15 08:30:00"]
        ]

    def test_cells_without_references_are_placed_sequentially(self):
        sheet = '<row><c t="inlineStr"><is><t>a</t></is></c><c><v>1</v></c></row><row><c><v>2</v></c><c><v>3</v></c></row>'
        assert _rows(parse_xlsx(build_xlsx({"S": sheet}))) == [["a", "1"], ["2", "3"]]

    def test_whitespace_only_cells_are_empty(self):
        sheet = (
            '<row r="1"><c r="A1" t="inlineStr"><is><t xml:space="preserve">   </t></is></c>'
            '<c r="B1" t="inlineStr"><is><t>x</t></is></c></row>'
        )
        # Column A is empty everywhere, so it is dropped entirely.
        assert _rows(parse_xlsx(build_xlsx({"S": sheet}))) == [["x"]]


class TestDateStyles:
    def _sheet(self, value: str, style: int) -> str:
        return f'<row r="1"><c r="A1" s="{style}"><v>{value}</v></c></row>'

    def test_builtin_date_format(self):
        styles = styles_with_formats([0, 14])
        doc = parse_xlsx(build_xlsx({"S": self._sheet("45366", 1)}, styles_xml=styles))
        assert _rows(doc) == [["2024-03-15"]]

    def test_builtin_datetime_format_with_fraction(self):
        styles = styles_with_formats([0, 22])
        doc = parse_xlsx(build_xlsx({"S": self._sheet("45366.5", 1)}, styles_xml=styles))
        assert _rows(doc) == [["2024-03-15 12:00:00"]]

    def test_builtin_time_only_format(self):
        styles = styles_with_formats([0, 21])
        doc = parse_xlsx(build_xlsx({"S": self._sheet("0.75", 1)}, styles_xml=styles))
        assert _rows(doc) == [["18:00:00"]]

    def test_custom_date_format(self):
        styles = styles_with_formats([0, 164], custom={164: "mmm d, yyyy;@"})
        doc = parse_xlsx(build_xlsx({"S": self._sheet("45292", 1)}, styles_xml=styles))
        assert _rows(doc) == [["2024-01-01"]]

    def test_custom_non_date_format_with_letters_in_quotes(self):
        styles = styles_with_formats([0, 165], custom={165: '0.0 "days"'})
        doc = parse_xlsx(build_xlsx({"S": self._sheet("45292", 1)}, styles_xml=styles))
        assert _rows(doc) == [["45292"]]

    def test_unstyled_number_stays_number(self):
        styles = styles_with_formats([0, 14])
        doc = parse_xlsx(build_xlsx({"S": self._sheet("45366", 0)}, styles_xml=styles))
        assert _rows(doc) == [["45366"]]

    def test_1904_date_system(self):
        styles = styles_with_formats([0, 14])
        data = build_xlsx({"S": self._sheet("43904", 1)}, styles_xml=styles, date1904=True)
        assert _rows(parse_xlsx(data)) == [["2024-03-15"]]

    def test_pre_1900_leap_bug_dates(self):
        styles = styles_with_formats([0, 14])
        sheet = (
            '<row r="1"><c r="A1" s="1"><v>1</v></c><c r="B1" s="1"><v>59</v></c>'
            '<c r="C1" s="1"><v>60</v></c><c r="D1" s="1"><v>61</v></c></row>'
        )
        assert _rows(parse_xlsx(build_xlsx({"S": sheet}, styles_xml=styles))) == [
            ["1900-01-01", "1900-02-28", "1900-02-29", "1900-03-01"]
        ]


class TestWorkbookStructure:
    def test_title_falls_back_to_core_property(self):
        data = build_xlsx({"S": "<row><c><v>1</v></c></row>"}, core_title="Core Title")
        assert parse_xlsx(data).title == "Core Title"
        assert parse_xlsx(data, title="Explicit").title == "Explicit"

    def test_empty_sheets_are_skipped(self):
        data = build_xlsx({"Empty": "", "Data": "<row><c><v>1</v></c></row>", "Blank": "<row/>"})
        doc = parse_xlsx(data)
        assert [s.heading for s in doc.sections] == ["Data"]

    def test_workbook_with_only_empty_sheets(self):
        doc = parse_xlsx(build_xlsx({"Empty": ""}, core_title="T"))
        assert doc.sections == []
        assert emit_markdown(doc) == "# T\n"

    def test_absolute_relationship_target(self):
        data = build_xlsx({"S": "<row><c><v>7</v></c></row>"})
        # Rewrite the rels part to use an absolute target.
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w") as dst:
            for item in src.infolist():
                content = src.read(item.filename)
                if item.filename == "xl/_rels/workbook.xml.rels":
                    content = content.replace(
                        b'Target="worksheets/sheet1.xml"', b'Target="/xl/worksheets/sheet1.xml"'
                    )
                dst.writestr(item, content)
        assert _rows(parse_xlsx(buf.getvalue())) == [["7"]]

    def test_single_row_sheet_emits_header_only_table(self):
        doc = parse_xlsx(build_xlsx({"S": "<row><c><v>1</v></c><c><v>2</v></c></row>"}), title="T")
        md = emit_markdown(doc)
        assert md == "# T\n\n## S\n\n| 1 | 2 |\n|---|---|\n"
        assert validate_markdown(md).valid

    def test_not_a_workbook_raises(self):
        with pytest.raises(ValueError, match="Not an Excel workbook"):
            parse_xlsx(build_docx("<w:p/>"))
        with pytest.raises(ValueError, match="Not an Excel workbook"):
            parse_xlsx(zip_bytes({"foo.txt": "bar"}))

    def test_non_zip_raises(self):
        with pytest.raises(ValueError, match="invalid ZIP"):
            parse_xlsx(b"<article/>")
