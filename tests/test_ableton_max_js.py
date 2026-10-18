"""Execute adopted Max JS with a minimal host boundary; native probes remain separate."""

import shutil
import subprocess
from pathlib import Path

import pytest

ASSETS = Path(__file__).parents[1] / 'src/tactus/bridges/ableton_support/m4l'
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Optional Node JS regression executor')


def run_js(asset, body):
    source = '''const fs=require('fs'), vm=require('vm'), assert=require('assert');
const events=[];
const context={jsarguments:['js'],outlet:(...a)=>events.push(a),post:()=>{},error:()=>{},
 arrayfromargs:(name,args)=>[name,...args],
 Task:function(){this.schedule=()=>{};this.repeat=()=>{};this.cancel=()=>{};},
 patcher:{getnamed:()=>null},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
''' + body
    result = subprocess.run([NODE, '-e', source, str(ASSETS / asset)], text=True,
                            capture_output=True, check=False)
    assert result.returncode == 0, result.stderr


def test_web_reload_really_reads_an_already_loaded_panel():
    run_js('agent_m4l_host.js', '''
const reads=[];
context.webObjectById={panel:{message:(...a)=>reads.push(a)}};
context.objectSpecById={panel:{html_path:'/old.html',object:'jweb'}};
context.loadedWebUis={panel:1};
context.report=()=>{};context.pushWebState=()=>{};
context.reloadWebUiCommand({webui:{id:'panel',html_path:'/new.html'}});
assert(reads.some(a=>a[1]==='/new.html'), 'reload acknowledged but did not read the new page');
''')


def test_tap_patch_loadbang_is_a_wakeup_not_invalid_json():
    run_js('agent_audio_tap.js', '''
if(typeof context.bang==='function')context.bang();
else {context.messagename='bang';context.anything();}
assert(!events.some(a=>a[0]===2 && a[1]==='error'), 'patch loadbang emitted invalid JSON error');
''')
