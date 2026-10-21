"""Capture native state and render a pinned project without changing the live tab.

Capture handles inline MIDI and ordinary file-backed takes. Collect plugin-owned
samples/IRs separately as materials/tools. Wrapped (section/reverse) sources and
subprojects need a work-authored capture recipe; they are rejected explicitly.
Reads: packaged project.lua; inputs.material/tool; audio.render; file hashes/copies.
"""

import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

from tactus import material, tool
from tactus.bridges import reaper

from . import audio


def _native(resource_path, **args):
    lua = tool(str(Path(__file__).with_suffix('.lua')))
    return reaper.execute(lua.read_text(), resource_path=resource_path, args=args, timeout=120)


def inspect(*, resource_path):
    """Read current project identity, selection, tracks/FX and take media; no save."""
    return _native(resource_path, mode='inspect')


def _rows(value):
    return [] if value == {} else value


def _digest(path):
    with Path(path).open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def _verify_media(state, root):
    root = Path(root).resolve()
    for row in _rows(state['media']):
        if row['inline_midi']:
            continue
        file = Path(row['file']).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            raise ValueError(f'Project still references media outside bundle: {file}')


def _content(state):
    # Saving a copy can advance REAPER's counter without changing native content.
    # All actual content, identity, selection, cursor and transport stay guarded.
    return {key: value for key, value in state.items() if key != 'change_count'}


def capture(*, resource_path, out):
    """Save an accepted native project/media to a NEW directory, retaining live state.

    capture.json marks completion. Pin the completed directory using ordinary
    tactus material add. Plugin-owned dependencies are not included automatically.
    An error may leave the new directory/private tab available for inspection.
    """
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError(out)
    before = inspect(resource_path=resource_path)
    if before.get('play_state', 0) != 0:
        raise ValueError('Stop transport before capture')
    files = {}
    sources = {}
    for row in _rows(before['media']):
        if row['wrapped'] or row['kind'] in ('RPP_PROJECT', 'VIDEO'):
            raise ValueError('Section/reverse, subproject and video sources need their own recipe')
        if row['inline_midi']:
            continue
        source = Path(row['file'])
        if not row['file'] or not source.is_absolute() or not source.is_file():
            raise ValueError(f'Collect missing/unsupported take media first: {source}')
        digest = _digest(source)
        relative = f'media/{digest}{source.suffix.lower()}'
        sources[source] = (relative, digest)
        files[row['take']] = str(out / relative)
    out.mkdir(parents=True)
    for source, (relative, digest) in sources.items():
        target = out / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        if _digest(target) != digest or _digest(source) != digest:
            raise ValueError('Source media changed while copying; capture again')
    captured = _native(resource_path, mode='capture', expected=before,
                       project=str(out / 'session.rpp'), files=files)
    _verify_media(captured, out)
    # Prove native serialization resolves the copied media when reopening.
    reopened = _native(resource_path, mode='verify', project=str(out / 'session.rpp'))
    _verify_media(reopened, out)
    after = inspect(resource_path=resource_path)
    if _content(before) != _content(after):
        raise ValueError('Live project changed during capture; inspect before adopting the copy')
    for source, (_, digest) in sources.items():
        if _digest(source) != digest:
            raise ValueError('Source media changed during capture; capture again')
    record = {'project': 'session.rpp', 'source': before,
              'files': {relative: digest for relative, digest in sources.values()},
              'reaper': reopened,
              'external_dependencies': 'Declare plugin binaries and plugin-owned assets separately'}
    pending = out / 'capture.json.tmp'
    pending.write_text(json.dumps(record, indent=2) + '\n')
    pending.replace(out / 'capture.json')
    return record


def render_project(ref, *, resource_path, reaper_bundle, seconds=8, sample_rate=24000):
    """Render an explicit range from a pinned project COPY; pool/live state stay intact."""
    if not isinstance(ref, str) or not ref.startswith('tree:sha256:'):
        raise ValueError('project_ref must be a pinned tree:sha256: bundle')
    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds) or seconds <= 0):
        raise ValueError('seconds must be finite and positive')
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError('sample_rate must be a positive integer')
    bundle = material(ref)
    if not (bundle / 'capture.json').is_file() or not (bundle / 'session.rpp').is_file():
        raise ValueError('Use a completed native capture bundle')
    record = json.loads((bundle / 'capture.json').read_text())
    if not isinstance(record, dict) or record.get('project') != 'session.rpp':
        raise ValueError('Use a completed native capture bundle')
    tool(reaper_bundle)
    scratch = Path(tempfile.mkdtemp(prefix='tactus-project-'))
    try:
        # material(tree) may use hardlinks: native save must only touch real copies.
        shutil.copytree(bundle, scratch / 'input')
        state = _native(resource_path, mode='verify', project=str(scratch / 'input/session.rpp'))
        _verify_media(state, scratch / 'input')
        result = audio.render('reaper.Main_openProject(args.project)',
                              resource_path=resource_path, reaper_bundle=reaper_bundle,
                              args={'project': str(scratch / 'input/session.rpp')},
                              seconds=seconds, sample_rate=sample_rate, channels=2)
    except Exception as exc:
        # A timeout cannot cancel native code: its input/output must remain available.
        exc.add_note(f'REAPER scratch retained at {scratch}; inspect host/reply before cleanup')
        raise
    shutil.rmtree(scratch)
    return result
