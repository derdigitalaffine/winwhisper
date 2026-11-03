/* Native Windows capture through Chromium; PCM is written incrementally to disk. */
(function(){
  'use strict';
  let active=null,starting=false;
  async function listDevices(){
    const devices=await navigator.mediaDevices.enumerateDevices();
    return [{name:'Standardmikrofon',value:''},...devices.filter(d=>d.kind==='audioinput'&&d.deviceId!=='default').map((d,i)=>({name:d.label||`Mikrofon ${i+1}`,value:d.deviceId}))];
  }
  async function start(settings){
    if(active||starting)throw new Error('Die Aufnahme läuft bereits.');starting=true;
    let stream,context,session;
    try{
      stream=await navigator.mediaDevices.getUserMedia({audio:{deviceId:settings.microphone?{exact:settings.microphone}:undefined,channelCount:1,echoCancellation:false,noiseSuppression:false,autoGainControl:false},video:false});
      context=new AudioContext({sampleRate:16000});await context.suspend();
      await context.audioWorklet.addModule('pcm-worklet.js');
      const node=new AudioWorkletNode(context,'local-pcm',{numberOfInputs:1,numberOfOutputs:1,channelCount:1,channelCountMode:'explicit',channelInterpretation:'speakers',outputChannelCount:[1]});
      const source=context.createMediaStreamSource(stream);source.connect(node);node.connect(context.destination);
      session=await window.studio.audio.start();
      const record={id:session.id,stream,context,node,source,sequence:0,queue:Promise.resolve(),queued:0,stopping:false,error:null,flushed:null};
      active=record;
      const fail=error=>{
        if(record.error)return;record.error=error;
        window.dispatchEvent(new CustomEvent('native-recording-error',{detail:'Aufnahmefehler: '+error.message+'. Bereits geschriebene Audiodaten bleiben erhalten.'}));
        stop().catch(()=>{});
      };
      node.port.onmessage=event=>{
        if(event.data.type==='flushed'){record.flushed?.();return;}
        if(event.data.type!=='pcm'||record.error)return;
        if(record.queued>=40){fail(new Error('Der Datenträger schreibt die Aufnahme zu langsam'));return;}
        const sequence=record.sequence++,pcm=new Uint8Array(event.data.buffer);record.queued++;
        record.queue=record.queue.then(()=>window.studio.audio.append(record.id,sequence,pcm)).finally(()=>{record.queued--;});
        record.queue.catch(fail);
      };
      for(const track of stream.getAudioTracks())track.onended=()=>{if(!record.stopping)fail(new Error('Mikrofonverbindung unterbrochen'));};
      await context.resume();return true;
    }catch(error){
      stream?.getTracks().forEach(t=>t.stop());if(context)await context.close().catch(()=>{});if(session)await window.studio.audio.stop(session.id).catch(()=>{});active=null;throw error;
    }finally{starting=false;}
  }
  async function stop(){
    const record=active;if(!record)return true;
    if(record.stopFlight)return record.stopFlight;
    record.stopping=true;
    record.stopFlight=(async()=>{
      let timer;
      try{
        // Freeze capture before flushing, so no packet can arrive after finalization.
        record.source.disconnect();
        const flushed=new Promise(resolve=>{record.flushed=resolve;timer=setTimeout(resolve,1500);});
        record.node.port.postMessage('flush');await flushed;clearTimeout(timer);
        await record.queue.catch(()=>{});
      }finally{
        record.source.disconnect();record.node.disconnect();record.stream.getTracks().forEach(t=>t.stop());
        await record.context.close().catch(()=>{});active=null;
        await window.studio.audio.stop(record.id);
      }
      return true;
    })();
    return record.stopFlight;
  }
  window.NativeRecorder={start,stop,listDevices,isActive:()=>!!active};
})();
