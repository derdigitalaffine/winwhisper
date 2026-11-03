"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');

test('setup exposes Tiny and verbose Whisper download diagnostics',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../desktop/setup.js'),'utf8');
  assert(source.includes('value="tiny"'));
  assert(source.includes('Tiny · kleinster Download, sehr schnell'));
  assert(source.includes('Whisper-Modell laden'));
  assert(source.includes('Downloadfortschritt'));
  assert(source.includes("'whisperx_studio.model_download'"));
});
