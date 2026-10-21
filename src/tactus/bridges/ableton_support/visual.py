"""Optional Live/Max-console window capture; no extra MCP commands or service."""

from ._vendor.visual_capture import capture_ableton_window as capture
from ._vendor.visual_capture import capture_max_console_window as max_console
from ._vendor.visual_capture import list_ableton_windows, list_max_console_windows

__all__ = ["capture", "list_ableton_windows", "list_max_console_windows", "max_console"]
