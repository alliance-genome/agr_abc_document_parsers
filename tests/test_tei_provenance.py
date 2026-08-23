"""Contract tests for additive TEI-to-Markdown page provenance."""

from agr_abc_document_parsers import (
    Document,
    SourceProvenance,
    convert_tei_to_markdown_with_provenance,
    convert_xml_to_markdown,
    emit_markdown_with_provenance,
    parse_tei,
    read_markdown,
    validate_markdown,
)

PROVENANCE_TEI = b"""\
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title level="a" xml:id="title-1" coords="1,10,10,50,10">Page-aware paper</title>
      </titleStmt>
      <publicationStmt><p/></publicationStmt>
      <sourceDesc><biblStruct><monogr><imprint/></monogr></biblStruct></sourceDesc>
    </fileDesc>
    <profileDesc>
      <abstract>
        <p xml:id="abstract-1" coords="1,10,30,50,10">Abstract text.</p>
      </abstract>
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div>
        <head xml:id="head-1" coords="2,10,10,50,10">Results</head>
        <p xml:id="p-cross" coords="2,10,30,50,10;3,10,10,50,10;2,1,1,1,1">
          Cross-page paragraph.
        </p>
        <formula xml:id="formula-1" coords="3,10,30,50,10">x = 1</formula>
        <list xml:id="list-1" coords="3,10,50,50,10">
          <item>First item</item><item>Second item</item>
        </list>
        <figure xml:id="figure-1" coords="4,10,10,50,10">
          <head>Figure 1.</head><figDesc>Figure caption.</figDesc>
        </figure>
        <figure type="table" xml:id="table-1" coords="5,10,10,50,10">
          <head>Table 1.</head><figDesc>Table caption.</figDesc>
          <table>
            <row role="head"><cell>Column</cell></row>
            <row><cell>Value</cell></row>
          </table>
        </figure>
      </div>
    </body>
    <back>
      <div type="acknowledgement">
        <div>
          <head xml:id="ack-head" coords="6,10,5,50,10">Acknowledgments</head>
          <p xml:id="ack-1" coords="6,10,10,50,10">Thanks to everyone.</p>
        </div>
      </div>
      <div type="references"><listBibl>
        <biblStruct xml:id="b0" coords="7,10,10,50,10">
          <analytic><title level="a">A cited paper</title></analytic>
          <monogr><title level="j">A Journal</title><imprint><date when="2024"/></imprint></monogr>
        </biblStruct>
      </listBibl></div>
    </back>
  </text>
</TEI>
"""


def _span_text(markdown: str, byte_start: int, byte_end: int) -> str:
    return markdown.encode("utf-8")[byte_start:byte_end].decode("utf-8")


def test_tei_provenance_preserves_canonical_markdown_contract() -> None:
    legacy = convert_xml_to_markdown(PROVENANCE_TEI, source_format="tei")
    emission = convert_tei_to_markdown_with_provenance(PROVENANCE_TEI)

    assert emission.markdown == legacy
    assert read_markdown(emission.markdown) == read_markdown(legacy)
    assert validate_markdown(emission.markdown).valid


def test_tei_provenance_spans_are_utf8_ordered_and_non_overlapping() -> None:
    emission = convert_tei_to_markdown_with_provenance(PROVENANCE_TEI)
    encoded_length = len(emission.markdown.encode("utf-8"))

    assert emission.spans
    previous_end = 0
    for span in emission.spans:
        assert 0 <= span.byte_start < span.byte_end <= encoded_length
        assert span.byte_start >= previous_end
        previous_end = span.byte_end


def test_tei_provenance_covers_supported_native_structures() -> None:
    emission = convert_tei_to_markdown_with_provenance(PROVENANCE_TEI)
    spans = {span.native_id: span for span in emission.spans if span.native_id}

    expected = {
        "title-1": ("title", (1,), "# Page-aware paper"),
        "abstract-1": ("abstract_paragraph", (1,), "Abstract text."),
        "head-1": ("section_heading", (2,), "## Results"),
        "p-cross": ("paragraph", (2, 3), "Cross-page paragraph."),
        "formula-1": ("formula", (3,), "x = 1"),
        "list-1": ("list", (3,), "- First item"),
        "figure-1": ("figure", (4,), "### Figure 1"),
        "table-1": ("table", (5,), "| Column |"),
        "ack-head": ("acknowledgments_heading", (6,), "## Acknowledgments"),
        "ack-1": ("acknowledgments", (6,), "Thanks to everyone."),
        "b0": ("reference", (7,), "1. (2024) A cited paper."),
    }

    assert set(spans) == set(expected)
    for native_id, (kind, pages, text_fragment) in expected.items():
        span = spans[native_id]
        assert span.kind == kind
        assert span.page_numbers == pages
        assert text_fragment in _span_text(emission.markdown, span.byte_start, span.byte_end)


def test_generated_figure_and_reference_headings_inherit_first_entry_page() -> None:
    emission = convert_tei_to_markdown_with_provenance(PROVENANCE_TEI)

    expected = {
        "figure_heading": ((4,), "## Figure Legends\n\n"),
        "reference_heading": ((7,), "## References\n\n"),
    }
    for kind, (pages, text) in expected.items():
        span = next(item for item in emission.spans if item.kind == kind)
        assert span.page_numbers == pages
        assert _span_text(emission.markdown, span.byte_start, span.byte_end) == text


def test_figure_heading_ignores_a_first_figure_that_emits_no_entry() -> None:
    xml = PROVENANCE_TEI.replace(
        b'<figure xml:id="figure-1" coords="4,10,10,50,10">',
        b'<figure xml:id="empty-figure" coords="2,10,10,50,10"><graphic/></figure>'
        b'<figure xml:id="figure-1" coords="4,10,10,50,10">',
    ).replace(b"<head>Figure 1.</head>", b"")

    emission = convert_tei_to_markdown_with_provenance(xml)
    heading = next(item for item in emission.spans if item.kind == "figure_heading")

    assert heading.native_id == "figure-1"
    assert heading.page_numbers == (4,)
    assert _span_text(emission.markdown, heading.byte_start, heading.byte_end) == (
        "## Figure Legends\n\n"
    )


def test_synthetic_back_heading_uses_descendant_native_head_page() -> None:
    xml = PROVENANCE_TEI.replace(
        b'<div type="references"><listBibl>',
        b'<div type="funding"><div>'
        b'<head xml:id="funding-head" coords="8,10,10,50,10">Funding details</head>'
        b'<p xml:id="funding-text" coords="9,10,30,50,10">Supported by AGR.</p>'
        b'</div></div><div type="references"><listBibl>',
    )

    emission = convert_tei_to_markdown_with_provenance(xml)
    generated = next(
        item
        for item in emission.spans
        if _span_text(emission.markdown, item.byte_start, item.byte_end) == "## Funding\n\n"
    )

    assert generated.page_numbers == (8,)
    assert generated.native_id == "funding-head"
    assert generated.kind == "section_heading"


def test_synthetic_back_heading_falls_back_to_descendant_content_page() -> None:
    xml = PROVENANCE_TEI.replace(
        b'<div type="references"><listBibl>',
        b'<div type="funding"><div>'
        b'<p xml:id="funding-text" coords="9,10,30,50,10">Supported by AGR.</p>'
        b'</div></div><div type="references"><listBibl>',
    )

    emission = convert_tei_to_markdown_with_provenance(xml)
    generated = next(
        item
        for item in emission.spans
        if _span_text(emission.markdown, item.byte_start, item.byte_end) == "## Funding\n\n"
    )

    assert generated.page_numbers == (9,)
    assert generated.kind == "section_heading"


def test_acknowledgments_heading_falls_back_to_content_page() -> None:
    xml = PROVENANCE_TEI.replace(
        b'<head xml:id="ack-head" coords="6,10,5,50,10">Acknowledgments</head>',
        b"",
    )

    document = parse_tei(xml)
    assert document.acknowledgments_heading_provenance.native_id == "ack-1"
    assert document.acknowledgments_heading_provenance.page_numbers == (6,)

    emission = convert_tei_to_markdown_with_provenance(xml)
    heading = next(item for item in emission.spans if item.kind == "acknowledgments_heading")

    assert heading.native_id == "ack-1"
    assert heading.page_numbers == (6,)
    assert _span_text(emission.markdown, heading.byte_start, heading.byte_end) == (
        "## Acknowledgments\n\n"
    )


def test_acknowledgments_emitter_preserves_pre_heading_field_provenance() -> None:
    emission = emit_markdown_with_provenance(
        Document(
            acknowledgments="Thanks to everyone.",
            acknowledgments_provenance=SourceProvenance(
                native_id="legacy-ack",
                page_numbers=(6,),
            ),
        )
    )
    heading = next(item for item in emission.spans if item.kind == "acknowledgments_heading")

    assert heading.native_id == "legacy-ack"
    assert heading.page_numbers == (6,)
    assert _span_text(emission.markdown, heading.byte_start, heading.byte_end) == (
        "## Acknowledgments\n\n"
    )


def test_invalid_coordinate_segments_are_ignored_without_reordering_pages() -> None:
    xml = PROVENANCE_TEI.replace(
        b'coords="2,10,30,50,10;3,10,10,50,10;2,1,1,1,1"',
        b'coords="0,1,1,1,1;nope;-2,1,1,1,1;3,1,1,1,1;2,1,1,1,1;3,2,2,2,2"',
    )

    emission = convert_tei_to_markdown_with_provenance(xml)
    paragraph = next(span for span in emission.spans if span.native_id == "p-cross")

    assert paragraph.page_numbers == (3, 2)
