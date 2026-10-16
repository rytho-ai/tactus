// Reference: unmodified DAWG createScore/performNotes/renderKeysTrack.
import {readFileSync,writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [root,specPath,output,rateArg]=process.argv.slice(2);
const load=(p:string)=>import(pathToFileURL(`${root}/${p}`).href);
const {createScore}=await load('core/score.ts');
const {performanceTimingFor,performNotes}=await load('core/expression.ts');
const {renderKeysTrack}=await load('src/audio/keys/engine.ts');
const spec=JSON.parse(readFileSync(specPath,'utf8'));
const sr=Number(rateArg);
const track={id:'v',name:'Piano',instrument:spec.family??'grand',keys:{...spec.params,sym:0},
 ...(spec.pedal?{pedal:spec.pedal.map(e=>({tick:e.time*960,state:e.state}))}:{}),
 ...(spec.softPedal?{softPedal:spec.softPedal.map(e=>({tick:e.time*960,state:e.state}))}:{})};
const score=createScore({tempoBpm:120,bars:Math.max(1,Math.ceil(spec.seconds/2)),tracks:[track],notes:spec.notes.map(n=>({id:n.id,trackId:'v',pitch:n.pitch,velocity:n.velocity,startTick:n.start*960,durationTicks:n.duration*960}))});
const notes=performNotes(score.tracks[0],score.notes,performanceTimingFor(score));
const left=new Float64Array(Math.round(spec.seconds*sr)),right=new Float64Array(left.length);
const begin=performance.now();
renderKeysTrack(left,right,notes,score.tracks[0],{score,sampleRate:sr,samples:left.length,samplesPerTick:sr/960,tempoBpm:120,ticksPerBeat:480});
const elapsed=(performance.now()-begin)/1000;
const out=new Float64Array(left.length*2);
for(let i=0;i<left.length;i++){out[2*i]=left[i];out[2*i+1]=right[i];}
writeFileSync(output,new Uint8Array(out.buffer));
console.log(JSON.stringify({elapsed,frames:left.length,performed:notes.map(n=>({id:n.id,start:n.startTick/960,off:(n.startTick+n.durationTicks)/960,damp:n.performance?.damp??null}))}));
