"use strict";
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const required=['package.json','README.md','desktop/main.cjs','desktop/preload.cjs','desktop/runtime.cjs','desktop/backend.cjs','desktop/files.cjs','desktop/wav.cjs','desktop/index.html','desktop/app.js','desktop/setup.js','desktop/native-recorder.js','desktop/pcm-worklet.js','desktop/profiles.json','container/Dockerfile','container/container_entry.py','container/whisperx-cli','container/whisperx_cli.py','container/whisperx_studio/windows_service.py','scripts/Build-Windows.ps1','scripts/Initialize-System.ps1','build/installer.nsh','build/icon.ico'];
for(const file of required)assert(fs.statSync(path.join(root,file)).isFile(),'Missing '+file);
for(const name of fs.readdirSync(path.join(root,'desktop')).filter(x=>/\.(cjs|js)$/.test(x))){
  const result=spawnSync(process.execPath,['--check',path.join(root,'desktop',name)],{encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
}
const p=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
assert.equal(p.build.nsis.deleteAppDataOnUninstall,false);
assert.equal(p.build.win.requestedExecutionLevel,'asInvoker');
assert.equal(p.build.extraResources[0].to,'engine');
const html=fs.readFileSync(path.join(root,'desktop/index.html'),'utf8');
const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]);assert.equal(new Set(ids).size,ids.length,'Duplicate HTML IDs');
for(const file of ['app.js','setup.js']){
  const source=fs.readFileSync(path.join(root,'desktop',file),'utf8');
  for(const match of source.matchAll(/\$\((['"])([^'"]+)\1\)/g))assert(ids.includes(match[2])||match[2]==='playhead',file+': missing #'+match[2]);
}
assert(html.indexOf('id="runtimeDialog"')<html.indexOf('src="setup.js"'));
assert(html.indexOf('src="native-recorder.js"')<html.indexOf('src="app.js"'));
for(const match of html.matchAll(/<script src="([^"]+)"/g))assert(fs.existsSync(path.join(root,'desktop',match[1])));
const icon=fs.readFileSync(path.join(root,'build/icon.ico'));assert.equal(icon.readUInt16LE(2),1);assert.equal(icon.readUInt16LE(4),1);assert.equal(icon[6],0,'Installer requires 256px icon');
console.log('Source structure, renderer references, JavaScript syntax and installer inputs verified.');
