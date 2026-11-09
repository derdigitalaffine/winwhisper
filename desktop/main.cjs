"use strict";
const {app,BrowserWindow,ipcMain,dialog,shell,session,protocol,net}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {randomUUID}=require('node:crypto');
const {RuntimeManager,run}=require('./runtime.cjs');
const {Backend}=require('./backend.cjs');
const {WorkspaceFiles}=require('./files.cjs');
const {WavWriter,repairRecordings}=require('./wav.cjs');
const profiles=require('./profiles.json');
app.setName('WinWhisper Studio');
if(process.platform==='win32')app.setAppUserModelId('de.local.winwhisper.studio');
const TRUSTED='winwhisper://app/index.html';
protocol.registerSchemesAsPrivileged([{scheme:'winwhisper',privileges:{standard:true,secure:true,supportFetchAPI:true,corsEnabled:true,stream:true}}]);
let win,runtime,backend,files,lastState=null,capture=null,reconnecting=null,restoring=false,closing=false,quitting=false,closeTimer,fileTransfer=false;
const resourceRoot=()=>app.isPackaged?process.resourcesPath:path.resolve(__dirname,'..');
const allowed=new Set(['init','refresh','logs','cancel','waveform','settings','transcribe','generate','setup_speakers','metadata','update_segment','speakers','cut','trim','undo','model_pull','warmup_asr','remove_asr']);

function send(event){if(win&&!win.isDestroyed())win.webContents.send('studio:event',event);}
function checkSender(event){if(event.sender!==win?.webContents||event.senderFrame?.url!==TRUSTED)throw new Error('Nicht autorisierte Fensteranfrage.');}
function emptyState(){return {project:false,busy:false,recording:false,status:'Lokale Windows-Umgebung einrichten.',title:'Neue Aufnahme',date:'',context:'',project_path:'',duration:0,spans:[],audio_url:'',segments:[],speakers:{},reports:[],can_undo:false,preliminary:false,models:[],model_status:'Lokale KI-Laufzeit noch nicht gestartet',microphones:[{name:'Standardmikrofon',value:''}],recent:[],settings:{language:'de',asr_model:'small',device:'auto',diarize:false,speaker_count:'auto',microphone:'',live:false,finalize_live:true},profiles};}
function receive(event){
  if(event.type==='state'){
    if(restoring&&!event.data.project)return;
    lastState=event.data;
    const state={...event.data};
    if(fileTransfer){state.cancelable=!!event.data.busy;state.busy=true;state.operation="Datei übertragen";state.status="Datei wird im lokalen Arbeitsbereich vorbereitet …";}
    if(state.audio_url)state.audio_url=files.streamURL(state.audio_url);
    send({type:'state',data:state});
  }else if(event.type!=='audio_changed')send(event);
}
async function recover(){
  if(reconnecting)return reconnecting;
  reconnecting=(async()=>{
    if(backend.child)return backend.request('refresh');
    const project=lastState?.project_path;
    restoring=!!project;
    try{
      await backend.connect();
      if(project){
        let listener,timer;
        const loaded=new Promise((resolve,reject)=>{
          listener=event=>{
            if(event.type==='state'&&!event.data.busy){event.data.project?resolve(true):reject(new Error(event.data.status||'Projekt konnte nicht wiederhergestellt werden.'));}
          };
          backend.on('event',listener);timer=setTimeout(()=>reject(new Error('Projektöffnung dauert zu lange.')),60000);
        });
        try{await Promise.all([loaded,backend.request('open_project',{path:project})]);}
        finally{clearTimeout(timer);backend.off('event',listener);}
      }else await backend.request('init',{},60000);
      const result=await backend.request('refresh');send({type:'backend_up'});return result;
    }finally{restoring=false;}
  })().finally(()=>{reconnecting=null;});
  return reconnecting;
}
async function command(action,data={}){
  if(!allowed.has(action))throw new Error('Unbekannte Aktion.');
  if(fileTransfer&&!['logs','waveform','cancel'].includes(action))throw new Error('Bitte die laufende Dateiübertragung abwarten.');
  if(action==='init'&&!backend.child){
    const status=await runtime.inspect();send({type:'setup_status',data:status});
    if(!status.ready){receive({type:'state',data:lastState||emptyState()});return true;}
    return recover();
  }
  if(action==='refresh')return recover();
  if(!backend.child)throw new Error('Bitte zuerst unter „Einrichtung“ die lokale KI-Laufzeit starten.');
  return backend.request(action,data);
}
async function chooseFile(mode,data={}){
  if(fileTransfer||lastState?.busy||lastState?.recording||capture)throw new Error('Bitte zuerst die Aufnahme oder Verarbeitung beenden.');
  if(!backend.child)throw new Error('Bitte zuerst die lokale KI-Laufzeit einrichten und starten.');
  fileTransfer=true;receive({type:'state',data:lastState||emptyState()});
  try {
  const open={audio:['Audio oder Video öffnen',[{name:'Audio / Video',extensions:['wav','mp3','m4a','flac','ogg','opus','aac','wma','aiff','mp4','mkv','webm','mov']},{name:'Alle Dateien',extensions:['*']}]],project:['Projekt öffnen',[{name:'WinWhisper-Projekt',extensions:['json']}]],transcript:['WhisperX-Transkript importieren',[{name:'JSON',extensions:['json']}]]};
  if(open[mode]){
    const [title,filters]=open[mode];
    const selected=await dialog.showOpenDialog(win,{title,filters,properties:['openFile']});
    if(selected.canceled||!selected.filePaths.length)return false;
    const logical=await files.import(selected.filePaths[0]);
    return backend.request({audio:'load_audio',project:'open_project',transcript:'import_transcript'}[mode],{path:logical});
  }
  const base=(lastState?.title||'Sitzung').replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,90);
  const types={audio_export:['Audio exportieren','_bearbeitet.wav','WAV','wav','export_audio'],save_project:['Projektdatei speichern','.whisperx.json','Projekt','json','save_as'],report_export:['Auswertung speichern','_Auswertung.md','Markdown','md','export_report'],transcript_export:['Transkript speichern','_Transkript.md','Markdown','md','export_transcript']};
  const choice=types[mode];if(!choice)throw new Error('Unbekannter Dateidialog.');
  const result=await dialog.showSaveDialog(win,{title:choice[0],defaultPath:base+choice[1],filters:[{name:choice[2],extensions:[choice[3]]}]});
  if(result.canceled||!result.filePath)return false;
  files.checkDestination(result.filePath);
  const logical=files.exportPath('.'+choice[3]);
  if(mode==='audio_export'){
    let listener,timer;
    const completed=new Promise((resolve,reject)=>{
      listener=event=>{if(event.type==='state'&&!event.data.busy){event.data.status?.startsWith('Fehler:')?reject(new Error(event.data.status)):resolve();}};
      backend.on('event',listener);timer=setTimeout(()=>reject(new Error('Audioexport dauert zu lange.')),30*60*1000);
    });
    try{await Promise.all([completed,backend.request(choice[4],{path:logical})]);await files.export(logical,result.filePath);}
    finally{clearTimeout(timer);backend.off('event',listener);}
  }else{
    await backend.request(choice[4],{path:logical,index:data.index});
    await files.export(logical,result.filePath);
  }
  send({type:'log',data:'Exportiert: '+result.filePath});return true;
  } finally { fileTransfer=false;receive({type:'state',data:lastState||emptyState()}); }
}
async function startCapture(){
  if(fileTransfer||capture||lastState?.busy||lastState?.recording)throw new Error('Eine Aufnahme, Dateiübertragung oder Verarbeitung läuft bereits.');
  if(!backend.child)throw new Error('Bitte zuerst die lokale KI-Laufzeit starten.');
  const file=path.join(runtime.workspace,'recordings',new Date().toISOString().replace(/[:.]/g,'-')+'-'+randomUUID()+'.wav');
  const writer=new WavWriter(file),id=randomUUID();
  capture={id,writer,peaks:[],stride:1,count:0,peak:0,lastEvent:0};
  try{await backend.request('external_record_start',{path:files.logical(file)});return {id,rate:16000};}
  catch(error){writer.close();capture=null;throw error;}
}
function appendCapture(id,sequence,pcm){
  const c=capture;if(!c||c.id!==id)throw new Error('Die Aufnahme ist nicht mehr aktiv.');
  if(!(pcm instanceof Uint8Array)&&!(pcm instanceof ArrayBuffer))throw new Error('Ungültiges Audiopaket.');
  const bytes=Buffer.from(pcm instanceof ArrayBuffer?new Uint8Array(pcm):pcm);
  const elapsed=c.writer.append(sequence,bytes);
  let peak=0;for(let i=0;i<bytes.length;i+=2)peak=Math.max(peak,Math.abs(bytes.readInt16LE(i))/32768);
  c.peak=Math.max(c.peak,peak);c.count++;
  if(c.count===c.stride){c.peaks.push(c.peak);c.peak=0;c.count=0;}
  if(c.peaks.length>=4096){const compact=[];for(let i=0;i<c.peaks.length;i+=2)compact.push(Math.max(c.peaks[i],c.peaks[i+1]||0));c.peaks=compact;c.stride*=2;}
  if(Date.now()-c.lastEvent>200){send({type:'record_wave',data:{elapsed,peaks:c.peaks}});c.lastEvent=Date.now();}
  return elapsed;
}
async function stopCapture(id){
  const c=capture;if(!c)return true;if(id&&id!==c.id)throw new Error('Ungültige Aufnahme.');
  capture=null;
  try{c.writer.close();}finally{if(backend.child)await backend.request('record_stop');}
  return true;
}
async function systemAction(action,options={}){
  if(!['wsl','docker','start-docker','ollama','whisperx'].includes(action))throw new Error('Unbekannter Einrichtungsschritt.');
  if(process.platform!=='win32')throw new Error('Dieser Einrichtungsschritt ist nur unter Windows verfügbar.');
  const script=path.join(resourceRoot(),'scripts','Initialize-System.ps1');
  const args=['-NoProfile','-ExecutionPolicy','Bypass','-File',script,'-Action',action,'-Workspace',runtime.workspace,'-Resources',resourceRoot()];
  if(action==='whisperx'){
    const device=options.device||'auto';
    if(!['auto','cpu','gpu'].includes(device))throw new Error('Ungültiger Gerätemodus.');
    args.push('-Device',device);
  }
  return run('powershell.exe',args,{timeout:30*60*1000,onLine:data=>send({type:'setup_log',data})});
}
async function finishClose(){
  if(quitting)return;quitting=true;clearTimeout(closeTimer);
  try{await stopCapture();}catch(error){send({type:'log',data:error.message});}
  await backend.shutdown();win?.close();
}
function makeWindow(){
  win=new BrowserWindow({width:1540,height:980,minWidth:1080,minHeight:720,show:false,frame:false,title:'WinWhisper Studio',backgroundColor:'#f5f6f8',icon:path.join(__dirname,'icon.png'),webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
  win.setMenu(null);win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  win.webContents.on('will-navigate',(event,url)=>{if(url!==TRUSTED)event.preventDefault();});
  let reloads=0;
  win.webContents.on('render-process-gone',async()=>{try{await stopCapture();}catch{}if(!quitting&&reloads++<1)win.webContents.reload();});
  win.on('ready-to-show',()=>win.show());
  win.on('close',async event=>{
    if(quitting)return;event.preventDefault();if(closing)return;closing=true;
    if(fileTransfer||runtime.flight||lastState?.busy||lastState?.recording||capture){
      const response=await dialog.showMessageBox(win,{type:'question',message:'Laufende Aufnahme oder Verarbeitung beenden und schließen?',detail:'Originalaufnahmen und gespeicherte Projekte bleiben erhalten.',buttons:['Weiterarbeiten','Beenden und schließen'],defaultId:0,cancelId:0});
      if(response.response!==1){closing=false;return;}
    }
    send({type:'prepare_close'});closeTimer=setTimeout(finishClose,30000);
  });
  win.loadURL(TRUSTED);
}
if(!app.requestSingleInstanceLock())app.quit();
else{
  app.on('second-instance',()=>{if(win){if(win.isMinimized())win.restore();win.show();win.focus();}});
  app.whenReady().then(()=>{
    const resources=app.isPackaged?process.resourcesPath:path.resolve(__dirname,'..');
    runtime=new RuntimeManager({workspace:path.join(app.getPath('userData'),'workspace'),resources});
    files=new WorkspaceFiles(runtime.workspace);backend=new Backend(runtime);
    const assets=new Set(['index.html','styles.css','app.js','renderer-core.js','setup.js','native-recorder.js','pcm-worklet.js','icon.svg','icon.png']);
    protocol.handle('winwhisper',request=>{
      const url=new URL(request.url);
      if(!['GET','HEAD'].includes(request.method))return new Response('Method not allowed',{status:405});
      if(url.host==='app'){
        const file=decodeURIComponent(url.pathname.slice(1));
        if(!assets.has(file))return new Response('Not found',{status:404});
        return net.fetch(pathToFileURL(path.join(__dirname,file)).href,{method:request.method});
      }
      if(url.host==='audio'){
        try{
          const logical=decodeURIComponent(url.pathname);
          if(!logical.endsWith('.wav'))throw new Error('Unsupported audio');
          return net.fetch(pathToFileURL(files.host(logical)).href,{method:request.method,headers:request.headers});
        }catch{return new Response('Not found',{status:404});}
      }
      return new Response('Not found',{status:404});
    });
    const repaired=repairRecordings(path.join(runtime.workspace,'recordings'));
    backend.on('event',receive);
    backend.on('down',message=>{if(lastState)lastState={...lastState,busy:false,recording:false};if(capture){capture.writer.close();capture=null;}send({type:'backend_down',data:message});});
    runtime.on('log',data=>send({type:'setup_log',data}));
    const ses=session.defaultSession;
    ses.setPermissionRequestHandler((web,permission,callback,details)=>callback(web===win?.webContents&&web.getURL()===TRUSTED&&permission==='media'&&Array.isArray(details.mediaTypes)&&details.mediaTypes.length>0&&details.mediaTypes.every(x=>x==='audio')));
    ses.setPermissionCheckHandler((web,permission,_origin,details)=>web===win?.webContents&&web.getURL()===TRUSTED&&permission==='media'&&details.mediaType==='audio');
    ipcMain.handle('studio:command',(e,action,data)=>{checkSender(e);return command(action,data);});
    ipcMain.handle('studio:file',(e,mode,data)=>{checkSender(e);return chooseFile(mode,data);});
    ipcMain.handle('studio:recent',(e,file)=>{checkSender(e);if(!lastState?.recent.some(r=>r.path===file))throw new Error('Projekt ist nicht in der Bibliothek.');return backend.request('open_project',{path:file});});
    ipcMain.handle('studio:audio',async(e,action,data={})=>{checkSender(e);if(action==='start')return startCapture();if(action==='append')return appendCapture(data.id,data.sequence,data.pcm);if(action==='stop')return stopCapture(data.id);throw new Error('Ungültige Audioaktion.');});
    ipcMain.handle('studio:setup',async(e,action,data={})=>{
      checkSender(e);
      if(action==='status')return runtime.inspect();
      if(action==='select'){
        if(fileTransfer||lastState?.busy||lastState?.recording||capture)throw new Error('Bitte laufende Arbeit zuerst beenden.');
        if(backend.child)await backend.restart();
        const result=await runtime.select(data.mode);send({type:'setup_status',data:result});
        if(result.ready)await recover();return runtime.inspect();
      }
      if(action==='prepare'){
        if(fileTransfer||lastState?.busy||lastState?.recording||capture)throw new Error('Bitte laufende Arbeit zuerst beenden.');
        if(backend.child)throw new Error('Die Laufzeit läuft bereits. Für einen Gerätewechsel zuerst „Umgebung neu starten“ verwenden.');
        const result=await runtime.prepare(data);await recover();return result;
      }
      if(action==='start'){await recover();return runtime.inspect();}
      if(action==='restart'){
        if(fileTransfer||lastState?.busy||lastState?.recording||capture)throw new Error('Bitte laufende Arbeit zuerst beenden.');
        await backend.restart();await recover();return runtime.inspect();
      }
      if(action==='workspace')return shell.openPath(runtime.workspace);
      if(action==='system'){
        if(data.action==='whisperx'){
          if(runtime.mode!=='native')throw new Error('WhisperX nativ kann nur im Windows-Modus eingerichtet werden.');
          if(fileTransfer||lastState?.busy||lastState?.recording||capture||backend.child)throw new Error('Bitte zuerst die laufende Verarbeitung beenden und die Windows-Laufzeit stoppen, bevor sie repariert wird.');
        }
        const result=await systemAction(data.action,data);
        if(data.action==='whisperx'){
          // A prior failed health check must not survive a successful repair.
          runtime.native.health=null;
          const status=await runtime.inspect();
          send({type:'setup_status',data:status});
          if(!status.ready)throw new Error(status.error||'Die Windows-Laufzeit konnte nach der Einrichtung nicht gestartet werden.');
          await recover();
        }
        if(data.action==='ollama'&&runtime.mode==='native'&&backend.child){await backend.restart();await recover();}
        return result;
      }
      throw new Error('Unbekannte Einrichtungsaktion.');
    });
    ipcMain.handle('studio:window',(e,action)=>{checkSender(e);if(action==='minimize')win.minimize();else if(action==='maximize')win.isMaximized()?win.unmaximize():win.maximize();else if(action==='close')win.close();else if(action==='close-ready'&&closing)return finishClose();else if(action==='close-cancel'){clearTimeout(closeTimer);closing=false;}});
    ipcMain.handle('studio:help',(e)=>{checkSender(e);return shell.openPath(path.join(resourceRoot(),'README.md'));});
    ipcMain.handle('studio:link',(e,which)=>{checkSender(e);const links={account:'https://huggingface.co/join',model:'https://huggingface.co/pyannote/speaker-diarization-community-1',token:'https://huggingface.co/settings/tokens',docker:'https://docs.docker.com/desktop/setup/install/windows-install/',wsl:'https://learn.microsoft.com/windows/wsl/install',ollama:'https://ollama.com/download/windows'};if(!links[which])throw new Error('Unbekannter Link.');return shell.openExternal(links[which]);});
    makeWindow();
    win.webContents.on('did-finish-load',()=>{for(const file of repaired)send({type:'log',data:'Unvollständige WAV-Aufnahme wiederhergestellt: '+file});});
  }).catch(error=>{dialog.showErrorBox('WinWhisper konnte nicht starten',error.message);app.quit();});
  app.on('before-quit',event=>{if(!quitting&&backend){event.preventDefault();finishClose();}});
  app.on('window-all-closed',()=>app.quit());
}
