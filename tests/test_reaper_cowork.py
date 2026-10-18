"""Shared selected-MIDI guards preserve live edits outside their explicit scope."""

import os

import pytest

from tactus.bridges import reaper
from tactus.bridges.reaper_support import selection as cowork

LIVE = os.environ.get("TACTUS_REAPER_RESOURCE_PATH")


@pytest.mark.parametrize(
    "notes",
    [
        None,
        [{"pitch": 60}],
        [{"start_qn": 2, "end_qn": 3, "pitch": True, "velocity": 80}],
        [{"start_qn": 2, "end_qn": 3, "pitch": 128, "velocity": 80}],
        [{"start_qn": 2, "end_qn": 3, "pitch": 60, "velocity": 0}],
        [{"start_qn": 2, "end_qn": 3, "pitch": 60, "velocity": 80, "channel": 16}],
        [{"start_qn": 2, "end_qn": 3, "pitch": 60, "velocity": 80, "muted": 1}],
        [{"start_qn": float("nan"), "end_qn": 3, "pitch": 60, "velocity": 80}],
        [{"start_qn": 0, "end_qn": 3, "pitch": 60, "velocity": 80}],
        [{"start_qn": 2, "end_qn": 2, "pitch": 60, "velocity": 80}],
        [{"start_qn": 2, "end_qn": 9, "pitch": 60, "velocity": 80}],
    ],
)
def test_bad_authored_notes_do_not_contact_live_host(monkeypatch, notes):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("The live project must not be touched")

    monkeypatch.setattr(cowork, "_execute", unexpected)
    with pytest.raises((TypeError, ValueError)):
        cowork.replace_notes({"token": "a", "range_qn": [1, 8]}, notes, resource_path="unused")


SETUP = """
reaper.Main_OnCommand(41929,0)
local p=reaper.EnumProjects(-1,'')
reaper.SetCurrentBPM(p,96,false)
for i,name in ipairs({'Unspecified lead','Another part'}) do
 reaper.InsertTrackAtIndex(i-1,true)
 reaper.GetSetMediaTrackInfo_String(reaper.GetTrack(p,i-1),'P_NAME',name,true)
end
local track=reaper.GetTrack(p,0)
reaper.TrackFX_AddByName(track,'ReaSynth (Cockos)',false,-1)
local item=reaper.CreateNewMIDIItemInProj(track,5,25,false)
local take=reaper.GetActiveTake(item)
local rows={{9,9.5,48},{15.5,16.5,70},{16.5,17,60},{18,18.5,64},
 {22,22.75,67},{26,27,65},{30,31,62},{31.5,32.5,71},{33,33.5,50}}
for _,n in ipairs(rows) do
 assert(reaper.MIDI_InsertNote(take,false,false,
  reaper.MIDI_GetPPQPosFromProjQN(take,n[1]),reaper.MIDI_GetPPQPosFromProjQN(take,n[2]),
  0,n[3],80,true))
end
assert(reaper.MIDI_InsertCC(take,false,false,reaper.MIDI_GetPPQPosFromProjQN(take,19),176,0,11,65))
assert(reaper.MIDI_InsertTextSysexEvt(take,false,false,
 reaper.MIDI_GetPPQPosFromProjQN(take,21),1,'keep this text'))
reaper.MIDI_Sort(take)
local other=reaper.CreateNewMIDIItemInProj(reaper.GetTrack(p,1),0,5,false)
reaper.MIDI_InsertNote(reaper.GetActiveTake(other),false,false,0,480,0,36,70,false)
reaper.SelectAllMediaItems(p,false)
reaper.SetMediaItemSelected(item,true)
reaper.GetSet_LoopTimeRange2(p,true,false,10,20,false)
reaper.Main_SaveProjectEx(p,args.path,8)
_G.tactus_cowork_test={project=p,track=track,item=item,take=take,other=other}
return {path=args.path}
"""

READ = """
local f=_G.tactus_cowork_test
local rows,cc,text={},{},{}
local _,n,c,t=reaper.MIDI_CountEvts(f.take)
for i=0,n-1 do
 local _,sel,mute,a,b,ch,pitch,vel=reaper.MIDI_GetNote(f.take,i)
 rows[#rows+1]={a,b,ch,pitch,vel,sel,mute}
end
for i=0,c-1 do cc[#cc+1]={reaper.MIDI_GetCC(f.take,i)} end
for i=0,t-1 do text[#text+1]={reaper.MIDI_GetTextSysexEvt(f.take,i)} end
local fx={}
for i=0,reaper.TrackFX_GetNumParams(f.track,0)-1 do
 fx[#fx+1]=reaper.TrackFX_GetParamNormalized(f.track,0,i)
end
local _,other=reaper.GetItemStateChunk(f.other,'',false)
local _,raw=reaper.MIDI_GetAllEvts(f.take)
-- Hex avoids passing arbitrary MIDI bytes through the JSON string transport.
local hex=raw:gsub('.',function(c)return string.format('%02x',c:byte())end)
return {notes=rows,cc=cc,text=text,fx=fx,other=other,raw=hex,
 undo=reaper.Undo_CanUndo2(f.project),time={reaper.GetSet_LoopTimeRange2(f.project,false,false,0,0,false)}}
"""


def native(code, args=None):
    return reaper.execute(code, resource_path=LIVE, args=args)


@pytest.fixture
def session(tmp_path):
    if not LIVE:
        pytest.skip("Opt in with an isolated TACTUS_REAPER_RESOURCE_PATH")
    previous = native("_G.tactus_test_previous=reaper.EnumProjects(-1,'');return true")
    assert previous
    native(SETUP, {"path": str(tmp_path / "selection.rpp")})
    yield
    native("reaper.SelectProjectInstance(_G.tactus_test_previous);return true")


def read():
    return native(READ)


def inspect():
    return cowork.inspect_selection(resource_path=LIVE)


def apply(snapshot, notes):
    return cowork.replace_notes(snapshot, notes, resource_path=LIVE)


def test_live_selected_four_bar_variation_keeps_fx_cc_other_items_and_undo(session):
    snapshot = inspect()
    assert snapshot["range_qn"] == [16, 32] and len(snapshot["notes"]) == 5
    # An unrelated sound-design change after inspection remains authoritative.
    native("reaper.TrackFX_SetParamNormalized(_G.tactus_cowork_test.track,0,0,.02);return true")
    before = read()
    notes = [{**note, "pitch": note["pitch"] + 2} for note in snapshot["notes"]]
    notes.append({"start_qn": 24, "end_qn": 24.5, "pitch": 77, "velocity": 64})
    result = apply(snapshot, notes)
    after = read()
    assert result["removed"] == 5 and result["inserted"] == 6
    for key in ("fx", "cc", "text", "other", "time"):
        assert after[key] == before[key], key
    # Retained indices: notes before, crossing the left edge, crossing right, and after.
    assert after["notes"][:2] == before["notes"][:2]
    assert after["notes"][-2:] == before["notes"][-2:]
    assert after["undo"] == "Tactus: vary selected MIDI"
    with pytest.raises(reaper.BridgeError, match="Inspection expired"):
        apply(snapshot, notes)
    assert native("return reaper.Undo_DoUndo2(_G.tactus_cowork_test.project)")
    undone = read()
    for key in ("notes", "cc", "text", "fx", "other", "time"):
        assert undone[key] == before[key], key


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("reaper.MIDI_SetNote(f.take,2,nil,nil,nil,nil,nil,63,nil,false)", "MIDI item changed"),
        ("reaper.GetSet_LoopTimeRange2(f.project,true,false,11,20,false)", "Time selection changed"),
        ("reaper.SelectAllMediaItems(f.project,false);reaper.SetMediaItemSelected(f.other,true)",
         "Selected MIDI item changed"),
        ("reaper.Main_OnCommand(41929,0)", "Active project changed"),
        ("reaper.SetCurrentBPM(f.project,100,false)", "Musical time changed|Time selection changed"),
    ],
)
def test_live_stale_or_changed_context_rejects_before_mutation(session, change, message):
    snapshot = inspect()
    native("local f=_G.tactus_cowork_test;" + change + ";return true")
    before = read()
    with pytest.raises(reaper.BridgeError, match=message):
        apply(snapshot, snapshot["notes"])
    assert read() == before


def test_live_new_inspection_replaces_previous_snapshot(session):
    first = inspect()
    second = inspect()
    with pytest.raises(reaper.BridgeError, match="Inspection expired"):
        apply(first, first["notes"])
    assert apply(second, second["notes"])["inserted"] == 5


@pytest.mark.parametrize(
    ("note", "message"),
    [
        ({"start_qn": 16, "end_qn": 16.25, "pitch": 70, "velocity": 90}, "retained same-pitch"),
        ({"start_qn": 24, "end_qn": 24.0000001, "pitch": 77, "velocity": 90}, "zero length"),
    ],
)
def test_live_preflight_prevents_boundary_overlap_and_zero_tick_notes(session, note, message):
    snapshot = inspect()
    before = read()
    with pytest.raises(reaper.BridgeError, match=message):
        apply(snapshot, [note])
    assert read() == before


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("reaper.SetMediaItemInfo_Value(f.item,'D_LENGTH',40)", "Repeated MIDI"),
        ("reaper.SetMediaItemTakeInfo_Value(f.take,'D_PLAYRATE',2)", "rate 1"),
        ("reaper.SelectAllMediaItems(f.project,false)", "exactly one MIDI"),
        (("local _,chunk=reaper.GetItemStateChunk(f.item,'',false);"
         "local clone=reaper.AddMediaItemToTrack(f.track);"
         "chunk=chunk:gsub('IGUID %b{}','IGUID '..reaper.genGuid());"
         "reaper.SetItemStateChunk(clone,chunk,false);reaper.SetMediaItemSelected(clone,false)"),
         "Shared pooled MIDI"),
    ],
)
def test_live_unsupported_source_shapes_are_explicit(session, change, message):
    native("local f=_G.tactus_cowork_test;" + change + ";return true")
    with pytest.raises(reaper.BridgeError, match=message):
        inspect()


def test_live_empty_proposal_deletes_only_contained_notes(session):
    snapshot = inspect()
    before = read()
    assert apply(snapshot, [])["inserted"] == 0
    after = read()
    assert len(after["notes"]) == 4
    assert after["notes"] == before["notes"][:2] + before["notes"][-2:]
    assert after["cc"] == before["cc"] and after["text"] == before["text"]
