-- Tactus REAPER bridge. Run this script in REAPER (Actions -> ReaScript -> Load).
-- Native Lua requests execute on the main thread with full ReaScript access.
-- Protocol v1: fresh directory scans, claimed requests, finite JSON replies. No auto retry.
if _G.tactus_bridge_running then return end
_G.tactus_bridge_running = true
reaper.atexit(function() _G.tactus_bridge_running = nil end)

local instance = reaper.genGuid():gsub('[^%da-fA-F]', ''):lower()
local root = reaper.GetResourcePath() .. '/tactus-bridge/instances/' .. instance
local requests, responses = root .. '/requests', root .. '/responses'
reaper.RecursiveCreateDirectory(requests, 0)
reaper.RecursiveCreateDirectory(responses, 0)
reaper.atexit(function()
  -- Best effort: os.remove only deletes empty directories, so unread replies survive;
  -- platforms whose remove() rejects directories keep the empty queue.
  os.remove(root .. '/heartbeat.json')
  os.remove(requests)
  os.remove(responses)
  os.remove(root)
end)

local function quote(s)
  return '"' .. s:gsub('[%z\1-\31\\"]', function(c)
    if c == '"' then return '\\"' end
    if c == '\\' then return '\\\\' end
    return string.format('\\u%04x', string.byte(c))
  end) .. '"'
end

local function json(value, seen)
  local kind = type(value)
  if kind == 'nil' then return 'null' end
  if kind == 'boolean' then return tostring(value) end
  if kind == 'string' then return quote(value) end
  if kind == 'number' then
    assert(value == value and math.abs(value) ~= math.huge, 'Non-finite return value')
    if math.type(value) == 'integer' then return tostring(value) end
    return string.format('%.17g', value)
  end
  assert(kind == 'table', 'Return JSON values, not ' .. kind .. ' handles/functions')
  seen = seen or {}
  assert(not seen[value], 'Cyclic return table')
  seen[value] = true
  local count, array, keys = 0, true, {}
  for k in pairs(value) do
    count = count + 1
    keys[#keys + 1] = k
    if type(k) ~= 'number' or k % 1 ~= 0 or k < 1 then array = false end
  end
  local parts = {}
  if array and count > 0 and count == #value then
    for i = 1, count do parts[i] = json(value[i], seen) end
  else
    array = false
    for _, k in ipairs(keys) do assert(type(k) == 'string', 'Return string keys or a dense array') end
    table.sort(keys)
    for _, k in ipairs(keys) do parts[#parts + 1] = quote(k) .. ':' .. json(value[k], seen) end
  end
  seen[value] = nil
  return (array and '[' or '{') .. table.concat(parts, ',') .. (array and ']' or '}')
end

local function write(path, value)
  local f = assert(io.open(path .. '.tmp', 'wb'))
  f:write(value)
  f:close()
  if not os.rename(path .. '.tmp', path) then
    os.remove(path) -- Windows rename cannot replace an existing heartbeat.
    assert(os.rename(path .. '.tmp', path))
  end
end

local function handle(name)
  local id = name:sub(1, -5)
  local active = requests .. '/' .. id .. '.active'
  if not os.rename(requests .. '/' .. name, active) then return end
  local output = {}
  local env = setmetatable({print = function(...)
    local row = {}
    for i = 1, select('#', ...) do row[i] = tostring(select(i, ...)) end
    output[#output + 1] = table.concat(row, '\t')
  end}, {__index = _G})
  local project, label
  local ok, result = xpcall(function()
    local chunk, err = loadfile(active, 't', env)
    assert(chunk, err)
    local request = chunk()
    assert(request.protocol == 1, 'Unsupported Tactus request protocol')
    assert(request.instance == instance, 'REAPER bridge instance changed')
    assert(os.time() <= request.expires, 'Request expired before execution')
    if request.project_id then
      local active = reaper.EnumProjects(-1, '')
      assert(tostring(active) == request.project_id,
        'REAPER active project changed; inspect targets before retrying')
    end
    label = request.undo
    if label then
      project = reaper.EnumProjects(-1, '')
      reaper.Undo_BeginBlock2(project)
    end
    return request.run()
  end, debug.traceback)
  if project then reaper.Undo_EndBlock2(project, label, -1) end
  local reply
  if ok then
    local encoded, value = pcall(json, result)
    if encoded then reply = '{"ok":true,"result":' .. value
    else reply = '{"ok":false,"error":' .. quote(value) end
  else reply = '{"ok":false,"error":' .. quote(result) end
  reply = reply .. ',"output":' .. quote(table.concat(output, '\n')) .. '}'
  write(responses .. '/' .. id .. '.json', reply)
  os.remove(active)
end

local last_beat = -math.huge
local function poll()
  -- REAPER caches directory listings; new requests must be visible on this tick.
  reaper.EnumerateFiles(requests, -1)
  local pending, i = {}, 0
  while true do
    local name = reaper.EnumerateFiles(requests, i)
    if not name then break end
    if name:match('^[%da-f]+%.lua$') then pending[#pending + 1] = name end
    i = i + 1
  end
  table.sort(pending)
  for _, name in ipairs(pending) do
    local ok, err = pcall(handle, name)
    if not ok then reaper.ShowConsoleMsg('Tactus bridge: ' .. tostring(err) .. '\n') end
  end
  if reaper.time_precise() - last_beat >= 1 then
    write(root .. '/heartbeat.json', json({protocol = 1, instance = instance, time = os.time(),
      version = reaper.GetAppVersion(), resource_path = reaper.GetResourcePath()}))
    last_beat = reaper.time_precise()
  end
  reaper.defer(poll)
end
poll()
