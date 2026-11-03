/* Optional real-container acceptance probe. Never uses the desktop's workspace.
 * node scripts/verify-container.cjs --audio /path/test.wav [--transcribe]
 *   [--model-store /path/ollama] [--hf-cache /path/huggingface/hub]
 *   [--torch-cache /path/torch] [--models] [--cpu]
 */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {DockerRuntime}=require('../desktop/runtime.cjs');
const {Backend}=require('../desktop/backend.cjs');
const root=path.resolve(__dirname,'..'),args=process.argv.slice(2);
const option=name=>args.includes(name)?args[args.indexOf(name)+1]:null;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  const audio=option('--audio');if(!audio||!fs.statSync(audio).isFile())throw new Error('--audio requires a test recording.');
  const workspace=fs.mkdtempSync(path.join(root,'validation/container-qa-'));
  const modelStore=option('--model-store');
  const spawnProcess=(cmd,argv,opts)=>{
    if(modelStore){argv=[...argv.slice(0,-1),...['blobs','manifests'].flatMap(dir=>['--mount',`type=bind,source=${path.resolve(modelStore,dir)},target=/data/models/ollama/${dir},readonly`]),argv.at(-1)];}
    return spawn(cmd,argv,opts);
  };
  const runtime=new DockerRuntime({workspace,resources:root,spawnProcess});
  const backend=new Backend(runtime),result={workspace,checks:[],passed:false};let state;
  backend.on('event',event=>{if(event.type==='state')state=event.data;else if(event.type==='log')fs.appendFileSync(path.join(workspace,'engine.log'),String(event.data)+'\n');});
  backend.on('down',error=>console.error(error));
  const check=(name,details={})=>{result.checks.push({name,passed:true,...details});console.log(name,JSON.stringify(details));};
  async function job(action,data={},timeout=120000){
    await backend.request(action,data,60000);const until=Date.now()+timeout;
    while(!state||state.busy){if(Date.now()>until){await backend.request('cancel');throw new Error('Job timeout: '+action);}await pause(200);}
    if(state.status.startsWith('Fehler:'))throw new Error(state.status);
    return state;
  }
  try{
    const hf=option('--hf-cache');
    if(hf){const dir='models--Systran--faster-whisper-small',target=path.join(workspace,'models/huggingface/hub',dir);fs.mkdirSync(path.dirname(target),{recursive:true});fs.cpSync(path.join(hf,dir),target,{recursive:true,verbatimSymlinks:true,mode:fs.constants.COPYFILE_FICLONE});}
    const torch=option('--torch-cache');
    if(torch)fs.cpSync(torch,path.join(workspace,'models/torch'),{recursive:true,verbatimSymlinks:true,mode:fs.constants.COPYFILE_FICLONE});
    result.runtime=await runtime.prepare({device:args.includes('--cpu')?'cpu':'auto'});check('Device preparation',{gpu:result.runtime.gpu});
    await backend.connect();await backend.request('init',{},60000);
    check('Private stdio service starts',{profiles:state.profiles.length});assert.equal(state.profiles.length,7);
    fs.copyFileSync(audio,path.join(workspace,'imports/test.wav'));
    await job('load_audio',{path:'/data/imports/test.wav'});assert(state.duration>0);const duration=state.duration;
    check('FFmpeg import and waveform',{duration,peaks:(await backend.request('waveform',{start:0,end:duration,width:400})).length});
    await job('cut',{start:0,end:Math.min(0.5,duration/4)});assert(state.duration<duration);
    await job('undo');assert(Math.abs(state.duration-duration)<0.01);check('Non-destructive cut and undo');
    if(args.includes('--transcribe')){
      await backend.request('settings',{asr_model:'small',language:'auto',device:'auto',diarize:false});
      await job('transcribe',{},15*60*1000);assert(state.segments.length>0);check('Real WhisperX transcription',{segments:state.segments.length,text:state.segments.map(s=>s.text).join(' ')});
    }
    if(args.includes('--models')){
      const segments=[
        {start:0,end:2,speaker:'SPEAKER_00',text:'Ich übernehme den Bericht bis Freitag.'},
        {start:2,end:4,speaker:'SPEAKER_01',text:'Ich schlage vor, die Kosten erst noch zu prüfen. Dazu ist heute nichts beschlossen.'},
        {start:4,end:6,speaker:'SPEAKER_00',text:'Danke. Die Kostenfrage bleibt also offen.'}
      ];
      fs.writeFileSync(path.join(workspace,'imports/fixture.json'),JSON.stringify({segments}));
      await job('import_transcript',{path:'/data/imports/fixture.json'});
      await backend.request('speakers',{names:{SPEAKER_00:'Anna',SPEAKER_01:'Ben'}});
      await backend.request('refresh');await pause(500);
      for(const model of ['gemma4:e2b','qwen3:14b-q4_K_M']){
        assert(state.models.includes(model),'Missing test model: '+model);
        const before=state.reports.length;
        await job('generate',{kind:'tasks',models:[model],options:{language:'de',detail:'detailed',verify:true}},20*60*1000);
        assert.equal(state.reports.length,before+1);assert.equal(state.reports.at(-1).kind,'tasks');
        const destination='/data/exports/'+model.split(':')[0]+'-tasks.md';
        await backend.request('export_report',{path:destination,index:state.reports.length-1});
        const markdown=fs.readFileSync(path.join(workspace,destination.slice(6)),'utf8');assert(markdown.length>20);
        check('Local task report and Markdown export',{model,markdown});
      }
    }
    result.passed=true;
  }finally{
    await backend.shutdown();
    fs.writeFileSync(path.join(root,'validation/container-smoke.json'),JSON.stringify(result,null,2)+'\n');
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
