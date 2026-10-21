"""Opt-in real FX guards: a separate muted test project, never the user's FX."""

import copy
import os
from pathlib import Path

import pytest

from tactus.bridges import reaper
from tactus.bridges.reaper_support import devices

LIVE = os.environ.get('TACTUS_REAPER_RESOURCE_PATH')


def native(code, args=None):
    return reaper.execute(code, resource_path=LIVE, args=args)


@pytest.fixture
def fx(tmp_path):
    if not LIVE:
        pytest.skip('Opt in with an isolated TACTUS_REAPER_RESOURCE_PATH')
    fixture = native('''
_G.tactus_fx_test_previous=reaper.EnumProjects(-1,'')
reaper.Main_OnCommand(41929,0)
reaper.InsertTrackAtIndex(0,true)
local t=reaper.GetTrack(0,0)
reaper.SetMediaTrackInfo_Value(t,'B_MUTE',1)
local fx=reaper.TrackFX_AddByName(t,'ReaSynth (Cockos)',false,-1)
assert(fx>=0,'Fixture needs ReaSynth')
_G.tactus_fx_test_path=args.path
reaper.Main_SaveProjectEx(0,args.path,8)
return {track_guid=reaper.GetTrackGUID(t),fx_guid=reaper.TrackFX_GetFXGUID(t,fx)}
''', {'path': str(tmp_path / 'fx.rpp')})
    try:
        yield fixture
    finally:
        native('''
reaper.Main_SaveProjectEx(0,_G.tactus_fx_test_path,8)
reaper.Main_OnCommand(40860,0) -- close the saved isolated fixture, without a dialog
reaper.SelectProjectInstance(_G.tactus_fx_test_previous)
return true
''')


def inspect(fx, **kw):
    return devices.inspect(resource_path=LIVE, **fx, **kw)


def test_native_cache_fresh_values_compact_readback_and_undo(fx):
    a = inspect(fx, parameters=[0, 1, 2])
    original_name = a['parameters'][0]['name']
    a['parameters'][0]['name'] = 'caller mutation'
    b = inspect(fx, parameters=[0, 1, 2])
    assert b['metadata_cached'] and b['parameters'][0]['name'] == original_name
    changed = devices.configure(b, {'0': .2, '1': .3, '2': .4}, resource_path=LIVE)
    assert 'parameters' not in changed
    assert changed['values'] == pytest.approx({'0': .2, '1': .3, '2': .4})
    assert native("return reaper.Undo_CanUndo2(0)") == 'Configure inspected FX'
    native('assert(reaper.Undo_DoUndo2(0));return true')
    assert inspect(fx, parameters=[0, 1, 2], metadata=False)['values'] == b['values']


@pytest.mark.parametrize('change,message', [
    ("reaper.TrackFX_SetParamNormalized(t,0,0,.8)", 'value changed'),
    ("reaper.TrackFX_Delete(t,0)", 'no longer'),
    ("reaper.TrackFX_Delete(t,0);reaper.TrackFX_AddByName(t,'ReaSynth (Cockos)',false,-1)",
     'no longer'),
])
def test_native_external_edit_or_replaced_fx_rejects(fx, change, message):
    s = inspect(fx, parameters=[0, 1])
    native('local t=reaper.GetTrack(0,0);' + change + ';return true')
    before = native("local _,s=reaper.GetTrackStateChunk(reaper.GetTrack(0,0),'',false);return s")
    with pytest.raises(reaper.BridgeError, match=message):
        devices.configure(s, {'1': .5}, resource_path=LIVE)
    assert native("local _,s=reaper.GetTrackStateChunk(reaper.GetTrack(0,0),'',false);return s") == before


@pytest.mark.parametrize('bad', [True, -.1, 1.1, '0.3'])
def test_native_batch_preflights_invalid_final_edit_before_any_write(fx, bad):
    s = inspect(fx, parameters=[0, 1])
    with pytest.raises(reaper.BridgeError, match='Invalid normalized'):
        devices.configure_many([{'snapshot': s, 'values': {'0': .2}},
                                {'snapshot': s, 'values': {'1': bad}}], resource_path=LIVE)
    assert inspect(fx, parameters=[0, 1])['values'] == s['values']


def test_native_guard_lifetime_refresh_project_unobserved_and_duplicate(fx):
    s = inspect(fx, parameters=[0])
    with pytest.raises(reaper.BridgeError, match='inspected parameters'):
        devices.configure(s, {'1': .2}, resource_path=LIVE)
    with pytest.raises(reaper.BridgeError, match='same parameter twice'):
        devices.configure_many([{'snapshot': s, 'values': {'0': .2}}] * 2, resource_path=LIVE)
    wrong_project = copy.deepcopy(s)
    wrong_project['project'] = 'different project'
    with pytest.raises(reaper.BridgeError, match='Active project changed'):
        devices.configure(wrong_project, {'0': .2}, resource_path=LIVE)
    inspect(fx, parameters=[0], refresh=True)
    with pytest.raises(reaper.BridgeError, match='layout changed'):
        devices.configure(s, {'0': .2}, resource_path=LIVE)
    s = inspect(fx, parameters=[0])
    native('_G.tactus_fx_descriptors=nil;return true')
    with pytest.raises(reaper.BridgeError, match='inspection expired'):
        devices.configure(s, {'0': .2}, resource_path=LIVE)
    assert inspect(fx, parameters=[0])['values'] == s['values']


def test_native_master_fx_uses_its_exact_guid(fx):
    master = native('''
local t=reaper.GetMasterTrack(0)
local fx=reaper.TrackFX_AddByName(t,'ReaSynth (Cockos)',false,-1)
assert(fx>=0)
return {track_guid=reaper.GetTrackGUID(t),fx_guid=reaper.TrackFX_GetFXGUID(t,fx)}
''')
    s = inspect(master, parameters=[0])
    assert devices.configure(s, {'0': .2}, resource_path=LIVE)['values']['0'] == pytest.approx(.2)


def test_native_setter_error_reports_partial_changes_without_retry(fx):
    s = inspect(fx, parameters=[0, 1])
    result = native('''
local setter=reaper.TrackFX_SetParamNormalized
local calls=0
reaper.TrackFX_SetParamNormalized=function(track,fx,index,value)
 calls=calls+1
 if index==1 then return false end
 return setter(track,fx,index,value)
end
local chunk=assert(load(args.source,'fixture-device-access','t',
 setmetatable({args={mode='configure',edits=args.edits}},{__index=_G})))
local ok,message=pcall(chunk)
reaper.TrackFX_SetParamNormalized=setter
assert(not ok and message:find('partial changes'))
return {calls=calls,first=reaper.TrackFX_GetParamNormalized(reaper.GetTrack(0,0),0,0),
 second=reaper.TrackFX_GetParamNormalized(reaper.GetTrack(0,0),0,1)}
''', {'source': Path(devices.__file__).with_suffix('.lua').read_text(),
      'edits': [{'snapshot': s, 'values': {'0': .2}},
                {'snapshot': s, 'values': {'1': .3}}]})
    assert result['calls'] == 2 and result['first'] == pytest.approx(.2)
    assert result['second'] == s['values']['1']
