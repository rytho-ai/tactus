-- Shared native FX inspection and preflight-all parameter batches. No music choices.
local cache=_G.tactus_fx_descriptors
if not cache then
  cache={instance=reaper.genGuid(),entries={},tick=0,builds=0,hits=0}
  _G.tactus_fx_descriptors=cache
end

local function finite(value)
  return type(value)=='number' and value==value and math.abs(value)~=math.huge
end

local function target(track_guid,fx_guid)
  local project=reaper.EnumProjects(-1,'')
  local track
  for i=-1,reaper.CountTracks(project)-1 do
    local candidate=i==-1 and reaper.GetMasterTrack(project) or reaper.GetTrack(project,i)
    if reaper.GetTrackGUID(candidate)==track_guid then track=candidate;break end
  end
  assert(track,'Track is no longer present; inspect again')
  for i=0,reaper.TrackFX_GetCount(track)-1 do
    if reaper.TrackFX_GetFXGUID(track,i)==fx_guid then return project,track,i end
  end
  error('FX is no longer in the target track; inspect again')
end

local function layout(project,track,fx,refresh)
  local key=tostring(project)..reaper.GetTrackGUID(track)..reaper.TrackFX_GetFXGUID(track,fx)
  local count=reaper.TrackFX_GetNumParams(track,fx)
  local names,parts={}, {tostring(count)}
  local _,fxname=reaper.TrackFX_GetFXName(track,fx,'')
  parts[#parts+1]=fxname
  for i=0,count-1 do
    local ok,name=reaper.TrackFX_GetParamName(track,fx,i,'')
    assert(ok,'Cannot read FX parameter name')
    names[i]=name;parts[#parts+1]=string.format('%q',name)
  end
  local fingerprint=table.concat(parts,'\0')
  local prior=cache.entries[key]
  local hit=not refresh and prior and prior.fingerprint==fingerprint
  cache.tick=cache.tick+1
  if not hit then
    local rows={}
    for i=0,count-1 do rows[#rows+1]={index=i,name=names[i],min=0,max=1} end
    prior={fingerprint=fingerprint,schema=reaper.genGuid(),parameters=rows}
    cache.entries[key]=prior;cache.builds=cache.builds+1
  else cache.hits=cache.hits+1 end
  prior.used=cache.tick
  local size,oldest,oldkey=0,math.huge,nil
  for k,row in pairs(cache.entries) do
    size=size+1
    if row.used<oldest then oldest,oldkey=row.used,k end
  end
  if size>32 then cache.entries[oldkey]=nil end
  return prior,count,not not hit,fxname
end

local function indices(requested,count)
  if requested==nil then
    requested={};for i=0,count-1 do requested[#requested+1]=i end
  end
  assert(type(requested)=='table' and #requested>0,'Select nonempty parameter indices')
  local result,seen={},{}
  for _,index in ipairs(requested) do
    assert(type(index)=='number' and index%1==0 and index>=0 and index<count,
      'Invalid zero-based FX parameter index')
    assert(not seen[index],'Select distinct FX parameter indices')
    seen[index]=true;result[#result+1]=index
  end
  return result
end

local function inspect(options)
  local project,track,fx=target(options.track_guid,options.fx_guid)
  local meta,count,hit,name=layout(project,track,fx,options.refresh)
  local selected=indices(options.parameters,count)
  local result={instance=cache.instance,project=tostring(project),
    track_guid=options.track_guid,fx_guid=options.fx_guid,name=name,schema=meta.schema,
    values={},display={},metadata_cached=hit}
  if options.metadata~=false then result.parameters={} end
  for _,index in ipairs(selected) do
    local key=tostring(index)
    result.values[key]=reaper.TrackFX_GetParamNormalized(track,fx,index)
    local ok,display=reaper.TrackFX_GetFormattedParamValue(track,fx,index,'')
    assert(ok,'Cannot read FX parameter display')
    result.display[key]=display
    if result.parameters then
      local row=meta.parameters[index+1]
      -- Return fresh tables; callers must not mutate the native descriptor cache.
      result.parameters[#result.parameters+1]={index=row.index,name=row.name,min=0,max=1}
    end
  end
  return result
end

if args.mode=='inspect' then return inspect(args) end
if args.mode=='stats' then
  local size=0;for _ in pairs(cache.entries) do size=size+1 end
  return {instance=cache.instance,schema_builds=cache.builds,schema_hits=cache.hits,
          cached_schemas=size}
end
assert(args.mode=='configure','Use inspect, configure or stats')
assert(type(args.edits)=='table' and #args.edits>0,'Supply inspected FX edits')
local prepared,observed,written={},{},{}
for _,edit in ipairs(args.edits) do
  assert(type(edit)=='table' and type(edit.snapshot)=='table' and
    type(edit.values)=='table','Each edit needs snapshot and values')
  local s,values=edit.snapshot,edit.values
  assert(s.instance==cache.instance,'FX inspection expired; inspect again')
  local project,track,fx=target(s.track_guid,s.fx_guid)
  assert(tostring(project)==s.project,'Active project changed; inspect again')
  local meta,count=layout(project,track,fx)
  assert(meta.schema==s.schema,'Parameter layout changed; inspect again')
  assert(type(s.values)=='table' and next(s.values),'Snapshot has no observed values')
  local selected={}
  for key,value in pairs(s.values) do
    local index=tonumber(key)
    assert(index and index%1==0 and tostring(index)==key and index>=0 and index<count,
      'Invalid inspected parameter index')
    assert(finite(value) and reaper.TrackFX_GetParamNormalized(track,fx,index)==value,
      'Parameter value changed; inspect again')
    selected[#selected+1]=index
  end
  assert(next(values),'Supply nonempty chosen parameter values')
  for key,value in pairs(values) do
    assert(s.values[key]~=nil,'Update only inspected parameters')
    assert(finite(value) and value>=0 and value<=1,'Invalid normalized parameter value')
    local identity=s.track_guid..s.fx_guid..':'..key
    assert(not written[identity],'A batch cannot write the same parameter twice')
    written[identity]=true
    prepared[#prepared+1]={track=track,fx=fx,index=tonumber(key),value=value}
  end
  observed[#observed+1]={track_guid=s.track_guid,fx_guid=s.fx_guid,
    parameters=selected,metadata=false}
end
for _,row in ipairs(prepared) do
  assert(reaper.TrackFX_SetParamNormalized(row.track,row.fx,row.index,row.value),
    'Native FX setter failed; partial changes may remain')
end
local result={}
for _,row in ipairs(observed) do result[#result+1]=inspect(row) end
return result
