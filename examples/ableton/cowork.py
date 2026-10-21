"""Compatibility imports for the shared guarded selected-note API.

The bridge owns snapshots, exact-content checks and full-note validation. A work
chooses all note values; coordinates remain clip-local beats.
"""

from tactus.bridges.ableton import inspect_selection, update_notes

__all__ = ['inspect_selection', 'update_notes']
