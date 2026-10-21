"""Run the packaged Lua executor with a narrow host stub to test its target guard."""

import shutil
import subprocess

import pytest

from tactus.bridges import reaper


@pytest.mark.skipif(shutil.which("lua") is None, reason="Lua interpreter unavailable")
def test_native_queue_rejects_changed_project_before_user_code(tmp_path):
    instance = "a" * 32
    root = tmp_path / "tactus-bridge" / "instances" / instance
    for name in ("requests", "responses"):
        (root / name).mkdir(parents=True)
    runner = tmp_path / "runner.lua"
    runner.write_text(r'''
local resource, bridge = arg[1], arg[2]
local instance = string.rep('a', 32)
local root = resource .. '/tactus-bridge/instances/' .. instance
local project = {}
local next_poll
reaper = {
  genGuid = function() return '{' .. instance .. '}' end,
  GetResourcePath = function() return resource end,
  RecursiveCreateDirectory = function() end,
  atexit = function() end,
  GetAppVersion = function() return 'stub' end,
  time_precise = os.clock,
  defer = function(callback) next_poll = callback end,
  EnumProjects = function() return project, '' end,
  ShowConsoleMsg = function(message) error(message) end,
  EnumerateFiles = function(path, index)
    if index < 0 then return nil end
    local rows = {}
    for _, name in ipairs({'a.lua', 'b.lua'}) do
      local file = io.open(path .. '/' .. name, 'rb')
      if file then file:close(); rows[#rows + 1] = name end
    end
    return rows[index + 1]
  end,
}
assert(loadfile(bridge))()
assert(next_poll)
local function submit(name, project_id)
  local file = assert(io.open(root .. '/requests/' .. name .. '.lua', 'wb'))
  file:write('return {protocol=1,instance="' .. instance .. '",project_id="' ..
    project_id .. '",expires=' .. (os.time() + 10) ..
    ',run=function() _G.mutated=true;return 42 end}')
  file:close()
  next_poll()
  local reply = assert(io.open(root .. '/responses/' .. name .. '.json', 'rb')):read('*a')
  return reply
end
assert(submit('a', 'wrong'):find('"ok":false', 1, true))
assert(not _G.mutated)
assert(submit('b', tostring(project)):find('"ok":true', 1, true))
assert(_G.mutated)
''', encoding="utf-8")
    result = subprocess.run(["lua", str(runner), str(tmp_path), str(reaper.script())],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
