"""
Pytest configuration and fixtures for safe_txns_sim_endpoint tests.
"""
import pytest
import sys
import os

# Add endpoint module to path for test imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'endpoint'))

@pytest.fixture
def reset_similarity_module():
    """Reset similarity module state between tests."""
    # Reset caches
    from similarity_matcher import _REFERENCE_CACHE, _ATHENA_CACHE
    _REFERENCE_CACHE.clear()
    _ATHENA_CACHE.clear()
    yield
    _REFERENCE_CACHE.clear()
    _ATHENA_CACHE.clear()

@pytest.fixture
def reset_inference_module():
    """Reset inference module state between tests."""
    import importlib
    try:
        import inference_rules
        importlib.reload(inference_rules)
    except:
        pass
    yield
    try:
        importlib.reload(inference_rules)
    except:
        pass
