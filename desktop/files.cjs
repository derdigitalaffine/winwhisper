"use strict";
const fs=require('node:fs');
const fsp=fs.promises;
const path=require('node:path');
const {randomUUID}=require('node:crypto');
const {pathToFileURL,fileURLToPath}=require('node:url');

class WorkspaceFiles {
  constructor(root){this.root=path.resolve(root);this.protected=new Set();this.originsFile=path.join(this.root,'origins.json');
    try{const values=JSON.parse(fs.readFileSync(this.originsFile,'utf8'));if(Array.isArray(values))for(const x of values)if(typeof x==='string')this.protected.add(this.key(x));}catch{}
  }
  key(file){const name=path.resolve(file);return process.platform==='win32'?name.toLowerCase():name;}
  host(logical){
    if(typeof logical!=='string'||!logical.startsWith('/data/')||logical.includes('\\')||logical.includes('\0'))throw new Error('Ungültiger Arbeitsbereichspfad.');
    const parts=logical.slice(6).split('/');
    if(parts.some(x=>!x||x==='.'||x==='..'||x.includes(':')))throw new Error('Ungültiger Arbeitsbereichspfad.');
    return path.join(this.root,...parts);
  }
  logical(file){
    const relative=path.relative(this.root,path.resolve(file));
    if(!relative||relative.startsWith('..'+path.sep)||relative==='..'||path.isAbsolute(relative))throw new Error('Datei liegt außerhalb des Arbeitsbereichs.');
    return '/data/'+relative.split(path.sep).join('/');
  }
  resolveAudioURL(value){
    const url=new URL(value);
    if(url.protocol!=='file:'||url.hostname)throw new Error('Ungültige Audioadresse.');
    const pathname=decodeURIComponent(url.pathname);
    if(pathname.startsWith('/data/')){
      const host=this.host(pathname);return {host,logical:pathname};
    }
    const host=fileURLToPath(url);
    const logical=this.logical(host); // validates that native file URLs stay in the workspace
    return {host,logical};
  }
  audioURL(value){return pathToFileURL(this.resolveAudioURL(value).host).href;}
  streamURL(value){const {logical}=this.resolveAudioURL(value);return 'winwhisper://audio'+logical;}
  async import(file){
    const stat=await fsp.stat(file);if(!stat.isFile())throw new Error('Bitte eine Datei wählen.');
    // Avoid duplicate huge copies when reopening an internal recording/project.
    try{return this.logical(file);}catch{}
    const dir=path.join(this.root,'imports',randomUUID());await fsp.mkdir(dir,{recursive:true});
    const dest=path.join(dir,path.basename(file));
    try{await fsp.copyFile(file,dest,fs.constants.COPYFILE_EXCL);}catch(error){await fsp.rm(dir,{recursive:true,force:true});throw error;}
    this.protected.add(this.key(file));
    const temp=this.originsFile+'.tmp';await fsp.writeFile(temp,JSON.stringify([...this.protected]));await fsp.rename(temp,this.originsFile);
    return this.logical(dest);
  }
  exportPath(extension){return '/data/exports/'+randomUUID()+extension;}
  checkDestination(dest){
    const key=this.key(dest);
    if(this.protected.has(key))throw new Error('Eine Originaldatei wird nicht überschrieben.');
    try{this.logical(dest);throw new Error('Bitte außerhalb des internen Arbeitsbereichs exportieren.');}catch(error){if(error.message!=='Datei liegt außerhalb des Arbeitsbereichs.')throw error;}
  }
  async export(logical,dest){
    this.checkDestination(dest);
    const temporary=dest+'.'+randomUUID()+'.tmp';
    try{await fsp.copyFile(this.host(logical),temporary,fs.constants.COPYFILE_EXCL);await fsp.rename(temporary,dest);}
    finally{await fsp.rm(temporary,{force:true});}
  }
}
module.exports={WorkspaceFiles};
