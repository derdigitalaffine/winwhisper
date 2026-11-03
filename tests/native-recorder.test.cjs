"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function harness({denied=false}={}){
  const calls=[],tracks=[{stop(){calls.push('track-stop');}}];let node;
  const stream={getTracks:()=>tracks,getAudioTracks:()=>tracks};
  class Context{
    constructor(options){assert.equal(options.sampleRate,16000);this.audioWorklet={addModule:async file=>assert.equal(file,'pcm-worklet.js')};this.destination={};}
    async suspend(){calls.push('suspend');}async resume(){calls.push('resume');}async close(){calls.push('context-close');}
    createMediaStreamSource(){return {connect(){},disconnect(){}};}
  }
  class Worklet{
    constructor(_ctx,_name,options){assert.equal(options.channelCount,1);assert.equal(options.channelCountMode,'explicit');node=this;this.port={onmessage:null,postMessage:message=>{if(message==='flush'){node.port.onmessage({data:{type:'pcm',buffer:new Int16Array([12,13]).buffer}});node.port.onmessage({data:{type:'flushed'}});}}};}
    connect(){}disconnect(){}
  }
  const window={dispatchEvent(){},studio:{audio:{start:async()=>{calls.push('writer-start');return {id:'capture',rate:16000};},append:async(id,sequence,pcm)=>{await new Promise(r=>setTimeout(r,5));calls.push(['append',id,sequence,pcm.length]);},stop:async id=>{calls.push(['writer-stop',id]);}}}};
  const navigator={mediaDevices:{getUserMedia:async options=>{assert.equal(options.video,false);if(denied)throw new Error('permission denied');return stream;},enumerateDevices:async()=>[{kind:'audioinput',deviceId:'default',label:'Default'},{kind:'audioinput',deviceId:'usb',label:'USB'}]}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../desktop/native-recorder.js'),'utf8'),{window,navigator,AudioContext:Context,AudioWorkletNode:Worklet,Uint8Array,Int16Array,CustomEvent:class{},setTimeout,clearTimeout,Promise});
  return {recorder:window.NativeRecorder,calls,node:()=>node};
}
test('native stop waits for final worklet packet and disk acknowledgment',async()=>{
  const h=harness();await h.recorder.start({microphone:'usb'});assert(h.recorder.isActive());
  h.node().port.onmessage({data:{type:'pcm',buffer:new Int16Array([1,2]).buffer}});
  await Promise.all([h.recorder.stop(),h.recorder.stop()]);
  const packets=h.calls.filter(x=>Array.isArray(x)&&x[0]==='append');assert.deepEqual(packets.map(x=>x[2]),[0,1]);
  assert.deepEqual(h.calls.at(-1),['writer-stop','capture']);assert.equal(h.calls.filter(x=>Array.isArray(x)&&x[0]==='writer-stop').length,1);assert(!h.recorder.isActive());assert(h.calls.includes('track-stop'));
});
test('permission denial starts no writer and is recoverable',async()=>{
  const h=harness({denied:true});await assert.rejects(h.recorder.start({}),/permission/);assert(!h.calls.includes('writer-start'));assert(!h.recorder.isActive());await h.recorder.stop();
});
test('native device list keeps default microphone and actual Windows device IDs',async()=>{
  const h=harness(),devices=await h.recorder.listDevices();assert.equal(devices.length,2);assert.equal(devices[0].value,'');assert.equal(devices[1].value,'usb');
});
