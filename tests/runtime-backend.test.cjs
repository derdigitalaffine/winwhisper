"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {EventEmitter}=require('node:events');
const {DockerRuntime}=require('../desktop/runtime.cjs');
const {Backend}=require('../desktop/backend.cjs');
function temp(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'winwhisper-runtime-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;}
function child(){const p=new EventEmitter();p.stdout=new EventEmitter();p.stdout.setEncoding=()=>{};p.stderr=new EventEmitter();p.stdin=new EventEmitter();p.stdin.writable=true;p.stdin.write=()=>true;p.stdin.end=()=>{};p.kill=()=>{p.emit('exit',1);};return p;}
test('runtime starts private owned container with an argument array and persistent workspace',async t=>{
  const calls=[],workspace=path.join(temp(t),'Ü Raum');let spawned;
  const runner=async(cmd,args)=>{calls.push(args);if(args[0]==='info')return JSON.stringify({OSType:'linux'});if(args[0]==='inspect')throw new Error('missing');return 'ok';};
  const rt=new DockerRuntime({workspace,resources:temp(t),runner,spawnProcess:(cmd,args,options)=>{spawned={cmd,args,options};return child();}});
  await rt.start();assert(spawned.args.includes('--init'));assert(spawned.args.includes('no-new-privileges'));assert(!spawned.args.includes('-p'));assert(!spawned.args.includes('--publish'));
  assert(spawned.args.includes('type=bind,source='+workspace+',target=/data'));assert.equal(spawned.options.shell,false);assert(spawned.args.includes('io.winwhisper.owner='+rt.owner));
});
test('runtime refuses Windows containers and reports missing Docker',async t=>{
  const rt=new DockerRuntime({workspace:temp(t),resources:temp(t),runner:async()=>JSON.stringify({OSType:'windows'})});
  assert.equal((await rt.inspect()).ready,false);await assert.rejects(rt.start(),/Linux/);
  rt.run=async()=>{throw new Error('not found');};assert.equal((await rt.inspect()).docker,false);
});
test('Docker fallback setup builds a missing engine and stores safe CPU mode',async t=>{
  const resources=temp(t),engine=path.join(resources,'engine'),workspace=temp(t),calls=[];fs.mkdirSync(engine);fs.writeFileSync(path.join(engine,'Dockerfile'),'FROM scratch\n');
  let built=false;
  const rt=new DockerRuntime({workspace,resources,runner:async(_cmd,args)=>{
    calls.push(args);
    if(args[0]==='info')return JSON.stringify({OSType:'linux'});
    if(args[0]==='image'&&!built)throw new Error('image missing');
    if(args[0]==='build'){built=true;return 'built';}
    if(args[0]==='run')throw new Error('no NVIDIA runtime');
    return 'ok';
  }});
  const result=await rt.prepare({device:'auto'});
  assert.equal(result.ready,true);assert.equal(result.gpu,false);
  const build=calls.find(args=>args[0]==='build');
  assert(build);assert(build.includes('--file'));assert(build.includes(path.join(engine,'Dockerfile')));
  assert(calls.some(args=>args[0]==='run'&&args.includes('nvidia-smi')));
  assert.deepEqual(JSON.parse(fs.readFileSync(rt.configFile,'utf8')),{version:1,gpu:false,device:'auto'});
  await assert.rejects(rt.prepare({device:'shell;rm'}),/Ungültiger/);
});

test('Docker fallback setup rejects unavailable required GPU without storing invalid mode',async t=>{
  const resources=temp(t),workspace=temp(t);
  const rt=new DockerRuntime({workspace,resources,runner:async(_cmd,args)=>{
    if(args[0]==='info')return JSON.stringify({OSType:'linux'});
    if(args[0]==='run')throw new Error('GPU unavailable');
    return 'ok';
  }});
  await assert.rejects(rt.prepare({device:'gpu'}),/NVIDIA-GPU in Docker/);
  assert.equal(fs.existsSync(rt.configFile),false);
  assert.equal(rt.flight,null);
});

test('Docker fallback setup coalesces concurrent preparations into one image build',async t=>{
  const resources=temp(t),engine=path.join(resources,'engine');fs.mkdirSync(engine);fs.writeFileSync(path.join(engine,'Dockerfile'),'FROM scratch\n');
  let image=false,builds=0;const rt=new DockerRuntime({workspace:temp(t),resources,runner:async(_cmd,args)=>{
    if(args[0]==='info')return JSON.stringify({OSType:'linux'});
    if(args[0]==='image'&&!image)throw new Error('missing');
    if(args[0]==='build'){builds++;await new Promise(resolve=>setTimeout(resolve,10));image=true;return 'ok';}
    return 'ok';
  }});
  const [a,b]=await Promise.all([rt.prepare({device:'cpu'}),rt.prepare({device:'cpu'})]);
  assert.equal(a.ready,true);assert.equal(b.ready,true);
  assert.equal(builds,1);assert.equal(rt.flight,null);
});
test('unowned container is never removed or stopped',async t=>{
  const args=[];const rt=new DockerRuntime({workspace:temp(t),resources:temp(t),runner:async(_cmd,a)=>{args.push(a);return 'another-owner';}});
  await assert.rejects(rt.removeOwned(),/fremder/);await rt.stop();assert(!args.some(a=>a[0]==='rm'||a[0]==='stop'));
});
test('RPC accepts split Unicode NDJSON, resolves IDs and pushes states',async()=>{
  const p=child(),backend=new Backend({start:async()=>p}),events=[];backend.on('event',e=>events.push(e));await backend.connect();
  p.stdin.write=(line,callback)=>{const r=JSON.parse(line);callback?.();const msg=JSON.stringify({type:'result',data:{id:r.id,value:'ü'}})+'\n';queueMicrotask(()=>{p.stdout.emit('data',msg.slice(0,12));p.stdout.emit('data',msg.slice(12));});};
  assert.equal(await backend.request('logs'),'ü');p.stdout.emit('data','{"type":"state","data":{"busy":false}}\n');assert.equal(events[0].type,'state');assert.equal(backend.pending.size,0);
});
test('pipe failures reject pending requests and permit reconnect',async()=>{
  let p=child();const backend=new Backend({start:async()=>p}),downs=[];backend.on('down',e=>downs.push(e));await backend.connect();
  const result=backend.request('logs');p.stdin.emit('error',new Error('EPIPE'));await assert.rejects(result,/EPIPE/);assert.equal(backend.child,null);assert.equal(backend.pending.size,0);
  p=child();await backend.connect();p.stdin.write=()=>{throw new Error('pipe');};await assert.rejects(backend.request('logs'),/pipe/);assert.equal(backend.pending.size,0);assert.equal(downs.length,1);
});
test('RPC timeout tears down an unresponsive client',async()=>{
  const p=child();let ended=false;p.stdin.end=()=>{ended=true;};const backend=new Backend({start:async()=>p});backend.on('down',()=>{});await backend.connect();
  await assert.rejects(backend.request('logs',{},15),/antwortet/);assert(ended);assert.equal(backend.child,null);assert.equal(backend.pending.size,0);
});
test('unexpected exit rejects all waiting requests without stale process interference',async()=>{
  let p=child(),old=p;const backend=new Backend({start:async()=>p});backend.on('down',()=>{});await backend.connect();const a=backend.request('logs'),b=backend.request('settings');old.emit('exit',1);await assert.rejects(a,/beendet/);await assert.rejects(b,/beendet/);
  p=child();await backend.connect();old.emit('exit',2);assert.equal(backend.child,p);assert.equal(backend.pending.size,0);
});
test('intentional container restart shuts down only its runtime and reconnects cleanly',async()=>{
  let p=child(),stops=0;const backend=new Backend({start:async()=>p,stop:async()=>{stops++;}});await backend.connect();
  p.stdin.write=(line,callback)=>{const request=JSON.parse(line);callback?.();queueMicrotask(()=>p.stdout.emit('data',JSON.stringify({type:'result',data:{id:request.id,value:true}})+'\n'));};
  await backend.restart();assert.equal(stops,1);assert.equal(backend.child,null);assert.equal(backend.closing,false);p=child();await backend.connect();assert.equal(backend.child,p);
});
