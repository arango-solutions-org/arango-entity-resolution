"""AsyncERPipeline against a real ArangoDB: an async run is a sync run.

The previous AsyncERPipeline reimplemented every stage and every stage was
broken, while its unit tests patched all three stage methods out. These tests
run the real pipeline twice on the same data, once through
ConfigurableERPipeline and once through AsyncERPipeline, and require the same
outcome.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from entity_resolution.config.er_config import ERPipelineConfig
from entity_resolution.core.async_pipeline import AsyncERPipeline
from entity_resolution.core.configurable_pipeline import ConfigurableERPipeline

pytestmark = pytest.mark.integration

PEOPLE = [
    {"_key": "p1", "name": "Jonathan Smith", "email": "js@acme.com"},
    {"_key": "p2", "name": "Jonathan Smith", "email": "js@acme.com"},
    {"_key": "p3", "name": "Jon Smith", "email": "js@acme.com"},
    {"_key": "p4", "name": "Maria Garcia", "email": "mg@globex.com"},
    {"_key": "p5", "name": "Maria Garcia", "email": "mg@globex.com"},
    {"_key": "p6", "name": "Wei Chen", "email": "wc@initech.com"},
]


@pytest.fixture
def people(db_connection):
    suffix = uuid.uuid4().hex[:8]
    names = {
        "collection": f"async_it_people_{suffix}",
        "edges": f"async_it_edges_{suffix}",
        "clusters": f"async_it_clusters_{suffix}",
    }
    db_connection.create_collection(names["collection"]).insert_many(PEOPLE)
    yield db_connection, names
    for name in names.values():
        if db_connection.has_collection(name):
            db_connection.delete_collection(name)


def _config(names) -> ERPipelineConfig:
    return ERPipelineConfig.from_dict({"entity_resolution": {
        "entity_type": "person",
        "collection_name": names["collection"],
        "edge_collection": names["edges"],
        "cluster_collection": names["clusters"],
        "blocking": {"strategy": "exact", "fields": ["email"]},
        "similarity": {"threshold": 0.8, "field_weights": {"name": 1.0}},
        "clustering": {"backend": "python_union_find", "store_results": True},
    }})


def _summary(results):
    return {
        "candidate_pairs": results["blocking"]["candidate_pairs"],
        "matches_found": results["similarity"]["matches_found"],
        "clusters_found": results["clustering"]["clusters_found"],
    }


def test_async_run_matches_sync_run(people) -> None:
    db, names = people
    sync = ConfigurableERPipeline(db=db, config=_config(names)).run()
    assert sync["blocking"]["candidate_pairs"] > 0, "fixture must produce candidates"
    asynchronous = asyncio.run(AsyncERPipeline(db, config=_config(names)).run())
    assert _summary(asynchronous) == _summary(sync)


def test_streaming_yields_each_stage_in_order_and_calls_back(people) -> None:
    db, names = people
    seen_by_callback = []

    async def callback(stage, result):
        seen_by_callback.append(stage)

    async def collect():
        pipeline = AsyncERPipeline(db, config=_config(names), progress_callback=callback)
        return [(stage, result) async for stage, result in pipeline.run_streaming()]

    streamed = asyncio.run(collect())
    stages = [stage for stage, _ in streamed]
    assert stages == ["blocking", "similarity", "edges", "clustering"]
    assert seen_by_callback == stages
    assert dict(streamed)["clustering"]["clusters_found"] >= 1


def test_concurrent_blocking_matches_the_configured_strategy(people) -> None:
    db, names = people
    config = _config(names)
    sync_pairs = {
        tuple(sorted((c["doc1_key"], c["doc2_key"])))
        for c in ConfigurableERPipeline(db=db, config=config).run_blocking()
    }
    merged = asyncio.run(AsyncERPipeline(db, config=config).run_blocking_concurrent(["exact"]))
    assert set(merged["merged_pairs"]) == sync_pairs
    assert merged["strategy_stats"]["exact"]["pairs_found"] == len(sync_pairs)
