"""Standalone Live Remote Script; ordinary imports do not require Live or MCP."""


def create_instance(c_instance):
    from .bridge import TactusBridge

    return TactusBridge(c_instance)
