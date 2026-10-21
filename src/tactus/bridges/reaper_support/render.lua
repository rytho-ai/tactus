-- Shared private-tab offline render. Setup, duration/rate/channels stay explicit.
local previous = reaper.EnumProjects(-1, '')
reaper.Main_OnCommand(41929, 0) -- New tab, ignore default template
local project = reaper.EnumProjects(-1, '')
assert(project ~= previous, 'Could not create private project tab')
local ok, result = xpcall(function()
  local env = setmetatable({args=args.data}, {__index=function(_, key)
    if key == 'args' then return nil end
    return _ENV[key]
  end})
  local setup, err = load(args.setup, '@tactus-authored-render', 't', env)
  assert(setup, err)
  setup()
  assert(reaper.EnumProjects(-1, '') == project, 'Setup changed the owned project tab')
  for key,value in pairs({PROJECT_SRATE=args.rate,PROJECT_SRATE_USE=1,
    RENDER_SRATE=args.rate,RENDER_CHANNELS=args.channels,RENDER_BOUNDSFLAG=0,
    RENDER_STARTPOS=0,RENDER_ENDPOS=args.seconds,RENDER_SETTINGS=0,
    RENDER_TAILFLAG=0,RENDER_DITHER=0,RENDER_NORMALIZE=0}) do
    reaper.GetSetProjectInfo(project,key,value,true)
  end
  reaper.GetSetProjectInfo_String(project,'RENDER_FORMAT','ZXZhdxgAAQ==',true)
  reaper.GetSetProjectInfo_String(project,'RENDER_FILE',args.out,true)
  reaper.GetSetProjectInfo_String(project,'RENDER_PATTERN','audio',true)
  reaper.Main_SaveProjectEx(project,args.out .. '/render.rpp',8)
  reaper.Main_OnCommand(42230,0) -- Render with settings and auto-close dialog
  reaper.Main_SaveProjectEx(project,args.out .. '/render.rpp',8)
  reaper.Main_OnCommand(40860,0) -- Only successful saved private tab is closed
  return {version=reaper.GetAppVersion()}
end, debug.traceback)
reaper.SelectProjectInstance(previous)
assert(ok, result)
return result
