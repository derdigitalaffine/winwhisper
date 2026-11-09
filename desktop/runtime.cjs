"use strict";
const {spawn,spawnSync}=require('node:child_process');
const {EventEmitter}=require('node:events');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');

const NATIVE_ENGINE_VERSION=2;

function run(command,args,{timeout=30000,onLine=()=>{},cwd,env}={}){
  return new Promise((resolve,reject)=>{
    let child,output='',finished=false;
    try{child=spawn(command,args,{cwd,env:env||process.env,windowsHide:true,shell:false,stdio:['ignore','pipe','pipe']});}
    catch(error){reject(error);return;}
    const done=(error)=>{
      if(finished)return;
      finished=true;clearTimeout(timer);
      error?reject(error):resolve(output.trim());
    };
    const timer=setTimeout(()=>{child.kill();done(new Error('Zeitüberschreitung: '+command));},timeout);
    for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{
      const text=chunk.toString();output=(output+text).slice(-65536);onLine(text);
    });
    child.on('error',done);
    child.on('close',code=>done(code===0?null:new Error(output.slice(-4000)||`${command} beendet (${code}).`)));
  });
}

function atomicJSON(file,value){
  fs.mkdirSync(path.dirname(file),{recursive:true});
  const temp=file+'.'+process.pid+'.tmp';
  fs.writeFileSync(temp,JSON.stringify(value,null,2));
  fs.renameSync(temp,file);
}

function readJSON(file,fallback={}){try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch{return fallback;}}

class NativeWindowsRuntime extends EventEmitter{
  constructor({workspace,resources,runner=run,spawnProcess=spawn,platform=process.platform}){
    super();this.workspace=path.resolve(workspace);this.resources=resources;this.run=runner;this.spawn=this.spawnProcess=spawnProcess;this.platform=platform;
    this.enginePath=path.join(resources,fs.existsSync(path.join(resources,'container'))?'container':'engine');
    this.runtimeRoot=path.join(this.workspace,'runtime','native');
    this.venv=path.join(this.runtimeRoot,'venv');
    this.python=path.join(this.venv,'Scripts','python.exe');
    this.configFile=path.join(this.runtimeRoot,'runtime.json');
    this.requirements=path.join(this.enginePath,'requirements-windows-py312.txt');
    this.entry=path.join(this.enginePath,'native_entry.py');
    this.flight=null;this.child=null;this.health=null;
    fs.mkdirSync(this.workspace,{recursive:true});
    for(const d of ['imports','exports','recordings','models','logs','home',path.join('runtime','native')])fs.mkdirSync(path.join(this.workspace,d),{recursive:true});
  }
  log(message){this.emit('log',String(message).replace(/\x1b\[[0-?]*[ -/]*[@-~]/g,''));}
  _config(){return readJSON(this.configFile,{});}
  _torchLib(){return path.join(this.venv,'Lib','site-packages','torch','lib');}
  _env(){
    const ollama=this.findOllama();
    const additions=[path.join(this.venv,'Scripts'),this._torchLib()];
    if(ollama)additions.push(path.dirname(ollama));
    return {...process.env,
      WINWHISPER_DATA:this.workspace,WINWHISPER_ENGINE:this.enginePath,
      WINWHISPER_CLI:path.join(this.enginePath,'whisperx_cli.py'),WINWHISPER_PLATFORM:'windows-native',
      WINWHISPER_OLLAMA:ollama||'',WINWHISPER_OLLAMA_URL:'http://127.0.0.1:11435',
      OLLAMA_HOST:'127.0.0.1:11435',OLLAMA_MODELS:path.join(this.workspace,'models','ollama'),OLLAMA_NO_CLOUD:'1',OLLAMA_KEEP_ALIVE:'30s',OLLAMA_MAX_LOADED_MODELS:'1',
      HF_HOME:path.join(this.workspace,'models','huggingface-native'),TORCH_HOME:path.join(this.workspace,'models','torch'),HF_HUB_DISABLE_TELEMETRY:'1',HF_HUB_DISABLE_SYMLINKS_WARNING:'1',HF_HUB_DISABLE_XET:'1',PYANNOTE_METRICS_ENABLED:'0',DO_NOT_TRACK:'1',
      PATH:additions.filter(Boolean).join(path.delimiter)+path.delimiter+(process.env.PATH||'')};
  }
  findOllama(){
    if(this.platform!=='win32')return null;
    const local=process.env.LOCALAPPDATA||'';
    const candidates=[path.join(local,'Programs','Ollama','ollama.exe'),path.join(local,'Ollama','ollama.exe')];
    for(const candidate of candidates)if(candidate&&fs.existsSync(candidate))return candidate;
    try{
      const result=spawnSync('where.exe',['ollama.exe'],{encoding:'utf8',windowsHide:true,timeout:4000});
      const first=(result.stdout||'').split(/\r?\n/).map(x=>x.trim()).find(Boolean);
      if(result.status===0&&first&&fs.existsSync(first))return first;
    }catch{}
    return null;
  }
  async _probeBasePython(){
    if(this.platform!=='win32')return null;
    const local=process.env.LOCALAPPDATA||'';
    const candidates=[
      {command:'py.exe',prefix:['-3.12']},
      {command:path.join(local,'Programs','Python','Python312','python.exe'),prefix:[]},
      {command:'python.exe',prefix:[]}
    ];
    const code='import platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}|{platform.architecture()[0]}")';
    for(const item of candidates){
      if(path.isAbsolute(item.command)&&!fs.existsSync(item.command))continue;
      try{
        const output=await this.run(item.command,[...item.prefix,'-c',code],{timeout:8000});
        if(output.trim()==='3.12|64bit')return item;
      }catch{}
    }
    return null;
  }
  async _ensureBasePython(){
    let base=await this._probeBasePython();if(base)return base;
    this.log('Python 3.12 x64 fehlt. WinWhisper installiert die Benutzer-Version über winget; WSL und Docker werden dafür nicht benötigt.');
    try{
      await this.run('winget.exe',['install','--id','Python.Python.3.12','--exact','--source','winget','--scope','user','--silent','--accept-source-agreements','--accept-package-agreements'],{timeout:20*60*1000,onLine:t=>this.log(t)});
    }catch(error){this.log('Python-Installation meldete: '+error.message.slice(-1200));}
    base=await this._probeBasePython();
    if(!base)throw new Error('Python 3.12 x64 konnte nicht automatisch eingerichtet werden. Bitte Python 3.12 für den aktuellen Benutzer installieren und erneut versuchen.');
    return base;
  }
  async _ensureVenv(){
    if(fs.existsSync(this.python))return;
    const base=await this._ensureBasePython();
    this.log('Isolierte WinWhisper-Python-Umgebung wird erstellt …');
    await this.run(base.command,[...base.prefix,'-m','venv',this.venv],{timeout:5*60*1000,onLine:t=>this.log(t)});
    if(!fs.existsSync(this.python))throw new Error('Die lokale Python-Umgebung wurde nicht vollständig erstellt.');
  }
  async _hasNvidia(){
    try{await this.run('nvidia-smi.exe',['-L'],{timeout:7000});return true;}catch{return false;}
  }
  async _healthCheck(){
    if(!fs.existsSync(this.python)||!fs.existsSync(this.entry)||!fs.existsSync(this.requirements))return {ok:false,error:'Native Engine-Dateien fehlen.'};
    try{
      const code='import imageio_ffmpeg,torch,ctranslate2,faster_whisper,whisperx; print("ok")';
      await this.run(this.python,['-c',code],{timeout:60000,cwd:this.enginePath,env:this._env()});
      return {ok:true};
    }catch(error){return {ok:false,error:error.message.slice(-1000)};}
  }
  async inspect(){
    const config=this._config();
    const python=fs.existsSync(this.python),ollama=!!this.findOllama();
    let engine=false,error='';
    if(python&&config.version===NATIVE_ENGINE_VERSION){
      if(!this.health)this.health=await this._healthCheck();
      engine=!!this.health.ok;if(!engine)error='Die native Python-Umgebung ist unvollständig. „Einrichten / reparieren“ ausführen. '+(this.health.error||'');
    }else if(!python)error='Native Windows-Laufzeit ist noch nicht eingerichtet.';
    else error='Native Windows-Laufzeit muss aktualisiert werden.';
    return {mode:'native',runtime:'native',runtimeLabel:'Windows nativ',native:true,python,engine,image:engine,ollama,gpu:config.gpu===true,device:config.gpu?'gpu':'cpu',workspace:this.workspace,platform:this.platform,ready:python&&engine,error};
  }
  async prepare({device='auto'}={}){
    if(!['auto','cpu','gpu'].includes(device))throw new Error('Ungültiger Gerätemodus.');
    if(this.platform!=='win32')throw new Error('Die native Laufzeit ist nur unter Windows verfügbar.');
    if(this.flight)return this.flight;
    this.flight=this._prepare(device).finally(()=>{this.flight=null;});return this.flight;
  }
  async _prepare(device){
    if(!['auto','cpu','gpu'].includes(device))throw new Error('Ungültiger Gerätemodus.');
    if(!fs.existsSync(this.requirements)||!fs.existsSync(this.entry))throw new Error('Native Engine-Dateien fehlen im Installationspaket.');
    const info=await this.inspect();
    if(!info.ready){
      throw new Error('Die WhisperX-Umgebung ist noch nicht eingerichtet. Bitte die Setup-Routine „WhisperX einrichten“ ausführen, bevor die Anwendung die Laufzeit startet.');
    }
    return this.inspect();
  }
  async start(){
    const info=await this.inspect();if(!info.ready)throw new Error(info.error||'Bitte zuerst die native Windows-Laufzeit einrichten.');
    if(this.child&&this.child.exitCode===null)return this.child;
    const child=this.spawn(this.python,[this.entry],{cwd:this.enginePath,env:this._env(),windowsHide:true,shell:false,stdio:['pipe','pipe','pipe']});
    this.child=child;child.once('exit',()=>{if(this.child===child)this.child=null;});return child;
  }
  async stop(){
    const child=this.child;if(!child||child.exitCode!==null)return;
    try{child.stdin.end();}catch{}
    await new Promise(resolve=>{const timer=setTimeout(()=>{try{child.kill();}catch{}resolve();},8000);child.once('exit',()=>{clearTimeout(timer);resolve();});});
  }
}

class DockerRuntime extends EventEmitter{
  constructor({workspace,resources,runner=run,spawnProcess=spawn,platform=process.platform}){
    super();this.workspace=path.resolve(workspace);this.resources=resources;this.run=runner;this.spawn=spawnProcess;this.platform=platform;
    this.enginePath=path.join(resources,fs.existsSync(path.join(resources,'container'))?'container':'engine');
    this.owner=crypto.createHash('sha256').update(this.workspace).digest('hex').slice(0,14);
    this.name='winwhisper-'+this.owner;this.image='winwhisper/engine:1.0.0';
    this.configFile=path.join(this.workspace,'runtime-docker.json');this.gpu=false;this.flight=null;
    const candidates=[path.join(process.env.ProgramFiles||'C:\\Program Files','Docker','Docker','resources','bin','docker.exe'),path.join(process.env.LOCALAPPDATA||'','Programs','DockerDesktop','resources','bin','docker.exe')];
    this.docker=platform==='win32'?(candidates.find(x=>fs.existsSync(x))||'docker'):'docker';
    fs.mkdirSync(this.workspace,{recursive:true});
    for(const d of ['imports','exports','recordings','models','logs','home'])fs.mkdirSync(path.join(this.workspace,d),{recursive:true});
    try{const c=JSON.parse(fs.readFileSync(this.configFile,'utf8'));this.gpu=c.gpu===true;}catch{}
  }
  log(message){this.emit('log',String(message).replace(/\x1b\[[0-?]*[ -/]*[@-~]/g,''));}
  async inspect(){
    const result={mode:'docker',runtime:'docker',runtimeLabel:'Docker / WSL 2',docker:false,linux:false,image:false,engine:false,ollama:false,gpu:this.gpu,workspace:this.workspace,platform:this.platform};
    try{
      const info=JSON.parse(await this.run(this.docker,['info','--format','{{json .}}'],{timeout:12000}));
      result.docker=true;result.linux=info.OSType==='linux';
      if(!result.linux)result.error='Docker Desktop muss Linux-Container verwenden.';
      if(result.linux){try{await this.run(this.docker,['image','inspect',this.image]);result.image=result.engine=result.ollama=true;}catch{}}
    }catch(error){result.error='Docker Desktop ist nicht bereit. Bitte installieren/starten und WSL 2 aktivieren. '+error.message.slice(0,400);}
    result.ready=result.docker&&result.linux&&result.image;return result;
  }
  async prepare({device='auto'}={}){
    if(!['auto','cpu','gpu'].includes(device))throw new Error('Ungültiger Gerätemodus.');
    if(this.flight)return this.flight;this.flight=this._prepare(device).finally(()=>{this.flight=null;});return this.flight;
  }
  async _prepare(device){
    if(!['auto','cpu','gpu'].includes(device))throw new Error('Ungültiger Gerätemodus.');
    const status=await this.inspect();
    if(!status.docker||!status.linux){
      throw new Error(status.error||'Docker / WSL 2 muss extern über die Setup-Routine bereit gemacht werden.');
    }
    if(!status.image){
      if(!fs.existsSync(path.join(this.enginePath,'Dockerfile')))throw new Error('Dockerfile fehlt im Installer.');
      this.log('Baue die isolierte WhisperX-/Ollama-Engine in Docker (einmaliger Download).');
      await this.run(this.docker,['build','--progress','plain','--tag',this.image,'--file',path.join(this.enginePath,'Dockerfile'),this.enginePath],{
        timeout:2*60*60*1000,onLine:chunk=>this.log(chunk)
      });
    }
    let gpu=false;
    if(device!=='cpu'){
      try{
        await this.run(this.docker,['run','--rm','--gpus','all','--entrypoint','nvidia-smi',this.image],{timeout:120000});
        gpu=true;
      }catch(error){
        if(device==='gpu')throw new Error('NVIDIA-GPU in Docker nicht verfügbar: '+error.message.slice(-350));
        this.log('Docker-GPU nicht verfügbar; die CPU bleibt nutzbar.');
      }
    }
    this.gpu=gpu;
    atomicJSON(this.configFile,{version:1,gpu,device:device});
    return this.inspect();
  }
  async removeOwned(){let owner;try{owner=await this.run(this.docker,['inspect','--format','{{index .Config.Labels "io.winwhisper.owner"}}',this.name],{timeout:10000});}catch{return;}if(owner.trim()!==this.owner)throw new Error('Ein fremder Container verwendet denselben Namen. Er wird nicht beendet.');await this.run(this.docker,['rm','--force',this.name],{timeout:20000});}
  async start(){
    const info=await this.inspect();if(!info.ready)throw new Error(info.error||'Bitte zuerst den lokalen Container einrichten.');await this.removeOwned();
    const mount=`type=bind,source=${this.workspace},target=/data`;if(this.workspace.includes(','))throw new Error('Der Arbeitsordner darf für Docker kein Komma enthalten.');
    const args=['run','--rm','-i','--init','--name',this.name,'--label',`io.winwhisper.owner=${this.owner}`,'--cap-drop','ALL','--security-opt','no-new-privileges','--shm-size','1g','--mount',mount];if(this.gpu)args.push('--gpus','all');args.push(this.image);
    return this.spawn(this.docker,args,{windowsHide:true,shell:false,stdio:['pipe','pipe','pipe']});
  }
  async stop(){let owner;try{owner=await this.run(this.docker,['inspect','--format','{{index .Config.Labels "io.winwhisper.owner"}}',this.name],{timeout:5000});}catch{return;}if(owner.trim()===this.owner)await this.run(this.docker,['stop','--time','12',this.name],{timeout:18000});}
}

class RuntimeManager extends EventEmitter{
  constructor(options){
    super();this.workspace=path.resolve(options.workspace);this.platform=options.platform||process.platform;this.configFile=path.join(this.workspace,'runtime-choice.json');
    this.native=new NativeWindowsRuntime(options);this.docker=new DockerRuntime(options);
    for(const runtime of [this.native,this.docker])runtime.on('log',message=>this.emit('log',message));
    const saved=readJSON(this.configFile,{}).mode;this.mode=['native','docker'].includes(saved)?saved:(this.platform==='win32'?'native':'docker');
    if(this.platform!=='win32'&&this.mode==='native')this.mode='docker';
  }
  get active(){return this.mode==='native'?this.native:this.docker;}
  get flight(){return this.active.flight;}
  async select(mode){if(!['native','docker'].includes(mode))throw new Error('Unbekannte Laufzeit.');if(mode==='native'&&this.platform!=='win32')throw new Error('Windows nativ ist nur unter Windows verfügbar.');this.mode=mode;atomicJSON(this.configFile,{version:1,mode});return this.inspect();}
  async inspect(){const result=await this.active.inspect();return {...result,mode:this.mode,availableModes:this.platform==='win32'?['native','docker']:['docker']};}
  prepare(options){return this.active.prepare(options);}
  start(){return this.active.start();}
  stop(){return this.active.stop();}
}

module.exports={RuntimeManager,NativeWindowsRuntime,DockerRuntime,run};
