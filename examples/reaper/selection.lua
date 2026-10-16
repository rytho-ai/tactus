-- A work-local recipe: one selected inline MIDI take, authored notes, native Undo.
local project,path=reaper.EnumProjects(-1,'')
local function selected()
  assert((reaper.GetPlayStateEx(project)&4)==0,'Recording is active; defer this edit')
  assert(reaper.CountSelectedMediaItems(project)==1,'Select exactly one MIDI item')
  local item=reaper.GetSelectedMediaItem(project,0)
  assert(reaper.CountTakes(item)==1,'This recipe expects a single-take MIDI item')
  local take=reaper.GetActiveTake(item)
  assert(take and reaper.TakeIsMIDI(take),'Select an inline MIDI item')
  local source=reaper.GetMediaItemTake_Source(take)
  assert(reaper.GetMediaSourceFileName(source,'')=='','Use in-project MIDI, not an external MIDI file')
  assert(reaper.GetMediaItemTakeInfo_Value(take,'D_PLAYRATE')==1 and
    reaper.GetMediaItemTakeInfo_Value(take,'D_STARTOFFS')==0,
    'This recipe expects rate 1 and source offset 0')
  local first,last=reaper.GetSet_LoopTimeRange2(project,false,false,0,0,false)
  local position=reaper.GetMediaItemInfo_Value(item,'D_POSITION')
  local finish=position+reaper.GetMediaItemInfo_Value(item,'D_LENGTH')
  assert(first<last and first>=position-1e-9 and last<=finish+1e-9,
    'Set a nonempty time selection inside the selected MIDI item')
  local length,is_qn=reaper.GetMediaSourceLength(source)
  if reaper.GetMediaItemInfo_Value(item,'B_LOOPSRC')~=0 then
    assert(is_qn and reaper.TimeMap2_timeToQN(project,finish)-
      reaper.TimeMap2_timeToQN(project,position)<=length+1e-9,
      'Repeated MIDI sources need a separate editing recipe')
  end
  local ok,chunk=reaper.GetItemStateChunk(item,'',false);assert(ok,'Cannot inspect MIDI item')
  -- REAPER serializes inline source-pool identities in its native item state.
  -- Require a recognizable single source, then reject aliases anywhere in this project.
  local pool=chunk:match('\n%s*POOLEDEVTS%s+(%b{})')
  assert(pool,'Unsupported inline MIDI source state')
  assert(not chunk:match('\n%s*POOLEDEVTS%s+%b{}.-\n%s*POOLEDEVTS%s+%b{}'),
    'This recipe expects one inline source')
  for i=0,reaper.CountMediaItems(project)-1 do
    local other=reaper.GetMediaItem(project,i)
    if other~=item then
      local success,state=reaper.GetItemStateChunk(other,'',false);assert(success)
      for id in state:gmatch('\n%s*POOLEDEVTS%s+(%b{})') do
        assert(id~=pool,'Shared pooled MIDI must be made independent before this recipe')
      end
    end
  end
  return item,take,chunk,first,last
end

local function notes_in(take,first,last)
  local rows,indices,retained={},{},{}
  local _,count=reaper.MIDI_CountEvts(take)
  for i=0,count-1 do
    local ok,sel,mute,start,finish,channel,pitch,velocity=reaper.MIDI_GetNote(take,i)
    assert(ok)
    local a,b=reaper.MIDI_GetProjTimeFromPPQPos(take,start),
      reaper.MIDI_GetProjTimeFromPPQPos(take,finish)
    if a>=first-1e-9 and b<=last+1e-9 then
      rows[#rows+1]={start_qn=reaper.MIDI_GetProjQNFromPPQPos(take,start),
        end_qn=reaper.MIDI_GetProjQNFromPPQPos(take,finish),pitch=pitch,
        velocity=velocity,channel=channel,selected=sel,muted=mute}
      indices[#indices+1]=i
    else
      retained[#retained+1]={start=start,finish=finish,channel=channel,pitch=pitch}
    end
  end
  return rows,indices,retained
end

if args.mode=='read' then
  local item,take,chunk,first,last=selected()
  local rows,indices,retained=notes_in(take,first,last)
  assert(#rows>0,'No fully contained notes in the time selection')
  local track=reaper.GetMediaItemTrack(item)
  local _,name=reaper.GetTrackName(track)
  local a,b=reaper.TimeMap2_timeToQN(project,first),reaper.TimeMap2_timeToQN(project,last)
  -- One outstanding inspection in this copyable example; a new read supersedes it.
  _G.tactus_selected_midi={token=args.token,project=project,item=item,take=take,chunk=chunk,
    first=first,last=last,first_qn=a,last_qn=b,indices=indices,retained=retained}
  return {token=args.token,project=path,track=name,track_guid=reaper.GetTrackGUID(track),
    item_guid=({reaper.GetSetMediaItemInfo_String(item,'GUID','',false)})[2],
    take_guid=({reaper.GetSetMediaItemTakeInfo_String(take,'GUID','',false)})[2],
    range_s={first,last},range_qn={a,b},notes=rows}
end

assert(args.mode=='apply','Use read or apply')
local saved=_G.tactus_selected_midi
assert(saved and saved.token==args.token,'Inspection expired; inspect the live selection again')
assert(project==saved.project,'Active project changed; inspect again')
assert(reaper.CountSelectedMediaItems(project)==1 and
  reaper.GetSelectedMediaItem(project,0)==saved.item and
  reaper.GetActiveTake(saved.item)==saved.take,'Selected MIDI item changed; inspect again')
local item,take,chunk,first,last=selected()
assert(item==saved.item and take==saved.take,'Selected MIDI item changed; inspect again')
assert(first==saved.first and last==saved.last,'Time selection changed; inspect again')
assert(chunk==saved.chunk,'MIDI item changed; inspect again')
assert(reaper.TimeMap2_timeToQN(project,first)==saved.first_qn and
  reaper.TimeMap2_timeToQN(project,last)==saved.last_qn,'Musical time changed; inspect again')

local prepared={}
local low,high=reaper.MIDI_GetPPQPosFromProjTime(take,first),
  reaper.MIDI_GetPPQPosFromProjTime(take,last)
for _,n in ipairs(args.notes) do
  local start=math.floor(reaper.MIDI_GetPPQPosFromProjQN(take,n.start_qn)+.5)
  local finish=math.floor(reaper.MIDI_GetPPQPosFromProjQN(take,n.end_qn)+.5)
  assert(start>=low-1e-7 and finish<=high+1e-7 and finish>start,
    'Rounded MIDI ticks fall outside the selection or have zero length')
  local row={start=start,finish=finish,channel=n.channel,pitch=n.pitch,
    velocity=n.velocity,selected=n.selected,muted=n.muted}
  for _,old in ipairs(saved.retained) do
    assert(old.channel~=row.channel or old.pitch~=row.pitch or
      old.finish<=row.start or row.finish<=old.start,'Note overlaps retained same-pitch MIDI')
  end
  for _,old in ipairs(prepared) do
    assert(old.channel~=row.channel or old.pitch~=row.pitch or
      old.finish<=row.start or row.finish<=old.start,'Overlapping same-pitch proposed notes')
  end
  prepared[#prepared+1]=row
end
reaper.Undo_BeginBlock2(project)
local ok,err=xpcall(function()
  for i=#saved.indices,1,-1 do assert(reaper.MIDI_DeleteNote(take,saved.indices[i])) end
  for _,n in ipairs(prepared) do
    assert(reaper.MIDI_InsertNote(take,n.selected,n.muted,n.start,n.finish,
      n.channel,n.pitch,n.velocity,true))
  end
  reaper.MIDI_Sort(take)
  reaper.UpdateArrange()
end,debug.traceback)
reaper.Undo_EndBlock2(project,'Tactus: vary selected MIDI',4) -- UNDO_STATE_ITEMS
_G.tactus_selected_midi=nil
assert(ok,err)
return {removed=#saved.indices,inserted=#prepared,range_qn={saved.first_qn,saved.last_qn},
  undo='Tactus: vary selected MIDI'}
