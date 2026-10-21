"""Own support contracts: isolated assets, correlated replies and unknown completion."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tactus.bridges.ableton_support import audio, devices, max, transport


def roundtrip(module, config, call, reply):
    with ThreadPoolExecutor() as pool:
        future = pool.submit(call)
        deadline = time.monotonic() + 2
        path = config['command_file']
        while not path.exists():
            assert time.monotonic() < deadline
            time.sleep(.002)
        payload = json.loads(path.read_text())
        # A status from another request and an intermediate event cannot finish it.
        config['status_file'].write_text(json.dumps(dict(reply, command_id='old')))
        time.sleep(.03)
        assert not future.done()
        config['status_file'].write_text(json.dumps(dict(reply, command_id=payload['id'])))
        return future.result()


def config_at(tmp_path):
    return {'instance_id': 'fixture', 'role': 'audio_effect',
            'command_file': tmp_path / 'command.json', 'status_file': tmp_path / 'status.json'}


def test_audio_build_isolates_state_and_copies_runtime(tmp_path):
    a, b = audio.build(tmp_path / 'a'), audio.build(tmp_path / 'b')
    assert a['command_file'] != b['command_file']
    assert a['status_file'] != b['status_file']
    assert (tmp_path / 'a/agent_audio_tap.js').is_file()
    assert (tmp_path / 'a/Tactus Audio Tap.amxd').read_bytes().startswith(b'ampf')
    patch = json.loads((tmp_path / 'a/Tactus Audio Tap.maxpat').read_text())
    js = next(x['box']['text'] for x in patch['patcher']['boxes']
              if x['box'].get('text', '').startswith('js agent_audio_tap.js'))
    assert a['command_file'] in js and a['status_file'] in js
    with pytest.raises(FileExistsError):
        audio.build(tmp_path / 'a')


def test_audio_waits_for_own_reply(tmp_path):
    c = config_at(tmp_path)
    assert roundtrip(audio, c, lambda: audio.command(c, 'status', timeout=1),
                     {'event': 'status', 'recording': False})['recording'] is False


def test_max_waits_for_own_reply_and_preserves_authored_data(tmp_path):
    c = config_at(tmp_path)
    message = {'command': 'set', 'values': [{'id': 'tone', 'value': 333}]}
    assert roundtrip(max, c, lambda: max.command(c, message, timeout=1),
                     {'event': 'set', 'changed': 1})['changed'] == 1
    assert message == {'command': 'set', 'values': [{'id': 'tone', 'value': 333}]}


def test_max_error_is_visible(tmp_path):
    c = config_at(tmp_path)
    with pytest.raises(max.MaxError, match='bad graph'):
        roundtrip(max, c, lambda: max.command(c, {'command': 'update'}, timeout=1),
                  {'event': 'error', 'reason': 'bad graph'})


@pytest.mark.parametrize('module', [audio, max])
def test_timeout_submits_once_and_retains_command(tmp_path, monkeypatch, module):
    c = config_at(tmp_path)
    writes = []
    original = module.write_json
    def record(path, value, **kw):
        writes.append(value)
        return original(path, value, **kw)
    monkeypatch.setattr(module, 'write_json', record)
    message = {'command': 'status'} if module is max else 'status'
    with pytest.raises(TimeoutError, match='unknown'):
        module.command(c, message, timeout=.04)
    assert len(writes) == 1
    assert json.loads(c['command_file'].read_text()) == writes[0]


def test_audio_refuses_overwrite_before_submitting(tmp_path):
    c = config_at(tmp_path)
    path = tmp_path / 'accepted.wav'
    path.write_bytes(b'kept')
    with pytest.raises(FileExistsError):
        audio.command(c, 'open', path=path)
    assert not c['command_file'].exists() and path.read_bytes() == b'kept'


def test_record_owns_lifecycle_but_allows_silence_and_caller_playback(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf

    path = tmp_path / 'take.wav'
    events = []

    def command(config, action, **kwargs):
        events.append(action)
        if action == 'stop':
            sf.write(path, np.zeros((512, 2)), 48000)
        return {'recording': False}

    monkeypatch.setattr(audio, 'command', command)
    with audio.record({}, path=path) as destination:
        assert destination == path
        events.append('caller-owned performance')
    assert events == ['status', 'open', 'start', 'caller-owned performance', 'stop']
    assert sf.info(path).frames == 512
    with pytest.raises(FileExistsError), audio.record({}, path=path):
        pytest.fail('Must not overwrite')
    assert events[-1] == 'stop'


@pytest.mark.parametrize('failure_at', ['start', 'body'])
def test_record_preserves_primary_error_and_reports_failed_stop(tmp_path, monkeypatch, failure_at):
    events = []
    primary = TimeoutError('Start completion unknown')

    def command(config, action, **kwargs):
        events.append(action)
        if action == 'start' and failure_at == 'start':
            raise primary
        if action == 'stop':
            raise TimeoutError('Stop completion unknown')
        return {'recording': False}

    monkeypatch.setattr(audio, 'command', command)
    with pytest.raises(TimeoutError) as error, audio.record({}, path=tmp_path/'take.wav'):
        assert failure_at == 'body'
        raise primary
    assert error.value is primary
    assert 'stop completion unknown' in primary.__notes__[0]
    assert events == ['status', 'open', 'start', 'stop']


def test_record_does_not_interrupt_existing_take(tmp_path, monkeypatch):
    events = []

    def command(config, action, **kwargs):
        events.append(action)
        return {'recording': True}

    monkeypatch.setattr(audio, 'command', command)
    with pytest.raises(RuntimeError, match='already recording'), audio.record({}, path=tmp_path/'take.wav'):
        pytest.fail('Must preserve the active recording')
    assert events == ['status']


@pytest.mark.parametrize('contents', ['missing', 'invalid', 'empty'])
def test_record_requires_a_completed_decodable_file(tmp_path, monkeypatch, contents):
    import numpy as np
    import soundfile as sf

    path = tmp_path/'take.wav'

    def command(config, action, **kwargs):
        if action == 'stop':
            if contents == 'invalid':
                path.write_bytes(b'not audio')
            elif contents == 'empty':
                sf.write(path, np.zeros((0, 2)), 48000)
        return {'recording': False}

    monkeypatch.setattr(audio, 'command', command)
    with pytest.raises((sf.LibsndfileError, ValueError)), audio.record({}, path=path):
        pass


@pytest.mark.parametrize('fail_performance', [False, True])
def test_capture_owns_scratch_and_decode_but_preserves_raw_timing_and_silence(
        tmp_path, monkeypatch, fail_performance):
    import numpy as np
    import soundfile as sf

    scratch = tmp_path/'raw'
    original = np.zeros((512, 2))
    original[200:220] = .125  # Leading silence and tail are intentionally retained.
    events = []

    def temporary(**kwargs):
        scratch.mkdir()
        return str(scratch)

    def command(config, action, **kwargs):
        events.append(action)
        if action == 'stop':
            sf.write(scratch/'capture.wav', original, 48000, subtype='FLOAT')
        return {'recording': False}

    def perform():
        events.append('performance')
        if fail_performance:
            raise ValueError('authored error')

    monkeypatch.setattr(audio.tempfile, 'mkdtemp', temporary)
    monkeypatch.setattr(audio, 'command', command)
    if fail_performance:
        with pytest.raises(ValueError, match='authored error') as error:
            audio.capture({}, perform)
        assert str(scratch) in error.value.__notes__[-1]
        assert (scratch/'capture.wav').is_file()
    else:
        samples, rate = audio.capture({}, perform)
        assert np.array_equal(samples, original) and rate == 48000
        assert not scratch.exists()
    assert events == ['status', 'open', 'start', 'performance', 'stop']


def test_device_append_submits_once_and_polls_fresh_chain(monkeypatch):
    mutations = []
    new = {'id': 'new', 'name': 'Chosen device', 'class': 'MxDeviceAudioEffect'}
    rows = iter([{'pending': True}, {'pending': False, 'device': new}])
    def execute(code, **kw):
        if 'begin_append' in code:
            mutations.append(kw)
        else:
            return next(rows)
    monkeypatch.setattr(devices.ableton, 'execute', execute)
    result = devices.append(['user_library', 'Chosen device'], bridge_path='bridge',
                            track_id='track', expected_chain=['old'])
    assert result == new
    assert len(mutations) == 1
    assert mutations[0]['args'] == {'track': 'track', 'chain': ['old'],
                                   'path': ['user_library', 'Chosen device'], 'uri': None}


def test_device_append_rejects_unexpected_native_replacement_without_reloading(monkeypatch):
    mutations = []
    def execute(code, **kw):
        if 'begin_append' in code:
            mutations.append(kw)
        else:
            raise devices.ableton.BridgeError('Device chain changed during load')
    monkeypatch.setattr(devices.ableton, 'execute', execute)
    with pytest.raises(devices.ableton.BridgeError, match='chain changed'):
        devices.append(['instruments', 'Operator'], bridge_path='bridge',
                       track_id='track', expected_chain=['old'])
    assert len(mutations) == 1


def test_device_append_timeout_does_not_repeat_load_or_configuration(monkeypatch):
    calls = []
    clock = iter([0., .01, .2, .3])
    monkeypatch.setattr(devices.time, 'monotonic', lambda: next(clock))
    monkeypatch.setattr(devices.time, 'sleep', lambda duration: None)
    def execute(code, **kw):
        calls.append((code, kw))
        return {'pending': True}
    monkeypatch.setattr(devices.ableton, 'execute', execute)
    with pytest.raises(TimeoutError, match='completion unknown'):
        devices.append(['audio_effects', 'Chosen device'], bridge_path='bridge',
                       track_id='track', expected_chain=[], parameters={'Wet': .2}, timeout=.1)
    assert len(calls) == 2 and 'begin_append' in calls[0][0]
    assert 'finish_append' in calls[1][0] and calls[1][1]['args']['parameters'] == {'Wet': .2}


def test_transport_context_confirms_start_and_stop_around_authored_duration(monkeypatch):
    reads = iter([False, True, False])
    writes = []
    monkeypatch.setattr(transport.ableton, 'read', lambda **kw: {'is_playing': next(reads)})
    monkeypatch.setattr(transport.ableton, 'execute', lambda code, **kw: writes.append((code, kw)))
    with transport.playing(bridge_path='bridge', mode='session', start_beat=.375,
                           track_id='track', clip_id='clip', launch_quantization='q_no_q'):
        assert len(writes) == 1
        assert writes[0][1]['args'] == {'mode': 'session', 'track': 'track', 'clip': 'clip',
                                       'quantization': 'q_no_q', 'start': .375}
    assert len(writes) == 2 and writes[-1][0] == 'song.stop_playing()'


def test_transport_context_does_not_interrupt_an_existing_performance(monkeypatch):
    monkeypatch.setattr(transport.ableton, 'read', lambda **kw: {'is_playing': True})
    monkeypatch.setattr(transport.ableton, 'execute', lambda *a, **kw: pytest.fail('Already playing'))
    with pytest.raises(RuntimeError, match='already playing'), transport.playing(
            bridge_path='bridge', mode='arrangement', start_beat=0):
        pytest.fail('Must preserve existing playback')


def test_transport_stop_is_attempted_once_on_body_error(monkeypatch):
    reads = iter([False, True, False])
    writes = []
    monkeypatch.setattr(transport.ableton, 'read', lambda **kw: {'is_playing': next(reads)})
    monkeypatch.setattr(transport.ableton, 'execute', lambda code, **kw: writes.append(code))
    with pytest.raises(ValueError, match='authored error'), transport.playing(
            bridge_path='bridge', mode='arrangement', start_beat=0):
        raise ValueError('authored error')
    assert writes.count('song.stop_playing()') == 1


@pytest.mark.parametrize('timeout', [True, 0, -1, float('nan'), float('inf')])
def test_invalid_timeouts_never_submit(tmp_path, timeout):
    c = config_at(tmp_path)
    for module, msg in [(audio, 'status'), (max, {'command': 'status'})]:
        with pytest.raises(ValueError):
            module.command(c, msg, timeout=timeout)
    assert not c['command_file'].exists()


def test_similarity_uses_readonly_feature_database_and_checks_schema(tmp_path):
    import sqlite3

    from tactus.bridges.ableton_support import similar
    from tactus.bridges.ableton_support._vendor.similar_sounds import encode_feature
    path = tmp_path / 'sounds?#.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE places(file_id INTEGER, name TEXT)')
        db.execute('INSERT INTO places VALUES (1, "Library")')
        db.execute('CREATE TABLE files(file_id INTEGER, parent_id INTEGER, name TEXT, '
                   'file_type INTEGER, file_kind INTEGER, flags INTEGER, fe_version INTEGER, '
                   'file_size INTEGER, mod_date INTEGER, place_id INTEGER, use_count INTEGER)')
        db.execute('CREATE TABLE fe_values(file_id INTEGER, hash INTEGER, data BLOB)')
        for i, (name, feature) in enumerate([('Kick', [0., 0.]), ('Near', [.1, 0.]),
                                             ('Far', [3., 4.])], 1):
            db.execute('INSERT INTO files VALUES (?,0,?,1,1,1,1,100,0,1,0)', (i, name))
            db.execute('INSERT INTO fe_values VALUES (?,?,?)', (i, i, encode_feature(feature)))
    before = path.read_bytes()
    result = similar.find({'db_path': path, 'base': 'Kick', 'limit': 2})
    assert [r['name'] for r in result['results']] == ['Near', 'Far']
    assert result['results'][1]['distance'] == 5
    assert path.read_bytes() == before
    old = tmp_path / 'live11.db'
    with sqlite3.connect(old) as db:
        db.execute('CREATE TABLE files(name TEXT)')
    with pytest.raises(RuntimeError, match='Live 12'):
        similar.find({'db_path': old, 'base': 'Kick'})


def test_generated_max_host_has_file_transport_without_udp(tmp_path, monkeypatch):
    monkeypatch.setenv('TACTUS_ABLETON_STATE_DIR', str(tmp_path / 'state'))
    c = max.build(tmp_path / 'host', role='audio_effect', instance_id='isolated')
    patch = json.loads((tmp_path / 'host' / (c['name']+'.maxpat')).read_text())
    texts = [r['box'].get('text', '') for r in patch['patcher']['boxes']]
    assert not any(t.startswith('udpreceive ') for t in texts)
    assert c['udp_port'] is None
    assert (tmp_path / 'host/agent_m4l_host.js').is_file()


def test_web_reload_materializes_top_level_assets_without_mutating_message(tmp_path, monkeypatch):
    c = config_at(tmp_path)
    generated = tmp_path / 'index.html'
    def webui(identity, spec):
        generated.write_text(spec['html'])
        return {'html_path': str(generated)}
    monkeypatch.setattr(max.agent_m4l, 'write_webui', webui)
    message = {'command': 'web_reload', 'webui': {'id': 'panel', 'html': '<h1>Voice</h1>'}}
    roundtrip(max, c, lambda: max.command(c, message, timeout=1),
              {'event': 'webui_reload', 'changed': 1})
    written = json.loads(c['command_file'].read_text())
    assert written['webui']['html_path'] == str(generated)
    assert generated.read_text() == '<h1>Voice</h1>'
    assert 'html_path' not in message['webui']


def test_max_update_accepts_durable_reload_marker_after_webui_status(tmp_path):
    c = config_at(tmp_path)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(max.command, c, {'command': 'update', 'patch': {'objects': []}},
                             timeout=.2)
        deadline = time.monotonic() + 1
        while not c['command_file'].exists():
            assert time.monotonic() < deadline
            time.sleep(.002)
        payload = json.loads(c['command_file'].read_text())
        c['status_file'].write_text(json.dumps({'command_id': payload['id'], 'event': 'set',
                                               'last_reload_command_id': payload['id']}))
        assert future.result()['last_reload_command_id'] == payload['id']
