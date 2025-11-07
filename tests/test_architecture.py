from __future__ import annotations

import ast
from pathlib import Path

# Get the project root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src" / "app"


def test_domain_layer_has_no_infrastructure_imports():
    """Test that domain layer only imports standard library and pydantic."""
    domain_dir = SRC_DIR / "domain"
    allowed_modules = {
        "typing",
        "datetime",
        "uuid",
        "pydantic",
        "pydantic_settings",
        "__future__",
        "annotations",
    }

    for py_file in domain_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        with py_file.open() as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split(".")[0]
                    if module_name not in allowed_modules and not module_name.startswith("_"):
                        assert False, f"Domain layer imports infrastructure: {module_name} in {py_file}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split(".")[0]
                    if module_name not in allowed_modules and not module_name.startswith("_"):
                        assert False, f"Domain layer imports infrastructure: {module_name} in {py_file}"


def test_services_dont_import_concrete_adapters():
    """Test that services don't import concrete adapter implementations."""
    services_dir = SRC_DIR / "services"
    forbidden_modules = {
        "observability.logger",
        "adapters",
        "persistence.adapters",
    }

    for py_file in services_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        with py_file.open() as f:
            content = f.read()

        for forbidden in forbidden_modules:
            if f"from ..{forbidden}" in content or f"from ...{forbidden}" in content:
                assert False, f"Service imports concrete adapter: {forbidden} in {py_file}"


def test_services_only_import_interfaces():
    """Test that services only import from application.interfaces, not concrete adapters."""
    services_dir = SRC_DIR / "services"

    for py_file in services_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        with py_file.open() as f:
            tree = ast.parse(f.read(), filename=str(py_file))

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    # Check if it's importing from a forbidden location
                    if "observability.logger" in str(node.module) or "adapters" in str(node.module):
                        # Allow NullObservabilityRecorder from interfaces
                        if "NullObservabilityRecorder" not in [alias.name for alias in node.names]:
                            assert False, f"Service imports from forbidden module: {node.module} in {py_file}"


def test_dependency_flow_is_correct():
    """
    Test that dependency flow follows hexagonal architecture:
    domain ← application ← services ← adapters
    """
    # This is a structural test - we verify by checking imports
    # Domain should not import anything from app
    # Services should only import from domain and application.interfaces
    # Adapters should import from application.interfaces and domain

    domain_dir = SRC_DIR / "domain"
    services_dir = SRC_DIR / "services"
    adapters_dir = SRC_DIR / "adapters"

    # Check domain doesn't import from services or adapters
    for py_file in domain_dir.rglob("*.py"):
        with py_file.open() as f:
            content = f.read()
            assert "from ..services" not in content, f"Domain imports services: {py_file}"
            assert "from ..adapters" not in content, f"Domain imports adapters: {py_file}"

    # Check services don't import from adapters (except via interfaces)
    for py_file in services_dir.rglob("*.py"):
        with py_file.open() as f:
            content = f.read()
            # Services can import from adapters only if it's through interfaces
            # But they shouldn't import concrete adapters directly
            if "from ..adapters" in content and "interfaces" not in content:
                # Check if it's importing a concrete class
                tree = ast.parse(content, filename=str(py_file))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        if node.module and "adapters" in node.module:
                            assert False, f"Service imports concrete adapter: {node.module} in {py_file}"

