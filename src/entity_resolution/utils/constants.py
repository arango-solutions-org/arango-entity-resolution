"""
Application Constants

Centralized constants to eliminate hard-coded values throughout the codebase.
All magic numbers, default values, and configuration constants are defined here.
"""

from typing import Dict, Any, List

# Database Connection Defaults — single source of truth for the whole package.
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8529
DEFAULT_USERNAME = "root"
DEFAULT_DATABASE = "_system"

DEFAULT_DATABASE_CONFIG = {
    'host': DEFAULT_HOST,
    'port': DEFAULT_PORT,
    'username': DEFAULT_USERNAME,
    'password': '',  # Must be provided via environment variable
    'database': DEFAULT_DATABASE,
}

# Entity Resolution Algorithm Constants
SIMILARITY_THRESHOLDS = {
    'default': 0.85,
    'strict': 0.95,
    'loose': 0.75,
    'minimum': 0.5
}

ALGORITHM_WEIGHTS = {
    'jaro_winkler': 0.4,
    'levenshtein': 0.3,
    'jaccard': 0.2,
    'phonetic': 0.1
}

# Field-specific similarity weights
FIELD_WEIGHTS = {
    'first_name': 0.25,
    'last_name': 0.25,
    'email': 0.20,
    'phone': 0.15,
    'company': 0.10,
    'address': 0.05
}

# Blocking Strategy Constants
BLOCKING_STRATEGIES = {
    'exact': {
        'fields': ['email', 'phone'],
        'weight': 1.0
    },
    'ngram': {
        'n': 3,
        'fields': ['first_name', 'last_name', 'company'],
        'weight': 0.8
    },
    'phonetic': {
        'algorithm': 'soundex',
        'fields': ['first_name', 'last_name'],
        'weight': 0.6
    }
}

# Clustering Constants
CLUSTERING_CONFIG = {
    'algorithm': 'connected_components',
    'max_cluster_size': 100,
    'min_cluster_confidence': 0.8,
    'merge_threshold': 0.9
}

# v3.0 Default Constants (for new components)
DEFAULT_MAX_BLOCK_SIZE = 100
DEFAULT_MIN_BLOCK_SIZE = 2
DEFAULT_SIMILARITY_THRESHOLD = 0.75
DEFAULT_BATCH_SIZE = 5000
DEFAULT_EDGE_BATCH_SIZE = 1000
DEFAULT_MIN_BM25_SCORE = 2.0
DEFAULT_MIN_CLUSTER_SIZE = 2
DEFAULT_VIEW_BUILD_WAIT_SECONDS = 10
DEFAULT_PROGRESS_CALLBACK_INTERVAL = 10000

# Maximum records loaded into Python memory by the deprecated EntityResolutionPipeline.
# Prefer ConfigurableERPipeline for large collections (operates at ArangoDB layer).
DEFAULT_BLOCKING_RECORD_LIMIT = 10_000

# Default Collection Names
DEFAULT_EDGE_COLLECTION = "similarTo"
DEFAULT_CLUSTER_COLLECTION = "entity_clusters"
DEFAULT_ADDRESS_EDGE_COLLECTION = "address_sameAs"

# Phase 3 (prototype) node embedding safety limits
#
# These are intentionally conservative defaults to prevent accidental OOM and
# to keep the Node2Vec-style SVD approach limited to small graphs.
PHASE3_NODE_EMBEDDING_LIMITS = {
    # Hard limits (raise ValueError if exceeded)
    'max_edges_fetched': 50000,
    'max_nodes': 10000,
    'max_dimensions': 128,
    # Warning thresholds (log warnings, continue)
    'warn_edges_threshold': 20000,
    'warn_nodes_threshold': 5000,
}

# Performance Limits
PERFORMANCE_LIMITS = {
    'max_records_per_batch': 1000,
    'max_pairs_per_batch': 50,
    'max_candidates_per_record': 20,
    'timeout_seconds': 30,
    'max_memory_mb': 512
}

# Foxx Service Configuration
FOXX_CONFIG = {
    'service_mount': '/entity-resolution',
    'timeout_seconds': 30,
    'retry_attempts': 3,
    'retry_delay_seconds': 1
}

# API Endpoints
API_ENDPOINTS = {
    'health': 'health',
    'similarity': {
        'compute': 'similarity/compute',
        'batch': 'similarity/batch',
        'functions': 'similarity/functions'
    },
    'blocking': {
        'strategies': 'blocking/strategies',
        'candidates': 'blocking/candidates'
    },
    'clustering': {
        'cluster': 'clustering/cluster',
        'validate': 'clustering/validate'
    },
    'setup': {
        'status': 'setup/status',
        'initialize': 'setup/initialize'
    }
}

# Data Quality Thresholds
DATA_QUALITY_THRESHOLDS = {
    'excellent': 0.95,
    'good': 0.85,
    'fair': 0.70,
    'poor': 0.50
}

# Demo Configuration
DEMO_CONFIG = {
    'default_record_count': 1000,
    'max_display_records': 20,
    'duplicate_rates': {
        'low': 0.1,
        'medium': 0.2,
        'high': 0.3
    },
    'business_scenarios': {
        'small': {
            'customers': 10000,
            'marketing_budget': 50000,
            'implementation_cost': 50000
        },
        'medium': {
            'customers': 50000,
            'marketing_budget': 250000,
            'implementation_cost': 75000
        },
        'large': {
            'customers': 500000,
            'marketing_budget': 2500000,
            'implementation_cost': 150000
        }
    }
}

# File and Directory Constants
DEFAULT_PATHS = {
    'config_dir': 'config',
    'data_dir': 'data',
    'logs_dir': 'logs',
    'reports_dir': 'reports',
    'temp_dir': 'temp'
}

# Logging Configuration
LOGGING_CONFIG = {
    'levels': {
        'DEBUG': 10,
        'INFO': 20,
        'WARNING': 30,
        'ERROR': 40,
        'CRITICAL': 50
    },
    'default_level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'max_file_size_mb': 10,
    'backup_count': 5
}

# Collection Names
COLLECTION_NAMES = {
    'customers': 'customers',
    'similarity_results': 'similarity_results',
    'entity_clusters': 'entity_clusters',
    'golden_records': 'golden_records',
    'duplicate_groups': 'duplicate_groups',
    'blocking_candidates': 'blocking_candidates'
}

# Error Messages
ERROR_MESSAGES = {
    'database_connection': 'Failed to connect to ArangoDB database',
    'invalid_config': 'Invalid configuration provided',
    'missing_fields': 'Required fields are missing',
    'timeout': 'Operation timed out',
    'insufficient_data': 'Insufficient data for processing',
    'foxx_unavailable': 'Foxx service is not available'
}

# Success Messages
SUCCESS_MESSAGES = {
    'database_connected': 'Successfully connected to database',
    'service_initialized': 'Service initialized successfully',
    'processing_complete': 'Processing completed successfully',
    'data_loaded': 'Data loaded successfully'
}

# Regular Expressions
REGEX_PATTERNS = {
    'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
    'phone': r'^[\+]?[1-9][\d]{0,15}$',
    'postal_code': r'^\d{5}(-\d{4})?$',
    'name': r'^[a-zA-Z\s\-\'\.]+$'
}

# Data Formats
DATA_FORMATS = {
    'date': '%Y-%m-%d',
    'datetime': '%Y-%m-%d %H:%M:%S',
    'timestamp': '%Y-%m-%dT%H:%M:%S.%fZ'
}

# Character Sets for Data Generation
CHARACTER_SETS = {
    'lowercase': 'abcdefghijklmnopqrstuvwxyz',
    'uppercase': 'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
    'digits': '0123456789',
    'special': '!@#$%^&*()_+-=[]{}|;:,.<>?'
}

# Business Impact Multipliers
BUSINESS_IMPACT_MULTIPLIERS = {
    'marketing_waste': 1.0,
    'customer_service_inefficiency': 0.3,
    'sales_opportunity_loss': 0.1,
    'compliance_risk': 0.05,
    'brand_reputation': 0.02
}

# Industry-Specific Constants
INDUSTRY_CONSTANTS = {
    'healthcare': {
        'patient_id_formats': ['MRN', 'SSN', 'DOB'],
        'matching_fields': ['first_name', 'last_name', 'dob', 'ssn'],
        'strict_matching': True
    },
    'financial': {
        'customer_id_formats': ['account_number', 'ssn', 'tax_id'],
        'matching_fields': ['first_name', 'last_name', 'ssn', 'address'],
        'compliance_required': True
    },
    'retail': {
        'customer_id_formats': ['email', 'phone', 'loyalty_id'],
        'matching_fields': ['email', 'phone', 'name', 'address'],
        'marketing_focused': True
    }
}

# Version Information
# v3.1.2: Current release
#   - Includes Entity Resolution Enrichments (TypeCompatibilityFilter, etc.)
#   - Standalone enrichment modules with lazy config loading
# v3.1.0-stable: Historical production identifier (used for 3.1.0 release)
# v3.0.0-stable: Previous production identifier
#   - Includes AddressERService, CrossCollectionMatchingService
#   - Vector search (EmbeddingService, VectorBlockingStrategy)
#   - WCC performance optimization (40-100x speedup)
#   - HybridBlockingStrategy, GeographicBlockingStrategy
#   - All services extracted from customer projects
# See VERSION_HISTORY.md for detailed version timeline
VERSION_INFO = {
    'major': 3,
    'minor': 8,
    'patch': 0,
    'release': ''
}

# Single source of version truth — hatchling reads this via regex in pyproject.toml.
# To release a new version: bump VERSION_INFO above AND this string, then create a
# GitHub Release. The publish.yml workflow will build and upload to PyPI automatically.
__version__ = "3.10.1"

def get_version_string() -> str:
    """Get formatted version string"""
    v = VERSION_INFO
    version = f"{v['major']}.{v['minor']}.{v['patch']}"
    if v['release']:
        version = f"{version}-{v['release']}"
    return version

def get_database_url(host: str = None, port: int = None) -> str:
    """Get formatted database URL"""
    h = host or DEFAULT_DATABASE_CONFIG['host']
    p = port or DEFAULT_DATABASE_CONFIG['port']
    return f"http://{h}:{p}"

def get_foxx_service_url(host: str = None, port: int = None, 
                        database: str = None, mount: str = None) -> str:
    """Get formatted Foxx service URL"""
    base_url = get_database_url(host, port)
    db = database or DEFAULT_DATABASE_CONFIG['database']
    service_mount = mount or FOXX_CONFIG['service_mount']
    return f"{base_url}/_db/{db}{service_mount}"

def get_business_impact_estimate(customer_count: int, duplicate_rate: float, 
                               marketing_budget: int) -> Dict[str, float]:
    """Calculate business impact estimates"""
    duplicates = int(customer_count * duplicate_rate)
    marketing_waste = marketing_budget * duplicate_rate
    
    impact = {
        'duplicate_customers': duplicates,
        'marketing_waste': marketing_waste
    }
    
    for factor, multiplier in BUSINESS_IMPACT_MULTIPLIERS.items():
        if factor != 'marketing_waste':
            impact[factor] = marketing_waste * multiplier
    
    impact['total_annual_cost'] = sum(impact.values()) - impact['duplicate_customers']
    
    return impact

# Database connection constants — use DEFAULT_DATABASE_CONFIG dict above instead
# of these individual aliases to reduce duplication.
# Test / demo database names
TEST_DATABASE_NAME = 'entity_resolution_test'
DEMO_DATABASE_NAME = 'entity_resolution_demo'
# Service constants
DEFAULT_FOXX_TIMEOUT = 30
DEFAULT_BLOCKING_THRESHOLD = 0.7