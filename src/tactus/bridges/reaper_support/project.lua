-- Shared native project capture/rebuild. Musical edits stay in author code.
local function inspect(project)
  local _, path = reaper.EnumProjects(-1, '')
  local a,b = reaper.GetSet_LoopTimeRange2(project,false,false,0,0,false)
  local num,denom,bpm = reaper.TimeMap_GetTimeSigAtTime(project,0)
  local result = {instance=tostring(project),
    path=path,change_count=reaper.GetProjectStateChangeCount(project),
    play_state=reaper.GetPlayStateEx(project),
    version=reaper.GetAppVersion(),tempo=bpm,meter={num,denom},
    cursor=reaper.GetCursorPositionEx(project),time_selection={a,b},tracks={},media={}}
  local chunks={}
  local function remember(track)
    local ok,chunk=reaper.GetTrackStateChunk(track,'',false)
    assert(ok,'Could not inspect native track state')
    chunks[#chunks+1]=chunk
  end
  remember(reaper.GetMasterTrack(project))
  for i=0,reaper.CountTracks(project)-1 do
    local track=reaper.GetTrack(project,i)
    remember(track)
    local _,name=reaper.GetTrackName(track)
    local row={guid=reaper.GetTrackGUID(track),name=name,fx={},items=0,
      gain=reaper.GetMediaTrackInfo_Value(track,'D_VOL'),
      selected=reaper.IsTrackSelected(track)}
    for f=0,reaper.TrackFX_GetCount(track)-1 do
      local _,fxname=reaper.TrackFX_GetFXName(track,f,'')
      row.fx[#row.fx+1]={name=fxname,enabled=reaper.TrackFX_GetEnabled(track,f)}
    end
    for j=0,reaper.CountTrackMediaItems(track)-1 do
      row.items=row.items+1
      local item=reaper.GetTrackMediaItem(track,j)
      for k=0,reaper.CountTakes(item)-1 do
        local take=reaper.GetTake(item,k)
        local source=reaper.GetMediaItemTake_Source(take)
        assert(source,'Take source unavailable')
        local _,id=reaper.GetSetMediaItemTakeInfo_String(take,'GUID','',false)
        local root=source
        while reaper.GetMediaSourceParent(root) do root=reaper.GetMediaSourceParent(root) end
        local file=reaper.GetMediaSourceFileName(root,'')
        local kind=reaper.GetMediaSourceType(root,'')
        result.media[#result.media+1]={take=id,file=file,kind=kind,
          wrapped=(root~=source),inline_midi=(file=='' and reaper.TakeIsMIDI(take))}
      end
    end
    result.tracks[#result.tracks+1]=row
  end
  -- Native setters need not advance the project change counter. Compare actual
  -- serialized tracks (including MIDI/FX/routing/envelopes), markers and tempo.
  for i=0,reaper.CountProjectMarkers(project)-1 do
    local _,region,pos,ending,name,id,color=reaper.EnumProjectMarkers3(project,i)
    chunks[#chunks+1]=string.format('%s:%.17g:%.17g:%q:%d:%d',
      tostring(region),pos,ending,name,id,color)
  end
  for i=0,reaper.CountTempoTimeSigMarkers(project)-1 do
    local _,time,measure,beat,tempo,n,d,linear=reaper.GetTempoTimeSigMarker(project,i)
    chunks[#chunks+1]=string.format('%.17g:%d:%.17g:%.17g:%d:%d:%s',
      time,measure,beat,tempo,n,d,tostring(linear))
  end
  result.native_state=table.concat(chunks,'\0')
  return result
end

local function current_matches(expected)
  local p,path=reaper.EnumProjects(-1,'')
  assert(tostring(p)==expected.instance and path==expected.path,
    'Active project changed; inspect again')
  assert(reaper.GetProjectStateChangeCount(p)==expected.change_count,
    'Project changed; inspect again before capture')
  assert(inspect(p).native_state==expected.native_state,
    'Project changed; inspect again before capture')
  assert(reaper.GetPlayStateEx(p)==0,'Stop transport before capture')
  return p
end

local function private_project(path, operation)
  local previous=reaper.EnumProjects(-1,'')
  reaper.Main_OnCommand(41929,0) -- New project tab, ignore template
  local private=reaper.EnumProjects(-1,'')
  assert(private~=previous,'Could not create private project tab')
  local ok,result=xpcall(function()
    reaper.Main_openProject(path)
    return operation(private)
  end,debug.traceback)
  if ok then
    -- Successful operations leave a saved, clean private tab. Errors retain it
    -- for inspection; never dismiss a dialog or discard an unknown live project.
    reaper.Main_OnCommand(40860,0) -- Close current project tab
  end
  reaper.SelectProjectInstance(previous)
  assert(ok,result)
  return result
end

if args.mode=='inspect' then
  return inspect(reaper.EnumProjects(-1,''))
elseif args.mode=='capture' then
  local live=current_matches(args.expected)
  reaper.Main_SaveProjectEx(live,args.project,0) -- save copy, retain live filename
  return private_project(args.project,function(p)
    -- SetMediaItemTake_Source changes only the copy. Item/take offsets, rates,
    -- MIDI, FX, routing and automation remain native project data.
    for i=0,reaper.CountMediaItems(p)-1 do
      local item=reaper.GetMediaItem(p,i)
      for k=0,reaper.CountTakes(item)-1 do
        local take=reaper.GetTake(item,k)
        local _,id=reaper.GetSetMediaItemTakeInfo_String(take,'GUID','',false)
        local file=args.files[id]
        if file then
          local source=assert(reaper.PCM_Source_CreateFromFile(file),'Cannot load copied media')
          reaper.SetMediaItemTake_Source(take,source)
        end
      end
    end
    reaper.Main_SaveProjectEx(p,args.project,8)
    return inspect(p)
  end)
elseif args.mode=='verify' then
  return private_project(args.project,inspect)

else
  error('Unknown project recipe mode')
end
