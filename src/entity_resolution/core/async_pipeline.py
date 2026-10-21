"""
Async/streaming ER pipeline.

Runs ``ConfigurableERPipeline`` in a thread-pool executor so callers can:

- await the full pipeline without blocking the event loop;
- iterate pipeline stages as they complete (async generator);
- run several blocking strategies concurrently and merge their candidates.

It wraps the synchronous pipeline rather than reimplementing it, so an async
run does exactly what a sync run does. An earlier version reimplemented every
stage, and every stage was broken: it passed arguments the strategies and
services do not accept, called a method that does not exist, and read a config
attribute that does not exist. Its tests replaced all three stages with
patches, so nothing noticed.

Usage (await full run)::

    pipeline = AsyncERPipeline(db, config=cfg)
    results = await pipeline.run()          # same dict as ConfigurableERPipeline.run()

Usage (streaming stages)::

    async for stage_name, stage_result in pipeline.run_streaming():
        print(f"{stage_name}: {stage_result}")

Usage (concurrent blocking strategies)::

    candidates = await pipeline.run_blocking_concurrent(strategies=["exact", "bm25"])
"""
from __future__ import annotations

import asyncio
import copy
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Shared executor — reused across pipeline instances for efficiency
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="arango-er")

_DONE = object()


class AsyncERPipeline:
    """
    Async wrapper around ``ConfigurableERPipeline``.

    All database work runs in a thread-pool executor so it never blocks the
    event loop. Results are those of ``ConfigurableERPipeline.run()``.

    Parameters
    ----------
    db:
        An authenticated python-arango ``Database`` handle.
    config:
        An ``ERPipelineConfig`` instance.
    config_path:
        Path to a YAML/JSON config file (used if *config* is not provided).
    executor:
        Optional ``ThreadPoolExecutor``. Defaults to a module-level shared one.
    progress_callback:
        Optional ``async`` callable ``(stage: str, result: dict) -> None``
        called after each stage completes.
    pipeline:
        Optional pre-built ``ConfigurableERPipeline`` (or anything with the same
        ``run(on_progress=...)`` and ``run_blocking()`` methods). Built from
        *db* and the config when omitted.
    """

    def __init__(
        self,
        db,
        config=None,
        config_path: Optional[Union[str, Path]] = None,
        executor: Optional[ThreadPoolExecutor] = None,
        progress_callback=None,
        pipeline=None,
    ) -> None:
        from entity_resolution.config.er_config import ERPipelineConfig
        from entity_resolution.core.configurable_pipeline import ConfigurableERPipeline

        self.db = db
        self.executor = executor or _EXECUTOR
        self.progress_callback = progress_callback

        if config is not None:
            self.config = config
        elif config_path is not None:
            config_path = Path(config_path)
            if config_path.suffix.lower() == ".json":
                self.config = ERPipelineConfig.from_json(config_path)
            else:
                self.config = ERPipelineConfig.from_yaml(config_path)
        else:
            raise ValueError("Either config or config_path must be provided")

        self._pipeline = pipeline or ConfigurableERPipeline(db=db, config=self.config)
        self._results: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> Dict[str, Any]:
        """Run the full pipeline without blocking the event loop.

        Returns exactly what ``ConfigurableERPipeline.run()`` returns.
        """
        async for _stage, _result in self.run_streaming():
            pass
        assert self._results is not None
        return self._results

    async def run_streaming(self) -> AsyncIterator[Tuple[str, Dict[str, Any]]]:
        """Yield ``(stage_name, stage_result)`` as each pipeline stage completes.

        Stages arrive in the order the sync pipeline runs them (``blocking``,
        ``similarity``, ``edges``, ``clustering``, plus ``embedding`` and
        ``collective`` when configured). A failure in the pipeline is raised
        here, after the stages that completed have been yielded. A consumer
        that stops iterating early does not stop the run: the pipeline keeps
        going in its worker thread, because a thread cannot be cancelled.
        """
        loop = asyncio.get_running_loop()
        events: asyncio.Queue = asyncio.Queue()

        def on_progress(event: Dict[str, Any]) -> None:  # called in the worker thread
            loop.call_soon_threadsafe(events.put_nowait, event)

        def work() -> Dict[str, Any]:
            try:
                return self._pipeline.run(on_progress=on_progress)
            finally:
                loop.call_soon_threadsafe(events.put_nowait, _DONE)

        future = loop.run_in_executor(self.executor, work)
        while True:
            event = await events.get()
            if event is _DONE:
                break
            if event.get("type") != "stage_complete":
                continue
            stage, result = event["stage"], event.get("result") or {}
            if self.progress_callback:
                await self.progress_callback(stage, result)
            yield stage, result
        self._results = await future  # re-raises a pipeline failure

    async def run_blocking_concurrent(
        self, strategies: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Run several blocking strategies concurrently and merge their candidates.

        Each strategy runs through ``ConfigurableERPipeline.run_blocking()`` on a
        copy of the config with ``blocking.strategy`` replaced, so each behaves
        exactly as a configured run would. Defaults to the configured strategy.
        A failing strategy is reported in ``strategy_stats`` without failing
        the others.
        """
        from entity_resolution.config.er_config import BlockingConfig
        from entity_resolution.core.configurable_pipeline import ConfigurableERPipeline

        names = list(dict.fromkeys(strategies or [self.config.blocking.strategy]))
        unknown = [n for n in names if n not in BlockingConfig.VALID_STRATEGIES]
        if unknown:
            raise ValueError(
                f"unknown blocking strategies {unknown}; valid: {list(BlockingConfig.VALID_STRATEGIES)}"
            )

        def blocking_for(name: str) -> list:
            config = copy.deepcopy(self.config)
            config.blocking.strategy = name
            return ConfigurableERPipeline(db=self.db, config=config).run_blocking()

        loop = asyncio.get_running_loop()
        outcomes = await asyncio.gather(
            *(loop.run_in_executor(self.executor, blocking_for, name) for name in names),
            return_exceptions=True,
        )

        merged: set = set()
        strategy_stats: Dict[str, Any] = {}
        for name, outcome in zip(names, outcomes):
            if isinstance(outcome, BaseException):
                logger.warning("Blocking strategy '%s' failed: %s", name, outcome)
                strategy_stats[name] = {"error": str(outcome)}
                continue
            pairs = {_pair_key(candidate) for candidate in outcome}
            pairs.discard(None)
            merged.update(pairs)
            strategy_stats[name] = {"pairs_found": len(pairs)}

        return {
            "strategies_run": names,
            "strategy_stats": strategy_stats,
            "total_unique_pairs": len(merged),
            "merged_pairs": sorted(merged),
        }


def _pair_key(candidate: Any) -> Optional[Tuple[str, str]]:
    """An order-independent key for a candidate pair in any strategy's format."""
    if isinstance(candidate, dict):
        a, b = candidate.get("doc1_key"), candidate.get("doc2_key")
    elif isinstance(candidate, (list, tuple)) and len(candidate) >= 2:
        a, b = candidate[0], candidate[1]
    else:
        return None
    if a is None or b is None or a == b:
        return None
    a, b = str(a), str(b)
    return (a, b) if a < b else (b, a)
