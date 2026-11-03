"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const C=require('../desktop/renderer-core.js');
test('edited/source timeline maps cuts and three-hour time values',()=>{
  const spans=[[0,10],[20,30],[45,60]];
  assert.deepEqual(C.editedToSource(12,spans),{time:22,index:1});assert.equal(C.sourceToEdited(46,spans),21);assert.equal(C.parseTime('03:00:00.125'),10800.125);assert.throws(()=>C.parseTime('NaN'));
});
test('Markdown and search escape transcript HTML and disallow executable links',()=>{
  const html=C.markdown('# Test\n<script>alert(1)</script>\n![x](https://x/a)\n[x](javascript:alert(1))\n[00:03](#s00001)');
  assert(!html.includes('<script>'));assert(!html.includes('<img'));assert(!html.includes('href="javascript:'));assert(html.includes('data-source="s00001"'));assert(C.highlight('<b>Anna</b>','Anna').includes('&lt;b&gt;'));
});
test('all renderer elements and runtime dialog are present before scripts',()=>{
  const html=fs.readFileSync(path.join(__dirname,'../desktop/index.html'),'utf8'),ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(ids.length,new Set(ids).size);assert(html.indexOf('id="runtimeDialog"')<html.indexOf('src="setup.js"'));
  for(const file of ['app.js','setup.js']){const s=fs.readFileSync(path.join(__dirname,'../desktop',file),'utf8');for(const m of s.matchAll(/\$\((['"])([^'"]+)\1\)/g))assert(ids.includes(m[2])||m[2]==='playhead',file+' '+m[2]);}
});
test('first launch opens setup even when the initial event was already delivered',async()=>{
  const elements=new Map();
  const get=id=>{if(!elements.has(id))elements.set(id,{textContent:'',open:false,addEventListener(){},showModal(){this.open=true;},querySelectorAll(){return [];}});return elements.get(id);};
  const status={ready:false,docker:true,linux:true,image:false,workspace:'/tmp/qa'};
  const context={window:{studio:{setup:async()=>status,onEvent(){}},StudioActions:{flushEditor:async()=>true}},document:{getElementById:get,addEventListener(){}}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../desktop/setup.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(get('runtimeDialog').open,true);
  assert.equal(get('setupWorkspace').textContent,'/tmp/qa');
});
test('delayed editor saves serialize and preserve newer or failed drafts',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'../desktop/app.js'),'utf8'),fields=new Map(),saves=[];
  const $=id=>{if(!fields.has(id))fields.set(id,{value:'',textContent:'',innerHTML:''});return fields.get(id);};
  $('segmentText').value='Erster Entwurf';$('segmentSpeaker').value='SPEAKER_00';
  const editor={C,$,clearTimeout,S:{project:true,busy:false,speakers:{},segments:[{id:'s00001',start:0,end:2,text:'Gespeichert',speaker:'SPEAKER_00'}]},selectedSegment:'s00001',editorID:'s00001',editorDirty:true,saveFlight:null,editTimer:null,speakerListKey:'',speakerIDs:()=>['SPEAKER_00'],name:x=>x,command:(_a,data)=>new Promise(resolve=>saves.push({data,resolve}))};
  vm.createContext(editor);vm.runInContext(source.slice(source.indexOf('  function renderInspector()'),source.indexOf('  async function selectSegment(')),editor);
  const first=editor.flushEditor(),queued=editor.flushEditor();assert.equal(saves.length,1);$('segmentText').value='Neue Korrektur';editor.S.segments[0].text='Erster Entwurf';editor.renderInspector();assert.equal($('segmentText').value,'Neue Korrektur');saves[0].resolve(true);await first;assert(editor.editorDirty);assert.equal(saves.length,2);editor.S.segments[0].text='Neue Korrektur';saves[1].resolve(true);await queued;assert(!editor.editorDirty);
  $('segmentText').value='Nicht gespeichert';editor.editorDirty=true;const failed=editor.flushEditor();saves[2].resolve(false);assert.equal(await failed,false);editor.renderInspector();assert.equal($('segmentText').value,'Nicht gespeichert');assert(editor.editorDirty);
});
