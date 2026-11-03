"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {WorkspaceFiles}=require('../desktop/files.cjs');

function temp(t){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'winwhisper-native-path-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));return dir;}

test('native file URLs are accepted only inside the workspace and become portable audio URLs',t=>{
  const root=temp(t),files=new WorkspaceFiles(root),preview=path.join(root,'projects','p1','preview.wav');
  fs.mkdirSync(path.dirname(preview),{recursive:true});fs.writeFileSync(preview,'wav');
  const uri=pathToFileURL(preview).href,logical=files.logical(preview);
  assert.equal(files.audioURL(uri),uri);
  assert.equal(files.streamURL(uri),'winwhisper://audio'+logical);
  assert.equal(files.streamURL('file://'+logical),'winwhisper://audio'+logical);
  const outside=path.join(temp(t),'outside.wav');fs.writeFileSync(outside,'x');
  assert.throws(()=>files.streamURL(pathToFileURL(outside).href),/außerhalb/);
});
