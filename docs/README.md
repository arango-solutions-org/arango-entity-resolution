# Documentation Index

Welcome to the ArangoDB Entity Resolution documentation!

---

## Quick Navigation

### Getting Started
- [Quick Start Guide](guides/QUICK_START.md) - Get up and running in 5 minutes
- [Main README](../README.md) - Project overview and installation

### Current Project Assessment
- [Project Health Scorecard](PROJECT_HEALTH_SCORECARD.md) - Engineering, quality, security, release, and operational health
- [SOTA and Competitive Scorecard](SOTA_COMPETITIVE_SCORECARD.md) - Current position against OSS and commercial ER systems
- [Public Benchmark Results](BENCHMARKS.md) - Reproducible quality and scalability evidence

### API Documentation
- [API Reference](api/API_REFERENCE.md) - Current CLI, MCP, and Python API surface for v3.5.1

### User Guides
- [Migration Guide v3.0](guides/MIGRATION_GUIDE_V3.md) - Upgrade from v1.x or v2.x
- [Custom Collections Guide](guides/CUSTOM_COLLECTIONS_GUIDE.md) - Work with your own data
- [Advanced Modules Guide](guides/ADVANCED_MODULES_GUIDE.md) - Orchestration, GraphRAG, geospatial, ETL normalizers, and more
- [Testing Guide](TESTING.md) - Current testing and release-validation guidance

### Architecture & Design
- [System Design](architecture/DESIGN.md) - How the system works
- [Centralized ER Service](architecture/CENTRALIZED_ER_SERVICE.md) - Enterprise service with shared knowledge graph
- [Graph Algorithms](architecture/GRAPH_ALGORITHMS_EXPLANATION.md) - Algorithm explanations

### Development
- [Enhancement Plan](archive/completed-work/LIBRARY_ENHANCEMENT_PLAN.md) - Historical formalization plan
- [Next Release Brief](development/NEXT_RELEASE_IMPLEMENTATION_BRIEF.md) - Implementation brief for releases `3.3.0`–`3.5.0` (all shipped)
- [GAE Enhancement Path](development/GAE_ENHANCEMENT_PATH.md) - GAE clustering design (implemented in 3.5.0)
- [Batch vs Bulk Processing](archive/completed-work/BATCH_VS_BULK_PROCESSING.md) - Performance patterns (archived: Foxx era)
- [Blocking Benchmarks](development/BLOCKING_BENCHMARKS.md) - Supported evaluator workflow
- [Runtime Health CI Runbook](development/RUNTIME_HEALTH_CI_RUNBOOK.md) - Runtime baseline, compare, and gate workflows
- [Provider Rollout Runbook](development/PROVIDER_ROLLOUT_RUNBOOK.md) - Rollout, monitoring, and rollback for ONNX Runtime providers
- [Release Checklist](development/RELEASE_CHECKLIST.md) - Steps for GitHub Release and PyPI publish
- [Project Evolution](development/PROJECT_EVOLUTION.md) - Historical project evolution notes
- [Git Hooks](development/GIT_HOOKS.md) - Development workflow

### Research & Papers
- [Research Directory](../research/README.md) - Research notes and papers
- [Bibliography](../research/bibliography.md) - Academic references

### Visual Documentation
- [Diagrams](diagrams/README.md) - System architecture diagrams

---

## Document Categories

### By Audience

**For Users:**
- Quick Start Guide
- API Reference
- README
- Migration Guide
- Custom Collections Guide

**For Developers:**
- System Design
- Development Documentation
- Testing Guide
- Git Hooks

**For Researchers:**
- Research Papers
- Algorithm Explanations
- Bibliography

### By Topic

**Entity Resolution:**
- API Reference (CLI, MCP, Python APIs)
- Graph Algorithms
- Custom Collections Guide

**System Architecture:**
- System Design
- Centralized ER Service
- Foxx Architecture
- Component diagrams

**Getting Started:**
- Quick Start Guide
- README
- CLI / MCP examples in the README

**Advanced Topics:**
- Advanced Modules Guide
- [Provider Compatibility Matrix](guides/PROVIDER_COMPATIBILITY_MATRIX.md)
- Historical enhancement plan
- GAE Enhancement Path
- Batch vs Bulk Processing

---

## Additional Resources

### Examples
- [Enhanced ER Examples](../examples/enhanced_er_examples.py) - Complete working examples
- API documentation includes inline examples

### Configuration
- [Config Example](../config.example.json) - Configuration template
- [Release Checklist](development/RELEASE_CHECKLIST.md) - Release and PyPI publication steps

### Tools
- [Demo Scripts](../demo/) - Demonstration tools

---

## Archive

Historical documentation is preserved in [`archive/`](archive/):
- **audits/** - Code audits and quality reports
- **test-reports/** - Test execution reports
- **session-notes/** - Development session notes
- **completed-work/** - Completed enhancement docs

> **Note:** Archive documents are kept for historical reference but may not reflect the current state of the project.

---

## Version Information

- **Current Version:** 3.10.1
- **API Version:** v3
- **Last Updated:** August 6, 2026

For version history, see [CHANGELOG.md](../CHANGELOG.md)

---

## Need Help?

1. **Getting Started:** Read the [Quick Start Guide](guides/QUICK_START.md)
2. **API Questions:** Check the [API Reference](api/API_REFERENCE.md)
3. **Migration:** See the [Migration Guide](guides/MIGRATION_GUIDE_V3.md)
4. **Examples:** Review [examples/enhanced_er_examples.py](../examples/enhanced_er_examples.py)
5. **Issues:** Check existing documentation or open an issue

---

**Documentation Structure Version:** 2.0 
**Last Reorganized:** November 11, 2025

