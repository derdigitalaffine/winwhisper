"use strict";
const {test}=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),os=require("node:os"),path=require("node:path");
const {GpuDiagnostics,parseNvidiaSmi,summarizeOllama}=require("../desktop/gpu-diagnostics.cjs");
function tmp(t){
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),"winwhisper-gpu-"));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  return directory;
}
const CUDA_OK=JSON.stringify({torchCuda:true,torchVersion:"2.8.0",cudaVersion:"12.8",ct2Devices:1,ct2Error:"",computeTypes:["float16","int8"]});

test("NVIDIA sampling parses GPU name, VRAM, utilization and driver; missing fields never fake zeroes",()=>{
  assert.deepEqual(parseNvidiaSmi("NVIDIA RTX 4070, 8192, 2500, 68, 581.00\r\n"),[
    {name:"NVIDIA RTX 4070",totalMb:8192,usedMb:2500,utilization:68,driver:"581.00"}
  ]);
  assert.equal(parseNvidiaSmi("NVIDIA GPU, N/A, 0, N/A, 580.00")[0].totalMb,null);
  assert.throws(()=>parseNvidiaSmi("bad"),/Unerwartete/);
});

test("Ollama /api/ps differentiates full CPU, full GPU, hybrid, no models, and unknown",()=>{
  const GB=1073741824;
  assert.deepEqual(summarizeOllama({models:[]}),[]);
  assert.deepEqual(summarizeOllama({models:[
    {name:"cpu:latest",size:8*GB,size_vram:0},
    {name:"gpu:latest",size:8*GB,size_vram:8*GB},
    {name:"mixed:latest",size:8*GB,size_vram:4*GB},
    {name:"unknown",size:8*GB}
  ]}).map(m=>m.placement),[
    "CPU (Modellspeicher)","GPU (Modellspeicher)","CPU + GPU (Modellspeicher)","Nicht bestimmbar"
  ]);
  assert.throws(()=>summarizeOllama({models:"invalid"}),/Ungültige/);
});

test("native GPU diagnostics inspect managed Python environment and cache costly CUDA imports",async t=>{
  const root=tmp(t),python=path.join(root,"python.exe"),configFile=path.join(root,"runtime.json");
  fs.writeFileSync(python,"fake");fs.writeFileSync(configFile,'{"version":2,"gpu":true}');
  const calls=[];let time=100000;
  const rt={mode:"native",platform:"win32",active:{
    python,enginePath:root,configFile,_env:()=>({PATH:"test"}),_config:()=>({gpu:true}),child:{exitCode:null}
  }};
  const diag=new GpuDiagnostics(rt,{
    clock:()=>time,
    runner:async(command,args)=>{
      calls.push({command,args});
      if(command==="nvidia-smi.exe")return "NVIDIA RTX A2000, 12288, 7168, 44, 560.00";
      if(command===python)return CUDA_OK;
      throw new Error("unexpected process");
    },
    ollamaFetch:async(port)=>{
      assert.equal(port,11435);
      return {models:[{name:"qwen",size:8589934592,size_vram:4294967296}]};
    }
  });
  let state=await diag.snapshot({transcriptionDevice:"auto"});
  assert.equal(state.gpu.devices[0].usedMb,7168);
  assert.equal(state.cuda.ready,true);
  assert.equal(state.whisperx.setupGpu,true);
  assert.equal(state.whisperx.running,true);
  assert.match(state.whisperx.configured,/GPU verfügbar/);
  assert.equal(state.ollama.models[0].placement,"CPU + GPU (Modellspeicher)");
  await diag.snapshot({transcriptionDevice:"cpu"});
  assert.equal(calls.filter(c=>c.command===python).length,1);
  assert.match((await diag.snapshot({transcriptionDevice:"cpu"})).whisperx.configured,/CPU ausdrücklich/);
  time+=61000;
  await diag.snapshot();
  assert.equal(calls.filter(c=>c.command===python).length,2);
  assert(calls.every(c=>c.command==="nvidia-smi.exe"||c.command===python));
});

test("CUDA failure never claims a GPU transcription, Ollama offline does not block other fields",async t=>{
  const root=tmp(t),python=path.join(root,"python.exe");fs.writeFileSync(python,"fake");
  const active={python,configFile:path.join(root,"runtime.json"),enginePath:root,_env:()=>({}),_config:()=>({gpu:false})};
  const diag=new GpuDiagnostics({mode:"native",platform:"win32",active},{
    runner:async(command)=>{throw new Error(command==="nvidia-smi.exe"?"missing driver":"CUDA import failed");},
    ollamaFetch:async()=>{throw new Error("ECONNREFUSED");}
  });
  const state=await diag.snapshot({transcriptionDevice:"gpu"});
  assert.equal(state.gpu.status,"missing");assert.equal(state.cuda.ready,false);
  assert.equal(state.cuda.status,"error");assert.equal(state.ollama.status,"offline");
  assert.match(state.whisperx.configured,/nicht betriebsbereit/);
});

test("Docker GPU diagnostics query only the owned engine via docker exec, not the host Ollama port",async t=>{
  const root=tmp(t),configFile=path.join(root,"runtime.json");fs.writeFileSync(configFile,"{}");
  const docker={gpu:true,image:"engine",name:"winwhisper-owned",docker:"docker.exe",configFile};
  const calls=[];
  const diag=new GpuDiagnostics({mode:"docker",platform:"win32",active:docker,docker},{
    runner:async(command,args)=>{
      calls.push({command,args});
      if(command==="nvidia-smi.exe")return "GPU, 16384, 3500, 23, 581.00";
      if(args.includes("/opt/venv/bin/python"))return CUDA_OK;
      if(args.includes("python3"))return JSON.stringify({models:[]});
      throw new Error("unknown request");
    },
    ollamaFetch:async()=>{throw new Error("host port must not be queried");}
  });
  const state=await diag.snapshot();
  assert.equal(state.cuda.ready,true);assert.equal(state.ollama.status,"ok");
  assert(calls.some(({command,args})=>command==="docker.exe"&&args[0]==="exec"&&args[1]===docker.name));
  assert(calls.every(({command,args})=>command==="nvidia-smi.exe"||(args[0]==="exec"&&args[1]===docker.name)));
});
