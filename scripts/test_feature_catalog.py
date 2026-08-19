#!/usr/bin/env python3
"""Focused standard-library regression tests for feature_catalog.py."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import feature_catalog


class FeatureCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = json.loads(feature_catalog.CATALOG_PATH.read_text(encoding="utf-8"))

    def _load_variant(self, mutate):
        variant = copy.deepcopy(self.catalog)
        mutate(variant)
        temporary = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        temporary.write(json.dumps(variant, ensure_ascii=False))
        temporary.close()
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return mock.patch.object(feature_catalog, "CATALOG_PATH", Path(temporary.name))

    def test_repository_catalog_is_valid_and_three_level(self) -> None:
        catalog, by_id = feature_catalog.load_catalog()
        self.assertEqual(catalog["schema_version"], 1)
        self.assertEqual(sum(item["level"] == "domain" for item in by_id.values()), 8)
        self.assertEqual(sum(item["level"] == "capability" for item in by_id.values()), 14)
        self.assertEqual(sum(item["level"] == "feature" for item in by_id.values()), 46)
        self.assertTrue(all(item["parent_id"] is None for item in by_id.values() if item["level"] == "domain"))

    def test_missing_parent_is_rejected(self) -> None:
        def mutate(data):
            item = next(item for item in data["items"] if item["id"] == "agent-definition")
            item["parent_id"] = "missing-parent"

        patcher = self._load_variant(mutate)
        with patcher, self.assertRaisesRegex(feature_catalog.CatalogError, "missing parent"):
            feature_catalog.load_catalog()

    def test_verified_feature_requires_passed_evidence(self) -> None:
        def mutate(data):
            item = next(item for item in data["items"] if item["id"] == "agent-definition")
            item["evidence"][0]["result"] = "blocked"

        patcher = self._load_variant(mutate)
        with patcher, self.assertRaisesRegex(feature_catalog.CatalogError, "passed evidence"):
            feature_catalog.load_catalog()

    def test_query_returns_feature_before_required_ancestors(self) -> None:
        matches = feature_catalog.query_catalog("RAG retrieval citations", 6)
        ids = [item["id"] for item in matches]
        self.assertEqual(ids[:3], ["rag-grounding-citations", "knowledge", "knowledge-context"])

    def test_query_does_not_match_platform_only_items(self) -> None:
        matches = feature_catalog.query_catalog("Desktop startup P95 release evidence", 6)
        ids = [item["id"] for item in matches]
        self.assertEqual(ids[:3], ["release-startup-evidence", "deployment", "enterprise-security"])
        self.assertNotIn("agent-run-creation", ids)

    def test_query_does_not_match_substrings_inside_words(self) -> None:
        matches = feature_catalog.query_catalog("RAG retrieval citations", 6)
        ids = [item["id"] for item in matches]
        self.assertNotIn("mcp-runtime-config", ids)
        self.assertNotIn("secrets-redaction", ids)

    def test_query_ignores_common_english_stopwords(self) -> None:
        matches = feature_catalog.query_catalog("RAG retrieval and citations", 6)
        self.assertNotIn("desktop-and-mobile", [item["id"] for item in matches])

    def test_matrix_render_is_deterministic(self) -> None:
        catalog, by_id = feature_catalog.load_catalog()
        first = feature_catalog.render_matrix(catalog, by_id)
        shuffled = dict(reversed(list(by_id.items())))
        second = feature_catalog.render_matrix(catalog, shuffled)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
