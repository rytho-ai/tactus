"""Optional read-only search of Live's local sound-analysis database (Live 12 feature)."""

import sqlite3
from pathlib import Path

from ._vendor import similar_sounds


def find(params=None):
    """Use Live's own analyzed features; fail clearly when that schema is absent."""
    params = {} if params is None else dict(params)
    path = Path(params.get('db_path') or similar_sounds.latest_live_files_db()).resolve()
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        required = {
            'files': {'file_id', 'parent_id', 'name', 'file_type', 'file_kind', 'flags',
                      'fe_version', 'file_size', 'mod_date', 'place_id', 'use_count'},
            'places': {'file_id', 'name'}, 'fe_values': {'file_id', 'hash', 'data'},
        }
        missing = []
        for table, fields in required.items():
            actual = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
            missing.extend(table + '.' + field for field in sorted(fields - actual))
        if missing:
            raise RuntimeError('A supported analyzed Live 12 database is required; missing: '
                               + ', '.join(missing))
    return similar_sounds.find_similar_sounds({**params, 'db_path': str(path)})
