"""Tests for the Word (.docx) parser."""

from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from agr_abc_document_parsers import emit_markdown, read_markdown, validate_markdown
from agr_abc_document_parsers.docx_parser import parse_docx
from agr_abc_document_parsers.models import Section

from .ooxml_helpers import W_NS, build_docx, build_xlsx, p, r, tbl

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES_DIR / "supplement_methods.docx"


def _flatten(sections: list[Section]) -> list[Section]:
    out: list[Section] = []
    for s in sections:
        out.append(s)
        out.extend(_flatten(s.subsections))
    return out


def _texts(doc) -> list[str]:
    """Paragraph texts in emission order (heading-less subsections included)."""
    return [para.text for s in _flatten(doc.sections) for para in s.paragraphs]


# ---------------------------------------------------------------------------
# Real python-docx-generated document
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def doc():
    return parse_docx(FIXTURE.read_bytes())


@pytest.fixture(scope="module")
def md(doc):
    return emit_markdown(doc)


class TestFixtureDocument:
    def test_title_from_title_style_beats_core_property(self, doc):
        assert doc.title == "Supplementary Methods for Gene Study"
        assert doc.source_format == "docx"

    def test_explicit_title_wins_and_demotes_title_paragraph(self):
        doc = parse_docx(FIXTURE.read_bytes(), title="Table S2")
        assert doc.title == "Table S2"
        assert _texts(doc)[0] == "Supplementary Methods for Gene Study"

    def test_heading_hierarchy(self, doc):
        assert [s.heading for s in doc.sections] == ["Strains and culture", "Statistics"]
        strains = doc.sections[0]
        assert [s.heading for s in strains.subsections] == ["Media"]
        assert strains.subsections[0].level == 2

    def test_skipped_heading_level_is_normalized(self, doc):
        stats = doc.sections[1]
        headed = [s for s in _flatten([stats]) if s.heading]
        assert [s.heading for s in headed] == ["Statistics", "Deeply nested note"]
        # Heading 3 directly under Heading 1 becomes a level-2 subsection (H3).
        assert headed[1].level == 2

    def test_inline_formatting(self, doc):
        para = doc.sections[0].paragraphs[0].text
        assert para == (
            "Worms were grown on NGM plates seeded with *E. coli* OP50 at 20 <sup>o</sup>C. "
            "The *unc-54* allele was **essential**."
        )

    def test_hyperlink(self, doc):
        assert (
            doc.sections[0].paragraphs[1].text
            == "Data are available from [the Alliance](https://www.alliancegenome.org/)."
        )

    def test_lists_and_block_order(self, md):
        expected = (
            "### Media\n\n"
            "Reagents used:\n\n"
            "- NGM agar\n- OP50 bacteria\n\n"
            "Then the paragraph after the list.\n\n"
            "1. Boil the agar\n2. Pour the plates\n\n"
            "## Statistics\n"
        )
        assert expected in md

    def test_table_with_header_row_and_following_text(self, md):
        expected = (
            "Summary statistics are shown below.\n\n"
            "| Strain | n | Mean lifespan (days) |\n"
            "|---|---|---|\n"
            "| N2 | 120 | 18.2 |\n"
            "| daf-2(e1370) | 115 | 34.7 |\n\n"
            "Table S1. Lifespan of the strains used.\n\n"
            "Final remarks after the table.\n\n"
            "### Deeply nested note\n"
        )
        assert expected in md
        table = doc_table(md)
        assert table is not None

    def test_soft_line_break_and_empty_paragraph(self, md):
        assert "Line one line two after a soft break" in md
        assert "\n\n\n" not in md

    def test_markdown_is_valid_schema(self, md):
        assert md.startswith("# Supplementary Methods for Gene Study\n\n## Strains and culture\n")
        result = validate_markdown(md)
        assert result.valid, result.errors
        assert result.warnings == []

    def test_round_trip_preserves_structure(self, md):
        back = read_markdown(md)
        assert back.title == "Supplementary Methods for Gene Study"
        assert [s.heading for s in back.sections] == ["Strains and culture", "Statistics"]
        stats = back.sections[1]
        assert any(t.rows and t.rows[0][0].text == "Strain" for t in stats.tables)

    def test_gzipped_input(self):
        doc = parse_docx(gzip.compress(FIXTURE.read_bytes()))
        assert doc.title == "Supplementary Methods for Gene Study"


def doc_table(md: str):
    for line in md.splitlines():
        if line.startswith("| Strain |"):
            return line
    return None


# ---------------------------------------------------------------------------
# Hand-built documents for edge cases
# ---------------------------------------------------------------------------


class TestHeadings:
    def test_localized_style_id_matched_by_name(self):
        doc = parse_docx(build_docx(p("Einleitung", style="Ueberschrift1") + p("Text")))
        assert doc.sections[0].heading == "Einleitung"
        assert doc.sections[0].paragraphs[0].text == "Text"

    def test_custom_style_based_on_heading(self):
        body = p("Top", style="Heading1") + p("Custom", style="MyCustomHead") + p("Body")
        doc = parse_docx(build_docx(body))
        assert doc.sections[0].subsections[0].heading == "Custom"
        assert doc.sections[0].subsections[0].paragraphs[0].text == "Body"

    def test_outline_level_only_style(self):
        doc = parse_docx(build_docx(p("Top", style="Heading1") + p("Deep", style="OutlineOnly")))
        # outlineLvl 2 -> heading level 3, normalized to 2 (no skip under level 1)
        sub = doc.sections[0].subsections[0]
        assert sub.heading == "Deep"
        assert sub.level == 2

    def test_direct_outline_level_on_paragraph(self):
        body = '<w:p><w:pPr><w:outlineLvl w:val="0"/></w:pPr>' + r("Direct") + "</w:p>" + p("Body")
        doc = parse_docx(build_docx(body))
        assert doc.sections[0].heading == "Direct"

    def test_body_text_outline_level_nine_is_not_heading(self):
        doc = parse_docx(build_docx(p("Just text", style="BodyText")))
        assert doc.sections[0].heading == ""
        assert doc.sections[0].paragraphs[0].text == "Just text"

    def test_heading_before_any_body_and_preamble(self):
        body = p("Preamble") + p("H1", style="Heading1") + p("Body") + p("H1b", style="Heading1")
        doc = parse_docx(build_docx(body))
        assert [s.heading for s in doc.sections] == ["", "H1", "H1b"]
        md = emit_markdown(parse_docx(build_docx(body), title="T"))
        assert md == "# T\n\nPreamble\n\n## H1\n\nBody\n\n## H1b\n"

    def test_empty_heading_paragraph_ignored(self):
        doc = parse_docx(build_docx(p("", style="Heading1") + p("Body")))
        assert len(doc.sections) == 1
        assert doc.sections[0].heading == ""

    def test_without_styles_part(self):
        doc = parse_docx(build_docx(p("Head", style="Heading2") + p("Body"), styles_xml=None))
        # Falls back to the Heading<N> style id pattern.
        assert doc.sections[0].heading == "Head"
        assert doc.sections[0].level == 1


class TestInlineText:
    def test_adjacent_runs_with_same_formatting_merge(self):
        runs = r("C. ", italic=True) + r("elegans", italic=True) + r(" is a worm")
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "*C. elegans* is a worm"

    def test_edge_whitespace_moved_outside_markers(self):
        runs = r("A") + r(" bold ", bold=True) + r("B")
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "A **bold** B"

    def test_bold_italic_sup_sub(self):
        runs = (
            r("Ca", bold=False)
            + r("2+", vert="superscript")
            + r(" and H")
            + r("2", vert="subscript")
            + r("O ")
            + r("both", bold=True, italic=True)
        )
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "Ca<sup>2+</sup> and H<sub>2</sub>O ***both***"

    def test_toggle_values_false(self):
        runs = '<w:r><w:rPr><w:b w:val="0"/><w:i w:val="false"/></w:rPr><w:t>plain</w:t></w:r>'
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "plain"

    def test_tabs_breaks_and_hyphens(self):
        runs = (
            "<w:r><w:t>a</w:t><w:tab/><w:t>b</w:t><w:br/><w:t>c</w:t>"
            "<w:noBreakHyphen/><w:t>d</w:t><w:softHyphen/><w:t>e</w:t></w:r>"
        )
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "a b c-de"

    def test_hyperlink_with_and_without_relationship(self):
        runs = (
            r("See ")
            + '<w:hyperlink r:id="rId9">'
            + r("here", bold=True)
            + "</w:hyperlink>"
            + r(" or ")
            + '<w:hyperlink w:anchor="_Toc1">'
            + r("internal")
            + "</w:hyperlink>"
            + r(".")
        )
        doc = parse_docx(build_docx(p(runs=runs), hyperlinks={"rId9": "https://x.org/a?b=1"}))
        assert (
            doc.sections[0].paragraphs[0].text == "See [**here**](https://x.org/a?b=1) or internal."
        )

    def test_deleted_text_and_field_codes_skipped_insertions_kept(self):
        runs = (
            '<w:del w:id="1"><w:r><w:delText>gone</w:delText></w:r></w:del>'
            '<w:ins w:id="2">'
            + r("added")
            + "</w:ins>"
            + '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            + '<w:r><w:instrText xml:space="preserve"> REF _Ref1 \\h </w:instrText></w:r>'
            + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            + r(" result")
            + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
            + '<w:fldSimple w:instr=" PAGE ">'
            + r(" 3")
            + "</w:fldSimple>"
            + '<w:proofErr w:type="spellStart"/><w:bookmarkStart w:id="0" w:name="_GoBack"/>'
        )
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "added result 3"

    def test_alternate_content_uses_single_branch(self):
        runs = (
            '<mc:AlternateContent><mc:Choice Requires="wps">' + r("chosen") + "</mc:Choice>"
            "<mc:Fallback>" + r("fallback") + "</mc:Fallback></mc:AlternateContent>"
        )
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "chosen"

    def test_text_box_content_becomes_following_blocks(self):
        txbx = (
            '<w:r><w:drawing><wp:anchor xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
            '<wps:txbx xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
            "<w:txbxContent>"
            + p("Box text")
            + "</w:txbxContent></wps:txbx></wp:anchor></w:drawing></w:r>"
        )
        doc = parse_docx(build_docx(p(runs=r("Before") + txbx) + p("After")))
        assert _texts(doc) == ["Before", "Box text", "After"]

    def test_math_text_flattened(self):
        runs = (
            r("E = ")
            + "<m:oMath><m:r><m:t>mc</m:t></m:r><m:sSup><m:e><m:r><m:t>2</m:t></m:r></m:e></m:sSup></m:oMath>"
        )
        doc = parse_docx(build_docx(p(runs=runs)))
        assert doc.sections[0].paragraphs[0].text == "E = mc2"

    def test_whitespace_collapsed(self):
        doc = parse_docx(build_docx(p(runs=r("  lots   of\n  space  "))))
        assert doc.sections[0].paragraphs[0].text == "lots of space"


class TestLists:
    def test_bullets_and_numbers_group_consecutive_items(self):
        body = (
            p("Intro")
            + p("one", num_id="1")
            + p("two", num_id="1")
            + p("first", num_id="2")
            + p("second", num_id="2")
            + p("Outro")
        )
        doc = parse_docx(build_docx(body), title="T")
        sec = doc.sections[0]
        assert [(lst.items, lst.ordered) for lst in sec.lists] == [
            (["one", "two"], False),
            (["first", "second"], True),
        ]
        md = emit_markdown(doc)
        assert md == "# T\n\nIntro\n\n- one\n- two\n\n1. first\n2. second\n\nOutro\n"

    def test_list_from_paragraph_style(self):
        doc = parse_docx(
            build_docx(p("styled bullet", style="ListBullet") + p("next", style="ListBullet"))
        )
        assert doc.sections[0].lists[0].items == ["styled bullet", "next"]
        assert doc.sections[0].lists[0].ordered is False

    def test_level_override_and_ilvl(self):
        body = p("overridden bullet", num_id="3") + p("level-1 decimal", num_id="1", ilvl="1")
        doc = parse_docx(build_docx(body))
        assert [(lst.items, lst.ordered) for lst in doc.sections[0].lists] == [
            (["overridden bullet"], False),
            (["level-1 decimal"], True),
        ]

    def test_num_id_zero_and_unknown_num_id_are_plain_paragraphs(self):
        doc = parse_docx(build_docx(p("not a list", num_id="0") + p("unknown", num_id="99")))
        assert _texts(doc) == ["not a list", "unknown"]
        assert doc.sections[0].lists == []

    def test_heading_with_numbering_is_a_heading(self):
        body = (
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>'
            + r("Numbered heading")
            + "</w:p>"
        )
        doc = parse_docx(build_docx(body))
        assert doc.sections[0].heading == "Numbered heading"


class TestTables:
    def test_grid_span_pads_columns_and_header_flag(self):
        body = (
            '<w:tbl><w:tblPr><w:tblCaption w:val="Strains used"/></w:tblPr>'
            "<w:tr><w:trPr><w:tblHeader/></w:trPr>"
            '<w:tc><w:tcPr><w:gridSpan w:val="2"/></w:tcPr>' + p("Wide") + "</w:tc>"
            "<w:tc>" + p("C") + "</w:tc></w:tr>"
            "<w:tr><w:tc>"
            + p("1")
            + "</w:tc><w:tc>"
            + p("2")
            + "</w:tc><w:tc>"
            + p("3")
            + "</w:tc></w:tr>"
            "</w:tbl>"
        )
        doc = parse_docx(build_docx(body), title="T")
        table = doc.sections[0].tables[0]
        assert [[c.text for c in row] for row in table.rows] == [["Wide", "", "C"], ["1", "2", "3"]]
        assert all(c.is_header for c in table.rows[0])
        assert table.caption == "Strains used"
        md = emit_markdown(doc)
        assert "| Wide |  | C |\n|---|---|---|\n| 1 | 2 | 3 |\n\nStrains used\n" in md

    def test_multi_paragraph_cells_and_pipes(self):
        body = tbl([["a | b", "x"], ["c", "d"]])
        body = body.replace("<w:tc>" + p("x") + "</w:tc>", "<w:tc>" + p("x1") + p("x2") + "</w:tc>")
        doc = parse_docx(build_docx(body), title="T")
        md = emit_markdown(doc)
        assert "| a \\| b | x1 x2 |" in md

    def test_ragged_rows_padded(self):
        doc = parse_docx(build_docx(tbl([["h1", "h2", "h3"], ["only one"]])), title="T")
        rows = doc.sections[0].tables[0].rows
        assert [len(r) for r in rows] == [3, 3]
        assert validate_markdown(emit_markdown(doc)).valid

    def test_nested_table_flattened_into_cell(self):
        inner = tbl([["i1", "i2"]])
        body = (
            "<w:tbl><w:tr><w:tc>"
            + p("outer")
            + inner
            + "</w:tc><w:tc>"
            + p("b")
            + "</w:tc></w:tr></w:tbl>"
        )
        doc = parse_docx(build_docx(body))
        assert doc.sections[0].tables[0].rows[0][0].text == "outer i1 i2"

    def test_empty_table_skipped(self):
        doc = parse_docx(build_docx(tbl([["", ""], ["", ""]]) + p("after")))
        assert doc.sections[0].tables == []
        assert _texts(doc) == ["after"]

    def test_tables_between_paragraphs_keep_order(self):
        body = p("P1") + tbl([["h"], ["v"]]) + p("P2") + tbl([["h2"], ["v2"]]) + p("P3")
        md = emit_markdown(parse_docx(build_docx(body), title="T"))
        assert md == ("# T\n\nP1\n\n| h |\n|---|\n| v |\n\nP2\n\n| h2 |\n|---|\n| v2 |\n\nP3\n")
        back = read_markdown(md)
        assert back.title == "T"


class TestNotes:
    FOOTNOTES = (
        f'<w:footnotes xmlns:w="{W_NS}">'
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:id="1"><w:p><w:r><w:footnoteRef/></w:r>'
        + r(" First note.")
        + "</w:p></w:footnote>"
        '<w:footnote w:id="2"><w:p>'
        + r("Second ")
        + "</w:p><w:p>"
        + r("note.")
        + "</w:p></w:footnote>"
        "</w:footnotes>"
    )
    ENDNOTES = (
        f'<w:endnotes xmlns:w="{W_NS}">'
        '<w:endnote w:id="1"><w:p>' + r("An endnote.") + "</w:p></w:endnote>"
        "</w:endnotes>"
    )

    def test_footnotes_and_endnotes_numbered_in_order(self):
        body = (
            p(runs=r("Alpha") + '<w:r><w:footnoteReference w:id="2"/></w:r>' + r(" text."))
            + p("H", style="Heading1")
            + p(runs=r("Beta") + '<w:r><w:endnoteReference w:id="1"/></w:r>')
            + p(runs=r("Gamma") + '<w:r><w:footnoteReference w:id="1"/></w:r>')
        )
        doc = parse_docx(
            build_docx(body, footnotes_xml=self.FOOTNOTES, endnotes_xml=self.ENDNOTES), title="T"
        )
        md = emit_markdown(doc)
        assert md == (
            "# T\n\n"
            "Alpha[^1] text.\n\n"
            "[^1]: Second note.\n\n"
            "## H\n\n"
            "Beta[^2]\n\n"
            "Gamma[^3]\n\n"
            "[^2]: An endnote.\n"
            "[^3]: First note.\n"
        )
        assert validate_markdown(md).valid

    def test_missing_note_definition_leaves_no_marker(self):
        body = p(runs=r("Alpha") + '<w:r><w:footnoteReference w:id="7"/></w:r>')
        doc = parse_docx(build_docx(body, footnotes_xml=self.FOOTNOTES))
        assert _texts(doc) == ["Alpha"]
        assert doc.sections[0].notes == []


class TestDocumentLevel:
    def test_title_fallback_order(self):
        body = p("Styled Title", style="Title") + p("Body")
        assert parse_docx(build_docx(body, core_title="Core")).title == "Styled Title"
        assert parse_docx(build_docx(p("Body"), core_title="Core")).title == "Core"
        assert parse_docx(build_docx(p("Body"))).title == ""
        assert parse_docx(build_docx(body), title="Given").title == "Given"

    def test_content_controls_and_strict_namespace(self):
        strict = "http://purl.oclc.org/ooxml/wordprocessingml/main"
        body = (
            "<w:sdt><w:sdtContent>"
            + p("H", style="Heading1")
            + p("inside")
            + "</w:sdtContent></w:sdt>"
        )
        doc = parse_docx(build_docx(body, styles_xml=None, w_ns=strict))
        assert doc.sections[0].heading == "H"
        assert doc.sections[0].paragraphs[0].text == "inside"

    def test_not_a_document_raises(self):
        with pytest.raises(ValueError, match="Not a Word document"):
            parse_docx(build_xlsx({"S": ""}))

    def test_non_zip_raises(self):
        with pytest.raises(ValueError, match="invalid ZIP"):
            parse_docx(b"<TEI/>")
