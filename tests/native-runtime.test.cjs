"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {EventEmitter}=require('node:events');
const {NativeWindowsRuntime,RuntimeManager}=require('../desktop/runtime.cjs');

function temp(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'winwhisper-native-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;}
function fakeChild(){const p=new EventEmitter();p.stdout=new EventEmitter();p.stderr=new EventEmitter();p.stdin=new EventEmitter();p.stdin.end=()=>{};p.exitCode=null;p.kill=()=>{p.exitCode=1;p.emit('exit',1);};return p;}
function fixture(t){
  const root=temp(t),resources=path.join(root,'resources'),engine=path.join(resources,'container'),workspace=path.join(root,'workspace');
  fs.mkdirSync(engine,{recursive:true});fs.writeFileSync(path.join(engine,'requirements-windows-py312.txt'),'whisperx==3.8.6\n');fs.writeFileSync(path.join(engine,'native_entry.py'),'print()\n');
  return {root,resources,engine,workspace};
}

test('Windows defaults to native runtime and persists Docker fallback selection',async t=>{
  const f=fixture(t),runner=async()=>{throw new Error('not installed');};
  let manager=new RuntimeManager({workspace:f.workspace,resources:f.resources,runner,platform:'win32'});
  assert.equal(manager.mode,'native');assert.equal((await manager.inspect()).mode,'native');
  await manager.select('docker');assert.equal(manager.mode,'docker');
  manager=new RuntimeManager({workspace:f.workspace,resources:f.resources,runner,platform:'win32'});assert.equal(manager.mode,'docker');
  await assert.rejects(manager.select('bad'),/Unbekannte/);
});

test('native runtime is ready from its managed venv and starts Python without a shell',async t=>{
  const f=fixture(t),calls=[];let spawned;
  const runner=async(command,args)=>{calls.push({command,args});return 'ok';};
  const rt=new NativeWindowsRuntime({workspace:f.workspace,resources:f.resources,runner,platform:'win32',spawnProcess:(command,args,options)=>{spawned={command,args,options};return fakeChild();}});
  fs.mkdirSync(path.dirname(rt.python),{recursive:true});fs.writeFileSync(rt.python,'fake');fs.writeFileSync(rt.configFile,JSON.stringify({version:2,flavor:'cpu',gpu:false}));
  const status=await rt.inspect();assert.equal(status.ready,true);assert.equal(status.native,true);assert.equal(status.gpu,false);
  await rt.start();assert.equal(spawned.command,rt.python);assert.deepEqual(spawned.args,[rt.entry]);assert.equal(spawned.options.shell,false);assert.equal(spawned.options.stdio[0],'pipe');
  assert.equal(spawned.options.env.HF_HOME,path.join(f.workspace,'models','huggingface-native'));
  assert.equal(spawned.options.env.HF_HUB_DISABLE_SYMLINKS_WARNING,'1');assert.equal(spawned.options.env.HF_HUB_DISABLE_XET,'1');
  assert(calls.some(call=>call.args[0]==='-c'));
});

test('native runtime stays unavailable when the managed environment is missing and validates device input',async t=>{
  const f=fixture(t);const calls=[];const rt=new NativeWindowsRuntime({workspace:f.workspace,resources:f.resources,runner:async(command,args)=>{calls.push({command,args});throw new Error('missing');},platform:'win32'});
  const status=await rt.inspect();assert.equal(status.ready,false);assert.equal(status.python,false);assert.match(status.error,/noch nicht eingerichtet/);
  await assert.rejects(rt.prepare({device:'shell'}),/Ungültiger/);
  await assert.rejects(rt.prepare({device:'cpu'}),/Setup-Routine|Einrichtungsroutine|nicht automatisch/);
  assert.equal(calls.some(c=>String(c.command).toLowerCase().includes('winget')||c.args?.[0]==='winget.exe'),false);
});

test('native runtime cannot be selected on non-Windows platforms',async t=>{
  const f=fixture(t),manager=new RuntimeManager({workspace:f.workspace,resources:f.resources,runner:async()=>{throw new Error('missing');},platform:'linux'});
  assert.equal(manager.mode,'docker');await assert.rejects(manager.select('native'),/nur unter Windows/);
});

test('legacy CPU runtime repairs CUDA once at start when NVIDIA is detected',async t=>{
  const f=fixture(t),calls=[];
  const rt=new NativeWindowsRuntime({workspace:f.workspace,resources:f.resources,platform:'win32',
    runner:async(command,args)=>{calls.push({command,args});return 'GPU 0: Test';},spawnProcess:()=>fakeChild()});
  fs.mkdirSync(path.dirname(rt.python),{recursive:true});fs.writeFileSync(rt.python,'fake');
  fs.writeFileSync(rt.configFile,JSON.stringify({version:2,flavor:'cpu',gpu:false}));
  await rt.start();await rt.start();
  const repairs=calls.filter(c=>c.command==='powershell.exe');
  assert.equal(repairs.length,1);assert(repairs[0].args.includes('auto'));
});

test('new explicit CPU setup remains CPU and never triggers an automatic CUDA install',async t=>{
  const f=fixture(t),calls=[];
  const rt=new NativeWindowsRuntime({workspace:f.workspace,resources:f.resources,platform:'win32',
    runner:async(command,args)=>{calls.push({command,args});return 'ok';},spawnProcess:()=>fakeChild()});
  fs.mkdirSync(path.dirname(rt.python),{recursive:true});fs.writeFileSync(rt.python,'fake');
  fs.writeFileSync(rt.configFile,JSON.stringify({version:3,flavor:'cpu',gpu:false,requestedDevice:'cpu'}));
  await rt.start();assert(!calls.some(c=>c.command==='powershell.exe'));
});
