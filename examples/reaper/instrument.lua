-- Authored ReaSynth phrase; shared audio.render owns the project tab and render.
local project = reaper.EnumProjects(-1, '')
reaper.SetCurrentBPM(project, 120, false)
reaper.InsertTrackAtIndex(0, true)
local track = reaper.GetTrack(project, 0)
reaper.GetSetMediaTrackInfo_String(track, 'P_NAME', 'Lead', true)
reaper.SetMediaTrackInfo_Value(track, 'D_VOL', 0.32)
assert(reaper.TrackFX_AddByName(track, 'ReaSynth (Cockos)', false, -1) >= 0)
local item = reaper.CreateNewMIDIItemInProj(track, 0, args.seconds, false)
local take = reaper.GetActiveTake(item)
for _, note in ipairs(args.notes) do
  reaper.MIDI_InsertNote(take, false, false,
    reaper.MIDI_GetPPQPosFromProjTime(take, note[1]),
    reaper.MIDI_GetPPQPosFromProjTime(take, note[1] + note[3]),
    0, note[2], note[4], true)
end
reaper.MIDI_Sort(take)
