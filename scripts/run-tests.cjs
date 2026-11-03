"use strict";
// Run each file directly: test discovery/process isolation differs across Node
// versions. Direct node:test files consistently execute their registered tests.
const {spawnSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
for(const file of fs.readdirSync(path.join(root,'tests')).filter(x=>x.endsWith('.test.cjs')).sort()){
  console.log('\n'+file);
  const result=spawnSync(process.execPath,[path.join(root,'tests',file)],{cwd:root,stdio:'inherit'});
  if(result.status!==0){process.exitCode=result.status||1;break;}
}
