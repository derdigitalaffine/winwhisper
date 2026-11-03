/* Audio stays local. Average/resample continuously across render quanta. */
class LocalPCM extends AudioWorkletProcessor {
  constructor(){super();this.phase=0;this.sum=0;this.count=0;this.buffer=new Int16Array(1600);this.used=0;this.port.onmessage=e=>{if(e.data==='flush'){this.flush();this.port.postMessage({type:'flushed'});}};}
  flush(){if(!this.used)return;const data=this.buffer.slice(0,this.used);this.port.postMessage({type:'pcm',buffer:data.buffer},[data.buffer]);this.used=0;}
  process(inputs,outputs){
    for(const channel of outputs[0]||[])channel.fill(0);
    const input=inputs[0]?.[0];if(!input)return true;
    for(let i=0;i<input.length;i++){
      this.sum+=input[i];this.count++;this.phase+=16000;
      if(this.phase>=sampleRate){
        this.phase-=sampleRate;const sample=Math.max(-1,Math.min(1,this.sum/this.count));
        this.buffer[this.used++]=Math.round(sample*(sample<0?32768:32767));this.sum=0;this.count=0;
        if(this.used===this.buffer.length)this.flush();
      }
    }
    return true;
  }
}
registerProcessor('local-pcm',LocalPCM);
