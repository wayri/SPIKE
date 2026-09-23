# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
import unittest
from scripts.index_solver_references import references


class ReferenceIndexTests(unittest.TestCase):
    def test_doi_markdown_and_deduplication(self):
        self.assertEqual(references('[paper](https://doi.org/10.1234/example). DOI:10.1234/example'),
                         ['https://doi.org/10.1234/example'])

    def test_balanced_parentheses_and_no_invented_citation(self):
        self.assertEqual(references('https://example.org/a(b)), methods without citations'),
                         ['https://example.org/a(b)'])
        self.assertEqual(references('Ohm law and independently derived conservation'), [])
