"""Tests for JATS/nXML parser."""

from agr_abc_document_parsers.jats_parser import parse_jats

# -- JATS XML test fixtures --------------------------------------------------

FULL_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Archiving
  and Interchange Tag Set v1.0 20120330//EN"
  "JATS-archivearticle1.dtd">
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-id journal-id-type="nlm-ta">Nat Genet</journal-id>
      <journal-title-group>
        <journal-title>Nature Genetics</journal-title>
      </journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmid">12345678</article-id>
      <article-id pub-id-type="doi">10.1038/ng.test.2024</article-id>
      <article-id pub-id-type="pmc">PMC9999999</article-id>
      <title-group>
        <article-title>Genomic Analysis of Model Organisms</article-title>
      </title-group>
      <contrib-group>
        <contrib contrib-type="author">
          <name><surname>Smith</surname><given-names>Alice M</given-names></name>
          <email>alice@example.com</email>
          <xref ref-type="aff" rid="aff1"/>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Jones</surname><given-names>Bob</given-names></name>
          <xref ref-type="aff" rid="aff2"/>
        </contrib>
      </contrib-group>
      <aff id="aff1">Department of Biology, MIT, Cambridge, MA, USA</aff>
      <aff id="aff2">Department of CS, Stanford University, Stanford, CA, USA</aff>
      <pub-date pub-type="epub"><year>2024</year></pub-date>
      <volume>56</volume>
      <issue>4</issue>
      <fpage>300</fpage>
      <lpage>315</lpage>
      <kwd-group>
        <kwd>genomics</kwd>
        <kwd>model organisms</kwd>
        <kwd>comparative analysis</kwd>
      </kwd-group>
      <abstract>
        <p>We performed a comprehensive genomic analysis of model organisms.</p>
        <p>Our results reveal conserved regulatory elements.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec id="sec1">
      <title>Introduction</title>
      <p>Model organisms are essential for <xref ref-type="bibr" rid="ref1">[1]</xref> genomic research.</p>
      <p>Previous studies have shown <xref ref-type="bibr" rid="ref2">[2]</xref> that...</p>
    </sec>
    <sec id="sec2">
      <title>Methods</title>
      <p>We collected samples from multiple organisms.</p>
      <sec id="sec2.1">
        <title>Sample Collection</title>
        <p>Samples were obtained from standard repositories.</p>
      </sec>
      <sec id="sec2.2">
        <title>Sequencing</title>
        <p>Whole-genome sequencing was performed using Illumina.</p>
      </sec>
    </sec>
    <sec id="sec3">
      <title>Results</title>
      <p>We identified significant genomic conservation.</p>
      <fig id="fig1">
        <label>Figure 1</label>
        <caption><title>Genomic conservation</title><p>Conservation scores across species.</p></caption>
        <graphic xlink:href="fig1.tif" xmlns:xlink="http://www.w3.org/1999/xlink"/>
      </fig>
      <table-wrap id="tab1">
        <label>Table 1</label>
        <caption><title>Species comparison</title><p>Key metrics by species.</p></caption>
        <table>
          <thead>
            <tr><th>Species</th><th>Genes</th><th>Conservation</th></tr>
          </thead>
          <tbody>
            <tr><td>C. elegans</td><td>20000</td><td>0.85</td></tr>
            <tr><td>D. melanogaster</td><td>14000</td><td>0.78</td></tr>
          </tbody>
        </table>
      </table-wrap>
      <disp-formula id="eq1">E = mc^2</disp-formula>
      <list list-type="bullet">
        <list-item><p>Finding one: conservation is high</p></list-item>
        <list-item><p>Finding two: regulatory elements shared</p></list-item>
      </list>
    </sec>
  </body>
  <back>
    <ack><p>We thank the genome sequencing centers for data access.</p></ack>
    <ref-list>
      <ref id="ref1">
        <element-citation publication-type="journal">
          <person-group person-group-type="author">
            <name><surname>Lee</surname><given-names>C</given-names></name>
            <name><surname>Park</surname><given-names>D</given-names></name>
          </person-group>
          <article-title>Comparative genomics review</article-title>
          <source>Annual Review of Genomics</source>
          <year>2020</year>
          <volume>21</volume>
          <issue>1</issue>
          <fpage>50</fpage>
          <lpage>75</lpage>
          <pub-id pub-id-type="doi">10.1146/annurev.2020</pub-id>
          <pub-id pub-id-type="pmid">11111111</pub-id>
        </element-citation>
      </ref>
      <ref id="ref2">
        <element-citation publication-type="journal">
          <person-group person-group-type="author">
            <name><surname>Wang</surname><given-names>E</given-names></name>
          </person-group>
          <article-title>Model organism databases</article-title>
          <source>Nucleic Acids Research</source>
          <year>2019</year>
          <volume>47</volume>
          <fpage>D1</fpage>
          <lpage>D10</lpage>
        </element-citation>
      </ref>
    </ref-list>
    <app-group>
      <app>
        <title>Supplementary Methods</title>
        <p>Additional details on the sequencing protocol.</p>
      </app>
    </app-group>
  </back>
</article>
"""

NO_NAMESPACE_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <article-meta>
      <article-id pub-id-type="doi">10.1234/no-ns</article-id>
      <title-group>
        <article-title>Paper Without Namespace</article-title>
      </title-group>
      <contrib-group>
        <contrib contrib-type="author">
          <name><surname>Doe</surname><given-names>Jane</given-names></name>
        </contrib>
      </contrib-group>
      <abstract><p>Abstract without namespace.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Introduction</title>
      <p>Body text without namespace.</p>
    </sec>
  </body>
  <back>
    <ref-list/>
  </back>
</article>
"""

STRUCTURED_ABSTRACT_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <article-meta>
      <title-group>
        <article-title>Paper With Structured Abstract</article-title>
      </title-group>
      <abstract>
        <sec>
          <title>Background</title>
          <p>Background paragraph text.</p>
        </sec>
        <sec>
          <title>Results</title>
          <p>Results paragraph text.</p>
        </sec>
        <sec>
          <title>Conclusions</title>
          <p>Conclusions paragraph text.</p>
        </sec>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Intro</title><p>Body.</p></sec>
  </body>
  <back><ref-list/></back>
</article>
"""

MIXED_CITATION_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <article-meta>
      <title-group>
        <article-title>Paper With Mixed Citations</article-title>
      </title-group>
      <abstract><p>Test abstract.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Intro</title><p>Text.</p></sec>
  </body>
  <back>
    <ref-list>
      <ref id="r1">
        <mixed-citation publication-type="journal">
          <person-group person-group-type="author">
            <name><surname>Mixed</surname><given-names>A</given-names></name>
          </person-group>
          <article-title>Mixed citation title</article-title>
          <source>Mixed Journal</source>
          <year>2021</year>
          <volume>10</volume>
          <fpage>1</fpage>
          <lpage>5</lpage>
        </mixed-citation>
      </ref>
    </ref-list>
  </back>
</article>
"""


class TestJatsParser:
    """Tests for parse_jats function."""

    def test_parse_title(self):
        """Title from //article-meta/title-group/article-title."""
        doc = parse_jats(FULL_JATS)
        assert doc.title == "Genomic Analysis of Model Organisms"

    def test_parse_authors(self):
        """Authors from contrib-group/contrib[@contrib-type='author']."""
        doc = parse_jats(FULL_JATS)
        assert len(doc.authors) == 2
        assert doc.authors[0].given_name == "Alice M"
        assert doc.authors[0].surname == "Smith"
        assert doc.authors[0].email == "alice@example.com"
        assert len(doc.authors[0].affiliations) == 1
        assert "MIT" in doc.authors[0].affiliations[0]
        assert doc.authors[1].surname == "Jones"
        assert "Stanford" in doc.authors[1].affiliations[0]

    def test_author_email_in_markdown(self):
        """Author emails are preserved in emitted Markdown."""
        from agr_abc_document_parsers.md_emitter import emit_markdown

        doc = parse_jats(FULL_JATS)
        md = emit_markdown(doc)
        assert "**Correspondence:** Alice M Smith (alice@example.com)" in md

    def test_author_email_roundtrip(self):
        """Author emails survive JATS → MD → Document round-trip."""
        from agr_abc_document_parsers.md_emitter import emit_markdown
        from agr_abc_document_parsers.md_reader import read_markdown

        doc = parse_jats(FULL_JATS)
        md = emit_markdown(doc)
        doc2 = read_markdown(md)
        assert doc2.authors[0].email == "alice@example.com"

    def test_parse_abstract(self):
        """Abstract from //article-meta/abstract."""
        doc = parse_jats(FULL_JATS)
        assert len(doc.abstract) == 2
        assert "comprehensive genomic analysis" in doc.abstract[0].text
        assert "conserved regulatory" in doc.abstract[1].text

    def test_parse_keywords(self):
        """Keywords from //kwd-group/kwd."""
        doc = parse_jats(FULL_JATS)
        assert len(doc.keywords) == 3
        assert "genomics" in doc.keywords
        assert "model organisms" in doc.keywords

    def test_parse_doi(self):
        """DOI from //article-id[@pub-id-type='doi']."""
        doc = parse_jats(FULL_JATS)
        assert doc.doi == "10.1038/ng.test.2024"

    def test_parse_body_sections(self):
        """//body/sec -> sections with <title> headings."""
        doc = parse_jats(FULL_JATS)
        assert len(doc.sections) == 3
        assert doc.sections[0].heading == "Introduction"
        assert doc.sections[1].heading == "Methods"
        assert doc.sections[2].heading == "Results"

    def test_parse_nested_sections(self):
        """Nested <sec> elements."""
        doc = parse_jats(FULL_JATS)
        methods = doc.sections[1]
        assert len(methods.subsections) == 2
        assert methods.subsections[0].heading == "Sample Collection"
        assert methods.subsections[0].level == 2
        assert methods.subsections[1].heading == "Sequencing"

    def test_parse_figures(self):
        """<fig> with label, caption — collected into doc.figures."""
        doc = parse_jats(FULL_JATS)
        assert any(f.label == "Figure 1" for f in doc.figures)
        fig = next(f for f in doc.figures if f.label == "Figure 1")
        assert "conservation" in fig.caption.lower()

    def test_parse_tables(self):
        """<table-wrap> with thead/tbody/tr/th/td."""
        doc = parse_jats(FULL_JATS)
        results = doc.sections[2]
        assert len(results.tables) == 1
        table = results.tables[0]
        assert table.label == "Table 1"
        assert len(table.rows) == 3  # 1 header + 2 data rows
        assert table.rows[0][0].text == "Species"
        assert table.rows[0][0].is_header is True
        assert table.rows[1][0].text == "C. elegans"
        assert table.rows[2][1].text == "14000"

    def test_parse_formulas(self):
        """<disp-formula> elements."""
        doc = parse_jats(FULL_JATS)
        results = doc.sections[2]
        assert len(results.formulas) == 1
        assert "E = mc^2" in results.formulas[0].text

    def test_parse_lists(self):
        """<list>/<list-item> elements."""
        doc = parse_jats(FULL_JATS)
        results = doc.sections[2]
        assert len(results.lists) == 1
        lst = results.lists[0]
        assert len(lst.items) == 2
        assert "conservation" in lst.items[0].lower()

    def test_parse_acknowledgments(self):
        """//back/ack."""
        doc = parse_jats(FULL_JATS)
        assert "genome sequencing centers" in doc.acknowledgments

    def test_parse_bibliography(self):
        """//back/ref-list/ref with element-citation."""
        doc = parse_jats(FULL_JATS)
        assert len(doc.references) == 2
        ref0 = doc.references[0]
        assert "Lee" in ref0.authors[0]
        assert ref0.title == "Comparative genomics review"
        assert ref0.journal == "Annual Review of Genomics"
        assert ref0.volume == "21"
        assert ref0.issue == "1"
        assert ref0.pages == "50-75"
        assert ref0.year == "2020"
        assert ref0.doi == "10.1146/annurev.2020"
        assert ref0.pmid == "11111111"

    def test_parse_appendices(self):
        """//back/app-group -> back_matter."""
        doc = parse_jats(FULL_JATS)
        assert len(doc.back_matter) >= 1
        assert any("Supplementary Methods" in s.heading for s in doc.back_matter)

    def test_source_format_set(self):
        """Document.source_format is 'jats'."""
        doc = parse_jats(FULL_JATS)
        assert doc.source_format == "jats"

    def test_parse_no_namespace(self):
        """JATS file without namespace (common variant)."""
        doc = parse_jats(NO_NAMESPACE_JATS)
        assert doc.title == "Paper Without Namespace"
        assert doc.doi == "10.1234/no-ns"
        assert len(doc.authors) == 1
        assert doc.authors[0].surname == "Doe"
        assert len(doc.abstract) == 1
        assert len(doc.sections) == 1

    def test_parse_table_colspan(self):
        """Table cells with colspan emit padding cells."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <table-wrap><table>
    <thead><tr><th colspan="2">Spanning Header</th><th>C</th></tr></thead>
    <tbody><tr><td>A</td><td>B</td><td>C</td></tr></tbody>
  </table></table-wrap>
</sec></body></article>
"""
        doc = parse_jats(jats)
        table = doc.sections[0].tables[0]
        # Header row should have 3 cells (1 real + 1 padding + 1 regular)
        assert len(table.rows[0]) == 3
        assert table.rows[0][0].text == "Spanning Header"
        assert table.rows[0][1].text == ""
        assert table.rows[0][2].text == "C"

    def test_parse_structured_abstract(self):
        """Structured abstract with <sec> preserves section titles."""
        doc = parse_jats(STRUCTURED_ABSTRACT_JATS)
        assert len(doc.abstract) == 3
        assert doc.abstract[0].text == "**Background:** Background paragraph text."
        assert doc.abstract[1].text == "**Results:** Results paragraph text."
        assert doc.abstract[2].text == "**Conclusions:** Conclusions paragraph text."

    def test_parse_mixed_citation(self):
        """References using <mixed-citation> instead of <element-citation>."""
        doc = parse_jats(MIXED_CITATION_JATS)
        assert len(doc.references) == 1
        ref = doc.references[0]
        assert "Mixed" in ref.authors[0]
        assert ref.title == "Mixed citation title"
        assert ref.journal == "Mixed Journal"
        assert ref.year == "2021"

    def test_parse_table_wrap_inside_p(self):
        """<table-wrap> nested inside <p> is extracted as a table."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Results</title>
  <p>See Table 1 below.
    <table-wrap><label>Table 1</label>
      <caption><p>Summary stats.</p></caption>
      <table>
        <thead><tr><th>Gene</th><th>Value</th></tr></thead>
        <tbody><tr><td>BRCA1</td><td>2.5</td></tr></tbody>
      </table>
    </table-wrap>
  More text after table.</p>
</sec></body></article>
"""
        doc = parse_jats(jats)
        sec = doc.sections[0]
        # Table extracted from <p>
        assert len(sec.tables) == 1
        assert sec.tables[0].label == "Table 1"
        assert sec.tables[0].rows[0][0].text == "Gene"
        assert sec.tables[0].rows[1][0].text == "BRCA1"
        # Text around block elements split into separate paragraphs
        assert len(sec.paragraphs) == 2
        assert "See Table 1" in sec.paragraphs[0].text
        assert "More text" in sec.paragraphs[1].text

    def test_parse_citation_alternatives(self):
        """References wrapped in <citation-alternatives>."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>Text.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <citation-alternatives>
      <element-citation publication-type="journal">
        <person-group><name>
          <surname>Alt</surname><given-names>A</given-names>
        </name></person-group>
        <article-title>Alt title</article-title>
        <source>Alt Journal</source>
        <year>2023</year>
      </element-citation>
    </citation-alternatives>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        assert len(doc.references) == 1
        assert doc.references[0].title == "Alt title"
        assert "Alt" in doc.references[0].authors[0]

    def test_parse_inline_formatting(self):
        """Inline <italic>, <bold>, <sup>, <sub> preserved as markdown."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <p>The gene <italic>drosophila</italic> is <bold>important</bold> for
  H<sub>2</sub>O and Ca<sup>2+</sup> studies.</p>
</sec></body></article>
"""
        doc = parse_jats(jats)
        para = doc.sections[0].paragraphs[0].text
        assert "*drosophila*" in para
        assert "**important**" in para
        assert "<sub>2</sub>" in para
        assert "<sup>2+</sup>" in para

    def test_parse_ext_link_in_paragraph(self):
        """<ext-link> in paragraphs emitted as markdown links."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <p>Data at <ext-link ext-link-type="uri"
    xlink:href="https://example.com/data"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    >example.com/data</ext-link>.</p>
</sec></body></article>
"""
        doc = parse_jats(jats)
        para = doc.sections[0].paragraphs[0].text
        assert "[example.com/data](https://example.com/data)" in para

    def test_parse_string_name_authors(self):
        """References with <string-name> instead of <name>."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <mixed-citation>
      <string-name><surname>Sn</surname><given-names>A</given-names></string-name>
      <article-title>SN title</article-title>
      <source>SN Journal</source>
      <year>2022</year>
    </mixed-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        assert "Sn" in doc.references[0].authors[0]

    def test_parse_elocation_id(self):
        """References with <elocation-id> instead of fpage/lpage."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation>
      <article-title>E-journal paper</article-title>
      <source>PLOS ONE</source>
      <year>2023</year>
      <elocation-id>e12345</elocation-id>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        assert doc.references[0].pages == "e12345"

    def test_parse_pmcid(self):
        """PMCID captured from pub-id[@pub-id-type='pmcid']."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation>
      <article-title>Title</article-title>
      <year>2024</year>
      <pub-id pub-id-type="doi">10.1234/test</pub-id>
      <pub-id pub-id-type="pmid">99999999</pub-id>
      <pub-id pub-id-type="pmcid">PMC1234567</pub-id>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        ref = doc.references[0]
        assert ref.doi == "10.1234/test"
        assert ref.pmid == "99999999"
        assert ref.pmcid == "PMC1234567"

    def test_parse_collab_author(self):
        """Collaborative/group author names."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation>
      <person-group>
        <collab>The International Consortium</collab>
      </person-group>
      <article-title>Consortium paper</article-title>
      <year>2024</year>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        assert "The International Consortium" in doc.references[0].authors

    def test_parse_author_orcid(self):
        """Author ORCID from contrib-id."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
  <contrib-group>
    <contrib contrib-type="author">
      <contrib-id contrib-id-type="orcid">0000-0001-2345-6789</contrib-id>
      <name><surname>Orcid</surname><given-names>A</given-names></name>
    </contrib>
  </contrib-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body></article>
"""
        doc = parse_jats(jats)
        assert doc.authors[0].orcid == "0000-0001-2345-6789"

    def test_parse_back_sections(self):
        """Back-matter sec, fn-group, notes parsed as back_matter."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back>
  <sec sec-type="data-availability">
    <title>Data Availability</title>
    <p>Data deposited at GEO.</p>
  </sec>
  <fn-group>
    <title>Author Contributions</title>
    <fn><p>A.B. conceived the study.</p></fn>
  </fn-group>
</back></article>
"""
        doc = parse_jats(jats)
        headings = [s.heading for s in doc.back_matter]
        assert "Data Availability" in headings
        assert "Author Contributions" in headings

    def test_parse_supplementary_material(self):
        """<supplementary-material> in sec rendered as paragraph."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Results</title>
  <p>Main findings.</p>
  <supplementary-material>
    <label>Supplementary File 1</label>
    <caption><p>Additional data tables.</p></caption>
  </supplementary-material>
</sec></body></article>
"""
        doc = parse_jats(jats)
        sec = doc.sections[0]
        supp_paras = [p for p in sec.paragraphs if "Supplementary" in p.text]
        assert len(supp_paras) == 1
        assert "Additional data" in supp_paras[0].text

    def test_parse_disp_quote(self):
        """<disp-quote> in sec rendered as block quote."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Discussion</title>
  <disp-quote><p>A famous quote here.</p></disp-quote>
</sec></body></article>
"""
        doc = parse_jats(jats)
        sec = doc.sections[0]
        quote_paras = [p for p in sec.paragraphs if p.text.startswith(">")]
        assert len(quote_paras) == 1
        assert "famous quote" in quote_paras[0].text

    def test_parse_def_list(self):
        """<def-list>/<def-item> rendered as list."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Glossary</title>
  <def-list>
    <def-item>
      <term>GO</term>
      <def><p>Gene Ontology</p></def>
    </def-item>
  </def-list>
</sec></body></article>
"""
        doc = parse_jats(jats)
        sec = doc.sections[0]
        assert len(sec.lists) == 1
        assert "**GO**" in sec.lists[0].items[0]
        assert "Gene Ontology" in sec.lists[0].items[0]

    def test_parse_table_wrap_foot(self):
        """<table-wrap-foot> footnotes captured in Table.foot_notes."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <table-wrap>
    <label>Table 1</label>
    <table>
      <thead><tr><th>Gene</th><th>FC</th></tr></thead>
      <tbody><tr><td>BRCA1</td><td>2.5</td></tr></tbody>
    </table>
    <table-wrap-foot>
      <fn id="tfn1"><p>FC, fold change.</p></fn>
      <fn id="tfn2"><p>*P &lt; 0.05.</p></fn>
    </table-wrap-foot>
  </table-wrap>
</sec></body></article>
"""
        doc = parse_jats(jats)
        table = doc.sections[0].tables[0]
        assert len(table.foot_notes) == 2
        assert "fold change" in table.foot_notes[0]
        assert "P <" in table.foot_notes[1]

    def test_parse_page_range(self):
        """<page-range> as fallback for pages in references."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation>
      <article-title>Title</article-title>
      <source>J</source>
      <year>2024</year>
      <page-range>100-110, 115</page-range>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        assert doc.references[0].pages == "100-110, 115"

    def test_parse_publisher_info(self):
        """<publisher-name> and <publisher-loc> in references."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation publication-type="book">
      <person-group person-group-type="author">
        <name><surname>Auth</surname><given-names>A</given-names></name>
      </person-group>
      <source>Biology Handbook</source>
      <year>2023</year>
      <publisher-name>Academic Press</publisher-name>
      <publisher-loc>New York</publisher-loc>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        ref = doc.references[0]
        assert ref.publisher == "Academic Press"
        assert ref.publisher_loc == "New York"

    def test_parse_chapter_title(self):
        """<chapter-title> / <part-title> for book chapters."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation publication-type="book">
      <article-title>Chapter One</article-title>
      <chapter-title>Methods in Molecular Biology</chapter-title>
      <source>Book Title</source>
      <year>2022</year>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        assert doc.references[0].chapter_title == "Methods in Molecular Biology"

    def test_parse_conf_name(self):
        """<conf-name> captured as conference."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation publication-type="confproc">
      <article-title>Deep learning for genomics</article-title>
      <conf-name>ISMB 2024</conf-name>
      <year>2024</year>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        assert doc.references[0].conference == "ISMB 2024"

    def test_parse_ref_editors(self):
        """Editors from person-group[@person-group-type='editor']."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation publication-type="book">
      <person-group person-group-type="author">
        <name><surname>Auth</surname><given-names>A</given-names></name>
      </person-group>
      <person-group person-group-type="editor">
        <name><surname>Editor</surname><given-names>E</given-names></name>
      </person-group>
      <article-title>Chapter</article-title>
      <source>Big Book</source>
      <year>2023</year>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        ref = doc.references[0]
        assert len(ref.editors) == 1
        assert "Editor E" in ref.editors[0]

    def test_parse_preformat(self):
        """<preformat> blocks rendered as code blocks."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Methods</title>
  <preformat>SELECT * FROM genes WHERE symbol = 'BRCA1';</preformat>
</sec></body></article>
"""
        doc = parse_jats(jats)
        sec = doc.sections[0]
        code_paras = [p for p in sec.paragraphs if "```" in p.text]
        assert len(code_paras) == 1
        assert "SELECT * FROM genes" in code_paras[0].text

    def test_parse_glossary_in_back(self):
        """<glossary> in back matter parsed with def-list."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back>
  <glossary>
    <title>Abbreviations</title>
    <def-list>
      <def-item>
        <term>GO</term>
        <def><p>Gene Ontology</p></def>
      </def-item>
      <def-item>
        <term>MOD</term>
        <def><p>Model Organism Database</p></def>
      </def-item>
    </def-list>
  </glossary>
</back></article>
"""
        doc = parse_jats(jats)
        headings = [s.heading for s in doc.back_matter]
        assert "Abbreviations" in headings
        abbr = [s for s in doc.back_matter if s.heading == "Abbreviations"][0]
        assert len(abbr.lists) >= 1
        assert "**GO**" in abbr.lists[0].items[0]

    def test_parse_empty_inline_formatting(self):
        """Empty <italic>/<bold>/<sup>/<sub> produce no stray markers."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <p>Before<italic></italic> middle<bold></bold> after <sup></sup> end<sub></sub>.</p>
</sec></body></article>
"""
        doc = parse_jats(jats)
        para = doc.sections[0].paragraphs[0].text
        assert "**" not in para
        assert "<sup></sup>" not in para
        assert "<sub></sub>" not in para
        assert "Before" in para
        assert "middle" in para

    def test_parse_nested_inline_formatting(self):
        """Nested inline markup: <italic>text <sup>x</sup></italic>."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <p>The gene <italic>Drosophila <sup>x</sup></italic> is studied.</p>
</sec></body></article>
"""
        doc = parse_jats(jats)
        para = doc.sections[0].paragraphs[0].text
        assert "*Drosophila <sup>x</sup>*" in para

    def test_parse_rowspan_expanded(self):
        """rowspan on table cells expanded into subsequent rows."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <table-wrap><table>
    <thead><tr><th>A</th><th>B</th></tr></thead>
    <tbody>
      <tr><td rowspan="2">Spanning</td><td>1</td></tr>
      <tr><td>2</td></tr>
    </tbody>
  </table></table-wrap>
</sec></body></article>
"""
        doc = parse_jats(jats)
        table = doc.sections[0].tables[0]
        assert len(table.rows) == 3  # 1 header + 2 data
        # Row 1 (first data row): "Spanning" | "1"
        assert table.rows[1][0].text == "Spanning"
        assert table.rows[1][1].text == "1"
        # Row 2 (second data row): "" (rowspan carry) | "2"
        assert len(table.rows[2]) == 2
        assert table.rows[2][0].text == ""  # expanded from rowspan
        assert table.rows[2][1].text == "2"

    def test_parse_ref_author_editor_separation(self):
        """Editors not captured as authors in refs with both groups."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back><ref-list>
  <ref id="r1">
    <element-citation publication-type="book">
      <person-group person-group-type="author">
        <name><surname>Writer</surname><given-names>A</given-names></name>
      </person-group>
      <person-group person-group-type="editor">
        <name><surname>Editor</surname><given-names>E</given-names></name>
      </person-group>
      <source>Big Book</source>
      <year>2023</year>
    </element-citation>
  </ref>
</ref-list></back></article>
"""
        doc = parse_jats(jats)
        ref = doc.references[0]
        assert len(ref.authors) == 1
        assert "Writer" in ref.authors[0]
        assert "Editor" not in ref.authors[0]
        assert len(ref.editors) == 1
        assert "Editor" in ref.editors[0]

    def test_parse_preformat_with_backticks(self):
        """<preformat> containing backticks uses wider fence."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Methods</title>
  <preformat>Run ```this``` command</preformat>
</sec></body></article>
"""
        doc = parse_jats(jats)
        sec = doc.sections[0]
        code_paras = [p for p in sec.paragraphs if "Run" in p.text]
        assert len(code_paras) == 1
        # Fence should be wider than 3 backticks
        assert "````" in code_paras[0].text

    def test_parse_disp_quote_multi_paragraph(self):
        """<disp-quote> with multiple <p> children gets per-paragraph >."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>Discussion</title>
  <disp-quote>
    <p>First paragraph of quote.</p>
    <p>Second paragraph of quote.</p>
  </disp-quote>
</sec></body></article>
"""
        doc = parse_jats(jats)
        sec = doc.sections[0]
        quote_paras = [p for p in sec.paragraphs if p.text.startswith(">")]
        assert len(quote_paras) == 1
        text = quote_paras[0].text
        assert "> First paragraph of quote." in text
        assert "> Second paragraph of quote." in text
        # Each paragraph gets its own > prefix
        assert text.count(">") == 2

    def test_parse_glossary_no_title_duplication(self):
        """Glossary title in back matter not duplicated as bold paragraph."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body>
<back>
  <glossary>
    <title>Abbreviations</title>
    <def-list>
      <def-item>
        <term>GO</term>
        <def><p>Gene Ontology</p></def>
      </def-item>
    </def-list>
  </glossary>
</back></article>
"""
        doc = parse_jats(jats)
        abbr = [s for s in doc.back_matter if s.heading == "Abbreviations"][0]
        # Title should be the section heading, not also a bold paragraph
        bold_titles = [p for p in abbr.paragraphs if "**Abbreviations**" in p.text]
        assert len(bold_titles) == 0

    def test_parse_whitespace_normalization(self):
        """XML indentation whitespace collapsed in paragraph text."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
</article-meta></front>
<body><sec><title>R</title>
  <p>Text with
    <xref ref-type="bibr" rid="r1">[1]</xref>
    and more text.</p>
</sec></body></article>
"""
        doc = parse_jats(jats)
        para = doc.sections[0].paragraphs[0].text
        assert "\n" not in para
        assert "  " not in para
        assert "Text with [1] and more text." == para


# -- Secondary abstracts, sub-articles, categories, roles ------------------

SECONDARY_ABSTRACTS_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <article-meta>
      <title-group>
        <article-title>Paper With Secondary Abstracts</article-title>
      </title-group>
      <abstract>
        <p>Main abstract paragraph.</p>
      </abstract>
      <abstract abstract-type="summary">
        <title>Author Summary</title>
        <p>Plain language summary of the paper.</p>
      </abstract>
      <abstract abstract-type="executive-summary">
        <p>Digest paragraph one.</p>
        <p>Digest paragraph two.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Intro</title><p>Body.</p></sec>
  </body>
  <back><ref-list/></back>
</article>
"""

SUB_ARTICLES_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <article-meta>
      <title-group>
        <article-title>Main Paper Title</article-title>
      </title-group>
      <abstract><p>Main abstract.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Introduction</title><p>Main body.</p></sec>
  </body>
  <back>
    <ref-list>
      <ref id="r1">
        <element-citation>
          <article-title>Main ref</article-title>
          <year>2024</year>
        </element-citation>
      </ref>
    </ref-list>
  </back>
  <sub-article article-type="decision-letter">
    <front-stub>
      <title-group>
        <article-title>Decision letter</article-title>
      </title-group>
      <contrib-group>
        <contrib contrib-type="author">
          <name><surname>Wittkopp</surname><given-names>Patricia J</given-names></name>
          <role>Reviewing Editor</role>
        </contrib>
      </contrib-group>
    </front-stub>
    <body>
      <sec><title>Summary</title><p>The reviewers find the paper interesting.</p></sec>
    </body>
  </sub-article>
  <sub-article article-type="reply">
    <front-stub>
      <title-group>
        <article-title>Author response</article-title>
      </title-group>
    </front-stub>
    <body>
      <p>We thank the reviewers for their comments.</p>
    </body>
    <back>
      <ref-list>
        <ref id="sr1">
          <element-citation>
            <article-title>Sub-article ref</article-title>
            <year>2023</year>
          </element-citation>
        </ref>
      </ref-list>
    </back>
  </sub-article>
</article>
"""

CATEGORIES_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <article-meta>
      <article-categories>
        <subj-group subj-group-type="heading">
          <subject>Research Article</subject>
        </subj-group>
        <subj-group subj-group-type="discipline">
          <subject>Cell Biology</subject>
          <subject>Genetics</subject>
        </subj-group>
      </article-categories>
      <title-group>
        <article-title>Paper With Categories</article-title>
      </title-group>
      <abstract><p>Abstract.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Intro</title><p>Body.</p></sec>
  </body>
  <back><ref-list/></back>
</article>
"""

AUTHOR_ROLES_JATS = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <article-meta>
      <title-group>
        <article-title>Paper With Author Roles</article-title>
      </title-group>
      <contrib-group>
        <contrib contrib-type="author">
          <name><surname>Waymack</surname><given-names>Rachel</given-names></name>
          <role>Conceptualization</role>
          <role>Software</role>
          <role>Formal analysis</role>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Fletcher</surname><given-names>Alvaro</given-names></name>
          <role>Investigation</role>
        </contrib>
        <contrib contrib-type="author">
          <name><surname>Smith</surname><given-names>Jane</given-names></name>
        </contrib>
      </contrib-group>
      <abstract><p>Abstract.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Intro</title><p>Body.</p></sec>
  </body>
  <back><ref-list/></back>
</article>
"""


class TestJatsSecondaryAbstracts:
    """Tests for secondary abstract parsing."""

    def test_parse_secondary_abstracts(self):
        doc = parse_jats(SECONDARY_ABSTRACTS_JATS)
        assert len(doc.secondary_abstracts) == 2
        sa0 = doc.secondary_abstracts[0]
        assert sa0.abstract_type == "summary"
        assert sa0.label == "Author Summary"
        assert len(sa0.paragraphs) == 1
        assert "Plain language summary" in sa0.paragraphs[0].text

        sa1 = doc.secondary_abstracts[1]
        assert sa1.abstract_type == "executive-summary"
        assert sa1.label == "eLife Digest"
        assert len(sa1.paragraphs) == 2

    def test_parse_main_abstract_excludes_secondary(self):
        doc = parse_jats(SECONDARY_ABSTRACTS_JATS)
        assert len(doc.abstract) == 1
        assert "Main abstract paragraph" in doc.abstract[0].text

    def test_all_abstracts_typed_fallback(self):
        """When all abstracts have a type, first is used as main."""
        jats = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
  <title-group><article-title>T</article-title></title-group>
  <abstract abstract-type="summary"><p>Summary text.</p></abstract>
  <abstract abstract-type="toc"><p>TOC text.</p></abstract>
</article-meta></front>
<body><sec><title>I</title><p>X.</p></sec></body></article>
"""
        doc = parse_jats(jats)
        # First abstract used as main
        assert len(doc.abstract) == 1
        assert "Summary text" in doc.abstract[0].text
        # Only the second becomes secondary (first is excluded)
        assert len(doc.secondary_abstracts) == 1
        assert doc.secondary_abstracts[0].abstract_type == "toc"


class TestJatsSubArticles:
    """Tests for sub-article parsing."""

    def test_parse_sub_articles(self):
        doc = parse_jats(SUB_ARTICLES_JATS)
        assert len(doc.sub_articles) == 2

        dl = doc.sub_articles[0]
        assert dl.title == "Decision letter"
        assert dl.article_type == "decision-letter"
        assert len(dl.authors) >= 1
        assert dl.authors[0].surname == "Wittkopp"
        assert len(dl.sections) >= 1

        ar = doc.sub_articles[1]
        assert ar.title == "Author response"
        assert ar.article_type == "reply"
        assert len(ar.references) == 1
        assert ar.references[0].title == "Sub-article ref"

    def test_parse_sub_article_front_stub(self):
        """Front-stub metadata extracted correctly."""
        doc = parse_jats(SUB_ARTICLES_JATS)
        dl = doc.sub_articles[0]
        # Editor roles parsed
        assert any("Reviewing Editor" in r for a in dl.authors for r in a.roles)

    def test_main_article_unaffected(self):
        """Sub-articles don't contaminate main document."""
        doc = parse_jats(SUB_ARTICLES_JATS)
        assert doc.title == "Main Paper Title"
        assert len(doc.references) == 1
        assert doc.references[0].title == "Main ref"


class TestJatsCategories:
    """Tests for category parsing."""

    def test_parse_categories(self):
        doc = parse_jats(CATEGORIES_JATS)
        assert "Research Article" in doc.categories
        assert "Cell Biology" in doc.categories
        assert "Genetics" in doc.categories
        assert len(doc.categories) == 3


class TestJatsAuthorRoles:
    """Tests for CRediT author role parsing."""

    def test_parse_author_roles(self):
        doc = parse_jats(AUTHOR_ROLES_JATS)
        assert len(doc.authors) == 3
        assert doc.authors[0].roles == [
            "Conceptualization",
            "Software",
            "Formal analysis",
        ]
        assert doc.authors[1].roles == ["Investigation"]
        assert doc.authors[2].roles == []


# -- Funding parsing --------------------------------------------------------


class TestFundingParsing:
    def test_parse_funding_group(self):
        """Parse funding-group with award-group entries."""
        xml = b"""<article>
          <front><article-meta>
            <funding-group>
              <award-group><funding-source>NIH</funding-source>
                <award-id>R01GM12345</award-id></award-group>
              <award-group><funding-source>Wellcome Trust</funding-source>
                <award-id>098765</award-id><award-id>054321</award-id></award-group>
              <funding-statement>Funded by NIH and Wellcome.</funding-statement>
            </funding-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.funding) == 2
        assert doc.funding[0].funder == "NIH"
        assert doc.funding[0].award_ids == ["R01GM12345"]
        assert doc.funding[1].funder == "Wellcome Trust"
        assert doc.funding[1].award_ids == ["098765", "054321"]
        assert doc.funding_statement == "Funded by NIH and Wellcome."

    def test_parse_standalone_funding_statement(self):
        """Parse funding-statement without award-group."""
        xml = b"""<article>
          <front><article-meta>
            <funding-group>
              <funding-statement>This work was self-funded.</funding-statement>
            </funding-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.funding) == 0
        assert doc.funding_statement == "This work was self-funded."

    def test_no_funding(self):
        """No funding-group produces empty fields."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert doc.funding == []
        assert doc.funding_statement == ""


# -- Author notes parsing --------------------------------------------------


class TestAuthorNotesParsing:
    def test_parse_author_notes(self):
        """Parse author-notes with corresp and fn elements."""
        xml = b"""<article>
          <front><article-meta>
            <author-notes>
              <corresp id="cor1">Corresponding author: foo@bar.edu</corresp>
              <fn fn-type="equal"><p>These authors contributed equally.</p></fn>
              <fn fn-type="present-address"><p>Current address: MIT.</p></fn>
            </author-notes>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.author_notes) == 3
        assert "foo@bar.edu" in doc.author_notes[0]
        assert "contributed equally" in doc.author_notes[1]
        assert "MIT" in doc.author_notes[2]

    def test_coi_excluded_from_author_notes(self):
        """COI footnotes in author-notes should NOT appear in author_notes."""
        xml = b"""<article>
          <front><article-meta>
            <author-notes>
              <corresp id="cor1">Contact: test@test.com</corresp>
              <fn fn-type="conflict"><p>No conflicts.</p></fn>
            </author-notes>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.author_notes) == 1
        assert "test@test.com" in doc.author_notes[0]
        assert "No conflicts" in doc.competing_interests


# -- Competing interests parsing --------------------------------------------


class TestCompetingInterestsParsing:
    def test_parse_coi_from_author_notes(self):
        """Parse competing interests from fn-type=conflict in author-notes."""
        xml = b"""<article>
          <front><article-meta>
            <author-notes>
              <fn fn-type="conflict">
                <p>The authors declare no competing interests.</p>
              </fn>
            </author-notes>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert "no competing interests" in doc.competing_interests

    def test_parse_coi_from_back_fn_group(self):
        """Parse competing interests from fn-group in back."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <fn-group>
              <fn fn-type="COI-statement"><p>No conflicts.</p></fn>
            </fn-group>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "No conflicts" in doc.competing_interests

    def test_coi_excluded_from_back_matter(self):
        """COI footnotes should NOT appear in back_matter."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <fn-group>
              <fn fn-type="conflict"><p>No conflicts.</p></fn>
              <fn fn-type="other"><p>Some other note.</p></fn>
            </fn-group>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "No conflicts" in doc.competing_interests
        # Back-matter fn-group notes are stored as paragraphs
        all_texts = []
        for sec in doc.back_matter:
            for p in sec.paragraphs:
                all_texts.append(p.text)
        assert any("Some other note" in t for t in all_texts)
        assert not any("No conflicts" in t for t in all_texts)


# -- Data availability parsing ---------------------------------------------


class TestDataAvailabilityParsing:
    def test_parse_from_back_notes(self):
        """Parse data availability from notes in back."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <notes notes-type="data-availability">
              <p>All data available at https://example.com.</p>
            </notes>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "All data available" in doc.data_availability

    def test_parse_from_custom_meta(self):
        """Parse data availability from custom-meta-group."""
        xml = b"""<article>
          <front><article-meta>
            <custom-meta-group>
              <custom-meta>
                <meta-name>Data Availability</meta-name>
                <meta-value>Data deposited at NCBI GEO.</meta-value>
              </custom-meta>
            </custom-meta-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert "deposited at NCBI GEO" in doc.data_availability

    def test_data_avail_in_back_matter_with_heading(self):
        """Data availability notes appear in back_matter with original heading."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <notes notes-type="data-availability">
              <title>Data Availability Statement</title>
              <p>Data at GEO.</p>
            </notes>
            <notes>
              <title>Publisher Note</title>
              <p>Some publisher note.</p>
            </notes>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "Data at GEO" in doc.data_availability
        all_paras = []
        all_headings = []
        for sec in doc.back_matter:
            if sec.heading:
                all_headings.append(sec.heading)
            for p in sec.paragraphs:
                all_paras.append(p.text)
        assert any("publisher note" in t.lower() for t in all_paras)
        # Data availability is now also in back_matter with its heading
        assert any("Data at GEO" in t for t in all_paras)
        assert "Data Availability Statement" in all_headings


# -- Supplementary material expanded coverage -------------------------------


class TestSupplementaryMaterialExpanded:
    def test_supp_material_in_back(self):
        """Supplementary material as direct child of back is captured."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Results</title><p>Text.</p></sec></body>
          <back>
            <supplementary-material>
              <label>S1 Table</label>
              <caption><p>List of primers used.</p></caption>
            </supplementary-material>
          </back>
        </article>"""
        doc = parse_jats(xml)
        all_text_parts = []
        for sec in doc.back_matter:
            for p in sec.paragraphs:
                all_text_parts.append(p.text)
        assert any("S1 Table" in t for t in all_text_parts)
        assert any("primers" in t for t in all_text_parts)

    def test_supp_material_in_app(self):
        """Supplementary material inside app element is captured."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Results</title><p>Text.</p></sec></body>
          <back>
            <app-group>
              <app>
                <title>Appendix A</title>
                <supplementary-material>
                  <label>S1 File</label>
                  <caption><p>Raw data.</p></caption>
                </supplementary-material>
              </app>
            </app-group>
          </back>
        </article>"""
        doc = parse_jats(xml)
        all_text_parts = []
        for sec in doc.back_matter:
            for p in sec.paragraphs:
                all_text_parts.append(p.text)
        assert any("S1 File" in t for t in all_text_parts)


# -- Inline formula ---------------------------------------------------------


class TestInlineFormula:
    def test_inline_formula_preserved(self):
        """Inline formula text is preserved in paragraph."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Methods</title>
            <p>The value of <inline-formula>x = 2y + 1</inline-formula> was used.</p>
          </sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert doc.sections
        para_text = doc.sections[0].paragraphs[0].text
        assert "x = 2y + 1" in para_text
        assert "was used" in para_text


# -- List with multi-paragraph items ----------------------------------------


class TestListMultiParagraph:
    def test_list_items_preserve_all_paragraphs(self):
        """List items with multiple <p> elements preserve all text."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Response</title>
            <p><list list-type="bullet">
              <list-item>
                <p><bold>Criteria</bold></p>
                <p>The criteria were clearly defined.</p>
                <p>Additional details follow.</p>
              </list-item>
              <list-item>
                <p><bold>Methods</bold></p>
                <p>The methods were validated.</p>
              </list-item>
            </list></p>
          </sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert doc.sections
        sec = doc.sections[0]
        assert len(sec.lists) == 1
        items = sec.lists[0].items
        assert len(items) == 2
        # First item should contain all three paragraphs
        assert "Criteria" in items[0]
        assert "clearly defined" in items[0]
        assert "Additional details" in items[0]
        # Second item should contain both paragraphs
        assert "Methods" in items[1]
        assert "validated" in items[1]


# -- Table inside <alternatives> ---------------------------------------------


class TestTableAlternatives:
    def test_table_in_alternatives_wrapper(self):
        """Table inside <alternatives> is still parsed."""
        xml = b"""<article>
          <front><article-meta></article-meta></front>
          <body><sec><title>Results</title>
            <table-wrap id="tab1">
              <label>Table 1.</label>
              <alternatives>
                <table>
                  <thead><tr><th>Drug</th><th>Resistance</th></tr></thead>
                  <tbody><tr><td>Tetracycline</td><td>High</td></tr></tbody>
                </table>
                <graphic xlink:href="table1.png"
                         xmlns:xlink="http://www.w3.org/1999/xlink"/>
              </alternatives>
            </table-wrap>
          </sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert doc.sections
        sec = doc.sections[0]
        assert len(sec.tables) == 1
        table = sec.tables[0]
        assert table.label == "Table 1."
        assert len(table.rows) == 2
        assert table.rows[0][0].text == "Drug"
        assert table.rows[1][0].text == "Tetracycline"


# -- New inline formatting: monospace, strike, underline --------------------


class TestMonospaceFormatting:
    def test_monospace_inline(self):
        """<monospace> rendered as backtick code spans."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>The gene <monospace>BRCA1</monospace> is important.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "`BRCA1`" in para
        assert "The gene `BRCA1` is important." == para

    def test_monospace_empty(self):
        """Empty <monospace> produces no stray backticks."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>Before<monospace></monospace> after.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "`" not in para


class TestStrikethroughFormatting:
    def test_strike_inline(self):
        """<strike> rendered as GFM strikethrough ~~...~~."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>This is <strike>deleted</strike> text.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "~~deleted~~" in para

    def test_strike_empty(self):
        """Empty <strike> produces no stray tildes."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>Before<strike></strike> after.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "~~" not in para


class TestUnderlineFormatting:
    def test_underline_inline(self):
        """<underline> rendered as <u>...</u> HTML."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>This is <underline>underlined</underline> text.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "<u>underlined</u>" in para

    def test_underline_empty(self):
        """Empty <underline> produces no stray tags."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>Before<underline></underline> after.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "<u>" not in para


# -- Subtitle extraction ---------------------------------------------------


class TestSubtitleExtraction:
    def test_title_with_subtitle(self):
        """<subtitle> appended to title with ': ' separator."""
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Main Title</article-title>
            <subtitle>A Comprehensive Review</subtitle>
          </title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.title == "Main Title: A Comprehensive Review"

    def test_title_without_subtitle(self):
        """No <subtitle> leaves title unchanged."""
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Plain Title</article-title>
          </title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.title == "Plain Title"

    def test_empty_subtitle_ignored(self):
        """Empty <subtitle> does not add trailing ': '."""
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Title</article-title>
            <subtitle>  </subtitle>
          </title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.title == "Title"


# -- Collab authors at article level ---------------------------------------


class TestCollabArticleAuthors:
    def test_collab_author(self):
        """<collab> in contrib-group captured as author surname."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <collab>The International Human Genome Consortium</collab>
            </contrib>
            <contrib contrib-type="author">
              <name><surname>Smith</surname><given-names>J</given-names></name>
            </contrib>
          </contrib-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert len(doc.authors) == 2
        assert doc.authors[0].surname == "The International Human Genome Consortium"
        assert doc.authors[0].given_name == ""
        assert doc.authors[1].surname == "Smith"

    def test_collab_only_authors(self):
        """Article with only collaborative authors."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <collab>ENCODE Project Consortium</collab>
            </contrib>
          </contrib-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert len(doc.authors) == 1
        assert doc.authors[0].surname == "ENCODE Project Consortium"


# -- NLM citation support --------------------------------------------------


class TestNlmCitation:
    def test_nlm_citation_parsed(self):
        """<nlm-citation> references parsed like element-citation."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <nlm-citation citation-type="journal">
              <person-group person-group-type="author">
                <name><surname>Old</surname><given-names>A</given-names></name>
              </person-group>
              <article-title>Legacy reference</article-title>
              <source>Old Journal</source>
              <year>2005</year>
              <volume>10</volume>
              <fpage>100</fpage>
              <lpage>110</lpage>
            </nlm-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        assert len(doc.references) == 1
        ref = doc.references[0]
        assert "Old" in ref.authors[0]
        assert ref.title == "Legacy reference"
        assert ref.journal == "Old Journal"
        assert ref.year == "2005"
        assert ref.pages == "100-110"

    def test_nlm_citation_in_alternatives(self):
        """<nlm-citation> inside <citation-alternatives> wrapper."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <citation-alternatives>
              <nlm-citation citation-type="journal">
                <article-title>Alt NLM title</article-title>
                <source>J</source>
                <year>2003</year>
              </nlm-citation>
            </citation-alternatives>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        assert len(doc.references) == 1
        assert doc.references[0].title == "Alt NLM title"


# -- Group container unpacking --------------------------------------------


class TestGroupContainers:
    def test_fig_group_in_section(self):
        """<fig-group> children collected into doc.figures."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title>
          <p>See figures below.</p>
          <fig-group>
            <fig id="f1"><label>Figure 1</label>
              <caption><p>Panel A.</p></caption></fig>
            <fig id="f2"><label>Figure 2</label>
              <caption><p>Panel B.</p></caption></fig>
          </fig-group>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 2
        assert doc.figures[0].label == "Figure 1"
        assert doc.figures[1].label == "Figure 2"

    def test_table_wrap_group_in_section(self):
        """<table-wrap-group> children unpacked into section.tables."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title>
          <table-wrap-group>
            <table-wrap id="t1"><label>Table 1</label>
              <table><thead><tr><th>A</th></tr></thead>
              <tbody><tr><td>1</td></tr></tbody></table>
            </table-wrap>
            <table-wrap id="t2"><label>Table 2</label>
              <table><thead><tr><th>B</th></tr></thead>
              <tbody><tr><td>2</td></tr></tbody></table>
            </table-wrap>
          </table-wrap-group>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        assert len(sec.tables) == 2
        assert sec.tables[0].label == "Table 1"
        assert sec.tables[1].label == "Table 2"

    def test_disp_formula_group_in_section(self):
        """<disp-formula-group> children unpacked into section.formulas."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <disp-formula-group>
            <disp-formula id="eq1">E = mc^2</disp-formula>
            <disp-formula id="eq2">F = ma</disp-formula>
          </disp-formula-group>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        assert len(sec.formulas) == 2
        assert "E = mc^2" in sec.formulas[0].text
        assert "F = ma" in sec.formulas[1].text

    def test_fig_group_at_body_level(self):
        """<fig-group> as direct child of <body> collected into doc.figures."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body>
          <fig-group>
            <fig id="f1"><label>Figure 1</label>
              <caption><p>Body-level fig.</p></caption></fig>
          </fig-group>
        </body></article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 1
        assert doc.figures[0].label == "Figure 1"


# -- Fallback text extraction for unknown block elements -------------------


class TestFallbackBlockExtraction:
    def test_unknown_block_text_preserved(self):
        """Unknown block elements in <sec> have text extracted as paragraph."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Discussion</title>
          <p>Normal paragraph.</p>
          <speech><speaker>Dr. Smith</speaker>
            <p>This is a speech element.</p>
          </speech>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        all_text_parts = [p.text for p in sec.paragraphs]
        assert any("Normal paragraph" in t for t in all_text_parts)
        assert any("Dr. Smith" in t or "speech element" in t for t in all_text_parts)

    def test_verse_group_text_preserved(self):
        """<verse-group> text extracted via fallback."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Epigraph</title>
          <verse-group>
            <verse-line>Roses are red,</verse-line>
            <verse-line>Violets are blue.</verse-line>
          </verse-group>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        all_text_parts = [p.text for p in sec.paragraphs]
        assert any("Roses" in t for t in all_text_parts)


# -- Table tfoot parsing --------------------------------------------------


class TestTableTfoot:
    def test_tfoot_rows_appended(self):
        """<tfoot> rows appended after tbody rows."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <table-wrap>
            <table>
              <thead><tr><th>Gene</th><th>Value</th></tr></thead>
              <tbody><tr><td>BRCA1</td><td>2.5</td></tr></tbody>
              <tfoot><tr><td>Total</td><td>2.5</td></tr></tfoot>
            </table>
          </table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert len(table.rows) == 3  # 1 header + 1 data + 1 footer
        assert table.rows[0][0].is_header is True
        assert table.rows[1][0].text == "BRCA1"
        assert table.rows[2][0].text == "Total"

    def test_tfoot_only_table(self):
        """Table with thead and tfoot but no tbody."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <table-wrap>
            <table>
              <thead><tr><th>Col</th></tr></thead>
              <tfoot><tr><td>Summary</td></tr></tfoot>
            </table>
          </table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert len(table.rows) == 2  # 1 header + 1 footer
        assert table.rows[1][0].text == "Summary"


# -- URI in references -----------------------------------------------------


class TestRefUriExtraction:
    def test_uri_element_in_citation(self):
        """<uri> in citation extracted as ext_link."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>Web resource</article-title>
              <year>2024</year>
              <uri xmlns:xlink="http://www.w3.org/1999/xlink"
                   xlink:href="https://example.com/data">Example Data</uri>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert "https://example.com/data" in ref.ext_links

    def test_uri_text_fallback(self):
        """<uri> with no href uses text content."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>Title</article-title>
              <year>2024</year>
              <uri>https://example.com/fallback</uri>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert "https://example.com/fallback" in ref.ext_links

    def test_uri_alongside_ext_link(self):
        """Both <ext-link> and <uri> captured."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>Title</article-title>
              <year>2024</year>
              <ext-link xmlns:xlink="http://www.w3.org/1999/xlink"
                        xlink:href="https://example.com/ext">link</ext-link>
              <uri xmlns:xlink="http://www.w3.org/1999/xlink"
                   xlink:href="https://example.com/uri">uri</uri>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert len(ref.ext_links) == 2
        assert "https://example.com/ext" in ref.ext_links
        assert "https://example.com/uri" in ref.ext_links


# -- Edition and comment in references -------------------------------------


class TestRefEditionComment:
    def test_edition_parsed(self):
        """<edition> captured in Reference.edition."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation publication-type="book">
              <source>Molecular Biology of the Cell</source>
              <year>2022</year>
              <edition>7th</edition>
              <publisher-name>Garland Science</publisher-name>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert ref.edition == "7th"

    def test_comment_parsed(self):
        """<comment> captured in Reference.comment."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>Upcoming paper</article-title>
              <year>2025</year>
              <comment>In press</comment>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert ref.comment == "In press"

    def test_edition_and_comment_together(self):
        """Both edition and comment parsed from same reference."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation publication-type="book">
              <source>Genetics</source>
              <year>2024</year>
              <edition>3rd</edition>
              <comment>Epub ahead of print</comment>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert ref.edition == "3rd"
        assert ref.comment == "Epub ahead of print"


# -- Boxed text, floats-group, bio tests -----------------------------------


class TestBoxedText:
    def test_boxed_text_with_title(self):
        """<boxed-text> with title creates a boxed subsection."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Discussion</title>
          <boxed-text>
            <title>Box 1: Key Finding</title>
            <p>Important discovery about gene regulation.</p>
          </boxed-text>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        assert len(sec.subsections) == 1
        box = sec.subsections[0]
        assert box.is_boxed is True
        assert box.heading == "Box 1: Key Finding"
        all_text_parts = [p.text for p in box.paragraphs]
        assert any("Important discovery" in t for t in all_text_parts)

    def test_boxed_text_with_label(self):
        """<boxed-text> with label creates a boxed subsection."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <boxed-text>
            <label>Protocol 1</label>
            <p>Steps for the experiment.</p>
          </boxed-text>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        assert len(sec.subsections) == 1
        box = sec.subsections[0]
        assert box.is_boxed is True
        assert box.heading == "Protocol 1"
        all_text_parts = [p.text for p in box.paragraphs]
        assert any("Steps for the experiment" in t for t in all_text_parts)

    def test_boxed_text_no_title(self):
        """<boxed-text> without title creates a boxed subsection."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title>
          <boxed-text>
            <p>Stand-alone boxed content.</p>
          </boxed-text>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        assert len(sec.subsections) == 1
        box = sec.subsections[0]
        assert box.is_boxed is True
        all_text_parts = [p.text for p in box.paragraphs]
        assert any("Stand-alone boxed content" in t for t in all_text_parts)


class TestFloatsGroup:
    def test_floats_group_figures(self):
        """<floats-group> figures attached to document."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title><p>See Fig 1.</p></sec></body>
        <floats-group>
          <fig id="f1"><label>Figure 1</label>
            <caption><p>Float fig caption.</p></caption></fig>
          <fig id="f2"><label>Figure 2</label>
            <caption><p>Second float fig.</p></caption></fig>
        </floats-group></article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 2
        assert doc.figures[0].label == "Figure 1"
        assert doc.figures[1].label == "Figure 2"

    def test_floats_group_tables(self):
        """<floats-group> tables attached to document."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title><p>See Table 1.</p></sec></body>
        <floats-group>
          <table-wrap id="t1"><label>Table 1</label>
            <table><thead><tr><th>A</th></tr></thead>
            <tbody><tr><td>1</td></tr></tbody></table>
          </table-wrap>
        </floats-group></article>"""
        doc = parse_jats(xml)
        assert len(doc.tables) == 1
        assert doc.tables[0].label == "Table 1"


class TestBioInBack:
    def test_bio_in_back(self):
        """<bio> in <back> captured as back_matter section."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back>
          <bio>
            <p>Dr. Smith is a professor at MIT.</p>
            <p>Her research focuses on gene regulation.</p>
          </bio>
        </back></article>"""
        doc = parse_jats(xml)
        # Bio paragraphs captured in back_matter (section without heading)
        assert len(doc.back_matter) >= 1
        bio_paras = []
        for sec in doc.back_matter:
            bio_paras.extend(p.text for p in sec.paragraphs)
        assert any("professor at MIT" in t for t in bio_paras)
        assert any("gene regulation" in t for t in bio_paras)


# -- Small caps, overline, roman (pass-through inline formatting) ----------


class TestPassThroughFormatting:
    def test_sc_text_preserved(self):
        """<sc> (small caps) text preserved in paragraph."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>The <sc>Hox</sc> gene cluster is important.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "Hox" in para
        assert "The Hox gene cluster is important." == para

    def test_sc_with_nested_formatting(self):
        """<sc> with nested <italic> preserves both."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>The <sc>gene <italic>Drosophila</italic></sc> cluster.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "gene *Drosophila*" in para

    def test_overline_text_preserved(self):
        """<overline> text preserved in paragraph."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>The value <overline>X</overline> is the complement.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "The value X is the complement." == para

    def test_roman_text_preserved(self):
        """<roman> text preserved in paragraph."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p><italic>This is italic with <roman>roman text</roman> inside.</italic></p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "roman text" in para


# -- Standalone <graphic> outside <fig> ------------------------------------


class TestStandaloneGraphic:
    def test_graphic_in_section(self):
        """Standalone <graphic> in <sec> becomes a Figure."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title>
          <p>See the image below.</p>
          <graphic xmlns:xlink="http://www.w3.org/1999/xlink"
                   xlink:href="image1.tif"/>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 1
        assert doc.figures[0].graphic_url == "image1.tif"
        assert doc.figures[0].label == ""

    def test_graphic_with_alt_text(self):
        """Standalone <graphic> with <alt-text> child."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title>
          <graphic xmlns:xlink="http://www.w3.org/1999/xlink"
                   xlink:href="diagram.png">
            <alt-text>Schematic of the pathway</alt-text>
          </graphic>
        </sec></body></article>"""
        doc = parse_jats(xml)
        fig = doc.figures[0]
        assert fig.graphic_url == "diagram.png"
        assert fig.alt_text == "Schematic of the pathway"

    def test_graphic_at_body_level(self):
        """Standalone <graphic> as direct child of <body>."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body>
          <graphic xmlns:xlink="http://www.w3.org/1999/xlink"
                   xlink:href="body-graphic.jpg"/>
        </body></article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 1
        assert doc.figures[0].graphic_url == "body-graphic.jpg"

    def test_graphic_inside_p(self):
        """<graphic> inside <p> extracted into doc.figures."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title>
          <p>Before image.
            <graphic xmlns:xlink="http://www.w3.org/1999/xlink"
                     xlink:href="inline.png"/>
          After image.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 1
        assert doc.figures[0].graphic_url == "inline.png"
        sec = doc.sections[0]
        assert len(sec.paragraphs) == 2
        assert "Before image" in sec.paragraphs[0].text
        assert "After image" in sec.paragraphs[1].text


# -- <media> elements ------------------------------------------------------


class TestMediaElements:
    def test_media_in_section(self):
        """<media> in <sec> rendered as descriptive paragraph."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Results</title>
          <p>Normal paragraph.</p>
          <media xmlns:xlink="http://www.w3.org/1999/xlink"
                 xlink:href="video1.mp4" mimetype="video">
            <label>Video 1</label>
            <caption><p>Time-lapse of cell division.</p></caption>
          </media>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        media_paras = [p for p in sec.paragraphs if "Video 1" in p.text]
        assert len(media_paras) == 1
        assert "cell division" in media_paras[0].text

    def test_media_without_label(self):
        """<media> without label still extracts caption."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <media xmlns:xlink="http://www.w3.org/1999/xlink"
                 xlink:href="data.csv">
            <caption><p>Supplementary dataset.</p></caption>
          </media>
        </sec></body></article>"""
        doc = parse_jats(xml)
        sec = doc.sections[0]
        media_paras = [p for p in sec.paragraphs if "dataset" in p.text.lower()]
        assert len(media_paras) == 1

    def test_media_at_body_level(self):
        """<media> as direct child of <body>."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body>
          <media xmlns:xlink="http://www.w3.org/1999/xlink"
                 xlink:href="animation.gif">
            <label>Animation 1</label>
            <caption><p>Protein folding simulation.</p></caption>
          </media>
        </body></article>"""
        doc = parse_jats(xml)
        assert len(doc.sections) == 1
        media_paras = [p for p in doc.sections[0].paragraphs if "Animation 1" in p.text]
        assert len(media_paras) == 1


# -- Improved formula parsing (tex-math, alternatives, MathML) ------------


class TestFormulaImproved:
    def test_tex_math_preserved(self):
        """<tex-math> content preserved as raw LaTeX."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <disp-formula id="eq1">
            <tex-math>E = mc^{2}</tex-math>
          </disp-formula>
        </sec></body></article>"""
        doc = parse_jats(xml)
        formula = doc.sections[0].formulas[0]
        assert "E = mc^{2}" in formula.text

    def test_alternatives_prefers_tex_math(self):
        """<alternatives> with tex-math and MathML uses tex-math."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <disp-formula id="eq1">
            <alternatives>
              <tex-math>\\alpha + \\beta = \\gamma</tex-math>
              <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML">
                <mml:mi>&#945;</mml:mi><mml:mo>+</mml:mo>
                <mml:mi>&#946;</mml:mi><mml:mo>=</mml:mo>
                <mml:mi>&#947;</mml:mi>
              </mml:math>
            </alternatives>
          </disp-formula>
        </sec></body></article>"""
        doc = parse_jats(xml)
        formula = doc.sections[0].formulas[0]
        assert "\\alpha" in formula.text
        assert "\\beta" in formula.text

    def test_mathml_annotation_latex(self):
        """MathML with LaTeX annotation extracts the annotation."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <disp-formula>
            <mml:math xmlns:mml="http://www.w3.org/1998/Math/MathML">
              <mml:semantics>
                <mml:mrow><mml:mi>x</mml:mi></mml:mrow>
                <mml:annotation encoding="LaTeX">x^2 + y^2 = z^2</mml:annotation>
              </mml:semantics>
            </mml:math>
          </disp-formula>
        </sec></body></article>"""
        doc = parse_jats(xml)
        formula = doc.sections[0].formulas[0]
        assert "x^2 + y^2 = z^2" in formula.text

    def test_plain_text_formula_unchanged(self):
        """Plain text formula (no tex-math/MathML) still works."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <disp-formula>F = ma</disp-formula>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert "F = ma" in doc.sections[0].formulas[0].text

    def test_formula_label_still_removed(self):
        """Label removed from formula text even with new extraction."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>Methods</title>
          <disp-formula>
            <label>(1)</label>
            <tex-math>a^2 + b^2 = c^2</tex-math>
          </disp-formula>
        </sec></body></article>"""
        doc = parse_jats(xml)
        formula = doc.sections[0].formulas[0]
        assert formula.label == "(1)"
        assert "a^2 + b^2 = c^2" in formula.text
        assert "(1)" not in formula.text


# -- <data-title> fallback for references ---------------------------------


class TestDataTitleRef:
    def test_data_title_as_fallback(self):
        """<data-title> used as title when no <article-title>."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation publication-type="data">
              <person-group person-group-type="author">
                <name><surname>Doe</surname><given-names>J</given-names></name>
              </person-group>
              <data-title>Genome-wide expression dataset</data-title>
              <source>GEO</source>
              <year>2024</year>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert ref.title == "Genome-wide expression dataset"

    def test_article_title_preferred_over_data_title(self):
        """<article-title> preferred when both present."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>The real title</article-title>
              <data-title>Dataset title</data-title>
              <year>2024</year>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        assert doc.references[0].title == "The real title"


# -- Named-content / styled-content with nested formatting ----------------


class TestNamedContentFormatting:
    def test_named_content_preserves_italic(self):
        """<named-content> with nested <italic> preserves formatting."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>The species <named-content content-type="genus-species">
            <italic>Drosophila melanogaster</italic>
          </named-content> is a model organism.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "*Drosophila melanogaster*" in para
        assert "model organism" in para

    def test_styled_content_preserves_formatting(self):
        """<styled-content> with nested formatting preserved."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>The <styled-content style="color:red">
            <bold>important</bold> result
          </styled-content> is notable.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "**important**" in para
        assert "result" in para

    def test_nested_named_content(self):
        """Deeply nested inline containers preserve formatting."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>Gene <named-content content-type="gene">
            <monospace>BRCA1</monospace>
          </named-content> is mutated.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "`BRCA1`" in para


# -- <break/> inline element ----------------------------------------------


class TestBreakElement:
    def test_break_in_paragraph(self):
        """<break/> emits a newline in inline text."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <p>Line one<break/>Line two</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        # Paragraph whitespace normalization collapses \n to space
        para = doc.sections[0].paragraphs[0].text
        assert "Line one" in para
        assert "Line two" in para

    def test_break_in_inline_text(self):
        """<break/> inside _inline_text (e.g., caption) preserved."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <fig id="f1"><label>Figure 1</label>
            <caption><p>Panel A shows X.<break/>Panel B shows Y.</p></caption>
          </fig>
        </sec></body></article>"""
        doc = parse_jats(xml)
        fig = next(f for f in doc.figures if "Figure 1" in f.label)
        # Caption uses _inline_text which should preserve break as \n
        assert "Panel A" in fig.caption
        assert "Panel B" in fig.caption


# -- History dates (received/accepted) ------------------------------------


class TestHistoryDates:
    def test_received_and_accepted_dates(self):
        """<history> dates parsed into Document fields."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <history>
            <date date-type="received">
              <day>15</day><month>3</month><year>2024</year>
            </date>
            <date date-type="accepted">
              <day>20</day><month>6</month><year>2024</year>
            </date>
          </history>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.received_date == "2024-03-15"
        assert doc.accepted_date == "2024-06-20"

    def test_partial_dates(self):
        """Dates with only year and month."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <history>
            <date date-type="received">
              <month>1</month><year>2025</year>
            </date>
          </history>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.received_date == "2025-01"

    def test_no_history(self):
        """No <history> leaves fields empty."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.received_date == ""
        assert doc.accepted_date == ""

    def test_accepted_alt_type(self):
        """<date date-type='acc'> recognized as accepted."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <history>
            <date date-type="acc">
              <day>5</day><month>12</month><year>2023</year>
            </date>
          </history>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.accepted_date == "2023-12-05"


# -- Copyright and license URL --------------------------------------------


class TestCopyrightAndLicenseUrl:
    def test_copyright_statement(self):
        """<copyright-statement> captured in Document.copyright."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <permissions>
            <copyright-statement>Copyright 2024 The Authors</copyright-statement>
            <copyright-year>2024</copyright-year>
          </permissions>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.copyright == "Copyright 2024 The Authors"

    def test_license_url(self):
        """License xlink:href captured as license_url."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <permissions>
            <license xmlns:xlink="http://www.w3.org/1999/xlink"
                     xlink:href="https://creativecommons.org/licenses/by/4.0/"
                     license-type="open-access">
              <license-p>This is an open access article.</license-p>
            </license>
          </permissions>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.license_url == "https://creativecommons.org/licenses/by/4.0/"
        assert "open access" in doc.license

    def test_no_permissions(self):
        """No <permissions> leaves fields empty."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.copyright == ""
        assert doc.license_url == ""


# -- <date-in-citation> in references -------------------------------------


class TestDateInCitation:
    def test_access_date(self):
        """<date-in-citation content-type='access-date'> added to comment."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>Web resource</article-title>
              <year>2024</year>
              <date-in-citation content-type="access-date">
                January 15, 2024
              </date-in-citation>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert "Accessed" in ref.comment
        assert "January 15, 2024" in ref.comment

    def test_date_in_citation_with_existing_comment(self):
        """Access date appended to existing comment."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>Title</article-title>
              <year>2024</year>
              <comment>Online database</comment>
              <date-in-citation content-type="access-date">
                2024-03-01
              </date-in-citation>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert "Online database" in ref.comment
        assert "2024-03-01" in ref.comment
        assert ";" in ref.comment

    def test_date_in_citation_no_content_type(self):
        """<date-in-citation> without content-type still captured."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body>
        <back><ref-list>
          <ref id="r1">
            <element-citation>
              <article-title>Title</article-title>
              <year>2024</year>
              <date-in-citation>March 2024</date-in-citation>
            </element-citation>
          </ref>
        </ref-list></back></article>"""
        doc = parse_jats(xml)
        ref = doc.references[0]
        assert "March 2024" in ref.comment
        # No "Accessed" prefix when content-type is not "access-date"
        assert not ref.comment.startswith("Accessed")


# -- <self-uri> extraction -------------------------------------------------


class TestSelfUri:
    def test_self_uri_from_href(self):
        """<self-uri xlink:href='...'> captured."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <self-uri xmlns:xlink="http://www.w3.org/1999/xlink"
                    xlink:href="https://example.com/article/12345"/>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.self_uri == "https://example.com/article/12345"

    def test_self_uri_text_fallback(self):
        """<self-uri> text used when no href attribute."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <self-uri>https://example.com/pdf/12345.pdf</self-uri>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.self_uri == "https://example.com/pdf/12345.pdf"

    def test_no_self_uri(self):
        """No <self-uri> leaves field empty."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert doc.self_uri == ""


# -- <trans-abstract> as secondary abstract --------------------------------


class TestTransAbstract:
    def test_trans_abstract_captured(self):
        """<trans-abstract> becomes a secondary abstract."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<article><front><article-meta>"
            "  <title-group><article-title>T</article-title></title-group>"
            "  <abstract><p>Main abstract in English.</p></abstract>"
            '  <trans-abstract xml:lang="es">'
            "    <title>Resumen</title>"
            "    <p>Resumen principal en espa\u00f1ol.</p>"
            "  </trans-abstract>"
            "</article-meta></front>"
            "<body><sec><title>I</title><p>X.</p></sec></body></article>"
        ).encode()
        doc = parse_jats(xml)
        assert len(doc.abstract) == 1
        assert "English" in doc.abstract[0].text
        assert len(doc.secondary_abstracts) == 1
        sa = doc.secondary_abstracts[0]
        assert sa.label == "Resumen"
        assert sa.abstract_type == "trans-abstract-es"
        assert "espa\u00f1ol" in sa.paragraphs[0].text

    def test_trans_abstract_no_title(self):
        """<trans-abstract> without <title> gets auto-generated label."""
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<article><front><article-meta>"
            "  <title-group><article-title>T</article-title></title-group>"
            "  <abstract><p>Main abstract.</p></abstract>"
            '  <trans-abstract xml:lang="fr">'
            "    <p>R\u00e9sum\u00e9 en fran\u00e7ais.</p>"
            "  </trans-abstract>"
            "</article-meta></front>"
            "<body><sec><title>I</title><p>X.</p></sec></body></article>"
        ).encode()
        doc = parse_jats(xml)
        assert len(doc.secondary_abstracts) == 1
        sa = doc.secondary_abstracts[0]
        assert "fr" in sa.label
        assert "fran\u00e7ais" in sa.paragraphs[0].text

    def test_multiple_trans_abstracts(self):
        """Multiple <trans-abstract> elements captured."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <abstract><p>English abstract.</p></abstract>
          <trans-abstract xml:lang="es"><p>Spanish summary.</p></trans-abstract>
          <trans-abstract xml:lang="pt"><p>Portuguese summary.</p></trans-abstract>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert len(doc.secondary_abstracts) == 2
        types = [sa.abstract_type for sa in doc.secondary_abstracts]
        assert "trans-abstract-es" in types
        assert "trans-abstract-pt" in types


# -- Improved keyword parsing ----------------------------------------------


class TestKeywordImprovements:
    def test_abbreviation_group_skipped(self):
        """kwd-group-type='abbreviations' not included in keywords."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <kwd-group kwd-group-type="author">
            <kwd>genomics</kwd>
            <kwd>bioinformatics</kwd>
          </kwd-group>
          <kwd-group kwd-group-type="abbreviations">
            <kwd>GO: Gene Ontology</kwd>
            <kwd>MOD: Model Organism Database</kwd>
          </kwd-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert "genomics" in doc.keywords
        assert "bioinformatics" in doc.keywords
        assert len(doc.keywords) == 2

    def test_compound_keywords(self):
        """<compound-kwd> parts joined with space."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <kwd-group>
            <kwd>simple keyword</kwd>
            <compound-kwd>
              <compound-kwd-part>Drosophila</compound-kwd-part>
              <compound-kwd-part>melanogaster</compound-kwd-part>
            </compound-kwd>
          </kwd-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert "simple keyword" in doc.keywords
        assert "Drosophila melanogaster" in doc.keywords

    def test_multiple_kwd_groups_combined(self):
        """Keywords from multiple non-abbreviation groups combined."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <kwd-group kwd-group-type="author">
            <kwd>alpha</kwd>
          </kwd-group>
          <kwd-group kwd-group-type="discipline">
            <kwd>beta</kwd>
          </kwd-group>
        </article-meta></front>
        <body><sec><title>I</title><p>X.</p></sec></body></article>"""
        doc = parse_jats(xml)
        assert "alpha" in doc.keywords
        assert "beta" in doc.keywords


# -- Table rowspan expansion -----------------------------------------------


class TestRowspanExpansion:
    def test_simple_rowspan(self):
        """rowspan=2 inserts empty cell in next row."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <table-wrap><table>
            <thead><tr><th>Category</th><th>Item</th><th>Value</th></tr></thead>
            <tbody>
              <tr><td rowspan="2">Group A</td><td>Item 1</td><td>10</td></tr>
              <tr><td>Item 2</td><td>20</td></tr>
            </tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert len(table.rows) == 3  # 1 header + 2 data
        # Row 1: "Group A" | "Item 1" | "10"
        assert table.rows[1][0].text == "Group A"
        assert table.rows[1][1].text == "Item 1"
        assert table.rows[1][2].text == "10"
        # Row 2: "" (carry from rowspan) | "Item 2" | "20"
        assert len(table.rows[2]) == 3
        assert table.rows[2][0].text == ""
        assert table.rows[2][1].text == "Item 2"
        assert table.rows[2][2].text == "20"

    def test_rowspan_3(self):
        """rowspan=3 inserts empty cells in two subsequent rows."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <table-wrap><table>
            <tbody>
              <tr><td rowspan="3">Span</td><td>A</td></tr>
              <tr><td>B</td></tr>
              <tr><td>C</td></tr>
            </tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert len(table.rows) == 3
        assert table.rows[0][0].text == "Span"
        assert table.rows[0][1].text == "A"
        assert table.rows[1][0].text == ""
        assert table.rows[1][1].text == "B"
        assert table.rows[2][0].text == ""
        assert table.rows[2][1].text == "C"

    def test_rowspan_with_colspan(self):
        """Both rowspan and colspan on same cell."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <table-wrap><table>
            <tbody>
              <tr><td rowspan="2" colspan="2">Big</td><td>C</td></tr>
              <tr><td>D</td></tr>
            </tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        # Row 0: "Big" | "" (colspan) | "C"
        assert len(table.rows[0]) == 3
        assert table.rows[0][0].text == "Big"
        assert table.rows[0][1].text == ""  # colspan padding
        assert table.rows[0][2].text == "C"
        # Row 1: "" | "" (both from rowspan of colspan=2 cell) | "D"
        assert len(table.rows[1]) == 3
        assert table.rows[1][0].text == ""
        assert table.rows[1][1].text == ""
        assert table.rows[1][2].text == "D"

    def test_no_rowspan_unchanged(self):
        """Tables without rowspan are unaffected."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>R</title>
          <table-wrap><table>
            <thead><tr><th>A</th><th>B</th></tr></thead>
            <tbody><tr><td>1</td><td>2</td></tr></tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert len(table.rows) == 2
        assert table.rows[0][0].text == "A"
        assert table.rows[1][0].text == "1"


# ── Trans-title-group ────────────────────────────────────────────────


class TestTransTitleGroup:
    """Tests for <trans-title-group> translated title extraction."""

    def test_single_trans_title(self):
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Original Title</article-title>
            <trans-title-group xml:lang="es">
              <trans-title>Titulo Original</trans-title>
            </trans-title-group>
          </title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.title == "Original Title"
        assert len(doc.trans_titles) == 1
        assert doc.trans_titles[0] == "Titulo Original [es]"

    def test_multiple_trans_titles(self):
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>English Title</article-title>
            <trans-title-group xml:lang="fr">
              <trans-title>Titre Francais</trans-title>
            </trans-title-group>
            <trans-title-group xml:lang="de">
              <trans-title>Deutscher Titel</trans-title>
            </trans-title-group>
          </title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert len(doc.trans_titles) == 2
        assert doc.trans_titles[0] == "Titre Francais [fr]"
        assert doc.trans_titles[1] == "Deutscher Titel [de]"

    def test_trans_title_with_subtitle(self):
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Main</article-title>
            <trans-title-group xml:lang="pt">
              <trans-title>Titulo</trans-title>
              <trans-subtitle>Um subtitulo</trans-subtitle>
            </trans-title-group>
          </title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.trans_titles[0] == "Titulo: Um subtitulo [pt]"

    def test_trans_title_no_lang(self):
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Main</article-title>
            <trans-title-group>
              <trans-title>Translated</trans-title>
            </trans-title-group>
          </title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.trans_titles[0] == "Translated"

    def test_trans_title_with_formatting(self):
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Main</article-title>
            <trans-title-group xml:lang="es">
              <trans-title>Efecto de <italic>Arabidopsis</italic></trans-title>
            </trans-title-group>
          </title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.trans_titles[0] == "Efecto de *Arabidopsis* [es]"

    def test_no_trans_titles(self):
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>No Translations</article-title>
          </title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.trans_titles == []

    def test_trans_title_emitted_in_markdown(self):
        xml = b"""<article><front><article-meta>
          <title-group>
            <article-title>Main Title</article-title>
            <trans-title-group xml:lang="es">
              <trans-title>Titulo Principal</trans-title>
            </trans-title-group>
          </title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        from agr_abc_document_parsers.md_emitter import emit_markdown

        md = emit_markdown(doc)
        assert "# Main Title" in md
        assert "*Titulo Principal [es]*" in md


# ── Counts metadata ──────────────────────────────────────────────────


class TestCountsMetadata:
    """Tests for <counts> metadata extraction."""

    def test_standard_counts(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <counts>
            <fig-count count="5"/>
            <table-count count="3"/>
            <page-count count="12"/>
            <ref-count count="42"/>
          </counts>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.counts == {
            "fig-count": 5,
            "table-count": 3,
            "page-count": 12,
            "ref-count": 42,
        }

    def test_equation_and_word_counts(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <counts>
            <equation-count count="8"/>
            <word-count count="5000"/>
          </counts>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.counts["equation-count"] == 8
        assert doc.counts["word-count"] == 5000

    def test_no_counts(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert doc.counts == {}

    def test_invalid_count_value_skipped(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <counts>
            <fig-count count="abc"/>
            <page-count count="10"/>
          </counts>
        </article-meta></front></article>"""
        doc = parse_jats(xml)
        assert "fig-count" not in doc.counts
        assert doc.counts["page-count"] == 10


# ── Email and URI inline rendering ───────────────────────────────────


class TestEmailInline:
    """Tests for <email> element handling in paragraphs."""

    def test_email_in_paragraph(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>Contact: <email>john@example.com</email> for details.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert "john@example.com" in doc.sections[0].paragraphs[0].text

    def test_email_in_split_paragraph(self):
        """Email inside a <p> that also contains a block element."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>Write to <email>info@lab.org</email>.
          <fig><label>Fig 1</label></fig>
          More text.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert "info@lab.org" in doc.sections[0].paragraphs[0].text


class TestUriInline:
    """Tests for <uri> element handling in paragraphs."""

    def test_uri_with_href(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>See <uri xlink:href="http://example.com/data"
               xmlns:xlink="http://www.w3.org/1999/xlink"
               >Dataset 1</uri> for raw data.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "[Dataset 1](http://example.com/data)" in para

    def test_uri_text_matches_href(self):
        """When text equals href, just emit the URL (no markdown link)."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>Visit <uri xlink:href="http://example.com"
               xmlns:xlink="http://www.w3.org/1999/xlink"
               >http://example.com</uri>.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0].text
        assert "http://example.com" in para
        # Should NOT have redundant [url](url) format
        assert "[http://example.com]" not in para

    def test_uri_no_href_uses_text(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>See <uri>http://data.org/set1</uri>.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert "http://data.org/set1" in doc.sections[0].paragraphs[0].text

    def test_uri_in_split_paragraph(self):
        """URI inside a <p> with block elements uses _collect_from_p path."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>Data at <uri xlink:href="http://example.com/data"
               xmlns:xlink="http://www.w3.org/1999/xlink"
               >Dataset</uri>.
          <fig><label>Fig 1</label></fig></p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert "[Dataset](http://example.com/data)" in doc.sections[0].paragraphs[0].text


# ── Named-content content-type annotation ────────────────────────────


class TestNamedContentAnnotation:
    """Tests for <named-content> content-type attribute extraction."""

    def test_gene_annotation(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>The <named-content content-type="gene">BRCA1</named-content>
          gene is important.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0]
        assert "BRCA1" in para.text
        assert len(para.named_content) == 1
        assert para.named_content[0].text == "BRCA1"
        assert para.named_content[0].content_type == "gene"

    def test_multiple_annotations(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p><named-content content-type="genus-species">E. coli</named-content>
          expresses <named-content content-type="gene">lacZ</named-content>.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0]
        assert len(para.named_content) == 2
        types = {nc.content_type for nc in para.named_content}
        assert types == {"genus-species", "gene"}

    def test_styled_content_annotation(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>Use <styled-content content-type="monospace">grep</styled-content>
          to search.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0]
        assert "grep" in para.text
        assert len(para.named_content) == 1
        assert para.named_content[0].content_type == "monospace"

    def test_no_content_type_no_annotation(self):
        """named-content without content-type attribute produces no annotation."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>The <named-content>something</named-content> here.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0]
        assert "something" in para.text
        assert para.named_content == []

    def test_annotation_with_nested_formatting(self):
        """named-content with nested italic preserves formatting in text."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>The <named-content content-type="genus-species"
            ><italic>Drosophila melanogaster</italic></named-content> fly.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0]
        assert "*Drosophila melanogaster*" in para.text
        assert para.named_content[0].text == "*Drosophila melanogaster*"
        assert para.named_content[0].content_type == "genus-species"

    def test_annotation_in_split_paragraph(self):
        """named-content in a paragraph with block elements (_collect_from_p)."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>Gene <named-content content-type="gene">TP53</named-content> is
          <fig><label>Fig 1</label></fig>
          shown above.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        para = doc.sections[0].paragraphs[0]
        assert "TP53" in para.text
        assert len(para.named_content) == 1
        assert para.named_content[0].content_type == "gene"


# ── Table cell alignment ─────────────────────────────────────────────


class TestTableCellAlignment:
    """Tests for table cell align attribute extraction and markdown emission."""

    def test_align_attribute_extracted(self):
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <table-wrap><table>
            <thead><tr>
              <th align="left">Name</th>
              <th align="center">Score</th>
              <th align="right">Rank</th>
            </tr></thead>
            <tbody><tr>
              <td align="left">A</td>
              <td align="center">95</td>
              <td align="right">1</td>
            </tr></tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert table.rows[0][0].align == "left"
        assert table.rows[0][1].align == "center"
        assert table.rows[0][2].align == "right"
        assert table.rows[1][0].align == "left"

    def test_align_in_markdown_separator(self):
        """Emitter uses header cell align for GFM column alignment."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <table-wrap><table>
            <thead><tr>
              <th align="left">A</th>
              <th align="center">B</th>
              <th align="right">C</th>
            </tr></thead>
            <tbody><tr>
              <td>1</td><td>2</td><td>3</td>
            </tr></tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        from agr_abc_document_parsers.md_emitter import emit_markdown

        md = emit_markdown(doc)
        assert "|---|:---:|---:|" in md

    def test_no_align_default_separator(self):
        """Without align attributes, separator uses plain ---."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <table-wrap><table>
            <thead><tr><th>A</th><th>B</th></tr></thead>
            <tbody><tr><td>1</td><td>2</td></tr></tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        from agr_abc_document_parsers.md_emitter import emit_markdown

        md = emit_markdown(doc)
        assert "|---|---|" in md

    def test_colspan_inherits_align(self):
        """Colspan padding cells inherit the source cell's alignment."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <table-wrap><table>
            <thead><tr>
              <th align="center" colspan="2">Wide</th>
              <th>C</th>
            </tr></thead>
            <tbody><tr>
              <td>1</td><td>2</td><td>3</td>
            </tr></tbody>
          </table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        # Both the cell and its colspan padding should have align="center"
        assert table.rows[0][0].align == "center"
        assert table.rows[0][1].align == "center"
        assert table.rows[0][2].align == ""


# ---------------------------------------------------------------------------
# Bug fix: multiple <table-wrap-foot> elements per table
# ---------------------------------------------------------------------------


class TestMultipleTableWrapFoot:
    """Verify all <table-wrap-foot> elements are captured, not just the first."""

    def test_multiple_table_wrap_foot(self):
        xml = b"""<article><body><sec>
          <table-wrap>
            <table><tbody>
              <tr><th>A</th><th>B</th></tr>
              <tr><td>1</td><td>2</td></tr>
            </tbody></table>
            <table-wrap-foot>
              <fn><p>First footnote</p></fn>
            </table-wrap-foot>
            <table-wrap-foot>
              <fn><p>Second footnote</p></fn>
              <fn><p>Third footnote</p></fn>
            </table-wrap-foot>
          </table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert len(table.foot_notes) == 3
        assert "First footnote" in table.foot_notes[0]
        assert "Second footnote" in table.foot_notes[1]
        assert "Third footnote" in table.foot_notes[2]

    def test_multiple_foot_with_bare_p(self):
        """Mixed: one foot with <fn>, another with bare <p>."""
        xml = b"""<article><body><sec>
          <table-wrap>
            <table><tbody><tr><td>X</td></tr></tbody></table>
            <table-wrap-foot>
              <fn><p>Footnote A</p></fn>
            </table-wrap-foot>
            <table-wrap-foot>
              <p>Bare paragraph footnote</p>
            </table-wrap-foot>
          </table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        assert len(table.foot_notes) == 2
        assert "Footnote A" in table.foot_notes[0]
        assert "Bare paragraph" in table.foot_notes[1]


# ---------------------------------------------------------------------------
# Bug fix: preamble flush with subsections/notes from boxed-text
# ---------------------------------------------------------------------------


class TestPreambleFlushSubsections:
    """Boxed-text content before first <sec> must not be lost."""

    def test_boxed_text_before_first_sec(self):
        """<boxed-text> with <sec> children before body <sec>."""
        xml = b"""<article><body>
          <boxed-text position="float">
            <sec><title>Key findings</title>
              <p>Finding one.</p>
            </sec>
            <sec><title>What is new</title>
              <p>New thing.</p>
            </sec>
          </boxed-text>
          <sec><title>Introduction</title>
            <p>Intro text.</p>
          </sec>
        </body></article>"""
        doc = parse_jats(xml)
        # Preamble section should be flushed with boxed subsection
        assert len(doc.sections) >= 2
        preamble = doc.sections[0]
        assert len(preamble.subsections) == 1
        box = preamble.subsections[0]
        assert box.is_boxed is True
        assert len(box.subsections) == 2
        assert box.subsections[0].heading == "Key findings"
        assert box.subsections[1].heading == "What is new"
        # Body section follows
        intro = doc.sections[1]
        assert intro.heading == "Introduction"

    def test_boxed_text_caption_title(self):
        """<boxed-text> with <caption><title> creates headed boxed subsection."""
        xml = b"""<article><body>
          <boxed-text position="float">
            <caption><title>Highlight box</title></caption>
            <sec><title>Summary</title>
              <p>Summary text.</p>
            </sec>
          </boxed-text>
          <sec><title>Methods</title><p>Methods text.</p></sec>
        </body></article>"""
        doc = parse_jats(xml)
        preamble = doc.sections[0]
        assert len(preamble.subsections) == 1
        box = preamble.subsections[0]
        assert box.is_boxed is True
        assert box.heading == "Highlight box"
        assert box.subsections[0].heading == "Summary"

    def test_trailing_boxed_text_flush(self):
        """Boxed-text after last <sec> is flushed as boxed subsection."""
        xml = b"""<article><body>
          <sec><title>Results</title><p>Result text.</p></sec>
          <boxed-text>
            <sec><title>Takeaway</title><p>Key point.</p></sec>
          </boxed-text>
        </body></article>"""
        doc = parse_jats(xml)
        assert len(doc.sections) == 2
        trailing = doc.sections[1]
        assert len(trailing.subsections) == 1
        box = trailing.subsections[0]
        assert box.is_boxed is True
        assert box.subsections[0].heading == "Takeaway"


# ---------------------------------------------------------------------------
# Bug fix: <sec> children inside <ack>
# ---------------------------------------------------------------------------


class TestAckSubSections:
    """Sections nested inside <ack> become back_matter entries."""

    def test_sec_inside_ack(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <ack><p>We thank the reviewers.</p>
              <sec><title>CRediT authorship</title>
                <p>Alice: Writing. Bob: Review.</p>
              </sec>
              <sec><title>Ethical considerations</title>
                <p>Ethics approval was obtained.</p>
              </sec>
            </ack>
          </back>
        </article>"""
        doc = parse_jats(xml)
        assert "We thank the reviewers" in doc.acknowledgments
        # Sections from <ack> appear in back_matter
        headings = [s.heading for s in doc.back_matter]
        assert "CRediT authorship" in headings
        assert "Ethical considerations" in headings

    def test_ack_without_sec(self):
        """No <sec> inside <ack> — back_matter unaffected."""
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back><ack><p>Thanks.</p></ack></back>
        </article>"""
        doc = parse_jats(xml)
        assert "Thanks" in doc.acknowledgments
        ack_headings = [
            s.heading for s in doc.back_matter if "CRediT" in s.heading or "Ethical" in s.heading
        ]
        assert ack_headings == []


# ---------------------------------------------------------------------------
# Bug fix: nested <notes> inside <notes> in back-matter
# ---------------------------------------------------------------------------


class TestNestedNotes:
    """Nested <notes> elements become subsections."""

    def test_declarations_with_nested_notes(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <notes>
              <title>Declarations</title>
              <notes>
                <title>Ethics approval</title>
                <p>Approved by IRB.</p>
              </notes>
              <notes>
                <title>Consent for publication</title>
                <p>All consented.</p>
              </notes>
            </notes>
          </back>
        </article>"""
        doc = parse_jats(xml)
        decl = [s for s in doc.back_matter if s.heading == "Declarations"]
        assert len(decl) == 1
        assert len(decl[0].subsections) == 2
        assert decl[0].subsections[0].heading == "Ethics approval"
        assert decl[0].subsections[1].heading == "Consent for publication"
        assert any("Approved by IRB" in p.text for p in decl[0].subsections[0].paragraphs)

    def test_notes_with_direct_p_and_nested(self):
        """Notes with both direct <p> and nested <notes>."""
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <back>
            <notes>
              <title>Disclosures</title>
              <p>General disclosure.</p>
              <notes>
                <title>COI</title>
                <p>None declared.</p>
              </notes>
            </notes>
          </back>
        </article>"""
        doc = parse_jats(xml)
        disc = [s for s in doc.back_matter if s.heading == "Disclosures"]
        assert len(disc) == 1
        # Direct paragraph
        assert any("General disclosure" in p.text for p in disc[0].paragraphs)
        # Nested subsection
        assert disc[0].subsections[0].heading == "COI"


# ---------------------------------------------------------------------------
# Bug fix: <boxed-text> in <floats-group>
# ---------------------------------------------------------------------------


class TestBoxedTextInFloatsGroup:
    """Boxed-text in floats-group becomes back_matter."""

    def test_boxed_text_floats_group(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
          <floats-group>
            <boxed-text position="float">
              <caption><title>Key points</title></caption>
              <list list-type="bullet">
                <list-item><p>Point one.</p></list-item>
                <list-item><p>Point two.</p></list-item>
              </list>
            </boxed-text>
          </floats-group>
        </article>"""
        doc = parse_jats(xml)
        # Boxed-text content should be in back_matter
        bm_with_lists = [s for s in doc.back_matter if s.lists]
        assert len(bm_with_lists) >= 1
        items = bm_with_lists[0].lists[0].items
        assert "Point one." in items[0]
        assert "Point two." in items[1]


# ---------------------------------------------------------------------------
# Bug fix: mixed <p> and <sec> in abstract
# ---------------------------------------------------------------------------


class TestMixedAbstract:
    """Abstract with both direct <p> and <sec> children."""

    def test_abstract_p_then_sec(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
            <abstract>
              <p>Lead paragraph of the abstract.</p>
              <sec><title>Methods</title>
                <p>We did X and Y.</p>
              </sec>
              <sec><title>Results</title>
                <p>We found Z.</p>
              </sec>
            </abstract>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.abstract) == 3
        assert doc.abstract[0].text == "Lead paragraph of the abstract."
        assert "Methods:" in doc.abstract[1].text
        assert "Results:" in doc.abstract[2].text

    def test_abstract_sec_then_p(self):
        """Reverse order: <sec> first, then bare <p>."""
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
            <abstract>
              <sec><title>Background</title>
                <p>Background info.</p>
              </sec>
              <p>Trailing abstract paragraph.</p>
            </abstract>
          </article-meta></front>
          <body><sec><title>Intro</title><p>Text.</p></sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.abstract) == 2
        assert "Background:" in doc.abstract[0].text
        assert doc.abstract[1].text == "Trailing abstract paragraph."


# ---------------------------------------------------------------------------
# Affiliation parsing improvements
# ---------------------------------------------------------------------------


class TestAffiliationParsing:
    """Tests for affiliation extraction from various JATS layouts."""

    def test_aff_inside_contrib_group(self):
        """eLife: <aff> nested inside <contrib-group>."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <xref ref-type="aff" rid="a1"/>
            </contrib>
            <aff id="a1"><label>1</label>
              <institution-wrap>
                <institution-id institution-id-type="ror">https://ror.org/123</institution-id>
                <institution>MIT</institution>
              </institution-wrap>
              <addr-line>Cambridge</addr-line>
              <country>USA</country>
            </aff>
          </contrib-group>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert len(doc.authors[0].affiliations) == 1
        assert "MIT" in doc.authors[0].affiliations[0]
        assert "Cambridge" in doc.authors[0].affiliations[0]
        # ROR URL should NOT be in affiliation text
        assert "ror.org" not in doc.authors[0].affiliations[0]
        # Label number should NOT be in affiliation text
        assert not doc.authors[0].affiliations[0].startswith("1")

    def test_aff_plain_text_with_label(self):
        """Plain text <aff> with <label> — label stripped."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <xref ref-type="aff" rid="A1"/>
            </contrib>
          </contrib-group>
          <aff id="A1"><label>1</label>Dept of Biology, MIT, USA</aff>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert doc.authors[0].affiliations[0] == "Dept of Biology, MIT, USA"

    def test_non_affiliation_filtered(self):
        """Entries like 'These authors contributed equally' filtered out."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <xref ref-type="aff" rid="A1"/>
              <xref ref-type="aff" rid="A18"/>
            </contrib>
          </contrib-group>
          <aff id="A1"><label>1</label>MIT, USA</aff>
          <aff id="A18"><label>18</label>These authors contributed equally</aff>
          <aff id="A19"><label>19</label>Lead contact</aff>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert len(doc.authors[0].affiliations) == 1
        assert "MIT" in doc.authors[0].affiliations[0]

    def test_inline_aff_in_contrib(self):
        """Inline <aff> directly inside <contrib> (Genetics style)."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <aff><institution>Stanford University</institution>,
                <addr-line>Stanford</addr-line>,
                <country country="US">United States</country>
              </aff>
            </contrib>
          </contrib-group>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert len(doc.authors[0].affiliations) == 1
        assert "Stanford University" in doc.authors[0].affiliations[0]

    def test_shared_affiliation_fallback(self):
        """All authors get affiliations when no xref but aff exists."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
            </contrib>
            <contrib contrib-type="author">
              <name><surname>Roe</surname><given-names>John</given-names></name>
            </contrib>
            <aff id="A1">MIT, USA</aff>
          </contrib-group>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert len(doc.authors[0].affiliations) == 1
        assert len(doc.authors[1].affiliations) == 1


# ---------------------------------------------------------------------------
# Email extraction from author-notes
# ---------------------------------------------------------------------------


class TestEmailExtraction:
    """Tests for email standardization from various JATS patterns."""

    def test_email_from_corresp(self):
        """Email in <author-notes>/<corresp> extracted to Author.email."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Smith</surname><given-names>Alice</given-names></name>
            </contrib>
          </contrib-group>
          <author-notes>
            <corresp>*Corresponding author: alice@example.com</corresp>
          </author-notes>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert doc.authors[0].email == "alice@example.com"
        # Corresp note should be removed from author_notes
        assert not any("alice@example.com" in n for n in doc.author_notes)

    def test_email_from_address(self):
        """Email inside <contrib>/<address>/<email> (Nature style)."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author" corresp="yes">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <address><email>jane@example.org</email></address>
            </contrib>
          </contrib-group>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert doc.authors[0].email == "jane@example.org"

    def test_multi_email_corresp(self):
        """Multiple emails in a single <corresp> matched to authors."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Smith</surname><given-names>Alice</given-names></name>
            </contrib>
            <contrib contrib-type="author">
              <name><surname>Jones</surname><given-names>Bob</given-names></name>
            </contrib>
          </contrib-group>
          <author-notes>
            <corresp>Corresponding authors: Alice Smith, alice@mit.edu;
              Bob Jones, bob@stanford.edu</corresp>
          </author-notes>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert doc.authors[0].email == "alice@mit.edu"
        assert doc.authors[1].email == "bob@stanford.edu"

    def test_email_match_by_surname_in_local_part(self):
        """Email local part contains author surname."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Wang</surname><given-names>Meng</given-names></name>
            </contrib>
          </contrib-group>
          <author-notes>
            <corresp>*Corresponding author: mengwang@example.org</corresp>
          </author-notes>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert doc.authors[0].email == "mengwang@example.org"

    def test_non_email_notes_preserved(self):
        """Notes without emails are kept in author_notes."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <xref ref-type="fn" rid="fn1"/>
            </contrib>
          </contrib-group>
          <author-notes>
            <fn id="fn1"><p>Present address: Oxford, UK</p></fn>
          </author-notes>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert any("Present address" in n for n in doc.author_notes)


# ---------------------------------------------------------------------------
# CRediT roles from fn-type="con" footnotes
# ---------------------------------------------------------------------------


class TestContributionFootnotes:
    """Tests for author role extraction from fn-type='con' footnotes."""

    def test_roles_from_fn_con(self):
        """eLife style: roles in back/fn-group with fn-type='con'."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <xref ref-type="fn" rid="con1"/>
            </contrib>
          </contrib-group>
        </article-meta></front>
        <body><sec><title>S</title><p>Text.</p></sec></body>
        <back><fn-group>
          <fn fn-type="con" id="con1">
            <p>Conceptualization, Investigation, Writing.</p>
          </fn>
        </fn-group></back></article>"""
        doc = parse_jats(xml)
        assert len(doc.authors[0].roles) == 1
        assert "Conceptualization" in doc.authors[0].roles[0]

    def test_roles_from_role_element(self):
        """Standard: roles in <role> elements (takes precedence)."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <role>Conceptualization</role>
              <role>Investigation</role>
            </contrib>
          </contrib-group>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert doc.authors[0].roles == ["Conceptualization", "Investigation"]


# ---------------------------------------------------------------------------
# Author notes with linked author names
# ---------------------------------------------------------------------------


class TestAuthorNotesLinkedNames:
    """Tests for footnote label resolution to author names."""

    def test_footnote_labels_resolved(self):
        """Footnote labels linked to author names via xref."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
          <contrib-group>
            <contrib contrib-type="author">
              <name><surname>Doe</surname><given-names>Jane</given-names></name>
              <xref ref-type="fn" rid="fn1"/>
              <xref ref-type="fn" rid="fn2"/>
            </contrib>
            <contrib contrib-type="author">
              <name><surname>Roe</surname><given-names>John</given-names></name>
              <xref ref-type="fn" rid="fn1"/>
            </contrib>
          </contrib-group>
          <author-notes>
            <fn id="fn1"><label>1</label>
              <p>These authors contributed equally</p>
            </fn>
            <fn id="fn2"><label>2</label>
              <p>Lead contact</p>
            </fn>
          </author-notes>
        </article-meta></front><body/></article>"""
        doc = parse_jats(xml)
        assert any("Jane Doe, John Roe" in n for n in doc.author_notes)
        assert any("Lead contact" in n for n in doc.author_notes)
        # Labels should not appear as numbers
        assert not any(n.startswith("1") for n in doc.author_notes)


# ---------------------------------------------------------------------------
# fn-group routing to dedicated fields
# ---------------------------------------------------------------------------


class TestFnGroupRouting:
    """Tests for routing fn-group content to dedicated Document fields."""

    def test_funding_routed_from_fn_group(self):
        """Funding footnote with bold title routed to funding_statement."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title><p>Text.</p></sec></body>
        <back>
          <fn-group>
            <fn fn-type="financial-disclosure">
              <p><bold>Funding</bold></p>
              <p>Supported by NIH grant R01.</p>
            </fn>
          </fn-group>
        </back></article>"""
        doc = parse_jats(xml)
        assert "NIH grant R01" in doc.funding_statement

    def test_data_availability_routed_from_fn_group(self):
        """Data availability footnote routed to data_availability."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title><p>Text.</p></sec></body>
        <back>
          <fn-group>
            <fn>
              <p><bold>Data and resource availability</bold></p>
              <p>All data deposited at GEO.</p>
            </fn>
          </fn-group>
        </back></article>"""
        doc = parse_jats(xml)
        assert "GEO" in doc.data_availability


# ---------------------------------------------------------------------------
# Table cell and citation formatting
# ---------------------------------------------------------------------------


class TestInlineFormatting:
    """Tests for inline formatting preservation."""

    def test_table_cell_italic(self):
        """Italic formatting preserved in table cells."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <table-wrap><table><thead>
            <tr><th>Type</th><th>Name</th></tr>
          </thead><tbody>
            <tr><td>Strain (<italic>D. rerio</italic>)</td>
                <td>foxf2a<sup>ca71</sup></td></tr>
          </tbody></table></table-wrap>
        </sec></body></article>"""
        doc = parse_jats(xml)
        table = doc.sections[0].tables[0]
        # Find the data row (not header)
        data_rows = [r for r in table.rows if not all(c.is_header for c in r)]
        assert len(data_rows) >= 1
        cell_texts = [c.text for c in data_rows[0]]
        assert any("*D. rerio*" in t for t in cell_texts)
        assert any("<sup>ca71</sup>" in t for t in cell_texts)

    def test_citation_superscript_preserved(self):
        """Superscript inside <xref ref-type='bibr'> preserved."""
        xml = b"""<article><front><article-meta>
          <title-group><article-title>T</article-title></title-group>
        </article-meta></front>
        <body><sec><title>S</title>
          <p>As described<xref rid="bib1" ref-type="bibr"><sup>1</sup></xref>
             previously.</p>
        </sec></body></article>"""
        doc = parse_jats(xml)
        assert "<sup>1</sup>" in doc.sections[0].paragraphs[0].text


# ---------------------------------------------------------------------------
# Metadata emission and round-trip
# ---------------------------------------------------------------------------


class TestMetadataRoundTrip:
    """Tests for new metadata fields emission and round-trip."""

    def test_orcid_round_trip(self):
        """ORCIDs survive JATS -> MD -> Document round-trip."""
        from agr_abc_document_parsers.md_emitter import emit_markdown
        from agr_abc_document_parsers.md_reader import read_markdown
        from agr_abc_document_parsers.models import Author, Document

        doc = Document(
            title="Paper",
            authors=[
                Author(
                    given_name="Alice",
                    surname="Smith",
                    orcid="https://orcid.org/0000-0001-2345-6789",
                ),
                Author(given_name="Bob", surname="Jones"),
            ],
        )
        md = emit_markdown(doc)
        assert "**ORCIDs:**" in md
        doc2 = read_markdown(md)
        assert doc2.authors[0].orcid == "https://orcid.org/0000-0001-2345-6789"
        assert doc2.authors[1].orcid == ""

    def test_received_accepted_round_trip(self):
        """Received/accepted dates survive round-trip."""
        from agr_abc_document_parsers.md_emitter import emit_markdown
        from agr_abc_document_parsers.md_reader import read_markdown
        from agr_abc_document_parsers.models import Document

        doc = Document(
            title="Paper",
            received_date="2024-01-15",
            accepted_date="2024-06-20",
            copyright="2024 The Authors",
            license_url="https://creativecommons.org/licenses/by/4.0/",
        )
        md = emit_markdown(doc)
        doc2 = read_markdown(md)
        assert doc2.received_date == "2024-01-15"
        assert doc2.accepted_date == "2024-06-20"
        assert doc2.copyright == "2024 The Authors"
        assert doc2.license_url == "https://creativecommons.org/licenses/by/4.0/"

    def test_affiliation_superscript_round_trip(self):
        """Per-author affiliation mapping survives round-trip."""
        from agr_abc_document_parsers.md_emitter import emit_markdown
        from agr_abc_document_parsers.md_reader import read_markdown
        from agr_abc_document_parsers.models import Author, Document

        doc = Document(
            title="Paper",
            authors=[
                Author(
                    given_name="Alice",
                    surname="Smith",
                    affiliations=["MIT", "Harvard"],
                ),
                Author(
                    given_name="Bob",
                    surname="Jones",
                    affiliations=["MIT"],
                ),
            ],
        )
        md = emit_markdown(doc)
        assert "Alice Smith<sup>1,2</sup>" in md
        assert "Bob Jones<sup>1</sup>" in md
        doc2 = read_markdown(md)
        assert doc2.authors[0].affiliations == ["MIT", "Harvard"]
        assert doc2.authors[1].affiliations == ["MIT"]

    def test_author_contributions_round_trip(self):
        """Author contributions section survives round-trip."""
        from agr_abc_document_parsers.md_emitter import emit_markdown
        from agr_abc_document_parsers.md_reader import read_markdown
        from agr_abc_document_parsers.models import Author, Document

        doc = Document(
            title="Paper",
            authors=[
                Author(
                    given_name="Alice",
                    surname="Smith",
                    roles=["Conceptualization", "Writing"],
                ),
                Author(
                    given_name="Bob",
                    surname="Jones",
                    roles=["Investigation"],
                ),
            ],
        )
        md = emit_markdown(doc)
        assert "## Author Contributions" in md
        doc2 = read_markdown(md)
        assert "Conceptualization" in doc2.authors[0].roles
        assert "Writing" in doc2.authors[0].roles
        assert "Investigation" in doc2.authors[1].roles

    def test_secondary_abstract_after_references(self):
        """Secondary abstracts emitted after references."""
        from agr_abc_document_parsers.md_emitter import emit_markdown
        from agr_abc_document_parsers.models import (
            Document,
            Paragraph,
            Reference,
            SecondaryAbstract,
        )

        doc = Document(
            title="Paper",
            abstract=[Paragraph(text="Abstract.")],
            secondary_abstracts=[
                SecondaryAbstract(
                    label="eLife digest",
                    paragraphs=[Paragraph(text="Plain language.")],
                )
            ],
            references=[
                Reference(index=1, authors=["A"], title="T", year="2024"),
            ],
        )
        md = emit_markdown(doc)
        lines = md.split("\n")
        ref_idx = next(i for i, ln in enumerate(lines) if "## References" in ln)
        digest_idx = next(i for i, ln in enumerate(lines) if "eLife digest" in ln)
        assert ref_idx < digest_idx


class TestFigureXrefLinkification:
    """Test that <xref ref-type='fig'> becomes a Markdown link."""

    def test_fig_xref_becomes_link(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Results</title>
            <p>See <xref ref-type="fig" rid="fig1">Fig. 1</xref> for details.</p>
            <fig id="fig1"><label>Fig. 1</label>
              <caption><title>My caption.</title></caption>
            </fig>
          </sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert any("[Fig. 1](#fig-1)" in p.text for p in doc.sections[0].paragraphs)

    def test_figure_xref_becomes_link(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Results</title>
            <p>As shown in <xref ref-type="fig" rid="f2">Figure 2</xref>.</p>
            <fig id="f2"><label>Figure 2</label>
              <caption><title>Caption two.</title></caption>
            </fig>
          </sec></body>
        </article>"""
        doc = parse_jats(xml)
        assert any("[Figure 2](#figure-2)" in p.text for p in doc.sections[0].paragraphs)

    def test_non_fig_xref_unchanged(self):
        """xref with ref-type='bibr' should NOT be linkified."""
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Intro</title>
            <p>See <xref ref-type="bibr" rid="b1">1</xref>.</p>
          </sec></body>
        </article>"""
        doc = parse_jats(xml)
        text = doc.sections[0].paragraphs[0].text
        assert "](#" not in text


class TestFigureCollection:
    """Test that all figures are collected into doc.figures."""

    def test_section_figures_moved_to_doc(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body>
            <sec><title>Results</title>
              <fig><label>Figure 1</label>
                <caption><title>Cap 1.</title></caption>
              </fig>
            </sec>
            <sec><title>Discussion</title>
              <fig><label>Figure 2</label>
                <caption><title>Cap 2.</title></caption>
              </fig>
            </sec>
          </body>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 2
        assert doc.figures[0].label.startswith("Figure 1")
        assert doc.figures[1].label.startswith("Figure 2")
        for sec in doc.sections:
            assert len(sec.figures) == 0

    def test_floats_group_figures_collected(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body><sec><title>Results</title>
            <p>Text.</p>
          </sec></body>
          <floats-group>
            <fig><label>Figure 1</label>
              <caption><title>Cap 1.</title></caption>
            </fig>
          </floats-group>
        </article>"""
        doc = parse_jats(xml)
        assert len(doc.figures) == 1
        assert doc.figures[0].label.startswith("Figure 1")

    def test_figures_sorted_by_number(self):
        xml = b"""<article>
          <front><article-meta>
            <title-group><article-title>T</article-title></title-group>
          </article-meta></front>
          <body>
            <sec><title>Discussion</title>
              <fig><label>Figure 3</label>
                <caption><title>C3.</title></caption>
              </fig>
            </sec>
            <sec><title>Results</title>
              <fig><label>Figure 1</label>
                <caption><title>C1.</title></caption>
              </fig>
            </sec>
          </body>
          <floats-group>
            <fig><label>Figure 2</label>
              <caption><title>C2.</title></caption>
            </fig>
          </floats-group>
        </article>"""
        doc = parse_jats(xml)
        labels = [f.label for f in doc.figures]
        assert "Figure 1" in labels[0]
        assert "Figure 2" in labels[1]
        assert "Figure 3" in labels[2]
