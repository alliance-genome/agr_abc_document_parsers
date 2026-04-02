"""Tests for utility functions in models.py."""

from agr_abc_document_parsers.models import figure_anchor_id


class TestFigureAnchorId:
    def test_figure_number(self):
        assert figure_anchor_id("Figure 1") == "figure-1"

    def test_fig_dot_number(self):
        assert figure_anchor_id("Fig. 1") == "fig-1"

    def test_supplementary_figure(self):
        assert figure_anchor_id("Supplementary Figure 1") == "supplementary-figure-1"

    def test_figure_s1(self):
        assert figure_anchor_id("Figure S1") == "figure-s1"

    def test_trailing_punctuation_stripped(self):
        assert figure_anchor_id("Figure 1.") == "figure-1"
        assert figure_anchor_id("Figure 1:") == "figure-1"

    def test_figure_10(self):
        assert figure_anchor_id("Figure 10") == "figure-10"

    def test_empty_string(self):
        assert figure_anchor_id("") == ""

    def test_supplementary_fig_dot(self):
        assert figure_anchor_id("Supplementary Fig. S1") == "supplementary-fig-s1"
