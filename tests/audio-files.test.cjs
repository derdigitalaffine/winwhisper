"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {WavWriter,header,repairRecordings}=require('../desktop/wav.cjs');
const {WorkspaceFiles}=require('../desktop/files.cjs');
function temp(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'winwhisper-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;}
test('WAV is durable and readable before stop, and finalized without buffering whole audio',t=>{
  const file=path.join(temp(t),'record.wav'),w=new WavWriter(file);
  const pcm=Buffer.alloc(3200);for(let i=0;i<1600;i++)pcm.writeInt16LE(1200,i*2);
  for(let i=0;i<100;i++)w.append(i,pcm);
  w.sync();let data=fs.readFileSync(file);assert.equal(data.readUInt32LE(40),320000);assert.equal(data.readUInt32LE(24),16000);assert.equal(data.length,320044);
  w.close();w.close();assert.throws(()=>w.append(100,pcm),/beendet/);assert.equal(data.readInt16LE(44),1200);
});
test('WAV rejects missing/out-of-order packets, odd lengths and oversized packets',t=>{
  const w=new WavWriter(path.join(temp(t),'record.wav'));t.after(()=>w.close());
  assert.throws(()=>w.append(1,Buffer.alloc(3200)),/Reihenfolge/);
  assert.throws(()=>w.append(0,Buffer.alloc(3)),/Audiopaket/);
  assert.throws(()=>w.append(0,Buffer.alloc(32002)),/Audiopaket/);
  assert.equal(w.bytes,0);w.append(0,Buffer.alloc(3200));assert.equal(w.bytes,3200);
});
test('WAV header supports a full three-hour recording and duration cap',t=>{
  const bytes=3*3600*32000;const h=header(bytes);assert.equal(h.readUInt32LE(4),bytes+36);assert.equal(h.readUInt32LE(40),bytes);
  assert.throws(()=>header(NaN));assert.throws(()=>header(0xffffffff));
  const w=new WavWriter(path.join(temp(t),'limit.wav'));w.bytes=3.25*3600*32000;assert.throws(()=>w.append(0,Buffer.alloc(3200)),/Aufnahmedauer/);w.bytes=0;w.close();
});
test('disk write failure does not advance packet sequence',t=>{
  const w=new WavWriter(path.join(temp(t),'disk.wav'));fs.closeSync(w.fd);
  assert.throws(()=>w.append(0,Buffer.alloc(3200)));assert.equal(w.bytes,0);assert.equal(w.sequence,0);w.closed=true;
});
test('restart repairs WAV length after crash without changing audio samples',t=>{
  const dir=temp(t),file=path.join(dir,'crashed.wav');
  fs.writeFileSync(file,Buffer.concat([header(0),Buffer.alloc(3200,12)]));
  const repaired=repairRecordings(dir);assert.deepEqual(repaired,[file]);const bytes=fs.readFileSync(file);assert.equal(bytes.readUInt32LE(40),3200);assert.equal(bytes[44],12);assert.deepEqual(repairRecordings(dir),[]);
});
test('host/container mappings handle Unicode, spaces and URL escapes',t=>{
  const root=temp(t),f=new WorkspaceFiles(root),logical='/data/projects/Sitzung ü %/preview.wav';
  assert.equal(f.logical(f.host(logical)),logical);
  assert(f.audioURL('file:///data/projects/Sitzung%20%C3%BC%20%25/preview.wav').includes('preview.wav'));
  for(const invalid of ['/data/../secret','/data/a/../../secret','/data/a\\secret','C:/secret','/etc/passwd','/data/a:secret','/data/a//b'])assert.throws(()=>f.host(invalid));
  assert.throws(()=>f.audioURL('https://example.com/audio'));assert.throws(()=>f.audioURL('file://server/data/x'));
});
test('import preserves originals, records protection across restart and exports atomically',async t=>{
  const root=temp(t),workspace=path.join(root,'workspace');fs.mkdirSync(workspace);const f=new WorkspaceFiles(workspace);
  const original=path.join(root,'Original ü.wav');fs.writeFileSync(original,'original');const logical=await f.import(original);
  assert.equal(fs.readFileSync(f.host(logical),'utf8'),'original');assert.equal(fs.readFileSync(original,'utf8'),'original');
  const next=new WorkspaceFiles(workspace);assert.throws(()=>next.checkDestination(original),/Original/);
  assert.throws(()=>next.checkDestination(path.join(workspace,'recordings','original.wav')),/Arbeitsbereich/);
  const out=path.join(root,'export.wav');fs.writeFileSync(out,'previous');await next.export(logical,out);assert.equal(fs.readFileSync(out,'utf8'),'original');assert.equal(fs.readFileSync(original,'utf8'),'original');
  assert.equal(await next.import(f.host(logical)),logical);
});
test('failed export preserves existing destination',async t=>{
  const root=temp(t),f=new WorkspaceFiles(root),outside=path.join(temp(t),'export.md');fs.writeFileSync(outside,'old');
  await assert.rejects(f.export('/data/missing.md',outside));assert.equal(fs.readFileSync(outside,'utf8'),'old');
});
test('AudioWorklet resampling preserves counts over render-quanta boundaries',()=>{
  for(const rate of [16000,44100,48000,96000]){
    let Processor;const messages=[];
    class Base{constructor(){this.port={postMessage:m=>messages.push(m)};}}
    const context={AudioWorkletProcessor:Base,registerProcessor:(_name,ctor)=>{Processor=ctor;},sampleRate:rate,Int16Array,Math};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../desktop/pcm-worklet.js'),'utf8'),context);
    const p=new Processor();for(let i=0;i<rate;i+=128){const block=new Float32Array(Math.min(128,rate-i)).fill(.5);p.process([[block]],[[new Float32Array(128)]]);}
    p.port.onmessage({data:'flush'});const pcm=messages.filter(m=>m.type==='pcm');assert.equal(pcm.reduce((n,m)=>n+m.buffer.byteLength/2,0),16000);
    for(const m of pcm)assert(Math.abs(new Int16Array(m.buffer)[0]-16384)<=1);
    assert.equal(messages.at(-1).type,'flushed');
  }
});
