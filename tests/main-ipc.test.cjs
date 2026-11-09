"use strict";
// Execute production main-process wiring with Electron/runtime boundaries mocked.
const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {EventEmitter}=require('node:events');
async function harness(t){
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'winwhisper-main-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
  const handlers=new Map(),events=[],protocols=new Map(),fetches=[],gpuCalls=[];let win,options,requestPermission,checkPermission,schemes,openChoice={canceled:true};
  class Runtime extends EventEmitter{
    constructor({workspace}){super();this.workspace=workspace;this.mode='native';this.flight=null;fs.mkdirSync(path.join(workspace,'recordings'),{recursive:true});this.ready=false;}
    async inspect(){return {mode:this.mode,runtimeLabel:this.mode==='native'?'Windows nativ':'Docker / WSL 2',native:this.mode==='native',docker:this.mode==='docker'&&this.ready,linux:true,engine:this.ready,image:this.ready,ollama:this.mode==='docker'&&this.ready,ready:this.ready,workspace:this.workspace};}
    async prepare(){this.ready=true;return this.inspect();}
    async select(mode){this.mode=mode;this.ready=false;return this.inspect();}
    async stop(){}
  }
  class Backend extends EventEmitter{
    constructor(runtime){super();this.runtime=runtime;this.child=null;this.state={project:false,busy:false,recording:false,project_path:'',audio_url:'',recent:[]};}
    async connect(){this.child={};}
    async request(action,data){
      if(action==='external_record_start')this.state={...this.state,recording:true};
      if(action==='record_stop')this.state={...this.state,recording:false};
      if(['init','refresh','external_record_start','record_stop'].includes(action))this.emit('event',{type:'state',data:this.state});
      return true;
    }
    async restart(){this.child=null;}
    async shutdown(){this.child=null;}
  }
  class Window extends EventEmitter{
    constructor(value){super();options=value;win=this;this.webContents=new EventEmitter();this.webContents.getURL=()=> 'winwhisper://app/index.html';this.webContents.send=(_c,e)=>events.push(e);this.webContents.setWindowOpenHandler=fn=>this.openHandler=fn;}
    setMenu(){}loadURL(){}isDestroyed(){return false;}show(){}isMinimized(){return false;}focus(){}
  }
  const app=new EventEmitter();Object.assign(app,{setName(){},setAppUserModelId(){},requestSingleInstanceLock:()=>true,whenReady:()=>Promise.resolve(),getPath:()=>dir,isPackaged:false,quit(){}});
  const electron={app,BrowserWindow:Window,ipcMain:{handle:(n,fn)=>handlers.set(n,fn)},dialog:{showOpenDialog:async()=>openChoice,showErrorBox:(_t,msg)=>{throw new Error(msg);}},shell:{openPath:async()=>true,openExternal:async()=>true},protocol:{registerSchemesAsPrivileged:value=>schemes=value,handle:(scheme,handler)=>protocols.set(scheme,handler)},net:{fetch:async(url,options)=>{fetches.push({url,options});return new Response('asset',{status:200});}},session:{defaultSession:{setPermissionRequestHandler:fn=>requestPermission=fn,setPermissionCheckHandler:fn=>checkPermission=fn}}};
  const directory=path.resolve(__dirname,'../desktop');
  const context={require:name=>name==='electron'?electron:name==='./runtime.cjs'?{RuntimeManager:Runtime,run:async()=>''}:name==='./backend.cjs'?{Backend}:name==='./gpu-diagnostics.cjs'?{GpuDiagnostics:class {snapshot(options){gpuCalls.push(options);return Promise.resolve({mode:'native',gpu:{devices:[]},cuda:{ready:false},ollama:{models:[]}});}}}:name.startsWith('./')?require(path.join(directory,name)):require(name),__dirname:directory,process,console,setTimeout,clearTimeout,Uint8Array,ArrayBuffer,Buffer,URL,Response};
  vm.runInNewContext(fs.readFileSync(path.join(directory,'main.cjs'),'utf8'),context);
  await new Promise(r=>setImmediate(r));
  const trusted={sender:win.webContents,senderFrame:{url:win.webContents.getURL()}};
  return {handlers,events,options,win,trusted,dir,protocols,fetches,gpuCalls,schemes,openFile:file=>{openChoice={canceled:false,filePaths:[file]};},requestPermission:()=>requestPermission,checkPermission:()=>checkPermission};
}
test('main process uses isolated sandboxed renderer and blocks foreign/unknown IPC',async t=>{
  const h=await harness(t),web=h.options.webPreferences;assert.equal(web.nodeIntegration,false);assert.equal(web.contextIsolation,true);assert.equal(web.sandbox,true);
  await assert.rejects(async()=>h.handlers.get('studio:command')({...h.trusted,senderFrame:{url:'https://example.com'}},'init'),/autorisiert/);
  await assert.rejects(h.handlers.get('studio:command')(h.trusted,'arbitrary_shell'),/Unbekannte/);
  assert.throws(()=>h.handlers.get('studio:recent')(h.trusted,'/tmp/not-allowed'),/Bibliothek/);
  assert.equal(h.win.openHandler().action,'deny');
});
test('GPU diagnostics are read-only and require the trusted application window',async t=>{
  const h=await harness(t),diagnose=h.handlers.get('studio:gpu-diagnostics');
  assert.equal(typeof diagnose,'function');
  await assert.rejects(diagnose({...h.trusted,senderFrame:{url:'https://example.invalid'}}),/autorisiert/);
  const result=await diagnose(h.trusted);
  assert.equal(result.mode,'native');
  assert.equal(h.gpuCalls.length,1);
  assert.equal(h.gpuCalls[0].transcriptionDevice,'auto');
});

test('missing native runtime leaves a usable setup UI and seven output profiles',async t=>{
  const h=await harness(t);assert.equal(await h.handlers.get('studio:command')(h.trusted,'init'),true);
  assert(h.events.some(e=>e.type==='setup_status'&&!e.data.ready&&e.data.mode==='native'));const state=h.events.find(e=>e.type==='state').data;assert.equal(state.profiles.length,7);assert.equal(state.busy,false);
});
test('runtime selection can switch to Docker fallback before preparation',async t=>{
  const h=await harness(t);const status=await h.handlers.get('studio:setup')(h.trusted,'select',{mode:'docker'});assert.equal(status.mode,'docker');assert.equal(status.ready,false);
});
test('permissions allow only the trusted microphone and deny camera/display/foreign pages',async t=>{
  const h=await harness(t),handler=h.requestPermission();let allowed;
  handler(h.win.webContents,'media',v=>allowed=v,{mediaTypes:['audio']});assert.equal(allowed,true);
  handler(h.win.webContents,'media',v=>allowed=v,{mediaTypes:['video']});assert.equal(allowed,false);
  handler(h.win.webContents,'display-capture',v=>allowed=v,{mediaTypes:['audio']});assert.equal(allowed,false);
  handler({getURL:()=> 'https://example.com'},'media',v=>allowed=v,{mediaTypes:['audio']});assert.equal(allowed,false);
  assert.equal(h.checkPermission()(h.win.webContents,'media','file://',{mediaType:'audio'}),true);
});
test('native recording IPC creates and closes a real WAV only for its session token',async t=>{
  const h=await harness(t);await h.handlers.get('studio:setup')(h.trusted,'prepare',{device:'cpu'});
  const audio=h.handlers.get('studio:audio'),session=await audio(h.trusted,'start');
  await assert.rejects(audio(h.trusted,'append',{id:'wrong',sequence:0,pcm:Buffer.alloc(3200)}),/aktiv/);
  assert.equal(await audio(h.trusted,'append',{id:session.id,sequence:0,pcm:Buffer.alloc(3200)}),.1);
  await audio(h.trusted,'stop',{id:session.id});
  const records=path.join(h.dir,'workspace/recordings'),names=fs.readdirSync(records);assert.equal(names.length,1);const wav=fs.readFileSync(path.join(records,names[0]));assert.equal(wav.readUInt32LE(40),3200);assert.equal(wav.length,3244);
  assert(h.events.some(e=>e.type==='record_wave'));assert(h.events.some(e=>e.type==='backend_up'));
});
test('secure local scheme serves worklet modules and only scoped WAV streams with byte ranges',async t=>{
  const h=await harness(t),route=h.protocols.get('winwhisper');
  assert(h.schemes[0].privileges.secure);assert(h.schemes[0].privileges.supportFetchAPI);assert(!h.schemes[0].privileges.bypassCSP);
  assert.equal((await route({url:'winwhisper://app/pcm-worklet.js',method:'GET'})).status,200);
  assert.equal((await route({url:'winwhisper://app/%2e%2e%2fmain.cjs',method:'GET'})).status,404);
  assert.equal((await route({url:'winwhisper://audio/etc/passwd',method:'GET'})).status,404);
  assert.equal((await route({url:'winwhisper://audio/data/logs/token.json',method:'GET'})).status,404);
  assert.equal((await route({url:'winwhisper://audio/data/projects/p/preview.wav',method:'GET',headers:{Range:'bytes=44-100'}})).status,200);
  assert.equal(h.fetches.at(-1).options.headers.Range,'bytes=44-100');
});
test('large-file staging reports progress and locks competing jobs until the copy finishes',async t=>{
  const h=await harness(t);await h.handlers.get('studio:setup')(h.trusted,'prepare',{device:'cpu'});
  const source=path.join(h.dir,'Sitzung.wav');fs.writeFileSync(source,'original');h.openFile(source);
  const copy=fs.promises.copyFile;let release,entered;const copied=new Promise(r=>entered=r),gate=new Promise(r=>release=r);
  fs.promises.copyFile=async(...args)=>{entered();await gate;return copy(...args);};
  try{
    const opening=h.handlers.get('studio:file')(h.trusted,'audio');await copied;
    assert(h.events.some(e=>e.type==='state'&&e.data.busy&&e.data.operation==='Datei übertragen'&&e.data.cancelable===false));
    await assert.rejects(h.handlers.get('studio:command')(h.trusted,'transcribe'),/Dateiübertragung/);
    release();await opening;assert.equal(h.events.filter(e=>e.type==='state').at(-1).data.busy,false);assert.equal(fs.readFileSync(source,'utf8'),'original');
  }finally{release();fs.promises.copyFile=copy;}
});
