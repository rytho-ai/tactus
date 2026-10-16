-- Work-authored REAPER instrument. `args` comes from Python; times are seconds.
-- Creates its own tab and restores the selected tab after rendering. Uses ReaSynth.
local previous = reaper.EnumProjects(-1, '')
reaper.Main_OnCommand(41929, 0) -- Ignore default template
local project = reaper.EnumProjects(-1, '')
local ok, result = xpcall(function()
  assert(project ~= previous and reaper.CountTracks(project) == 0)
  reaper.SetCurrentBPM(project, 120, false)
  reaper.GetSetProjectInfo(project, 'PROJECT_SRATE', args.rate, true)
  reaper.GetSetProjectInfo(project, 'PROJECT_SRATE_USE', 1, true)
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
  reaper.GetSetProjectInfo(project, 'RENDER_SRATE', args.rate, true)
  reaper.GetSetProjectInfo(project, 'RENDER_CHANNELS', 2, true)
  reaper.GetSetProjectInfo(project, 'RENDER_BOUNDSFLAG', 0, true)
  reaper.GetSetProjectInfo(project, 'RENDER_STARTPOS', 0, true)
  reaper.GetSetProjectInfo(project, 'RENDER_ENDPOS', args.seconds, true)
  reaper.GetSetProjectInfo(project, 'RENDER_SETTINGS', 0, true)
  reaper.GetSetProjectInfo(project, 'RENDER_TAILFLAG', 0, true)
  reaper.GetSetProjectInfo(project, 'RENDER_DITHER', 0, true)
  reaper.GetSetProjectInfo(project, 'RENDER_NORMALIZE', 0, true)
  reaper.GetSetProjectInfo_String(project, 'RENDER_FORMAT', 'ZXZhdxgAAQ==', true)
  reaper.GetSetProjectInfo_String(project, 'RENDER_FILE', args.out, true)
  reaper.GetSetProjectInfo_String(project, 'RENDER_PATTERN', 'lead', true)
  reaper.Main_SaveProjectEx(project, args.out .. '/instrument.rpp', 8)
  reaper.Main_OnCommand(42230, 0) -- Native render using settings, auto-close dialog
  return {version = reaper.GetAppVersion(), track = reaper.GetTrackGUID(track)}
end, debug.traceback)
reaper.SelectProjectInstance(previous)
assert(ok, result)
return result
