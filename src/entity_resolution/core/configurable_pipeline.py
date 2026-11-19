"""
Configuration-driven ER pipeline.

Runs complete entity resolution pipelines from YAML/JSON configuration files.
"""

from typing import Callable, Dict, Any, Optional, Union
from datetime import datetime
from pathlib import Path
from arango.database import StandardDatabase
import logging
import os
import time

from ..config.er_config import ERPipelineConfig
from ..services.batch_similarity_service import BatchSimilarityService
from ..services.similarity_edge_service import SimilarityEdgeService
from ..services.wcc_clustering_service import WCCClusteringService
from ..services.address_er_service import AddressERService
from ..services.embedding_service import EmbeddingService
from ..services.onnx_embedding_backend import OnnxRuntimeEmbeddingBackend
from ..strategies import (
    CollectBlockingStrategy,
    BM25BlockingStrategy,
    VectorBlockingStrategy,
    LSHBlockingStrategy,
    GraphEmbeddingBlockingStrategy,
)


class ConfigurableERPipeline:
    """
    ER pipeline that runs from configuration.
    
    This class orchestrates a complete ER pipeline based on configuration,
    automatically instantiating and configuring services.
    
    Example:
        ```python
        from entity_resolution.core import ConfigurableERPipeline
        
        pipeline = ConfigurableERPipeline(
            db=db,
            config_path='er_config.yaml'
        )
        
        results = pipeline.run()
        
        print(f"Blocks: {results['blocking']['blocks_found']}")
        print(f"Matches: {results['similarity']['matches_found']}")
        print(f"Clusters: {results['clustering']['clusters_found']}")
        ```
    """
    
    def __init__(
        self,
        db: StandardDatabase,
        config: Optional[ERPipelineConfig] = None,
        config_path: Optional[Union[str, Path]] = None
    ):
        """
        Initialize configurable ER pipeline.
        
        Args:
            db: ArangoDB database connection
            config: ERPipelineConfig instance (if provided, config_path is ignored)
            config_path: Path to YAML/JSON configuration file
        
        Raises:
            ValueError: If neither config nor config_path provided
            FileNotFoundError: If config_path doesn't exist
        """
        if config is None and config_path is None:
            raise ValueError("Either config or config_path must be provided")
        
        self.db = db
        
        # Load configuration
        if config is not None:
            self.config = config
        else:
            config_path = Path(config_path)
            if config_path.suffix.lower() == '.json':
                self.config = ERPipelineConfig.from_json(config_path)
            else:
                self.config = ERPipelineConfig.from_yaml(config_path)
        
        # Validate configuration
        errors = self.config.validate()
        if errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
        
        # Initialize logger
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._active_learning_stats: Dict[str, Any] = {
            'enabled': bool(getattr(self.config, 'active_learning', None) and self.config.active_learning.enabled),
            'pairs_reviewed': 0,
            'llm_calls': 0,
            'score_overrides': 0,
            'feedback_collection': None,
        }
        self._embedding_preflight_stats: Optional[Dict[str, Any]] = None
        #: Populated when similarity.auto_threshold is enabled — the chosen
        #: operating point travels with the results that were produced under it.
        self._auto_threshold_selection: Optional[Dict[str, Any]] = None

    def run(
        self,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Run complete ER pipeline based on configuration.
        
        Pipeline phases:
        1. Setup (if needed, e.g., for address ER)
        2. Blocking (based on config.blocking)
        3. Similarity (based on config.similarity)
        4. Edge creation (based on config.edges)
        5. Clustering (based on config.clustering)
        
        Args:
            on_progress: Optional callback invoked at stage transitions with
                a dict containing ``type``, ``stage``, and ``timestamp`` keys.
        
        Returns:
            Results dictionary with metrics for each phase:
            {
                'blocking': {
                    'candidate_pairs': int,
                    'runtime_seconds': float
                },
                'similarity': {
                    'matches_found': int,
                    'pairs_processed': int,
                    'runtime_seconds': float
                },
                'edges': {
                    'edges_created': int,
                    'runtime_seconds': float
                },
                'clustering': {
                    'clusters_found': int,
                    'runtime_seconds': float
                },
                'total_runtime_seconds': float
            }
        """
        start_time = time.time()
        results = {
            'embedding': {},
            'blocking': {},
            'similarity': {},
            'edges': {},
            'clustering': {},
            'collective': {},
            'total_runtime_seconds': 0.0
        }
        
        self.logger.info("=" * 80)
        self.logger.info("CONFIGURABLE ER PIPELINE")
        self.logger.info("=" * 80)
        self.logger.info(f"Entity Type: {self.config.entity_type}")
        self.logger.info(f"Collection: {self.config.collection_name}")
        self.logger.info("")

        # Phase 0a: apply pending schema migrations (idempotent). Disable with
        # ER_NO_MIGRATE=1. Best-effort — a migration failure is logged but does
        # not abort the run.
        self._maybe_migrate_schema(results)

        # Optional phase 0: resolve embedding runtime/provider from config.
        if self.config.embedding:
            if on_progress:
                on_progress({"type": "stage_start", "stage": "embedding", "timestamp": datetime.utcnow().isoformat()})
            self.logger.info("Phase 0: Embedding runtime setup...")
            embedding_start = time.time()
            results['embedding'] = self._setup_embedding_runtime()
            setup_seconds = time.time() - embedding_start
            results['embedding']['runtime_seconds'] = round(setup_seconds, 2)
            results['embedding']['setup_latency_ms'] = round(setup_seconds * 1000, 1)
            self.logger.info(
                "[OK] Embedding runtime=%s provider=%s",
                results['embedding'].get('runtime'),
                results['embedding'].get('resolved_provider', results['embedding'].get('resolved_device')),
            )
            if on_progress:
                on_progress({"type": "stage_complete", "stage": "embedding", "result": results['embedding'], "timestamp": datetime.utcnow().isoformat()})
        else:
            results['embedding'] = {
                'enabled': False,
                'runtime_seconds': 0.0,
            }
        
        # Special handling for address ER
        if self.config.entity_type == 'address':
            return self._run_address_er(results, start_time)
        
        # Standard ER pipeline
        # Phase 1: Blocking
        if on_progress:
            on_progress({"type": "stage_start", "stage": "blocking", "timestamp": datetime.utcnow().isoformat()})
        self.logger.info("Phase 1: Blocking...")
        blocking_start = time.time()
        candidate_pairs = self.run_blocking()
        blocking_time = time.time() - blocking_start
        
        results['blocking'] = {
            'candidate_pairs': len(candidate_pairs),
            'runtime_seconds': round(blocking_time, 2)
        }
        if self._embedding_preflight_stats is not None:
            results['blocking']['embedding_preflight'] = self._embedding_preflight_stats
            results['embedding']['preflight'] = self._embedding_preflight_stats
        self.logger.info(f"[OK] Found {len(candidate_pairs):,} candidate pairs")
        if on_progress:
            on_progress({"type": "stage_complete", "stage": "blocking", "result": results['blocking'], "timestamp": datetime.utcnow().isoformat()})
        
        # Phase 1b: Collective resolution (optional, plan 3.2).
        # Honouring collective.enabled here is what makes the config flag real:
        # it was previously parsed and validated but never consulted by run(),
        # so users who set it got a silently ignored stage. Reported as its own
        # results key rather than replacing clustering, so the standard
        # score -> edge -> cluster path stays authoritative for persistence.
        collective_cfg = getattr(self.config, "collective", None)
        if collective_cfg is not None and collective_cfg.enabled and candidate_pairs:
            if on_progress:
                on_progress({"type": "stage_start", "stage": "collective", "timestamp": datetime.utcnow().isoformat()})
            self.logger.info("Phase 1b: Collective resolution...")
            collective_start = time.time()
            collective_result = self.run_collective(candidate_pairs)
            collective_time = time.time() - collective_start
            if collective_result is None:
                # run_collective already logged why (no graph_context).
                results['collective'] = {
                    'enabled': True,
                    'applied': False,
                    'reason': 'requires similarity.graph_context',
                    'runtime_seconds': round(collective_time, 2),
                }
            else:
                results['collective'] = {
                    'enabled': True,
                    'applied': True,
                    'rounds': collective_result.get('rounds'),
                    'converged': collective_result.get('converged'),
                    'oscillated': collective_result.get('oscillated'),
                    'clusters_found': collective_result.get('num_clusters'),
                    'runtime_seconds': round(collective_time, 2),
                }
            if on_progress:
                on_progress({"type": "stage_complete", "stage": "collective", "result": results['collective'], "timestamp": datetime.utcnow().isoformat()})
        else:
            results['collective'] = {
                'enabled': bool(collective_cfg and collective_cfg.enabled),
                'applied': False,
                'runtime_seconds': 0.0,
            }

        # Phase 2: Similarity
        if on_progress:
            on_progress({"type": "stage_start", "stage": "similarity", "timestamp": datetime.utcnow().isoformat()})
        if candidate_pairs and self.config.similarity:
            self.logger.info("Phase 2: Similarity computation...")
            similarity_start = time.time()
            matches = self.run_similarity(candidate_pairs)
            similarity_time = time.time() - similarity_start
            
            results['similarity'] = {
                'matches_found': len(matches),
                'pairs_processed': len(candidate_pairs),
                'runtime_seconds': round(similarity_time, 2),
                'active_learning': self._active_learning_stats.copy(),
                'auto_threshold': self._auto_threshold_selection,
            }
            self.logger.info(f"[OK] Found {len(matches):,} matches")
        else:
            matches = []
            results['similarity'] = {
                'matches_found': 0,
                'pairs_processed': 0,
                'runtime_seconds': 0.0,
                'active_learning': self._active_learning_stats.copy(),
            }
        if on_progress:
            on_progress({"type": "stage_complete", "stage": "similarity", "result": results['similarity'], "timestamp": datetime.utcnow().isoformat()})
        
        # Phase 3: Edge Creation
        if on_progress:
            on_progress({"type": "stage_start", "stage": "edges", "timestamp": datetime.utcnow().isoformat()})
        if matches:
            self.logger.info("Phase 3: Edge creation...")
            edge_start = time.time()
            edges_created = self.run_edge_creation(matches)
            edge_time = time.time() - edge_start
            
            results['edges'] = {
                'edges_created': edges_created,
                'runtime_seconds': round(edge_time, 2)
            }
            self.logger.info(f"[OK] Created {edges_created:,} edges")
        else:
            results['edges'] = {
                'edges_created': 0,
                'runtime_seconds': 0.0
            }
        if on_progress:
            on_progress({"type": "stage_complete", "stage": "edges", "result": results['edges'], "timestamp": datetime.utcnow().isoformat()})

        # Phase 4: Clustering — only run when edges actually exist
        if on_progress:
            on_progress({"type": "stage_start", "stage": "clustering", "timestamp": datetime.utcnow().isoformat()})
        edges_created = results.get('edges', {}).get('edges_created', 0)
        if self.config.clustering.store_results and edges_created > 0:
            self.logger.info("Phase 4: Clustering...")
            cluster_start = time.time()
            clusters = self.run_clustering()
            cluster_time = time.time() - cluster_start

            results['clustering'] = {
                'clusters_found': len(clusters),
                'runtime_seconds': round(cluster_time, 2)
            }
            self.logger.info(f"[OK] Found {len(clusters):,} clusters")
        else:
            results['clustering'] = {
                'clusters_found': 0,
                'runtime_seconds': 0.0
            }
        if on_progress:
            on_progress({"type": "stage_complete", "stage": "clustering", "result": results['clustering'], "timestamp": datetime.utcnow().isoformat()})
        
        results['total_runtime_seconds'] = round(time.time() - start_time, 2)
        
        # Summary
        self.logger.info("")
        self.logger.info("=" * 80)
        self.logger.info("SUMMARY")
        self.logger.info("=" * 80)
        if results['embedding'].get('enabled'):
            self.logger.info(
                "Embedding Runtime: %s",
                results['embedding'].get('runtime'),
            )
        self.logger.info(f"Candidate Pairs: {results['blocking']['candidate_pairs']:,}")
        self.logger.info(f"Matches Found: {results['similarity']['matches_found']:,}")
        self.logger.info(f"Edges Created: {results['edges']['edges_created']:,}")
        self.logger.info(f"Clusters Found: {results['clustering']['clusters_found']:,}")
        self.logger.info(f"Total Runtime: {results['total_runtime_seconds']:.2f}s")

        if on_progress:
            on_progress({
                "type": "pipeline_complete",
                "total_runtime_seconds": results['total_runtime_seconds'],
                "summary": {
                    "candidate_pairs": results['blocking']['candidate_pairs'],
                    "matches_found": results['similarity']['matches_found'],
                    "edges_created": results['edges']['edges_created'],
                    "clusters_found": results['clustering']['clusters_found'],
                },
                "timestamp": datetime.utcnow().isoformat(),
            })
        
        return results

    def _maybe_migrate_schema(self, results: Dict[str, Any]) -> None:
        """Apply pending ER schema migrations at startup unless disabled.

        Controlled by the ``ER_NO_MIGRATE`` environment variable. Failures are
        logged and recorded in ``results['schema']`` but never abort the run.
        """
        import os

        if os.getenv("ER_NO_MIGRATE", "").strip() in ("1", "true", "True"):
            results['schema'] = {"migrated": False, "reason": "disabled via ER_NO_MIGRATE"}
            return
        try:
            from ..migrations import MigrationRunner

            runner = MigrationRunner(self.db)
            outcome = runner.migrate()
            results['schema'] = outcome
            if outcome["applied"]:
                self.logger.info(
                    "Applied schema migrations %s (now v%s)",
                    outcome["applied"], outcome["to_version"],
                )
        except Exception as exc:  # never block the pipeline on migration issues
            self.logger.warning("Schema migration skipped: %s", exc)
            results['schema'] = {"migrated": False, "error": str(exc)}

    def _setup_embedding_runtime(self) -> Dict[str, Any]:
        """
        Resolve and initialize embedding runtime selection from config.

        This Phase 0 setup validates runtime/provider selection and captures
        resolved runtime metadata for observability. It intentionally does not
        generate embeddings yet.
        """
        embedding_cfg = self.config.embedding
        if embedding_cfg is None:
            return {'enabled': False}

        if embedding_cfg.runtime == 'pytorch':
            service = EmbeddingService(
                model_name=embedding_cfg.model_name,
                runtime=embedding_cfg.runtime,
                device=embedding_cfg.device,
                provider=embedding_cfg.provider,
                provider_options=embedding_cfg.provider_options,
                onnx_model_path=embedding_cfg.onnx_model_path,
                embedding_field=embedding_cfg.embedding_field,
                multi_resolution_mode=embedding_cfg.multi_resolution_mode,
                coarse_model_name=embedding_cfg.coarse_model_name,
                fine_model_name=embedding_cfg.fine_model_name,
                embedding_field_coarse=embedding_cfg.embedding_field_coarse,
                embedding_field_fine=embedding_cfg.embedding_field_fine,
                profile=embedding_cfg.profile,
                batch_size=embedding_cfg.batch_size,
            )
            self._embedding_runtime = service
            result = {
                'enabled': True,
                'runtime': 'pytorch',
                'model_name': embedding_cfg.model_name,
                'requested_device': embedding_cfg.device,
                'resolved_device': service.device,
                'requested_provider': embedding_cfg.provider,
                'resolved_provider': service.resolved_provider,
                'batch_size': embedding_cfg.batch_size,
                'health': service.get_runtime_health(),
                'telemetry': {
                    'provider_used': service.resolved_provider,
                    'device_used': service.device,
                    'fallback_count': 1 if embedding_cfg.device == 'auto' and service.device == 'cpu' else 0,
                },
            }
            self._enforce_embedding_startup_mode(result, embedding_cfg.startup_mode)
            return result

        if embedding_cfg.runtime == 'onnxruntime':
            backend = OnnxRuntimeEmbeddingBackend(
                model_path=embedding_cfg.onnx_model_path or '',
                provider=embedding_cfg.provider,
                provider_options=embedding_cfg.provider_options,
                fallback_to_cpu=True,
                coreml_use_basic_optimizations=embedding_cfg.coreml_use_basic_optimizations,
                coreml_warmup_runs=embedding_cfg.coreml_warmup_runs,
                coreml_max_p95_latency_ms=embedding_cfg.coreml_max_p95_latency_ms,
                coreml_warmup_batch_size=embedding_cfg.coreml_warmup_batch_size,
                coreml_warmup_seq_len=embedding_cfg.coreml_warmup_seq_len,
            )
            backend.load_model()
            resolved_provider = backend.resolved_provider
            self._embedding_runtime = backend
            result = {
                'enabled': True,
                'runtime': 'onnxruntime',
                'model_name': embedding_cfg.model_name,
                'onnx_model_path': embedding_cfg.onnx_model_path,
                'requested_provider': embedding_cfg.provider,
                'resolved_provider': resolved_provider,
                'provider_options': embedding_cfg.provider_options,
                'batch_size': embedding_cfg.batch_size,
                'health': backend.health(),
                'telemetry': {
                    'provider_used': backend.resolved_provider,
                    'fallback_count': backend.fallback_count,
                    'fallback_occurred': backend.fallback_count > 0,
                    'last_fallback_reason': backend.last_fallback_reason,
                    'coreml_warmup_p95_latency_ms': backend.last_warmup_p95_latency_ms,
                    'coreml_max_p95_latency_ms': embedding_cfg.coreml_max_p95_latency_ms,
                    'session_optimization_level': backend.session_optimization_level,
                },
            }
            self._enforce_embedding_startup_mode(result, embedding_cfg.startup_mode)
            return result

        raise ValueError(f"Unsupported embedding runtime: {embedding_cfg.runtime}")

    def _enforce_embedding_startup_mode(self, setup: Dict[str, Any], startup_mode: str) -> None:
        """
        Enforce strict/permissive startup policy for embedding runtime setup.
        """
        if startup_mode != 'strict':
            return

        runtime = setup.get('runtime')
        health = setup.get('health', {})
        if runtime == 'pytorch':
            requested_device = setup.get('requested_device')
            if requested_device == 'cuda' and not health.get('cuda_available', False):
                raise RuntimeError(
                    "Embedding runtime strict startup failed: requested device 'cuda' "
                    "is not available on this host"
                )
            if requested_device == 'mps' and not health.get('mps_available', False):
                raise RuntimeError(
                    "Embedding runtime strict startup failed: requested device 'mps' "
                    "is not available on this host"
                )
            return

        if runtime == 'onnxruntime':
            requested_provider = setup.get('requested_provider')
            available = set(health.get('available_ort_providers', []))
            required_provider_name = {
                'cpu': 'CPUExecutionProvider',
                'coreml': 'CoreMLExecutionProvider',
                'cuda': 'CUDAExecutionProvider',
                'tensorrt': 'TensorrtExecutionProvider',
            }.get(requested_provider)
            if required_provider_name and required_provider_name not in available:
                raise RuntimeError(
                    "Embedding runtime strict startup failed: requested provider "
                    f"'{requested_provider}' is not available. "
                    f"Available providers: {sorted(available)}"
                )

    def get_embedding_runtime_health(self, startup_mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Public helper for CLI/MCP to inspect embedding runtime diagnostics.
        """
        setup_start = time.time()
        embedding_cfg = self.config.embedding
        if startup_mode is not None:
            if embedding_cfg is None:
                return {'enabled': False, 'reason': 'embedding config not provided'}
            if startup_mode not in ('permissive', 'strict'):
                raise ValueError(
                    "startup_mode override must be 'permissive' or 'strict', "
                    f"got: {startup_mode}"
                )
            original_mode = embedding_cfg.startup_mode
            embedding_cfg.startup_mode = startup_mode
            try:
                setup = self._setup_embedding_runtime()
            finally:
                embedding_cfg.startup_mode = original_mode
        else:
            setup = self._setup_embedding_runtime()
        setup_latency_ms = round((time.time() - setup_start) * 1000, 1)
        if not setup.get('enabled'):
            return {'enabled': False, 'reason': 'embedding config not provided'}
        return {
            'enabled': True,
            'runtime': setup.get('runtime'),
            'model_name': setup.get('model_name'),
            'requested_device': setup.get('requested_device'),
            'resolved_device': setup.get('resolved_device'),
            'requested_provider': setup.get('requested_provider'),
            'resolved_provider': setup.get('resolved_provider'),
            'health': setup.get('health', {}),
            'telemetry': setup.get('telemetry', {}),
            'setup_latency_ms': setup_latency_ms,
        }
    
    def _run_address_er(
        self,
        results: Dict[str, Any],
        start_time: float
    ) -> Dict[str, Any]:
        """Run address-specific ER pipeline."""
        # Use AddressERService for address ER
        address_service = AddressERService(
            db=self.db,
            collection=self.config.collection_name,
            edge_collection=self.config.edge_collection,
            config={
                'max_block_size': self.config.blocking.max_block_size,
                'min_bm25_score': 2.0,
                'batch_size': self.config.similarity.batch_size
            }
        )
        
        # Setup infrastructure
        address_service.setup_infrastructure()
        
        # Run address ER
        address_results = address_service.run(
            max_block_size=self.config.blocking.max_block_size,
            create_edges=True,
            cluster=self.config.clustering.store_results,
            min_cluster_size=self.config.clustering.min_cluster_size
        )
        
        # Map results to standard format
        results['blocking'] = {
            'blocks_found': address_results['blocks_found'],
            'addresses_matched': address_results['addresses_matched'],
            'runtime_seconds': 0.0  # Included in total
        }
        results['similarity'] = {
            'matches_found': address_results['addresses_matched'],
            'runtime_seconds': 0.0
        }
        results['edges'] = {
            'edges_created': address_results['edges_created'],
            'runtime_seconds': 0.0
        }
        results['clustering'] = {
            'clusters_found': address_results.get('clusters_found', 0),
            'runtime_seconds': 0.0
        }
        results['total_runtime_seconds'] = address_results['runtime_seconds']
        
        return results
    
    def run_blocking(self) -> list:
        """Run blocking phase based on configuration."""
        strategy = self.config.blocking.strategy
        self._embedding_preflight_stats = None
        
        if strategy == 'exact':
            # Use CollectBlockingStrategy
            blocking_fields, computed_fields = self._get_blocking_fields()
            blocking_strategy = CollectBlockingStrategy(
                db=self.db,
                collection=self.config.collection_name,
                blocking_fields=blocking_fields,
                max_block_size=self.config.blocking.max_block_size,
                min_block_size=self.config.blocking.min_block_size,
                computed_fields=computed_fields or None,
                allow_unsafe_expressions=self.config.blocking.allow_unsafe_expressions,
            )
            return list(blocking_strategy.generate_candidates())
        
        elif strategy in ('bm25', 'arangosearch'):
            # Note: 'arangosearch' is a deprecated alias for 'bm25'.
            return self._run_bm25_blocking()

        elif strategy == 'vector':
            embedding_field = self.config.blocking.embedding_field
            if not embedding_field and self.config.embedding:
                embedding_field = self.config.embedding.embedding_field

            blocking_strategy = VectorBlockingStrategy(
                db=self.db,
                collection=self.config.collection_name,
                embedding_field=embedding_field or 'embedding_vector',
                similarity_threshold=self.config.blocking.similarity_threshold,
                limit_per_entity=self.config.blocking.limit_per_entity,
                blocking_field=self.config.blocking.blocking_field,
            )
            self._embedding_preflight_stats = blocking_strategy.check_embeddings_exist()
            return list(blocking_strategy.generate_candidates())

        elif strategy == 'lsh':
            embedding_field = self.config.blocking.embedding_field
            if not embedding_field and self.config.embedding:
                embedding_field = self.config.embedding.embedding_field

            blocking_strategy = LSHBlockingStrategy(
                db=self.db,
                collection=self.config.collection_name,
                embedding_field=embedding_field or 'embedding_vector',
                num_hash_tables=self.config.blocking.num_hash_tables,
                num_hyperplanes=self.config.blocking.num_hyperplanes,
                random_seed=self.config.blocking.random_seed,
                blocking_field=self.config.blocking.blocking_field,
            )
            self._embedding_preflight_stats = blocking_strategy.check_embeddings_exist()
            return list(blocking_strategy.generate_candidates())

        elif strategy == 'graph_embedding':
            embedding_field = self.config.blocking.embedding_field or 'node_embedding'
            blocking_strategy = GraphEmbeddingBlockingStrategy(
                db=self.db,
                collection=self.config.collection_name,
                edge_collection=self.config.blocking.edge_collection,
                embedding_field=embedding_field,
                similarity_threshold=self.config.blocking.similarity_threshold,
                limit_per_entity=self.config.blocking.limit_per_entity,
                blocking_field=self.config.blocking.blocking_field,
                node2vec_params=self.config.blocking.node2vec_params,
                create_vector_index=self.config.blocking.create_vector_index,
            )
            return list(blocking_strategy.generate_candidates())

        else:
            self.logger.warning(f"Unknown blocking strategy: {strategy}")
            return []


    def _run_bm25_blocking(self) -> list:
        """BM25 blocking, with the generic ``blocking.fields`` list read safely.

        ``blocking.fields`` means "block on these together" under ``exact``.
        BM25 searches ONE field and may filter on one more, so the list does not
        map onto it, and the mapping used to be silent and wrong
        (arango-solutions-org/arango-entity-resolution#3):

        - ``fields[1]`` became ``blocking_field``, an exact-equality pre-filter
          that dropped every pair differing in that field. It is now taken only
          from an explicit ``blocking.blocking_field``; other entries are ignored
          with a warning.
        - A computed field's expression was discarded, so BM25 searched an
          attribute that does not exist and found nothing. The view indexes
          stored attributes only, so that is now an error.
        - Zero candidates finished fast and looked like "no duplicates". On a
          non-empty collection it now logs a warning naming what was searched.
        """
        blocking = self.config.blocking
        generic_fields, computed_fields = self._get_blocking_fields()

        search_field = blocking.search_field or (generic_fields[0] if generic_fields else None)
        if not search_field:
            raise ValueError(
                "BM25 blocking strategy requires a search_field. "
                "Set blocking.search_field in your config, or provide at least "
                "one entry in blocking.fields."
            )
        blocking_field = blocking.blocking_field

        for role, name in (("search_field", search_field), ("blocking_field", blocking_field)):
            if name and name in computed_fields:
                raise ValueError(
                    f"BM25 blocking cannot use computed field {name!r} as its {role}: "
                    "the ArangoSearch view indexes stored document attributes, and the "
                    f"expression {computed_fields[name]!r} exists only in generated "
                    "blocking queries. Store the value as an attribute, or name a "
                    f"stored attribute in blocking.{role}."
                )

        if not blocking.search_field:
            self.logger.warning(
                "BM25 blocking: blocking.search_field is not set; searching %r, "
                "the first entry of blocking.fields.", search_field,
            )
        ignored = [f for f in generic_fields if f not in (search_field, blocking_field)]
        if ignored:
            self.logger.warning(
                "BM25 blocking ignores blocking.fields entries %s: it searches one "
                "field and filters on at most one. Set blocking.blocking_field to "
                "restrict candidates to records with an equal value in a field.",
                ignored,
            )

        search_view = f"{self.config.collection_name}_search"
        candidates = list(BM25BlockingStrategy(
            db=self.db,
            collection=self.config.collection_name,
            search_view=search_view,
            search_field=search_field,
            blocking_field=blocking_field,
        ).generate_candidates())

        if not candidates:
            try:
                records = self.db.collection(self.config.collection_name).count()
            except Exception:  # count is diagnostic only; never fail blocking on it
                records = None
            if records:
                self.logger.warning(
                    "BM25 blocking returned zero candidate pairs from %d records "
                    "(view %r, search_field %r, blocking_field %r). That usually "
                    "means a misconfiguration, not an absence of duplicates: check "
                    "that the view indexes the field with its analyzer.",
                    records, search_view, search_field, blocking_field,
                )
        return candidates

    def _get_blocking_fields(self) -> tuple[list, dict]:
        """
        Extract blocking field names (and optional computed fields) from config.

        Delegates to ``BlockingConfig.parse_fields()`` (H3 — single canonical
        implementation shared with ERPipelineConfig; no local duplication).

        Returns:
            (field_names, computed_fields)
        """
        return self.config.blocking.parse_fields()

    
    def _effective_field_weights(self) -> Dict[str, float]:
        """Configured field weights, or equal weights across blocking fields."""
        field_weights = self.config.similarity.field_weights
        if not field_weights:
            blocking_field_names, _ = self.config.blocking.parse_fields()
            if blocking_field_names:
                weight = 1.0 / len(blocking_field_names)
                field_weights = {f: weight for f in blocking_field_names}
        return field_weights

    def build_similarity_service(self) -> BatchSimilarityService:
        """Construct the BatchSimilarityService from config (shared by run + estimate).

        When ``similarity.scoring_method == 'fellegi_sunter'``, loads the latest
        EM-learned m/u from ``er_model_params`` and builds an FS scorer; falls
        back to the weighted heuristic (with a warning) if no model exists yet.
        """
        scoring_method = getattr(self.config.similarity, "scoring_method", "weighted_heuristic")
        fs_scorer = None
        if scoring_method == "fellegi_sunter":
            fs_scorer = self._load_fs_scorer()
            if fs_scorer is None:
                self.logger.warning(
                    "scoring_method='fellegi_sunter' but no model parameters found in "
                    "er_model_params; run `arango-er estimate` first. Falling back to "
                    "weighted_heuristic for this run."
                )
                scoring_method = "weighted_heuristic"

        return BatchSimilarityService(
            db=self.db,
            collection=self.config.collection_name,
            field_weights=self._effective_field_weights(),
            similarity_algorithm=self.config.similarity.algorithm,
            batch_size=self.config.similarity.batch_size,
            field_transformers=getattr(self.config.similarity, "transformers", {}),
            field_algorithms=getattr(self.config.similarity, "field_algorithms", None) or None,
            scoring_method=scoring_method,
            fs_scorer=fs_scorer,
            graph_context=self._build_graph_context(),
        )

    def run_collective(self, candidate_pairs: list):
        """Iterative collective resolution (plan 3.2).

        Requires ``collective.enabled`` and a ``similarity.graph_context`` (the
        lift comes from merges transferring relationships). Returns the resolver
        result (``clusters``, ``rounds``, ``converged``, ...), or ``None`` when
        not applicable.
        """
        cfg = getattr(self.config, "collective", None)
        if not (cfg and cfg.enabled):
            return None
        graph_context = self._build_graph_context()
        if graph_context is None:
            self.logger.warning(
                "collective.enabled but no similarity.graph_context configured; skipping"
            )
            return None

        from .collective_resolver import CollectiveResolver, connected_components

        sim = self.build_similarity_service()
        pair_tuples = [
            (p["doc1_key"], p["doc2_key"]) if isinstance(p, dict) else tuple(p)
            for p in candidate_pairs
        ]
        keys = set()
        for a, b in pair_tuples:
            keys.add(a)
            keys.add(b)
        base_cache = graph_context.batch_fetch_neighbor_sets(keys)

        def score_fn(pairs, cache):
            return sim.compute_similarities(
                list(pairs), threshold=0.0, return_all=True, neighbor_cache=cache
            )

        resolver = CollectiveResolver(
            score_pairs=score_fn,
            cluster=connected_components,
            base_neighbor_cache=base_cache,
            threshold=self.config.similarity.threshold,
            max_rounds=cfg.max_rounds,
        )
        result = resolver.resolve(pair_tuples)
        self.logger.info(
            "collective resolution: %d rounds, converged=%s, %d clusters",
            result["rounds"], result["converged"], result["num_clusters"],
        )
        return result

    def _build_graph_context(self):
        """Construct a GraphContextSimilarity when similarity.graph_context is enabled (plan 3.1)."""
        gc = getattr(self.config.similarity, "graph_context", None)
        if gc is None or not gc.enabled:
            return None
        from ..similarity.graph_context import GraphContextSimilarity

        return GraphContextSimilarity(
            db=self.db,
            vertex_collection=self.config.collection_name,
            edge_collections=gc.edge_collections,
            max_hops=gc.max_hops,
            features=gc.features,
            count_saturation=gc.count_saturation,
        )

    def _graph_feature_names(self) -> list:
        """Namespaced graph feature field names when graph context is enabled."""
        gc = getattr(self.config.similarity, "graph_context", None)
        if gc is None or not gc.enabled:
            return []
        from ..similarity.graph_context import FEATURE_PREFIX

        return [FEATURE_PREFIX + f for f in gc.features]

    def _effective_scoring_field_names(self) -> list:
        """Attribute fields + graph feature fields — the FS/EM comparison vector."""
        return list(self._effective_field_weights().keys()) + self._graph_feature_names()

    def build_model_parameter_estimator(self, similarity_service=None):
        """Construct the estimator from the same comparison config used at runtime."""
        from ..learning import ModelParameterEstimator

        cfg = self.config.similarity
        return ModelParameterEstimator(
            db=self.db,
            similarity_service=similarity_service,
            edge_collection=self.config.edge_collection,
            field_names=self._effective_scoring_field_names(),
            agreement_thresholds=getattr(cfg, "agreement_thresholds", {}),
            algorithm=cfg.algorithm,
            comparison_levels=getattr(cfg, "comparison_levels", None),
        )

    def _load_fs_scorer(self):
        """Build a FellegiSunterScorer from the latest persisted model params.

        Models are looked up by configuration hash (field set, agreement
        thresholds, algorithm). That strictness is deliberate: m/u are estimated
        under a specific binarisation, so applying them to comparisons made a
        different way is statistically invalid. ``arango-er estimate`` builds its
        estimator through the same :meth:`build_model_parameter_estimator`, so a
        train-then-run cycle matches by construction — a mismatch means the
        config changed after training.
        """
        from ..learning.fellegi_sunter_scorer import FellegiSunterScorer

        estimator = self.build_model_parameter_estimator()
        chash = estimator.configuration_hash()
        doc = estimator.load_latest(chash)
        if not doc:
            self._log_missing_fs_model(estimator, chash)
            return None
        cfg = self.config.similarity
        # from_model_doc reads comparison_levels from the document itself. Levels
        # must come from the MODEL rather than the config: the document carries
        # the learned per-level m/u alongside the bands they were estimated
        # against, whereas the config only describes structure. Pairing
        # configured bands with probabilities learned under different ones is
        # exactly what the config hash exists to prevent.
        return FellegiSunterScorer.from_model_doc(
            doc,
            match_prior=getattr(cfg, "match_prior", None),
            term_frequencies=estimator.load_term_frequencies(),
        )

    def _log_missing_fs_model(self, estimator, chash: str) -> None:
        """Explain WHY no model matched, distinguishing the two causes.

        "Never trained" and "trained under a different configuration" need
        different fixes, and conflating them sends a user who already ran
        ``arango-er estimate`` off to run it again. When models exist, the
        stored configurations are listed so the difference is visible.
        """
        try:
            others = estimator.list_model_configurations()
        except Exception:  # pragma: no cover - diagnostics must never break a run
            others = []

        if not others:
            self.logger.warning(
                "scoring_method='fellegi_sunter' but no model parameters exist in "
                "'%s'. Run `arango-er estimate --config <your config>` to train "
                "one. Falling back to weighted_heuristic for this run.",
                estimator.model_collection,
            )
            return

        self.logger.warning(
            "scoring_method='fellegi_sunter' but no model matches this "
            "configuration (hash %s: fields=%s, thresholds=%s, algorithm=%s). "
            "%d model(s) are stored under different configurations: %s. "
            "Parameters are only valid for the comparison settings they were "
            "trained under, so they are not reused. Re-run `arango-er estimate` "
            "with the current config. Falling back to weighted_heuristic.",
            chash,
            estimator.field_names,
            estimator._effective_thresholds(),
            estimator.algorithm,
            len(others),
            others,
        )

    def run_similarity(self, candidate_pairs: list) -> list:
        """Run similarity phase based on configuration."""
        if not candidate_pairs:
            return []

        similarity_service = self.build_similarity_service()

        # BatchSimilarityService.compute_similarities expects (key1, key2) tuples;
        # blocking strategies return rich dicts — normalise at the boundary.
        if candidate_pairs and isinstance(candidate_pairs[0], dict):
            pair_tuples = [(p["doc1_key"], p["doc2_key"]) for p in candidate_pairs]
        else:
            pair_tuples = candidate_pairs

        active_learning_cfg = getattr(self.config, 'active_learning', None)
        if active_learning_cfg and active_learning_cfg.enabled:
            return self._run_similarity_with_active_learning(similarity_service, pair_tuples)

        if getattr(self.config.similarity, 'auto_threshold', False):
            return self._run_similarity_with_auto_threshold(
                similarity_service, pair_tuples
            )

        matches = similarity_service.compute_similarities(
            candidate_pairs=pair_tuples,
            threshold=self.config.similarity.threshold
        )

        return matches

    def _run_similarity_with_auto_threshold(
        self,
        similarity_service: BatchSimilarityService,
        pair_tuples: list[tuple[str, str]],
    ) -> list:
        """Score everything, infer the cutoff from the scores, then filter.

        Requires scoring at threshold 0 first: the threshold is derived from the
        shape of the score distribution, so the distribution has to exist before
        a cutoff can be chosen. That costs nothing extra in scoring work — the
        same pairs are scored either way — only in memory, since all scored pairs
        are held rather than only the passing ones.

        When the scores carry no evidence for a cutoff (not meaningfully
        bimodal), the configured ``threshold`` is kept and a warning is emitted.
        Inference can therefore only improve on the constant where there is
        support for doing so; it never silently substitutes a guess.
        """
        from ..learning.threshold_selection import select_threshold_unsupervised

        sim_cfg = self.config.similarity
        scored = similarity_service.compute_similarities(
            candidate_pairs=pair_tuples,
            threshold=0.0,
            return_all=True,
        )
        selection = select_threshold_unsupervised(
            [row[2] for row in scored],
            min_valley_depth=getattr(
                sim_cfg, 'auto_threshold_min_valley_depth', 0.15
            ),
            fallback=sim_cfg.threshold,
        )
        self._auto_threshold_selection = selection.to_dict()

        if selection.warning:
            self.logger.warning(
                "auto_threshold: keeping configured threshold %.3f — %s",
                sim_cfg.threshold, selection.warning,
            )
        else:
            self.logger.info(
                "auto_threshold: selected %.4f (configured was %.3f, "
                "valley depth %.3f over %d pairs)",
                selection.threshold, sim_cfg.threshold,
                selection.diagnostics.get('valley_depth', 0.0),
                selection.diagnostics.get('sample_size', 0),
            )

        return [row for row in scored if row[2] >= selection.threshold]

    def _run_similarity_with_active_learning(
        self,
        similarity_service: BatchSimilarityService,
        pair_tuples: list[tuple[str, str]],
    ) -> list:
        """Run similarity plus optional LLM verification for uncertain pairs."""
        verifier = self._build_active_learning_verifier()
        active_cfg = self.config.active_learning
        threshold = min(self.config.similarity.threshold, active_cfg.low_threshold)
        detailed_matches = similarity_service.compute_similarities_detailed(
            candidate_pairs=pair_tuples,
            threshold=threshold,
        )

        doc_cache = similarity_service.batch_fetch_documents(
            list({key for pair in pair_tuples for key in pair})
        )

        matches = []
        self._active_learning_stats = {
            'enabled': True,
            'pairs_reviewed': 0,
            'llm_calls': 0,
            'score_overrides': 0,
            'feedback_collection': verifier.store.collection,
        }
        if getattr(self, "_llm_healthcheck", None) is not None:
            self._active_learning_stats['healthcheck'] = self._llm_healthcheck

        for item in detailed_matches:
            score = item['weighted_score']
            final_score = score
            self._active_learning_stats['pairs_reviewed'] += 1

            if verifier.verifier.needs_verification(score):
                field_scores = self._format_field_scores_for_llm(item['field_scores'])
                result = verifier.verify(
                    doc_cache.get(item['doc1_key'], {'_key': item['doc1_key']}),
                    doc_cache.get(item['doc2_key'], {'_key': item['doc2_key']}),
                    score=score,
                    field_scores=field_scores,
                )
                if result.get('llm_called'):
                    self._active_learning_stats['llm_calls'] += 1
                if result.get('score_override') is not None:
                    final_score = result['score_override']
                    self._active_learning_stats['score_overrides'] += 1

            if final_score >= self.config.similarity.threshold:
                matches.append((item['doc1_key'], item['doc2_key'], round(final_score, 4)))

        matches.sort(key=lambda x: x[2], reverse=True)
        return matches

    def _build_active_learning_verifier(self):
        """Construct the active learning verifier for this pipeline run."""
        from entity_resolution.reasoning.feedback import AdaptiveLLMVerifier, FeedbackStore

        cfg = self.config.active_learning
        feedback_collection = cfg.feedback_collection or f"{self.config.collection_name}_llm_feedback"
        store = FeedbackStore(self.db, collection=feedback_collection)
        # The structured `llm:` block used to be parsed, validated and then
        # dropped here: only the bare `model` string was passed, so provider,
        # base_url, timeout and api_key_env never reached the verifier, and
        # neither did mask_fields, the one control over what leaves the network.
        provider = cfg.llm
        extra: Dict[str, Any] = {}
        if provider is not None:
            extra["base_url"] = provider.base_url
            extra["timeout_seconds"] = provider.timeout_seconds
            if provider.api_key_env:
                extra["api_key"] = os.environ.get(provider.api_key_env)
        verifier = AdaptiveLLMVerifier(
            feedback_store=store,
            refresh_every=cfg.refresh_every,
            model=cfg.effective_model_string(),
            low_threshold=cfg.low_threshold,
            high_threshold=cfg.high_threshold,
            entity_type=self.config.entity_type,
            optimizer_target_precision=cfg.optimizer_target_precision,
            optimizer_min_samples=cfg.optimizer_min_samples,
            mask_fields=cfg.mask_fields,
            **extra,
        )
        if provider is not None and provider.healthcheck_on_start:
            health = verifier.verifier.healthcheck()
            self._llm_healthcheck = health
            if not health.get("ok"):
                # Not fatal: the verifier answers from the score when the LLM
                # fails, and that fallback is counted, never credited to it.
                self.logger.warning(
                    "LLM healthcheck failed for %s: %s", health.get("model"), health.get("error")
                )
        return verifier

    def _format_field_scores_for_llm(self, field_scores: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
        """Convert plain per-field scores into the structure expected by LLM prompts."""
        return {
            field: {
                'score': score,
                'method': self.config.similarity.algorithm,
            }
            for field, score in field_scores.items()
        }


    def run_edge_creation(self, matches: list) -> int:
        """Run edge creation phase."""
        if not matches:
            return 0
        
        edge_service = SimilarityEdgeService(
            db=self.db,
            edge_collection=self.config.edge_collection,
            batch_size=1000
        )
        
        edges_created = edge_service.create_edges(
            matches=matches,
            metadata={
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'method': 'configurable_pipeline'
            }
        )
        
        return edges_created
    
    def run_clustering(self) -> list:
        """Run clustering phase based on configuration."""
        clustering_service = WCCClusteringService(
            db=self.db,
            edge_collection=self.config.edge_collection,
            cluster_collection=self.config.cluster_collection,
            min_cluster_size=self.config.clustering.min_cluster_size,
            backend=self.config.clustering.backend,
            auto_select_threshold_edges=self.config.clustering.auto_select_threshold_edges,
            sparse_backend_enabled=self.config.clustering.sparse_backend_enabled,
            gae_config=self.config.clustering.gae,
        )
        
        clusters = clustering_service.cluster(
            store_results=self.config.clustering.store_results
        )
        
        return clusters
    
    def __repr__(self) -> str:
        """String representation."""
        return (f"ConfigurableERPipeline("
                f"entity_type='{self.config.entity_type}', "
                f"collection='{self.config.collection_name}')")

