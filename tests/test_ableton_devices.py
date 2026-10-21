"""Device semantics through the native owner; actual native latency is measured separately."""

import ast
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_ableton_state import Native, host  # noqa: F401 - reuse the native reader fixture

from tactus.bridges.TactusBridge.devices import DeviceAccess


@pytest.fixture
def access(host):  # noqa: F811 - pytest injects the imported fixture
    p = host.device._parameters[0]
    p.is_enabled = True
    p.str_for_value = lambda value: str(value)
    host.device._parameters.append(Native(name='Mode', min=0, max=1, value=0,
        is_enabled=True, is_quantized=True, value_items=('Off', 'On'),
        str_for_value=lambda value: ('Off', 'On')[int(value)]))
    def item(name, uri, children=(), loadable=True):
        return SimpleNamespace(name=name, uri=uri, children=list(children),
                               is_loadable=loadable, is_device=True)
    preset = item('Soft preset', 'file:preset')
    device = item('Chosen FX', 'device:fx', [preset])
    browser = Native(observable=('full_refresh',), hotswap_target=None,
                     audio_effects=item('Audio Effects', 'root', [device], False))
    host.app.browser = browser
    host.state.devices.close()
    host.state.devices = DeviceAccess(host.state)
    return SimpleNamespace(api=host.state.devices, host=host, p=p,
                           mode=host.device._parameters[1], browser=browser)


def inspect(a, names=None, metadata=True):
    return a.api.inspect(str(a.host.lead._live_ptr), str(a.host.device._live_ptr), names, metadata)


def test_cache_contains_only_descriptions_and_returns_isolated_copies(access):
    a = access
    first = inspect(a)
    assert not first['metadata_cached']
    first['parameters'][0]['name'] = 'poisoned'
    a.p.value = .7
    second = inspect(a)
    assert second['metadata_cached'] and second['values']['Cutoff'] == .7
    assert second['parameters'][0]['name'] == 'Cutoff'
    assert a.api.stats()['schema_builds'] == 1
    assert a.api.stats()['schema_hits'] == 1
    short = inspect(a, ['Cutoff'], metadata=False)
    assert 'parameters' not in short and short['values'] == {'Cutoff': .7}
    assert a.host.reads == []  # No notes or media vectors needed.


@pytest.mark.parametrize('change', ['value', 'name', 'range', 'items', 'identity', 'device'])
def test_fresh_preconditions_reject_changed_value_layout_or_target(access, change):
    a = access
    before = inspect(a)
    if change == 'value': a.p.value = .9
    if change == 'name': a.p.name = 'Another parameter'
    if change == 'range': a.p.max = 2
    if change == 'items': a.mode.value_items = ('No', 'Yes')
    if change == 'identity': a.p._live_ptr += 10000
    if change == 'device': a.host.lead.devices = []
    previous = a.p.value
    with pytest.raises(ValueError, match='changed|no longer'):
        a.api.configure([{'snapshot': before, 'values': {'Cutoff': .6}}])
    assert a.p.value == previous


@pytest.mark.parametrize('bad', [None, True, float('nan'), 1.1, -.1, .5])
def test_invalid_last_parameter_prevents_entire_batch(access, bad):
    a = access
    snapshot = inspect(a)
    with pytest.raises(ValueError, match='Invalid native'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .8, 'Mode': bad}}])
    assert a.p.value == .5 and a.mode.value == 0


def test_disabled_and_unobserved_parameters_are_not_written(access):
    a = access
    snapshot = inspect(a, ['Cutoff'])
    with pytest.raises(ValueError, match='present in'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Mode': 1}}])
    a.p.is_enabled = False
    with pytest.raises(ValueError, match='disabled'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .8}}])
    assert a.p.value == .5


def test_recycled_native_pointer_ids_do_not_authorize_a_replacement(access):
    a = access
    snapshot = inspect(a)
    replacement = Native(name=a.host.device.name, class_name=a.host.device.class_name,
                         can_have_chains=False, parameters=a.host.device._parameters)
    replacement._live_ptr = a.host.device._live_ptr
    a.host.lead.devices = [replacement]
    with pytest.raises(ValueError, match='layout changed'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .8}}])
    assert a.p.value == .5


def test_compact_readback_can_guard_next_edit_and_old_snapshot_is_stale(access):
    a = access
    snapshot = inspect(a, ['Cutoff'])
    result = a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .8}}])[0]
    assert result['values'] == {'Cutoff': .8} and 'parameters' not in result
    with pytest.raises(ValueError, match='value changed'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .6}}])
    assert a.api.configure([{'snapshot': result, 'values': {'Cutoff': .6}}])[0]['values'] == {
        'Cutoff': .6}


def test_batch_checks_every_snapshot_before_first_write_and_rejects_duplicate_writes(access):
    a = access
    snapshot = inspect(a)
    stale = copy.deepcopy(snapshot)
    stale['values']['Mode'] = 1
    with pytest.raises(ValueError, match='changed'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .8}},
                         {'snapshot': stale, 'values': {'Mode': 1}}])
    assert a.p.value == .5
    with pytest.raises(ValueError, match='same parameter twice'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .8}},
                         {'snapshot': snapshot, 'values': {'Cutoff': .6}}])
    assert a.p.value == .5


def test_native_setter_failure_is_not_retried_or_rolled_back(access):
    a = access
    calls = []
    class Failing:
        _live_ptr = 98765
        name, min, max, is_quantized, is_enabled = 'Failure', 0, 1, False, True
        def str_for_value(self, value): return str(value)
        @property
        def value(self): return .4
        @value.setter
        def value(self, value):
            calls.append(value)
            raise RuntimeError('native setter failed')
    a.host.device._parameters.append(Failing())
    snapshot = inspect(a)
    with pytest.raises(RuntimeError, match='native setter failed'):
        a.api.configure([{'snapshot': snapshot, 'values': {'Cutoff': .8, 'Failure': .9}}])
    assert a.p.value == .8 and calls == [.9]


def test_master_device_inspection_does_not_require_track_mute(access):
    a = access
    master = a.host.master
    del master.mute
    master.devices = [a.host.device]
    result = a.api.inspect(str(master._live_ptr), str(a.host.device._live_ptr), ['Cutoff'])
    assert result['values'] == {'Cutoff': .5}


def test_browser_cache_search_copy_isolation_refresh_and_close(access):
    a = access
    first = a.api.browse(recursive=True)
    assert not first['cache_hit'] and [r['name'] for r in first['entries']] == ['Chosen FX']
    first['entries'][0]['path'].append('poison')
    warm = a.api.browse(recursive=True, search='chosen')
    assert warm['cache_hit'] and warm['entries'][0]['path'] == ['audio_effects', 'Chosen FX']
    assert len(a.api.browse(recursive=True, include_presets=True)['entries']) == 2
    a.browser.emit('full_refresh')
    assert not a.api.browse(recursive=True)['cache_hit']
    assert not a.api.browse(recursive=True, refresh=True)['cache_hit']
    a.host.state.close()
    assert not a.browser.listeners['full_refresh']
    assert a.api.stats()['cached_catalogs'] == a.api.stats()['cached_schemas'] == 0
    with pytest.raises(RuntimeError, match='closed'):
        a.api.browse()


def test_fresh_browser_resolution_can_disambiguate_uri_but_never_uses_cached_target(access):
    a = access
    a.api.browse()
    a.browser.audio_effects.children.append(SimpleNamespace(name='Chosen FX', uri='other',
        is_loadable=True, is_device=True, children=[]))
    with pytest.raises(ValueError, match='ambiguous'):
        a.api._browser_node(['audio_effects', 'Chosen FX'])
    assert a.api._browser_node(['audio_effects', 'Chosen FX'], 'other').uri == 'other'


def test_standalone_module_is_valid_embedded_python37():
    source = Path(__file__).parents[1] / 'src/tactus/bridges/TactusBridge/devices.py'
    ast.parse(source.read_text(), feature_version=(3, 7))


def test_append_waits_without_writing_then_configures_once_with_readback(access):
    a = access
    track = a.host.lead
    track_id, device_id = str(track._live_ptr), str(a.host.device._live_ptr)
    assert a.api.finish_append(track_id, [device_id], {'Cutoff': .8}) == {'pending': True}
    assert a.p.value == .5
    track.devices = []
    a.browser.load_item = lambda item: track.devices.append(a.host.device)
    a.api.begin_append(['audio_effects', 'Chosen FX'], track_id, [])
    result = a.api.finish_append(track_id, [], {'Cutoff': .8}, metadata=True)
    assert not result['pending'] and result['device']['id'] == device_id
    assert result['device']['snapshot']['values'] == {'Cutoff': .8}
    assert result['device']['snapshot']['parameters'][0]['name'] == 'Cutoff'
    with pytest.raises(ValueError, match='chain changed'):
        a.api.finish_append(track_id, ['different'])


def test_new_reader_epoch_or_cache_eviction_expires_old_snapshots(access):
    a = access
    s = inspect(a)
    a.host.state.instance = 'another-set-epoch'
    with pytest.raises(ValueError, match='expired'):
        a.api.configure([{'snapshot': s, 'values': {'Cutoff': .8}}])


    a.host.state.instance = s['instance']
    for index in range(33):
        device = Native(name='FX', class_name='Fx', parameters=a.host.device._parameters)
        a.api._layout(device)
    assert len(a.api._targets) == 32
    with pytest.raises(ValueError, match='layout changed'):
        a.api.configure([{'snapshot': s, 'values': {'Cutoff': .8}}])
    a.host.state.close()
    with pytest.raises(RuntimeError, match='closed'):
        a.api.configure([{'snapshot': s, 'values': {'Cutoff': .8}}])


def test_closed_device_owner_cannot_repopulate_caches_in_a_live_reader(access):
    a = access
    assert not a.host.state._closed
    a.api.close()
    with pytest.raises(RuntimeError, match='closed'):
        inspect(a)
    assert a.api.stats()['cached_schemas'] == 0
