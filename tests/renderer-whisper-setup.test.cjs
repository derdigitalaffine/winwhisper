"use strict";
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');

test('setup exposes selectable Tiny and removable Whisper models',()=>{
  const source=fs.readFileSync(path.join(__dirname,'../desktop/setup.js'),'utf8');
  assert(source.includes('value="tiny"'));
  assert(source.includes('Tiny · kleinster Download, sehr schnell'));
  assert(source.includes('value="base"'));
  assert(source.includes('value="small"'));
  assert(source.includes('value="medium"'));
  assert(source.includes('value="large-v3"'));
  assert(source.includes('Ausgewähltes Whisper-Modell entfernen'));
  assert(source.includes("api.command('settings',{asr_model:model})"));
  assert(source.includes("api.command('warmup_asr',{model})"));
  assert(source.includes("api.command('remove_asr',{model})"));
  assert(source.includes('unvollständiger lokaler Cache'));
  assert(source.includes('Downloadfortschritt'));
});
