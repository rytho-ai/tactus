"""Opt-in lossless web-output cache; content and implementation bind each entry.

Entries are immutable and checked before reuse. A corrupt entry is ignored; the
exporter recomputes the output. Each export gets an independent copy of its audio,
so editing an export cannot change the cache or another export. Maps and run
identity never enter entries: the exporter regenerates those for every delivery.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import scipy
import soundfile

from .inputs.pool import hash_file


def implementation() -> str:
    root = Path(__file__).parent
    parts = [hash_file(root / name) for name in (
        '_delivery.py', '_delivery_cache.py', 'store.py',
        '_biquad.py', 'analysis/level.py', 'analysis/_level.py',
        'analysis/_revision.py', 'analysis/_schema.py',
    )]
    return hashlib.sha256(json.dumps([parts, sys.version, np.__version__, scipy.__version__,
                                     soundfile.__version__, soundfile.__libsndfile_version__]).encode()).hexdigest()


class WebOutputCache:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.implementation = implementation()

    def key(self, name, audio, rate, codec, depth, peaks):
        content = hashlib.sha256(np.ascontiguousarray(audio).tobytes()).hexdigest()
        spec = [self.implementation, name, content, str(audio.dtype), audio.shape,
                rate, codec, depth, peaks]
        return hashlib.sha256(json.dumps(spec).encode()).hexdigest()

    def restore(self, key: str, out: Path):
        folder = self.root / key
        try:
            record = folder / 'record.json'
            audio = folder / 'audio'
            if folder.is_symlink() or record.is_symlink() or audio.is_symlink():
                return None
            raw = record.read_bytes()
            checksum = (folder / 'record.sha256').read_text()
            if hashlib.sha256(raw).hexdigest() != checksum:
                return None
            entry = json.loads(raw)
            if entry['key'] != key or hash_file(audio) != entry['audio_sha256']:
                return None
            metadata = entry['metadata']
            destination = out / metadata['file']
            if not destination.resolve().is_relative_to((out / 'audio').resolve()):
                return None
            shutil.copyfile(audio, destination)
            return metadata
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, key: str, metadata: dict, out: Path):
        # A winning concurrent writer owns its immutable entry. Corrupt entries
        # remain ignored rather than overwriting data another reader may hold.
        folder = self.root / key
        if folder.exists():
            return
        with tempfile.TemporaryDirectory(prefix='.writing-', dir=self.root) as temporary:
            staged = Path(temporary) / 'entry'
            staged.mkdir()
            audio = staged / 'audio'
            shutil.copyfile(out / metadata['file'], audio)
            raw = json.dumps({'key': key, 'metadata': metadata, 'audio_sha256': hash_file(audio)},
                             allow_nan=False, sort_keys=True).encode()
            (staged / 'record.json').write_bytes(raw)
            (staged / 'record.sha256').write_text(hashlib.sha256(raw).hexdigest())
            try:
                staged.rename(folder)
            except OSError:
                if not folder.exists():
                    raise
