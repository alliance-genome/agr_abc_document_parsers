"""Tests for plain text extraction (plain_text.py)."""
from agr_abc_document_parsers.models import (
    Document,
    Figure,
    Formula,
    ListBlock,
    Paragraph,
    Reference,
    Section,
    Table,
)
from agr_abc_document_parsers.plain_text import (
    extract_abstract_text,
    extract_plain_text,
    extract_sentences,
    strip_markdown_formatting,
)

# ---------------------------------------------------------------------------
# strip_markdown_formatting
# ---------------------------------------------------------------------------


class TestStripMarkdownFormatting:

    def test_bold(self):
        assert strip_markdown_formatting("The **bold** word") == "The bold word"

    def test_italic(self):
        assert strip_markdown_formatting("The *italic* word") == "The italic word"

    def test_bold_and_italic(self):
        text = "**Bold** and *italic* text"
        assert strip_markdown_formatting(text) == "Bold and italic text"

    def test_superscript(self):
        assert strip_markdown_formatting("Ca<sup>2+</sup>") == "Ca2+"

    def test_subscript(self):
        assert strip_markdown_formatting("H<sub>2</sub>O") == "H2O"

    def test_hyperlink(self):
        assert strip_markdown_formatting("[click here](https://example.com)") == "click here"

    def test_all_formats(self):
        text = "**Bold** *italic* <sup>sup</sup> <sub>sub</sub> [link](url)"
        assert strip_markdown_formatting(text) == "Bold italic sup sub link"

    def test_no_formatting(self):
        text = "Plain text with no formatting."
        assert strip_markdown_formatting(text) == text

    def test_empty_string(self):
        assert strip_markdown_formatting("") == ""

    def test_nested_bold_italic(self):
        # Bold containing italic-like content
        assert strip_markdown_formatting("***text***") == "text"

    def test_gene_name_italic(self):
        assert strip_markdown_formatting("The *daf-16* gene") == "The daf-16 gene"


# ---------------------------------------------------------------------------
# extract_plain_text
# ---------------------------------------------------------------------------


class TestExtractPlainText:

    def test_empty_document(self):
        assert extract_plain_text(Document()) == ""

    def test_title_only(self):
        doc = Document(title="My Paper Title")
        assert extract_plain_text(doc) == "My Paper Title"

    def test_title_with_formatting(self):
        doc = Document(title="A Study of *C. elegans* Genes")
        result = extract_plain_text(doc)
        assert result == "A Study of C. elegans Genes"

    def test_abstract(self):
        doc = Document(
            title="Title",
            abstract=[
                Paragraph(text="First paragraph."),
                Paragraph(text="Second paragraph."),
            ],
        )
        result = extract_plain_text(doc)
        assert "Title" in result
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_sections(self):
        doc = Document(sections=[
            Section(heading="Introduction", paragraphs=[
                Paragraph(text="Intro text with **bold**."),
            ]),
            Section(heading="Methods", paragraphs=[
                Paragraph(text="Methods text."),
            ]),
        ])
        result = extract_plain_text(doc)
        assert "Introduction" in result
        assert "Intro text with bold." in result
        assert "Methods" in result

    def test_nested_sections(self):
        doc = Document(sections=[
            Section(heading="Methods", subsections=[
                Section(heading="Samples", paragraphs=[
                    Paragraph(text="Sample info."),
                ]),
            ]),
        ])
        result = extract_plain_text(doc)
        assert "Methods" in result
        assert "Samples" in result
        assert "Sample info." in result

    def test_figures_captions(self):
        doc = Document(sections=[
            Section(heading="Results", figures=[
                Figure(label="Figure 1", caption="Expression of *BRCA1*."),
            ]),
        ])
        result = extract_plain_text(doc)
        assert "Expression of BRCA1." in result

    def test_table_captions(self):
        doc = Document(sections=[
            Section(heading="Results", tables=[
                Table(label="Table 1", caption="Summary of **findings**."),
            ]),
        ])
        result = extract_plain_text(doc)
        assert "Summary of findings." in result

    def test_lists(self):
        doc = Document(sections=[
            Section(heading="Methods", lists=[
                ListBlock(items=["Step *one*", "Step **two**"], ordered=False),
            ]),
        ])
        result = extract_plain_text(doc)
        assert "Step one" in result
        assert "Step two" in result

    def test_acknowledgments(self):
        doc = Document(acknowledgments="We thank the **NIH** for funding.")
        result = extract_plain_text(doc)
        assert "We thank the NIH for funding." in result

    def test_excludes_references(self):
        doc = Document(
            title="Title",
            references=[
                Reference(index=1, authors=["Auth A"], title="Ref title",
                          journal="Nature", year="2020"),
            ],
        )
        result = extract_plain_text(doc)
        assert "Ref title" not in result
        assert "Nature" not in result

    def test_back_matter(self):
        doc = Document(back_matter=[
            Section(heading="Funding", paragraphs=[
                Paragraph(text="NIH grant R01."),
            ]),
        ])
        result = extract_plain_text(doc)
        assert "Funding" in result
        assert "NIH grant R01." in result

    def test_supplements_included(self):
        doc = Document(
            title="Main Paper",
            supplements=[
                Document(sections=[
                    Section(heading="Supplementary Methods",
                            paragraphs=[Paragraph(text="Extra methods.")]),
                ]),
            ],
        )
        result = extract_plain_text(doc, include_supplements=True)
        assert "Main Paper" in result
        assert "Supplementary Methods" in result
        assert "Extra methods." in result

    def test_supplements_excluded(self):
        doc = Document(
            title="Main Paper",
            supplements=[
                Document(sections=[
                    Section(heading="Supplementary Methods",
                            paragraphs=[Paragraph(text="Extra methods.")]),
                ]),
            ],
        )
        result = extract_plain_text(doc, include_supplements=False)
        assert "Main Paper" in result
        assert "Extra methods." not in result

    def test_doc_level_figures(self):
        doc = Document(figures=[
            Figure(label="Figure 1", caption="A *doc-level* figure."),
        ])
        result = extract_plain_text(doc)
        assert "A doc-level figure." in result

    def test_formulas(self):
        doc = Document(sections=[
            Section(heading="Theory", formulas=[
                Formula(text="E = mc^2"),
            ]),
        ])
        result = extract_plain_text(doc)
        assert "E = mc^2" in result

    def test_section_notes(self):
        doc = Document(sections=[
            Section(heading="Discussion", notes=[
                "See **supplementary** materials.",
            ]),
        ])
        result = extract_plain_text(doc)
        assert "See supplementary materials." in result


# ---------------------------------------------------------------------------
# extract_abstract_text
# ---------------------------------------------------------------------------


class TestExtractAbstractText:

    def test_empty(self):
        assert extract_abstract_text(Document()) == ""

    def test_single_paragraph(self):
        doc = Document(abstract=[Paragraph(text="Abstract text here.")])
        assert extract_abstract_text(doc) == "Abstract text here."

    def test_multiple_paragraphs(self):
        doc = Document(abstract=[
            Paragraph(text="First paragraph."),
            Paragraph(text="Second paragraph."),
        ])
        result = extract_abstract_text(doc)
        assert "First paragraph." in result
        assert "Second paragraph." in result

    def test_strips_formatting(self):
        doc = Document(abstract=[
            Paragraph(text="Study of *C. elegans* with **RNA-seq**."),
        ])
        result = extract_abstract_text(doc)
        assert result == "Study of C. elegans with RNA-seq."


# ---------------------------------------------------------------------------
# extract_sentences
# ---------------------------------------------------------------------------


class TestExtractSentences:

    def test_empty(self):
        assert extract_sentences(Document()) == []

    def test_single_sentence(self):
        doc = Document(abstract=[Paragraph(text="A single sentence.")])
        sentences = extract_sentences(doc)
        assert len(sentences) == 1
        assert sentences[0] == "A single sentence."

    def test_multiple_sentences(self):
        doc = Document(abstract=[
            Paragraph(text="First sentence. Second sentence. Third sentence."),
        ])
        sentences = extract_sentences(doc)
        assert len(sentences) == 3
        assert sentences[0] == "First sentence."
        assert sentences[1] == "Second sentence."
        assert sentences[2] == "Third sentence."

    def test_abbreviation_dr(self):
        doc = Document(abstract=[
            Paragraph(text="Dr. Smith conducted the study. Results were clear."),
        ])
        sentences = extract_sentences(doc)
        assert len(sentences) == 2
        assert sentences[0] == "Dr. Smith conducted the study."

    def test_abbreviation_fig(self):
        doc = Document(abstract=[
            Paragraph(text="As shown in Fig. 1. The data confirms this."),
        ])
        sentences = extract_sentences(doc)
        assert len(sentences) == 2
        assert "Fig. 1." in sentences[0]

    def test_abbreviation_et_al(self):
        doc = Document(abstract=[
            Paragraph(text="Smith et al. reported findings. This was confirmed."),
        ])
        sentences = extract_sentences(doc)
        assert len(sentences) == 2
        assert "et al." in sentences[0]

    def test_abbreviation_eg(self):
        doc = Document(abstract=[
            Paragraph(text="Some species (e.g. C. elegans) were studied. Analysis followed."),
        ])
        sentences = extract_sentences(doc)
        assert len(sentences) == 2
        assert "e.g." in sentences[0]

    def test_exclamation_question(self):
        doc = Document(abstract=[
            Paragraph(text="What is this? It is important! Results follow."),
        ])
        sentences = extract_sentences(doc)
        assert len(sentences) == 3

    def test_strips_formatting_in_sentences(self):
        doc = Document(abstract=[
            Paragraph(text="The *daf-16* gene is important. It regulates **aging**."),
        ])
        sentences = extract_sentences(doc)
        assert len(sentences) == 2
        assert sentences[0] == "The daf-16 gene is important."
        assert sentences[1] == "It regulates aging."

    def test_multiline_collapsed(self):
        doc = Document(
            title="Title",
            abstract=[Paragraph(text="Abstract sentence.")],
            sections=[Section(heading="Intro",
                              paragraphs=[Paragraph(text="Body sentence.")])],
        )
        sentences = extract_sentences(doc)
        # All paragraphs collapsed into sentences
        assert any("Abstract sentence." in s for s in sentences)
        assert any("Body sentence." in s for s in sentences)

    def test_with_supplements(self):
        doc = Document(
            abstract=[Paragraph(text="Main text.")],
            supplements=[
                Document(sections=[
                    Section(heading="S1",
                            paragraphs=[Paragraph(text="Supplement text.")])
                ]),
            ],
        )
        sentences = extract_sentences(doc, include_supplements=True)
        assert any("Supplement text." in s for s in sentences)

    def test_without_supplements(self):
        doc = Document(
            abstract=[Paragraph(text="Main text.")],
            supplements=[
                Document(sections=[
                    Section(heading="S1",
                            paragraphs=[Paragraph(text="Supplement text.")])
                ]),
            ],
        )
        sentences = extract_sentences(doc, include_supplements=False)
        assert not any("Supplement text." in s for s in sentences)


# ---------------------------------------------------------------------------
# Integration with real fixtures
# ---------------------------------------------------------------------------


class TestPlainTextFixtures:
    """Test plain text extraction on real converted XML fixtures."""

    def _load_fixture_doc(self, fixture_path: str) -> Document:
        import gzip
        from pathlib import Path

        from agr_abc_document_parsers.tei_parser import parse_tei

        path = Path(__file__).parent / "fixtures" / fixture_path
        with gzip.open(path, "rb") as f:
            xml_bytes = f.read()
        return parse_tei(xml_bytes)

    def test_fixture_produces_text(self):
        doc = self._load_fixture_doc("tei_with_figures_keywords.tei.gz")
        text = extract_plain_text(doc)
        assert len(text) > 100
        assert doc.title.replace("*", "") in text or doc.title[:20] in text

    def test_fixture_abstract(self):
        doc = self._load_fixture_doc("tei_with_figures_keywords.tei.gz")
        abstract = extract_abstract_text(doc)
        assert len(abstract) > 50

    def test_fixture_sentences(self):
        doc = self._load_fixture_doc("tei_with_figures_keywords.tei.gz")
        sentences = extract_sentences(doc)
        assert len(sentences) > 10
        # Most sentences should be non-trivial
        long_sentences = [s for s in sentences if len(s) > 20]
        assert len(long_sentences) > 5

    def test_fixture_no_markdown_artifacts(self):
        doc = self._load_fixture_doc("tei_with_tables.tei.gz")
        text = extract_plain_text(doc)
        # Should not contain Markdown formatting markers
        assert "**" not in text
        assert "<sup>" not in text
        assert "<sub>" not in text

    def test_fixture_no_abstract(self):
        doc = self._load_fixture_doc("tei_no_abstract_no_doi.tei.gz")
        abstract = extract_abstract_text(doc)
        assert abstract == ""
        # But full text should still work
        text = extract_plain_text(doc)
        assert len(text) > 50
