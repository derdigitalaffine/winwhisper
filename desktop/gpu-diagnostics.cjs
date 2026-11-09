"use strict";

// Read-only, on-demand GPU diagnostics. No shell commands and no external
// telemetry. NVIDIA utilization is system-wide, NOT proof a job used the GPU.
const fs=require("node:fs");
const http=require("node:http");
const {run,nvidiaSmi}=require("./runtime.cjs");

function number(value){
  const parsed=Number(String(value).trim());
  return Number.isFinite(parsed)&&parsed>=0?parsed:null;
}
function parseNvidiaSmi(text){
  return String(text).trim().split(/\r?\n/).filter(Boolean).map(line=>{
    const fields=line.split(/\s*,\s*/);
    if(fields.length<5)throw new Error("Unerwartete Ausgabe von nvidia-smi.");
    return {name:fields[0],totalMb:number(fields[1]),usedMb:number(fields[2]),
      utilization:number(fields[3]),driver:fields.slice(4).join(", ").trim()};
  });
}
function summarizeOllama(payload){
  if(!payload||!Array.isArray(payload.models))throw new Error("Ungültige Ollama-Antwort.");
  return payload.models.map(model=>{
    const total=number(model.size),vram=number(model.size_vram);
    let placement="Nicht bestimmbar";
    if(total!==null&&total>0&&vram!==null){
      if(vram===0)placement="CPU (Modellspeicher)";
      else if(vram>=total*0.98)placement="GPU (Modellspeicher)";
      else placement="CPU + GPU (Modellspeicher)";
    }
    return {name:String(model.name||model.model||"Unbekannt").slice(0,120),
      sizeGb:total===null?null:Math.round(total/1073741824*10)/10,
      vramGb:vram===null?null:Math.round(vram/1073741824*10)/10,placement};
  });
}
function fetchLocalOllama(port=11435){
  return new Promise((resolve,reject)=>{
    const request=http.get({hostname:"127.0.0.1",port,path:"/api/ps",timeout:1800,
      agent:false,headers:{Accept:"application/json"}},response=>{
      if(response.statusCode!==200){response.resume();reject(new Error("HTTP "+response.statusCode));return;}
      let body="";
      response.setEncoding("utf8");
      response.on("data",chunk=>{
        body+=chunk;
        if(body.length>262144)request.destroy(new Error("Ollama-Antwort zu groß."));
      });
      response.on("end",()=>{try{resolve(JSON.parse(body));}catch(error){reject(error);}});
      response.on("error",reject);
    });
    request.on("timeout",()=>request.destroy(new Error("Zeitüberschreitung")));
    request.on("error",reject);
  });
}
const PYTHON_CUDA_CHECK="import json; from whisperx_studio.gpu_runtime import probe; print(json.dumps(probe()))";

class GpuDiagnostics{
  constructor(runtime,{runner=run,ollamaFetch=fetchLocalOllama,clock=()=>Date.now()}={}){
    this.runtime=runtime;this.runner=runner;this.ollamaFetch=ollamaFetch;this.clock=clock;
    this.cachedCuda=null;this.flight=null;
  }
  async cuda(){
    const runtime=this.runtime;
    const docker=runtime.mode==="docker";
    const active=runtime.active;
    if(docker&&!active.gpu)return {status:"disabled",reason:"Docker wurde ohne NVIDIA-GPU eingerichtet."};
    if(!docker&&!fs.existsSync(active.python))return {status:"missing",reason:"Native Python-Umgebung nicht installiert."};
    if(docker&&(!active.image||!active.name))return {status:"missing",reason:"Docker-Engine noch nicht gestartet."};
    const config=active.configFile;
    let revision=0;
    try{revision=fs.statSync(config).mtimeMs;}catch{}
    const key=[runtime.mode,config,revision,docker?Boolean(active.gpu):active.python].join("|");
    if(this.cachedCuda?.key===key&&this.clock()-this.cachedCuda.at<(this.cachedCuda.data.status==="ok"?60000:5000))return this.cachedCuda.data;
    let data;
    try{
      const command=docker?active.docker:active.python;
      const args=docker?["exec",active.name,"/opt/venv/bin/python","-c",PYTHON_CUDA_CHECK]:["-c",PYTHON_CUDA_CHECK];
      const output=await this.runner(command,args,{timeout:25000,
        ...(!docker?{cwd:active.enginePath,env:active._env()}:{})});
      const raw=JSON.parse(output.trim().split(/\r?\n/).at(-1));
      data={status:"ok",torchCuda:raw.torchCuda===true,ct2Devices:Number(raw.ct2Devices)||0,
        torchVersion:String(raw.torchVersion||""),cudaVersion:raw.cudaVersion||null,
        computeTypes:Array.isArray(raw.computeTypes)?raw.computeTypes:[],
        error:String(raw.ct2Error||"").slice(0,1000),dllPaths:raw.dllPaths||[],deviceName:raw.deviceName||"",freeMb:raw.freeMb||0};
      data.ready=(raw.ready!==false)&&data.torchCuda&&data.ct2Devices>0&&data.computeTypes.length>0;
    }catch(error){data={status:"error",ready:false,reason:String(error.message).slice(-350)};}
    this.cachedCuda={key,at:this.clock(),data};
    return data;
  }
  async nvidia(){
    if(this.runtime.platform!=="win32")return {status:"unsupported",devices:[],
      reason:"NVIDIA-Windows-Treiberdiagnose nur unter Windows verfügbar."};
    try{
      const result=await this.runner(nvidiaSmi(),
        ["--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version","--format=csv,noheader,nounits"],
        {timeout:5000});
      const devices=parseNvidiaSmi(result);
      return {status:devices.length?"ok":"missing",devices,
        reason:devices.length?"":"Keine NVIDIA-GPU erkannt."};
    }catch(error){return {status:"missing",devices:[],reason:"nvidia-smi nicht erreichbar oder NVIDIA-Treiber fehlt."};}
  }
  async ollama(){
    try{
      let response;
      if(this.runtime.mode==="docker"){
        const docker=this.runtime.docker;
        if(!docker?.name)throw new Error("Docker-Engine nicht bereit.");
        const script="import urllib.request,sys; sys.stdout.write(urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=2).read(262145).decode('utf-8'))";
        const output=await this.runner(docker.docker,["exec",docker.name,"python3","-c",script],{timeout:5000});
        response=JSON.parse(output);
      }else{
        response=await this.ollamaFetch(11435);
      }
      return {status:"ok",models:summarizeOllama(response),reason:""};
    }catch(error){return {status:"offline",models:[],reason:"Lokaler Ollama-Dienst nicht erreichbar oder nicht gestartet."};}
  }
  snapshot({transcriptionDevice="auto"}={}){
    if(this.flight)return this.flight;
    this.flight=this._snapshot(transcriptionDevice).finally(()=>{this.flight=null;});
    return this.flight;
  }
  async _snapshot(transcriptionDevice){
    const selected=["auto","gpu","cpu"].includes(transcriptionDevice)?transcriptionDevice:"auto";
    const [gpu,cuda,ollama]=await Promise.all([this.nvidia(),this.cuda(),this.ollama()]);
    const active=this.runtime.active;
    let configured="Nicht eingerichtet";
    if(selected==="cpu")configured="CPU ausdrücklich ausgewählt";
    else if(cuda.ready)configured="GPU verfügbar – tatsächliche Nutzung nur während eines Auftrags messbar";
    else if(selected==="gpu")configured="GPU angefordert, aber CUDA/CTranslate2 nicht betriebsbereit";
    else configured="CPU-Fallback: CUDA/CTranslate2 nicht betriebsbereit";
    return {
      timestamp:new Date(this.clock()).toISOString(),mode:this.runtime.mode,
      gpu,cuda,ollama,
      whisperx:{selected,configured,
        setupGpu:this.runtime.mode==="docker"?active.gpu===true:active._config().gpu===true,
        running:this.runtime.mode==="native"?Boolean(active.child&&active.child.exitCode===null):null}
    };
  }
}
module.exports={GpuDiagnostics,parseNvidiaSmi,summarizeOllama,fetchLocalOllama};
