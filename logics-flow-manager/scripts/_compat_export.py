from __future__ import annotations

from importlib import import_module


def export_module(module_name: str, namespace: dict[str, object]) -> None:
    module = import_module(module_name)
    namespace.update({key: value for key, value in module.__dict__.items() if not key.startswith('__')})
