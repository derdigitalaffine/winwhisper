"use strict";
const {spawn} = require('node:child_process');
const {EventEmitter} = require('node:events');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

function run(command, args, {timeout=30000, onLine=()=>{}, cwd}={}) {
  return new Promise((resolve,reject)=>{
    let child, output='', finished=false;
    try {child=spawn(command,args,{cwd,windowsHide:true,shell:false,stdio:['ignore','pipe','pipe']});}
    catch(error){reject(error);return;}
    const done=(error)=>{
      if(finished)return;
      finished=true;clearTimeout(timer);
      error ? reject(error) : resolve(output.trim());
    };
    const timer=setTimeout(()=>{child.kill();done(new Error('Zeitüberschreitung: '+command));},timeout);
    for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{
      const text=chunk.toString();output=(output+text).slice(-65536);onLine(text);
    });
    child.on('error',done);
    child.on('close',code=>done(code===0?null:new Error(output.slice(-4000)||`${command} beendet (${code}).`)));
  });
}

class DockerRuntime extends EventEmitter {
  constructor({workspace, resources, runner=run, spawnProcess=spawn, platform=process.platform}) {
    super();this.workspace=path.resolve(workspace);this.resources=resources;this.run=runner;this.spawn=spawnProcess;this.platform=platform;
    this.enginePath=path.join(resources,fs.existsSync(path.join(resources,'container'))?'container':'engine');
    this.owner=crypto.createHash('sha256').update(this.workspace).digest('hex').slice(0,14);
    this.name='winwhisper-'+this.owner;this.image='winwhisper/engine:1.0.0';
    this.configFile=path.join(this.workspace,'runtime.json');this.gpu=false;this.flight=null;
    const candidates=[path.join(process.env.ProgramFiles||'C:\\Program Files','Docker','Docker','resources','bin','docker.exe'),path.join(process.env.LOCALAPPDATA||'','Programs','DockerDesktop','resources','bin','docker.exe')];
    this.docker=platform==='win32'?(candidates.find(x=>fs.existsSync(x))||'docker'):'docker';
    fs.mkdirSync(this.workspace,{recursive:true});
    for(const d of ['imports','exports','recordings','models','logs','home'])fs.mkdirSync(path.join(this.workspace,d),{recursive:true});
    try{const c=JSON.parse(fs.readFileSync(this.configFile,'utf8'));this.gpu=c.gpu===true;}catch{}
  }
  log(message){this.emit('log',String(message).replace(/\x1b\[[0-?]*[ -/]*[@-~]/g,''));}
  async inspect(){
    const result={docker:false,linux:false,image:false,gpu:this.gpu,workspace:this.workspace,platform:this.platform};
    try{
      const info=JSON.parse(await this.run(this.docker,['info','--format','{{json .}}'],{timeout:12000}));
      result.docker=true;result.linux=info.OSType==='linux';
      if(!result.linux)result.error='Docker Desktop muss Linux-Container verwenden.';
      if(result.linux){try{await this.run(this.docker,['image','inspect',this.image]);result.image=true;}catch{}}
    }catch(error){result.error='Docker Desktop ist nicht bereit. Bitte installieren/starten und WSL 2 aktivieren. '+error.message.slice(0,400);}
    result.ready=result.docker && result.linux && result.image;
    return result;
  }
  async prepare({device='auto'}={}){
    if(!['auto','cpu','gpu'].includes(device))throw new Error('Ungültiger Gerätemodus.');
    if(this.flight)return this.flight;
    this.flight=this._prepare(device).finally(()=>{this.flight=null;});
    return this.flight;
  }
  async _prepare(device){
    const status=await this.inspect();
    if(!status.docker||!status.linux)throw new Error(status.error);
    if(!status.image){
      this.log('WhisperX und Ollama werden eingerichtet. Der erste Download kann mehrere GB umfassen.');
      await this.run(this.docker,['build','--pull','--tag',this.image,this.enginePath],{timeout:60*60*1000,onLine:t=>this.log(t)});
    }
    this.gpu=false;
    if(device!=='cpu'){
      try{
        await this.run(this.docker,['run','--rm','--network','none','--gpus','all','--entrypoint','python3',this.image,'-c','import torch; assert torch.cuda.is_available(), "CUDA nicht verfügbar"; print(torch.cuda.get_device_name(0))'],{timeout:120000,onLine:t=>this.log(t)});
        this.gpu=true;
      }catch(error){if(device==='gpu')throw error;this.log('GPU-Test nicht erfolgreich. CPU-Betrieb wird verwendet. '+error.message.slice(-500));}
    }
    const temp=this.configFile+'.tmp';fs.writeFileSync(temp,JSON.stringify({version:1,image:this.image,gpu:this.gpu},null,2));fs.renameSync(temp,this.configFile);
    this.log(this.gpu?'Container bereit · NVIDIA-GPU':'Container bereit · CPU');
    return this.inspect();
  }
  async removeOwned(){
    let owner;
    try{owner=await this.run(this.docker,['inspect','--format','{{index .Config.Labels "io.winwhisper.owner"}}',this.name],{timeout:10000});}catch{return;}
    if(owner.trim()!==this.owner)throw new Error('Ein fremder Container verwendet denselben Namen. Er wird nicht beendet.');
    await this.run(this.docker,['rm','--force',this.name],{timeout:20000});
  }
  async start(){
    const info=await this.inspect();if(!info.ready)throw new Error(info.error||'Bitte zuerst den lokalen Container einrichten.');
    await this.removeOwned();
    const mount=`type=bind,source=${this.workspace},target=/data`;
    if(this.workspace.includes(','))throw new Error('Der Arbeitsordner darf für Docker kein Komma enthalten.');
    const args=['run','--rm','-i','--init','--name',this.name,'--label',`io.winwhisper.owner=${this.owner}`,'--cap-drop','ALL','--security-opt','no-new-privileges','--shm-size','1g','--mount',mount];
    if(this.gpu)args.push('--gpus','all');
    args.push(this.image);
    return this.spawn(this.docker,args,{windowsHide:true,shell:false,stdio:['pipe','pipe','pipe']});
  }
  async stop(){
    // Stop only our own container. Models, projects and Docker Desktop stay intact.
    let owner;
    try{owner=await this.run(this.docker,['inspect','--format','{{index .Config.Labels "io.winwhisper.owner"}}',this.name],{timeout:5000});}catch{return;}
    if(owner.trim()===this.owner)await this.run(this.docker,['stop','--time','12',this.name],{timeout:18000});
  }
}
module.exports={DockerRuntime,run};
