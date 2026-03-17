"""Tests for Markdown reader (md_reader.py)."""

from agr_abc_document_parsers.md_emitter import emit_markdown
from agr_abc_document_parsers.md_reader import (
    load_document_with_supplements,
    read_markdown,
)
from agr_abc_document_parsers.models import (
    Author,
    Document,
    Figure,
    FundingEntry,
    ListBlock,
    Paragraph,
    Reference,
    SecondaryAbstract,
    Section,
    Table,
    TableCell,
)


def _make_doc(**kwargs) -> Document:
    """Helper to create a Document with defaults overridden by kwargs."""
    return Document(**kwargs)


# ---------------------------------------------------------------------------
# Basic element parsing
# ---------------------------------------------------------------------------


class TestReadMarkdownBasic:
    """Test parsing of individual document elements."""

    def test_empty_string(self):
        doc = read_markdown("")
        assert doc.title == ""
        assert doc.authors == []
        assert doc.abstract == []

    def test_title_only(self):
        doc = read_markdown("# My Paper Title\n")
        assert doc.title == "My Paper Title"

    def test_title_and_authors(self):
        md = "# Title\n\nAlice Smith, Bob Jones\n"
        doc = read_markdown(md)
        assert doc.title == "Title"
        assert len(doc.authors) == 2
        assert doc.authors[0].given_name == "Alice"
        assert doc.authors[0].surname == "Smith"
        assert doc.authors[1].given_name == "Bob"
        assert doc.authors[1].surname == "Jones"

    def test_abstract(self):
        md = "# Title\n\n## Abstract\n\nFirst paragraph.\n\nSecond paragraph.\n"
        doc = read_markdown(md)
        assert len(doc.abstract) == 2
        assert doc.abstract[0].text == "First paragraph."
        assert doc.abstract[1].text == "Second paragraph."

    def test_keywords_after_abstract(self):
        md = (
            "# Title\n\n## Abstract\n\nAbstract text.\n\n"
            "**Keywords:** gene expression, RNA-seq, transcriptomics\n\n"
            "## Introduction\n\nIntro text.\n"
        )
        doc = read_markdown(md)
        assert doc.keywords == ["gene expression", "RNA-seq", "transcriptomics"]
        assert len(doc.abstract) == 1
        assert doc.abstract[0].text == "Abstract text."

    def test_keywords_without_abstract(self):
        md = "# Title\n\nAuthor A\n\n**Keywords:** kw1, kw2\n\n## Introduction\n\nText.\n"
        doc = read_markdown(md)
        assert doc.keywords == ["kw1", "kw2"]

    def test_sections(self):
        md = "# Title\n\n## Introduction\n\nIntro text.\n\n## Methods\n\nMethods text.\n"
        doc = read_markdown(md)
        assert len(doc.sections) == 2
        assert doc.sections[0].heading == "Introduction"
        assert doc.sections[0].paragraphs[0].text == "Intro text."
        assert doc.sections[1].heading == "Methods"

    def test_nested_sections(self):
        md = (
            "## Methods\n\nMethods overview.\n\n"
            "### Samples\n\nSample text.\n\n"
            "#### RNA extraction\n\nRNA text.\n\n"
            "### Analysis\n\nAnalysis text.\n"
        )
        doc = read_markdown(md)
        assert len(doc.sections) == 1
        sec = doc.sections[0]
        assert sec.heading == "Methods"
        assert len(sec.subsections) == 2
        assert sec.subsections[0].heading == "Samples"
        assert len(sec.subsections[0].subsections) == 1
        assert sec.subsections[0].subsections[0].heading == "RNA extraction"
        assert sec.subsections[1].heading == "Analysis"

    def test_figures(self):
        md = "## Results\n\n**Figure 1.** Expression levels.\n"
        doc = read_markdown(md)
        assert len(doc.sections[0].figures) == 1
        fig = doc.sections[0].figures[0]
        assert fig.label == "Figure 1"
        assert fig.caption == "Expression levels."

    def test_figure_no_caption(self):
        md = "## Results\n\n**Figure 1.**\n"
        doc = read_markdown(md)
        fig = doc.sections[0].figures[0]
        assert fig.label == "Figure 1"
        assert fig.caption == ""

    def test_tables_gfm(self):
        md = "## Results\n\n| Gene | Expression |\n|---|---|\n| BRCA1 | 2.5 |\n"
        doc = read_markdown(md)
        assert len(doc.sections[0].tables) == 1
        table = doc.sections[0].tables[0]
        assert len(table.rows) == 2
        assert table.rows[0][0].text == "Gene"
        assert table.rows[0][0].is_header is True
        assert table.rows[1][0].text == "BRCA1"
        assert table.rows[1][0].is_header is False

    def test_table_with_caption(self):
        md = "## Results\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n**Table 1.** Summary.\n"
        doc = read_markdown(md)
        table = doc.sections[0].tables[0]
        assert table.label == "Table 1"
        assert table.caption == "Summary."

    def test_table_with_footnotes(self):
        md = (
            "## Results\n\n"
            "| A | B |\n"
            "|---|---|\n"
            "| 1 | 2 |\n\n"
            "**Table 1.** Summary.\n\n"
            "FC, fold change.\n"
            "*P < 0.05.\n"
        )
        doc = read_markdown(md)
        table = doc.sections[0].tables[0]
        assert table.label == "Table 1"
        assert table.caption == "Summary."
        assert len(table.foot_notes) == 2
        assert table.foot_notes[0] == "FC, fold change."
        assert table.foot_notes[1] == "*P < 0.05."

    def test_unordered_list(self):
        md = "## Methods\n\n- Step one\n- Step two\n- Step three\n"
        doc = read_markdown(md)
        assert len(doc.sections[0].lists) == 1
        lst = doc.sections[0].lists[0]
        assert lst.ordered is False
        assert lst.items == ["Step one", "Step two", "Step three"]

    def test_ordered_list(self):
        md = "## Methods\n\n1. First\n2. Second\n3. Third\n"
        doc = read_markdown(md)
        lst = doc.sections[0].lists[0]
        assert lst.ordered is True
        assert lst.items == ["First", "Second", "Third"]

    def test_footnotes(self):
        md = (
            "## Discussion\n\n"
            "[^1]: Additional methodological details.\n"
            "[^2]: See supplementary materials.\n"
        )
        doc = read_markdown(md)
        assert doc.sections[0].notes == [
            "Additional methodological details.",
            "See supplementary materials.",
        ]

    def test_acknowledgments(self):
        md = "## Acknowledgments\n\nWe thank the NIH for funding.\n"
        doc = read_markdown(md)
        assert doc.acknowledgments == "We thank the NIH for funding."

    def test_references(self):
        md = (
            "## References\n\n"
            "1. Lee C, Park D (2020) Genomic analysis of expression."
            " *Nature Genetics*, 52(3), 100-110."
            " doi:10.1038/ng.2020\n"
            "2. Wang E (2019) RNA-seq best practices."
            " *Bioinformatics*, 36, 200-215.\n"
        )
        doc = read_markdown(md)
        assert len(doc.references) == 2
        ref1 = doc.references[0]
        assert ref1.index == 1
        assert ref1.authors == ["Lee C", "Park D"]
        assert ref1.year == "2020"
        assert ref1.title == "Genomic analysis of expression"
        assert ref1.journal == "Nature Genetics"
        assert ref1.volume == "52"
        assert ref1.issue == "3"
        assert ref1.pages == "100-110"
        assert ref1.doi == "10.1038/ng.2020"

    def test_reference_with_pmid_pmcid(self):
        md = (
            "## References\n\n"
            "1. Doe J (2024) Test paper."
            " *PLOS ONE*."
            " doi:10.1234/test"
            " PMID:11111111"
            " PMCID:PMC9999999"
            " https://example.com/data\n"
        )
        doc = read_markdown(md)
        ref = doc.references[0]
        assert ref.doi == "10.1234/test"
        assert ref.pmid == "11111111"
        assert ref.pmcid == "PMC9999999"
        assert ref.ext_links == ["https://example.com/data"]

    def test_reference_with_editors_publisher(self):
        md = (
            "## References\n\n"
            "1. Auth A (2023) Book chapter title."
            " In: Part One."
            " Edited by Editor E."
            " *Big Book*."
            " New York: Academic Press.\n"
        )
        doc = read_markdown(md)
        ref = doc.references[0]
        assert ref.title == "Book chapter title"
        assert ref.chapter_title == "Part One"
        assert ref.editors == ["Editor E"]
        assert ref.journal == "Big Book"
        assert ref.publisher_loc == "New York"
        assert ref.publisher == "Academic Press"

    def test_back_matter(self):
        md = (
            "## Introduction\n\nText.\n\n"
            "## Acknowledgments\n\nThanks.\n\n"
            "## Appendix\n\nExtra content.\n\n"
            "## References\n\n1. Ref (2024) Title. *J*.\n"
        )
        doc = read_markdown(md)
        assert doc.acknowledgments == "Thanks."
        assert len(doc.back_matter) == 1
        assert doc.back_matter[0].heading == "Appendix"
        assert doc.back_matter[0].paragraphs[0].text == "Extra content."

    def test_escaped_pipe_in_table(self):
        md = "## Results\n\n| Gene | Notes |\n|---|---|\n| BRCA1 | see ref \\| note |\n"
        doc = read_markdown(md)
        table = doc.sections[0].tables[0]
        assert table.rows[1][0].text == "BRCA1"
        assert table.rows[1][1].text == "see ref | note"


# ---------------------------------------------------------------------------
# Supplement / partial document handling
# ---------------------------------------------------------------------------


class TestReadMarkdownSupplements:
    """Test parsing of partial/supplement documents."""

    def test_no_title(self):
        md = "## Section One\n\nSome content.\n"
        doc = read_markdown(md)
        assert doc.title == ""
        assert len(doc.sections) == 1
        assert doc.sections[0].heading == "Section One"

    def test_no_abstract(self):
        md = "# Supplement Title\n\n## Data\n\nData content.\n"
        doc = read_markdown(md)
        assert doc.abstract == []
        assert len(doc.sections) == 1

    def test_no_references(self):
        md = "# Title\n\n## Methods\n\nText.\n"
        doc = read_markdown(md)
        assert doc.references == []

    def test_body_only(self):
        md = "## Results\n\nResult text.\n\n## Discussion\n\nDiscussion text.\n"
        doc = read_markdown(md)
        assert doc.title == ""
        assert doc.authors == []
        assert len(doc.sections) == 2

    def test_preamble_content_no_headings(self):
        """Content with no headings at all goes into a section."""
        md = "This is some text without any headings.\n\nAnother paragraph.\n"
        doc = read_markdown(md)
        # First non-heading line could be parsed as author or preamble
        # depending on content; the important thing is no crash
        assert isinstance(doc, Document)

    def test_load_document_with_supplements(self):
        main_md = "# Main Paper\n\n## Abstract\n\nAbstract.\n"
        supp1_md = "## Supplementary Methods\n\nExtra methods.\n"
        supp2_md = "## Supplementary Tables\n\n| A |\n|---|\n| 1 |\n"

        doc = load_document_with_supplements(
            main_md,
            [supp1_md, supp2_md],
        )
        assert doc.title == "Main Paper"
        assert len(doc.supplements) == 2
        assert doc.supplements[0].sections[0].heading == "Supplementary Methods"
        assert len(doc.supplements[1].sections[0].tables) == 1

    def test_load_document_no_supplements(self):
        main_md = "# Paper\n\n## Intro\n\nText.\n"
        doc = load_document_with_supplements(main_md)
        assert doc.title == "Paper"
        assert doc.supplements == []

    def test_supplements_field_on_document(self):
        doc = Document()
        assert doc.supplements == []
        doc.supplements.append(Document(title="Supp 1"))
        assert len(doc.supplements) == 1


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """Test that emit -> read -> emit produces identical Markdown."""

    def _assert_round_trip(self, doc: Document) -> None:
        """Assert that a document round-trips through emit/read/emit."""
        md1 = emit_markdown(doc)
        doc2 = read_markdown(md1)
        md2 = emit_markdown(doc2)
        assert md1 == md2, (
            f"Round-trip failed.\n--- Original ---\n{md1}\n--- Round-tripped ---\n{md2}"
        )

    def test_round_trip_title_only(self):
        self._assert_round_trip(_make_doc(title="My Paper"))

    def test_round_trip_title_and_authors(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper Title",
                authors=[
                    Author(given_name="Alice", surname="Smith"),
                    Author(given_name="Bob", surname="Jones"),
                ],
            )
        )

    def test_round_trip_abstract(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                abstract=[
                    Paragraph(text="First abstract paragraph."),
                    Paragraph(text="Second abstract paragraph."),
                ],
            )
        )

    def test_round_trip_keywords(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                abstract=[Paragraph(text="Abstract.")],
                keywords=["gene expression", "RNA-seq", "transcriptomics"],
            )
        )

    def test_round_trip_sections(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Introduction",
                        paragraphs=[
                            Paragraph(text="Intro text."),
                        ],
                    ),
                    Section(
                        heading="Methods",
                        paragraphs=[
                            Paragraph(text="Methods text."),
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_nested_sections(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Methods",
                        subsections=[
                            Section(
                                heading="Samples",
                                paragraphs=[
                                    Paragraph(text="Sample text."),
                                ],
                                subsections=[
                                    Section(
                                        heading="RNA extraction",
                                        paragraphs=[
                                            Paragraph(text="RNA text."),
                                        ],
                                    ),
                                ],
                            ),
                            Section(
                                heading="Analysis",
                                paragraphs=[
                                    Paragraph(text="Analysis text."),
                                ],
                            ),
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_figures(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Results",
                        figures=[
                            Figure(label="Figure 1", caption="Expression levels."),
                            Figure(label="Figure 2", caption="Protein levels."),
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_tables(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Results",
                        tables=[
                            Table(
                                label="Table 1",
                                caption="Summary.",
                                rows=[
                                    [
                                        TableCell(text="Gene", is_header=True),
                                        TableCell(text="Expr", is_header=True),
                                    ],
                                    [TableCell(text="BRCA1"), TableCell(text="2.5")],
                                ],
                            ),
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_table_with_footnotes(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Results",
                        tables=[
                            Table(
                                label="Table 1",
                                caption="Summary.",
                                rows=[
                                    [
                                        TableCell(text="A", is_header=True),
                                        TableCell(text="B", is_header=True),
                                    ],
                                    [TableCell(text="1"), TableCell(text="2")],
                                ],
                                foot_notes=["FC, fold change.", "*P < 0.05."],
                            ),
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_lists(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Methods",
                        lists=[
                            ListBlock(items=["Step one", "Step two"], ordered=False),
                            ListBlock(items=["First", "Second"], ordered=True),
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_footnotes(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Discussion",
                        notes=[
                            "Additional details.",
                            "See supplementary.",
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_acknowledgments(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                acknowledgments="We thank the NIH.",
            )
        )

    def test_round_trip_references(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                references=[
                    Reference(
                        index=1,
                        authors=["Lee C", "Park D"],
                        title="Genomic analysis of expression",
                        journal="Nature Genetics",
                        volume="52",
                        issue="3",
                        pages="100-110",
                        year="2020",
                        doi="10.1038/ng.2020",
                    ),
                    Reference(
                        index=2,
                        authors=["Wang E"],
                        title="RNA-seq best practices",
                        journal="Bioinformatics",
                        volume="36",
                        pages="200-215",
                        year="2019",
                    ),
                ],
            )
        )

    def test_round_trip_reference_with_ids(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                references=[
                    Reference(
                        index=1,
                        authors=["Doe J"],
                        title="Test paper",
                        journal="PLOS ONE",
                        year="2024",
                        doi="10.1234/test",
                        pmid="11111111",
                        pmcid="PMC9999999",
                        ext_links=["https://example.com/data"],
                    ),
                ],
            )
        )

    def test_round_trip_reference_with_editors_publisher(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                references=[
                    Reference(
                        index=1,
                        authors=["Auth A"],
                        title="Book chapter title",
                        chapter_title="Part One",
                        editors=["Editor E"],
                        journal="Big Book",
                        publisher="Academic Press",
                        publisher_loc="New York",
                        year="2023",
                    ),
                ],
            )
        )

    def test_round_trip_back_matter(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                sections=[
                    Section(
                        heading="Introduction",
                        paragraphs=[
                            Paragraph(text="Text."),
                        ],
                    )
                ],
                acknowledgments="Thanks.",
                back_matter=[
                    Section(
                        heading="Funding",
                        paragraphs=[
                            Paragraph(text="NIH grant."),
                        ],
                    )
                ],
                references=[
                    Reference(index=1, authors=["A B"], title="T", journal="J", year="2024")
                ],
            )
        )

    def test_round_trip_full_document(self):
        """Full document with all elements."""
        doc = Document(
            title="A Study of Gene Expression",
            authors=[
                Author(given_name="Alice", surname="Smith"),
                Author(given_name="Bob", surname="Jones"),
            ],
            abstract=[Paragraph(text="This study examines gene expression.")],
            keywords=["gene expression", "RNA-seq"],
            sections=[
                Section(heading="Introduction", paragraphs=[Paragraph(text="Intro text here.")]),
                Section(
                    heading="Methods",
                    paragraphs=[Paragraph(text="Methods text here.")],
                    lists=[
                        ListBlock(items=["Step one", "Step two"], ordered=False),
                    ],
                ),
                Section(
                    heading="Results",
                    paragraphs=[Paragraph(text="Results text.")],
                    figures=[
                        Figure(label="Figure 1", caption="Expression levels."),
                    ],
                    tables=[
                        Table(
                            label="Table 1",
                            caption="Summary.",
                            rows=[
                                [
                                    TableCell(text="Gene", is_header=True),
                                    TableCell(text="Expr", is_header=True),
                                ],
                                [TableCell(text="BRCA1"), TableCell(text="2.5")],
                            ],
                        ),
                    ],
                ),
            ],
            acknowledgments="We thank the NIH.",
            references=[
                Reference(
                    index=1,
                    authors=["Lee C"],
                    title="Ref title",
                    journal="Nature",
                    volume="1",
                    year="2020",
                ),
            ],
        )
        self._assert_round_trip(doc)

    def test_round_trip_empty_document(self):
        self._assert_round_trip(Document())


# ---------------------------------------------------------------------------
# Round-trip with real fixture data
# ---------------------------------------------------------------------------


class TestRoundTripFixtures:
    """Round-trip tests using real converted XML fixtures.

    Uses idempotent round-trip: the second read/emit cycle must match
    the first. The first cycle may normalize ordering differences caused
    by doc-level figures and headingless back-matter sections from the
    TEI parser — these produce Markdown that can't be perfectly
    reconstructed on the first pass.
    """

    def _assert_fixture_idempotent(self, fixture_path: str) -> None:
        """Parse XML fixture, verify second round-trip is stable."""
        import gzip
        from pathlib import Path

        from agr_abc_document_parsers.tei_parser import parse_tei

        path = Path(__file__).parent / "fixtures" / fixture_path
        with gzip.open(path, "rb") as f:
            xml_bytes = f.read()

        doc = parse_tei(xml_bytes)
        md1 = emit_markdown(doc)

        # First round-trip (normalizes doc-level content)
        doc2 = read_markdown(md1)
        md2 = emit_markdown(doc2)

        # Second round-trip (must be stable)
        doc3 = read_markdown(md2)
        md3 = emit_markdown(doc3)

        assert md2 == md3, (
            f"Idempotent round-trip failed for {fixture_path}.\n"
            f"--- First pass (first 500 chars) ---\n{md2[:500]}\n"
            f"--- Second pass (first 500 chars) ---\n{md3[:500]}"
        )

    def test_tei_with_figures_keywords(self):
        self._assert_fixture_idempotent("tei_with_figures_keywords.tei.gz")

    def test_tei_with_tables(self):
        self._assert_fixture_idempotent("tei_with_tables.tei.gz")

    def test_tei_no_abstract_no_doi(self):
        self._assert_fixture_idempotent("tei_no_abstract_no_doi.tei.gz")


# ---------------------------------------------------------------------------
# New feature parsing tests
# ---------------------------------------------------------------------------


class TestReadMarkdownNewFeatures:
    """Test parsing of secondary abstracts, sub-articles, categories, roles."""

    def test_parse_categories(self):
        md = (
            "# Title\n\n"
            "**Categories:** Research Article, Cell Biology, Genetics\n\n"
            "Author Name\n\n"
            "## Abstract\n\nAbstract text.\n"
        )
        doc = read_markdown(md)
        assert doc.categories == ["Research Article", "Cell Biology", "Genetics"]
        assert doc.title == "Title"

    def test_parse_secondary_abstracts(self):
        md = (
            "# Title\n\n"
            "## Abstract\n\nMain abstract text.\n\n"
            "## Author Summary\n\nPlain language summary.\n\n"
            "## eLife Digest\n\nDigest paragraph one.\n\nDigest paragraph two.\n\n"
            "**Keywords:** kw1, kw2\n\n"
            "## Introduction\n\nBody text.\n"
        )
        doc = read_markdown(md)
        assert len(doc.abstract) == 1
        assert "Main abstract text" in doc.abstract[0].text
        assert len(doc.secondary_abstracts) == 2
        assert doc.secondary_abstracts[0].label == "Author Summary"
        assert doc.secondary_abstracts[0].abstract_type == "summary"
        assert len(doc.secondary_abstracts[0].paragraphs) == 1
        assert doc.secondary_abstracts[1].label == "eLife Digest"
        assert doc.secondary_abstracts[1].abstract_type == "executive-summary"
        assert len(doc.secondary_abstracts[1].paragraphs) == 2

    def test_parse_sub_articles(self):
        md = (
            "# Title\n\n"
            "## Abstract\n\nAbstract.\n\n"
            "## Introduction\n\nBody.\n\n"
            "## References\n\n1. Main ref (2024) Title. *J*.\n\n"
            "---\n\n"
            "## Decision letter\n\n"
            "Pat Wittkopp, Justin Crocker\n\n"
            "The reviewers find the paper interesting.\n\n"
            "---\n\n"
            "## Author response\n\n"
            "We thank the reviewers.\n\n"
            "### References\n\n"
            "1. Sub ref (2023) Sub title. *J2*.\n"
        )
        doc = read_markdown(md)
        assert doc.title == "Title"
        assert len(doc.references) == 1
        assert len(doc.sub_articles) == 2

        dl = doc.sub_articles[0]
        assert dl.title == "Decision letter"
        assert len(dl.authors) == 2
        assert dl.authors[0].given_name == "Pat"
        assert dl.authors[0].surname == "Wittkopp"

        ar = doc.sub_articles[1]
        assert ar.title == "Author response"
        assert len(ar.references) == 1
        assert ar.references[0].title == "Sub title"

    def test_parse_role_footnotes(self):
        md = (
            "# Title\n\n"
            "Rachel Waymack, Alvaro Fletcher\n\n"
            "## References\n\n1. Ref (2024) T. *J*.\n\n"
            "[^1]: Rachel Waymack: Conceptualization, Software\n"
            "[^2]: Alvaro Fletcher: Investigation\n"
        )
        doc = read_markdown(md)
        assert len(doc.authors) == 2
        assert doc.authors[0].roles == ["Conceptualization", "Software"]
        assert doc.authors[1].roles == ["Investigation"]

    def test_no_sub_articles_when_none(self):
        md = "# Title\n\n## References\n\n1. Ref (2024) T. *J*.\n"
        doc = read_markdown(md)
        assert doc.sub_articles == []


# ---------------------------------------------------------------------------
# Round-trip tests for new features
# ---------------------------------------------------------------------------


class TestRoundTripNewFeatures:
    """Round-trip tests for secondary abstracts, sub-articles, categories, roles."""

    def _assert_round_trip(self, doc: Document) -> None:
        md1 = emit_markdown(doc)
        doc2 = read_markdown(md1)
        md2 = emit_markdown(doc2)
        assert md1 == md2, (
            f"Round-trip failed.\n--- Original ---\n{md1}\n--- Round-tripped ---\n{md2}"
        )

    def test_round_trip_categories(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                categories=["Research Article", "Cell Biology"],
                authors=[Author(given_name="A", surname="B")],
            )
        )

    def test_round_trip_secondary_abstracts(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                abstract=[Paragraph(text="Main abstract.")],
                secondary_abstracts=[
                    SecondaryAbstract(
                        abstract_type="summary",
                        label="Author Summary",
                        paragraphs=[Paragraph(text="Author summary text.")],
                    ),
                    SecondaryAbstract(
                        abstract_type="executive-summary",
                        label="eLife Digest",
                        paragraphs=[
                            Paragraph(text="Digest paragraph one."),
                            Paragraph(text="Digest paragraph two."),
                        ],
                    ),
                ],
                keywords=["kw1"],
            )
        )

    def test_round_trip_sub_articles(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                references=[
                    Reference(index=1, authors=["A B"], title="T", journal="J", year="2024"),
                ],
                sub_articles=[
                    Document(
                        title="Decision letter",
                        authors=[Author(given_name="Pat", surname="Wittkopp")],
                        sections=[
                            Section(
                                heading="Summary",
                                paragraphs=[
                                    Paragraph(text="Interesting paper."),
                                ],
                            )
                        ],
                    ),
                    Document(
                        title="Author response",
                        sections=[
                            Section(
                                paragraphs=[
                                    Paragraph(text="We thank the reviewers."),
                                ]
                            )
                        ],
                        references=[
                            Reference(
                                index=1, authors=["X Y"], title="Sub ref", journal="J2", year="2023"
                            ),
                        ],
                    ),
                ],
            )
        )

    def test_round_trip_author_roles(self):
        self._assert_round_trip(
            _make_doc(
                title="Paper",
                authors=[
                    Author(
                        given_name="Rachel",
                        surname="Waymack",
                        roles=["Conceptualization", "Software"],
                    ),
                    Author(given_name="Alvaro", surname="Fletcher", roles=["Investigation"]),
                ],
                references=[
                    Reference(index=1, authors=["A B"], title="T", journal="J", year="2024"),
                ],
            )
        )

    def test_round_trip_full_with_all_new_features(self):
        """Full document with all new features."""
        self._assert_round_trip(
            Document(
                title="A Study",
                categories=["Research Article", "Genetics"],
                authors=[
                    Author(given_name="Alice", surname="Smith", roles=["Conceptualization"]),
                    Author(given_name="Bob", surname="Jones"),
                ],
                abstract=[Paragraph(text="Main abstract.")],
                secondary_abstracts=[
                    SecondaryAbstract(
                        abstract_type="summary",
                        label="Author Summary",
                        paragraphs=[Paragraph(text="Summary text.")],
                    ),
                ],
                keywords=["gene expression"],
                sections=[
                    Section(heading="Introduction", paragraphs=[Paragraph(text="Intro.")]),
                ],
                acknowledgments="Thanks.",
                funding=[
                    FundingEntry(funder="NIH", award_ids=["R01GM12345"]),
                ],
                funding_statement="Supported by NIH.",
                author_notes=["Corresponding author: a@b.edu"],
                competing_interests="No competing interests.",
                data_availability="Data at GEO.",
                references=[
                    Reference(
                        index=1,
                        authors=["Lee C"],
                        title="Ref",
                        journal="Nature",
                        volume="1",
                        year="2020",
                    ),
                ],
                sub_articles=[
                    Document(
                        title="Decision letter",
                        sections=[
                            Section(
                                heading="Review",
                                paragraphs=[
                                    Paragraph(text="Good work."),
                                ],
                            )
                        ],
                    ),
                ],
            )
        )


class TestReadMarkdownNewFields:
    """Tests for reading funding, author notes, competing interests, data availability."""

    def test_read_funding(self):
        md = (
            "# Paper\n\n"
            "## Funding\n\n"
            "NIH: R01GM12345\n"
            "Wellcome: 098765, 054321\n\n"
            "This work was supported by grants.\n"
        )
        doc = read_markdown(md)
        assert len(doc.funding) == 2
        assert doc.funding[0].funder == "NIH"
        assert doc.funding[0].award_ids == ["R01GM12345"]
        assert doc.funding[1].funder == "Wellcome"
        assert doc.funding[1].award_ids == ["098765", "054321"]
        assert doc.funding_statement == "This work was supported by grants."

    def test_read_funding_statement_only(self):
        md = "# Paper\n\n## Funding\n\nThis work was supported by the NIH.\n"
        doc = read_markdown(md)
        assert not doc.funding
        assert doc.funding_statement == "This work was supported by the NIH."

    def test_read_author_notes(self):
        md = (
            "# Paper\n\n"
            "## Author Notes\n\n"
            "Corresponding author: foo@bar.edu\n\n"
            "These authors contributed equally.\n"
        )
        doc = read_markdown(md)
        assert len(doc.author_notes) == 2
        assert "foo@bar.edu" in doc.author_notes[0]
        assert "contributed equally" in doc.author_notes[1]

    def test_read_competing_interests(self):
        md = "# Paper\n\n## Competing Interests\n\nThe authors declare no competing interests.\n"
        doc = read_markdown(md)
        assert doc.competing_interests == "The authors declare no competing interests."

    def test_read_data_availability(self):
        md = "# Paper\n\n## Data Availability\n\nAll data at https://example.com.\n"
        doc = read_markdown(md)
        assert doc.data_availability == "All data at https://example.com."

    def test_round_trip_funding(self):
        doc = _make_doc(
            title="Paper",
            funding=[
                FundingEntry(funder="NIH", award_ids=["R01GM12345"]),
                FundingEntry(funder="Wellcome", award_ids=["098765", "054321"]),
            ],
            funding_statement="This work was supported by grants.",
        )
        md = emit_markdown(doc)
        doc2 = read_markdown(md)
        assert len(doc2.funding) == 2
        assert doc2.funding[0].funder == "NIH"
        assert doc2.funding[0].award_ids == ["R01GM12345"]
        assert doc2.funding[1].funder == "Wellcome"
        assert doc2.funding[1].award_ids == ["098765", "054321"]
        assert doc2.funding_statement == "This work was supported by grants."

    def test_round_trip_all_new_fields(self):
        doc = _make_doc(
            title="Paper",
            acknowledgments="Thanks.",
            funding=[FundingEntry(funder="NSF", award_ids=["DBI-123"])],
            funding_statement="Funded by NSF.",
            author_notes=["Corresponding: a@b.edu"],
            competing_interests="None declared.",
            data_availability="Data at GEO.",
            references=[Reference(index=1, authors=["A B"], title="T", journal="J", year="2024")],
        )
        md1 = emit_markdown(doc)
        doc2 = read_markdown(md1)
        md2 = emit_markdown(doc2)
        assert md1 == md2
