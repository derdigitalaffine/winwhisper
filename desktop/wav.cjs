"use strict";
const fs=require('node:fs');
function header(bytes,rate=16000){
  if(!Number.isSafeInteger(bytes)||bytes<0||bytes>0xffffffff-36||bytes%2)throw new Error('Ungültige WAV-Länge.');
  const b=Buffer.alloc(44);b.write('RIFF');b.writeUInt32LE(36+bytes,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(rate,24);b.writeUInt32LE(rate*2,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(bytes,40);return b;
}
class WavWriter {
  constructor(file){this.file=file;this.fd=fs.openSync(file,'wx');this.bytes=0;this.sequence=0;this.closed=false;this.lastSync=0;fs.writeSync(this.fd,header(0));fs.fsyncSync(this.fd);}
  append(sequence,pcm){
    if(this.closed)throw new Error('Aufnahme ist bereits beendet.');
    if(sequence!==this.sequence)throw new Error('Audiopakete sind unvollständig oder in falscher Reihenfolge.');
    const b=Buffer.from(pcm);
    if(!b.length||b.length>32000||b.length%2)throw new Error('Ungültiges Audiopaket.');
    if(this.bytes+b.length>3.25*3600*32000)throw new Error('Maximale Aufnahmedauer erreicht. Bitte Aufnahme beenden.');
    let offset=0;while(offset<b.length)offset+=fs.writeSync(this.fd,b,offset,b.length-offset,44+this.bytes+offset);
    this.bytes+=b.length;this.sequence++;
    const now=Date.now();if(now-this.lastSync>1000){this.sync();this.lastSync=now;}
    return this.bytes/32000;
  }
  sync(){fs.writeSync(this.fd,header(this.bytes),0,44,0);fs.fsyncSync(this.fd);}
  close(){if(!this.closed){try{this.sync();}finally{fs.closeSync(this.fd);this.closed=true;}}return this.file;}
}
function repairRecordings(directory){
  const repaired=[];
  for(const file of fs.readdirSync(directory).filter(x=>x.endsWith('.wav'))){
    const full=require('node:path').join(directory,file);let fd;
    try{
      fd=fs.openSync(full,'r+');const h=Buffer.alloc(44);if(fs.readSync(fd,h,0,44,0)!==44)continue;
      if(h.toString('ascii',0,4)!=='RIFF'||h.toString('ascii',8,16)!=='WAVEfmt '||h.toString('ascii',36,40)!=='data'||h.readUInt16LE(20)!==1||h.readUInt16LE(22)!==1||h.readUInt32LE(24)!==16000||h.readUInt16LE(34)!==16)continue;
      const size=fs.fstatSync(fd).size;
      if(h.readUInt32LE(4)+8===size && h.readUInt32LE(40)+44<=size)continue;
      const bytes=Math.floor((size-44)/2)*2;
      if(bytes<0||bytes>3.25*3600*32000||bytes===h.readUInt32LE(40))continue;
      fs.writeSync(fd,header(bytes),0,44,0);fs.fsyncSync(fd);repaired.push(full);
    }catch{}finally{if(fd!==undefined)fs.closeSync(fd);}
  }
  return repaired;
}
module.exports={header,WavWriter,repairRecordings};
