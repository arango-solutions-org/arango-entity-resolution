"""
Tests for top-3 bang-for-buck features:
  1. AsyncERPipeline — async/streaming pipeline
  2. FeedbackStore / ThresholdOptimizer / AdaptiveLLMVerifier — active learning
  3. demo.py — arango-er-mcp --demo helper functions
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# Feature 1: AsyncERPipeline
# ===========================================================================

class TestAsyncERPipeline:
    """AsyncERPipeline wraps the sync pipeline in asyncio.

    These tests used to patch out all three stage methods of the object under
    test, so they passed while every stage was broken. They now use real
    objects; the end-to-end parity with a sync run against a real database is
    in tests/test_async_pipeline_integration.py.
    """

    def _make_config(self):
        from entity_resolution.config.er_config import (
            BlockingConfig, ClusteringConfig, ERPipelineConfig, SimilarityConfig,
        )
        return ERPipelineConfig(
            entity_type="company",
            collection_name="companies",
            blocking=BlockingConfig(strategy="exact", fields=["name"]),
            similarity=SimilarityConfig(threshold=0.80),
            clustering=ClusteringConfig(),
        )

    def test_init_builds_the_real_sync_pipeline(self):
        from entity_resolution.core.async_pipeline import AsyncERPipeline
        from entity_resolution.core.configurable_pipeline import ConfigurableERPipeline

        config = self._make_config()
        pipeline = AsyncERPipeline(db=None, config=config)
        assert pipeline.config.collection_name == "companies"
        assert isinstance(pipeline._pipeline, ConfigurableERPipeline)
        assert pipeline._pipeline.config is config

    def test_init_requires_config_or_path(self):
        from entity_resolution.core.async_pipeline import AsyncERPipeline
        with pytest.raises(ValueError, match="Either config or config_path"):
            AsyncERPipeline(db=None)

    def test_a_pipeline_failure_is_raised_by_the_stream(self, monkeypatch):
        # With no database the real pipeline fails in blocking. The failure must
        # surface from run(), not hang the event loop or vanish in a thread.
        from entity_resolution.core.async_pipeline import AsyncERPipeline

        monkeypatch.setenv("ER_NO_MIGRATE", "1")
        pipeline = AsyncERPipeline(db=None, config=self._make_config())
        with pytest.raises(AttributeError):
            asyncio.run(asyncio.wait_for(pipeline.run(), timeout=30))

    def test_concurrent_blocking_rejects_unknown_strategies(self):
        from entity_resolution.core.async_pipeline import AsyncERPipeline

        pipeline = AsyncERPipeline(db=None, config=self._make_config())
        with pytest.raises(ValueError, match="unknown blocking strategies"):
            asyncio.run(pipeline.run_blocking_concurrent(["collect"]))

    def test_pair_keys_are_order_independent_across_formats(self):
        from entity_resolution.core.async_pipeline import _pair_key

        assert _pair_key({"doc1_key": "b", "doc2_key": "a"}) == ("a", "b")
        assert _pair_key(("b", "a", 0.9)) == ("a", "b")
        assert _pair_key({"doc1_key": "a", "doc2_key": "a"}) is None
        assert _pair_key({"doc1_key": "a"}) is None


# ===========================================================================
# Feature 2: FeedbackStore / ThresholdOptimizer / AdaptiveLLMVerifier
# ===========================================================================

class TestFeedbackStore:
    """FeedbackStore persists LLM verdicts in ArangoDB."""

    def _make_store(self):
        from entity_resolution.reasoning.feedback import FeedbackStore
        db = MagicMock()
        db.has_collection.return_value = True
        db.aql.execute.return_value = iter([])
        db.collection.return_value = MagicMock()
        return FeedbackStore(db, collection="er_feedback")

    def test_save_calls_insert(self):
        store = self._make_store()
        key = store.save(
            {"_key": "a1"},
            {"_key": "b1"},
            score=0.72,
            decision="match",
            confidence=0.91,
        )
        store.db.collection.return_value.insert.assert_called_once()
        doc = store.db.collection.return_value.insert.call_args[0][0]
        assert doc["decision"] == "match"
        assert doc["score"] == 0.72

    def test_save_deterministic_key(self):
        """Same pair always produces same document key regardless of order."""
        store = self._make_store()
        k1 = store.save({"_key": "x"}, {"_key": "y"}, score=0.8, decision="match", confidence=0.9)
        k2 = store.save({"_key": "y"}, {"_key": "x"}, score=0.8, decision="match", confidence=0.9)
        assert k1 == k2

    def test_create_collection_if_missing(self):
        from entity_resolution.reasoning.feedback import FeedbackStore
        db = MagicMock()
        db.has_collection.return_value = False
        db.aql.execute.return_value = iter([])
        FeedbackStore(db, collection="new_coll")
        db.create_collection.assert_called_once_with("new_coll")


class TestThresholdOptimizer:
    """ThresholdOptimizer returns defaults when samples are insufficient."""

    def _make_optimizer(self, verdicts):
        from entity_resolution.reasoning.feedback import FeedbackStore, ThresholdOptimizer
        store = MagicMock(spec=FeedbackStore)
        store.all_verdicts.return_value = verdicts
        return ThresholdOptimizer(store, min_samples=5)

    def test_returns_defaults_when_too_few_samples(self):
        opt = self._make_optimizer([
            {"score": 0.7, "decision": "match"},
            {"score": 0.4, "decision": "no_match"},
        ])
        result = opt.optimize()
        assert result["optimized"] is False
        assert result["low_threshold"] == 0.55
        assert result["high_threshold"] == 0.80

    def test_returns_optimized_with_percentile(self):
        verdicts = (
            [{"score": 0.85 + i * 0.01, "decision": "match"} for i in range(10)]
            + [{"score": 0.30 + i * 0.02, "decision": "no_match"} for i in range(10)]
        )
        opt = self._make_optimizer(verdicts)
        result = opt.optimize()
        # Whether sklearn or percentile, result should be sensible
        assert 0.25 <= result["low_threshold"] < result["high_threshold"] <= 0.95
        assert result["sample_count"] == 20


class TestAdaptiveLLMVerifier:
    """AdaptiveLLMVerifier saves verdicts and refreshes thresholds."""

    def _make_adaptive(self):
        from entity_resolution.reasoning.feedback import AdaptiveLLMVerifier, FeedbackStore
        store = MagicMock(spec=FeedbackStore)
        with patch("entity_resolution.reasoning.feedback.ThresholdOptimizer"):
            with patch("entity_resolution.reasoning.llm_verifier.litellm"):
                verifier = AdaptiveLLMVerifier(feedback_store=store, refresh_every=5)
        return verifier, store

    def test_verdict_saved_when_llm_called(self):
        verifier, store = self._make_adaptive()
        verifier.verifier.verify = MagicMock(return_value={
            "decision": "match", "confidence": 0.88, "llm_called": True, "model": "gpt-4o"
        })
        verifier.verify({"_key": "a"}, {"_key": "b"}, score=0.70)
        store.save.assert_called_once()

    def test_verdict_not_saved_on_fast_path(self):
        verifier, store = self._make_adaptive()
        verifier.verifier.verify = MagicMock(return_value={
            "decision": "match", "confidence": 0.99, "llm_called": False
        })
        verifier.verify({"_key": "a"}, {"_key": "b"}, score=0.95)
        store.save.assert_not_called()

    def test_thresholds_refresh_after_n_calls(self):
        verifier, store = self._make_adaptive()
        verifier.verifier.verify = MagicMock(return_value={
            "decision": "match", "confidence": 0.88, "llm_called": False
        })
        verifier._optimizer.optimize = MagicMock(return_value={
            "optimized": True, "low_threshold": 0.50, "high_threshold": 0.75, "sample_count": 25
        })
        for _ in range(6):  # refresh_every=5, trigger on call 5
            verifier.verify({"_key": "a"}, {"_key": "b"}, score=0.70)
        verifier._optimizer.optimize.assert_called()


# ===========================================================================
# Feature 3: Demo quickstart helpers
# ===========================================================================

class TestDemoHelpers:
    """Demo quickstart internals work without real Docker or DB."""

    def test_sample_companies_have_duplicates(self):
        from entity_resolution.mcp.demo import SAMPLE_COMPANIES
        assert len(SAMPLE_COMPANIES) >= 10
        cities = [c["city"] for c in SAMPLE_COMPANIES]
        # Multiple companies in Boston = intentional duplicates
        assert cities.count("Boston") >= 2

    def test_content_hash_stable(self):
        from entity_resolution.reasoning.feedback import _content_hash
        rec = {"name": "Acme", "city": "Boston"}
        assert _content_hash(rec) == _content_hash(rec)

    def test_content_hash_different_for_different_records(self):
        from entity_resolution.reasoning.feedback import _content_hash
        a = {"name": "Acme"}
        b = {"name": "TechFlow"}
        assert _content_hash(a) != _content_hash(b)

    def test_demo_module_importable(self):
        """demo.py is importable without triggering any side effects."""
        import importlib
        mod = importlib.import_module("entity_resolution.mcp.demo")
        assert callable(getattr(mod, "run_demo", None))
        assert isinstance(mod.SAMPLE_COMPANIES, list)

    def test_run_sse_server_uses_fastmcp_transport(self):
        from entity_resolution.mcp import server as server_module

        original_host = server_module.mcp.settings.host
        original_port = server_module.mcp.settings.port
        try:
            with patch.object(server_module.mcp, "run") as mock_run:
                server_module.run_sse_server(host="127.0.0.1", port=8080)

            assert server_module.mcp.settings.host == "127.0.0.1"
            assert server_module.mcp.settings.port == 8080
            mock_run.assert_called_once_with(transport="sse")
        finally:
            server_module.mcp.settings.host = original_host
            server_module.mcp.settings.port = original_port

    def test_reasoning_exports(self):
        """reasoning/__init__.py exports all four classes."""
        from entity_resolution import reasoning
        for name in ["LLMMatchVerifier", "FeedbackStore", "ThresholdOptimizer", "AdaptiveLLMVerifier"]:
            assert hasattr(reasoning, name), f"Missing export: {name}"
