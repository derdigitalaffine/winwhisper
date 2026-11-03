"use strict";
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('studio',{
  command:(action,data={})=>ipcRenderer.invoke('studio:command',action,data),
  chooseFile:(mode,data={})=>ipcRenderer.invoke('studio:file',mode,data),
  openRecent:file=>ipcRenderer.invoke('studio:recent',file),
  window:action=>ipcRenderer.invoke('studio:window',action),
  help:()=>ipcRenderer.invoke('studio:help'),
  openLink:which=>ipcRenderer.invoke('studio:link',which),
  setup:(action,data={})=>ipcRenderer.invoke('studio:setup',action,data),
  audio:{start:()=>ipcRenderer.invoke('studio:audio','start'),append:(id,sequence,pcm)=>ipcRenderer.invoke('studio:audio','append',{id,sequence,pcm}),stop:id=>ipcRenderer.invoke('studio:audio','stop',{id})},
  onEvent:callback=>{const listener=(_e,payload)=>callback(payload);ipcRenderer.on('studio:event',listener);return ()=>ipcRenderer.removeListener('studio:event',listener);}
});
