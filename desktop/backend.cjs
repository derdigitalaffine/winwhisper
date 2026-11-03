"use strict";
const {EventEmitter}=require('node:events');

class Backend extends EventEmitter {
  constructor(runtime){super();this.runtime=runtime;this.child=null;this.pending=new Map();this.nextID=0;this.connectFlight=null;this.closing=false;}
  connect(){
    if(this.child)return Promise.resolve();
    if(!this.connectFlight)this.connectFlight=this._connect().finally(()=>{this.connectFlight=null;});
    return this.connectFlight;
  }
  async _connect(){
    const child=await this.runtime.start();this.child=child;
    let buffer='';
    const down=(error)=>{
      if(this.child!==child)return;this.child=null;
      for(const item of this.pending.values()){clearTimeout(item.timer);item.reject(error);}
      this.pending.clear();if(!this.closing)this.emit('down',error.message);
    };
    child.stdout.setEncoding('utf8');
    child.stdout.on('data',chunk=>{
      if(this.child!==child)return;
      buffer+=chunk;
      if(Buffer.byteLength(buffer)>64*1024*1024){down(new Error('Hintergrundmeldung zu groß.'));child.kill();return;}
      let index;
      while((index=buffer.indexOf('\n'))>=0){
        const line=buffer.slice(0,index);buffer=buffer.slice(index+1);
        try{
          const event=JSON.parse(line);
          if(!event||typeof event.type!=='string')throw new Error('Ungültige Meldung');
          if(event.type==='result'){
            const item=this.pending.get(event.data?.id);if(!item)continue;
            clearTimeout(item.timer);this.pending.delete(event.data.id);
            event.data.error?item.reject(new Error(event.data.error)):item.resolve(event.data.value);
          }else this.emit('event',event);
        }catch(error){this.emit('event',{type:'log',data:'Ungültige Hintergrundmeldung: '+error.message});}
      }
    });
    child.stderr.on('data',chunk=>this.emit('event',{type:'log',data:chunk.toString()}));
    child.stdin.on('error',down);child.on('error',down);
    child.on('exit',(code,signal)=>down(new Error(`Lokaler Container beendet (${signal||code}). Über „Verbindung prüfen“ neu starten.`)));
  }
  request(action,data={},timeout=30000){
    const child=this.child;
    if(!child||!child.stdin.writable||child.stdin.destroyed)return Promise.reject(new Error('Lokaler Container nicht verbunden. Bitte die Einrichtung öffnen.'));
    if(this.pending.size>=64)return Promise.reject(new Error('Zu viele gleichzeitige Anfragen.'));
    return new Promise((resolve,reject)=>{
      const id=++this.nextID;
      const timer=setTimeout(()=>{this.pending.delete(id);reject(new Error('Der lokale Container antwortet nicht.'));child.stdin.end();child.kill();},timeout);
      const failed=error=>{if(!error)return;const item=this.pending.get(id);if(item){clearTimeout(timer);this.pending.delete(id);reject(error);}};
      this.pending.set(id,{resolve,reject,timer});
      try{child.stdin.write(JSON.stringify({id,action,data})+'\n',failed);}catch(error){failed(error);}
    });
  }
  async shutdown(){
    this.closing=true;
    if(this.child){await this.request('shutdown',{},12000).catch(()=>{});this.child?.stdin.end();}
    await this.runtime.stop().catch(()=>{});
  }
  async restart(){
    await this.shutdown();
    const old=this.child;this.child=null;old?.kill();this.closing=false;
  }
}
module.exports={Backend};
