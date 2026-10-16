// Original DAWG BowedString, not its session/ensemble renderer.
import {readFileSync,writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [root,recipePath,output,rateArg]=process.argv.slice(2);
const load=(p:string)=>import(pathToFileURL(`${root}/${p}`).href);
const {BowedString}=await load('src/audio/strings/bow.ts');
const {bodyFor,applyBody}=await load('src/audio/strings/body.ts');
const r=JSON.parse(readFileSync(recipePath,'utf8')),sr=Number(rateArg);
const spec={decay:.6,track:.5,damp:.5,pos:.12,pressure:.5,speed:.6,attack:.08,release:.15,tremhz:0,sord:0,...r.spec};
function interp(p:number[][],t:number,col:number,base=0){
 if(!p?.length)return base;
 if(t<=p[0][0])return p[0][col];
 for(let i=1;i<p.length;i++)if(t<p[i][0]){const f=(t-p[i-1][0])/(p[i][0]-p[i-1][0]);return p[i-1][col]+(p[i][col]-p[i-1][col])*f;}
 return p.at(-1)![col];
}
const cents=r.cents?.length?(t:number)=>interp(r.cents,t,1):undefined;
const controls=r.controls?.length?(t:number)=>({pressure:interp(r.controls,t,1),speed:interp(r.controls,t,2),sord:interp(r.controls,t,3),dyn:interp(r.controls,t,4)}):undefined;
const vibrato=r.vibrato_hz&&r.vibrato_cents?(t:number)=>r.vibrato_cents*Math.sin(2*Math.PI*r.vibrato_hz*t):undefined;
const t0=performance.now();
const voice=new BowedString(spec,{hz:r.hz,velocity:r.velocity??.8,hold:r.hold??1,seed:r.seed??1,...(cents?{cents}:{}),...(controls?{control:controls}:{}),...(vibrato?{vibrato}:{})},sr,r.seconds??3);
const out=new Float64Array(Math.round((r.seconds??3)*sr));
const events=(r.events??[]).map(e=>({...e,at:Math.round(e.time*sr)}));
let cursor=0,index=0;
while(cursor<out.length){
 while(index<events.length&&events[index].at<=cursor){const e=events[index++];
  if(e.kind==='slur'){
   if(!voice.canSlurTo(e.hz))throw new Error('invalid slur');
   voice.slurTo(e.hz,e.at,e.hold,e.cents?.length?(t:number)=>interp(e.cents,t,1):undefined);
  }else voice.releaseAt(e.at);
 }
 let end=Math.min(out.length,cursor+128);
 if(index<events.length)end=Math.min(end,events[index].at);
 voice.process(out,cursor,end-cursor);cursor=end;
}
if(r.body_size!==undefined)applyBody(out,bodyFor('violin',r.body_size),sr);
const elapsed=(performance.now()-t0)/1000;
writeFileSync(output,new Uint8Array(out.buffer));
console.log(JSON.stringify({elapsed,frames:out.length,done:voice.done,offAt:voice.offAt}));
