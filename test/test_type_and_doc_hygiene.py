"""Automated type reflection and docstring hygiene tests for Tiny SHell."""

import ast
import inspect
import typing

import tsh_client
import tsh_pel


def test_runtime_type_hints_resolution():
    """Verify that typing.get_type_hints() succeeds on all modules, classes, and functions without NameError."""
    for mod in (tsh_pel, tsh_client):
        typing.get_type_hints(mod)

        for name, obj in inspect.getmembers(mod):
            if inspect.isfunction(obj):
                hints = typing.get_type_hints(obj)
                assert isinstance(hints, dict), f"Failed resolving hints for function {mod.__name__}.{name}"
            elif inspect.isclass(obj) and obj.__module__ == mod.__name__:
                hints = typing.get_type_hints(obj)
                assert isinstance(hints, dict), f"Failed resolving hints for class {mod.__name__}.{name}"
                for m_name, m_obj in inspect.getmembers(obj):
                    if inspect.isfunction(m_obj) or inspect.isroutine(m_obj):
                        try:
                            m_hints = typing.get_type_hints(m_obj)
                            assert isinstance(m_hints, dict)
                        except Exception as exc:
                            raise AssertionError(
                                f"Failed resolving hints for {mod.__name__}.{obj.__name__}.{m_name}: {exc}"
                            ) from exc


def test_ast_docstring_completeness():
    """Verify via AST that all functions, methods, and classes in Python modules have non-empty docstrings."""
    for mod in ("tsh_pel.py", "tsh_client.py"):
        with open(mod, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=mod)

        missing = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node)
                if not doc or not doc.strip():
                    missing.append(f"{node.name} (line {node.lineno})")

        assert not missing, f"Missing docstrings in {mod}: {missing}"
