(function(){
  'use strict';
  const api=window.studio,$=id=>document.getElementById(id);if(!api)return;
  let working=false;
  function log(text){const box=$('setupLog');box.textContent=(box.textContent+String(text)+'\n').slice(-24000);box.scrollTop=box.scrollHeight;}
  async function show(){if(window.StudioActions&&(await window.StudioActions.flushEditor())===false)return;const dialog=$('runtimeDialog');if(!dialog.open)dialog.showModal();refresh();}
  function display(status){
    $('setupSummary').textContent=status.ready?'Lokale Umgebung bereit.':status.error||'WhisperX-Umgebung muss noch eingerichtet werden.';
    $('setupDocker').textContent=status.docker?(status.linux?'Docker · Linux-Container bereit':'Docker · bitte auf Linux-Container wechseln'):'Docker Desktop · nicht bereit';
    $('setupEngine').textContent=status.image?'WhisperX + Ollama · installiert':'WhisperX + Ollama · noch nicht installiert';
    $('setupDevice').textContent=status.gpu?'Verarbeitung · NVIDIA-GPU':'Verarbeitung · CPU / noch ungeprüft';
    $('setupWorkspace').textContent=status.workspace||'';
  }
  async function refresh(){try{display(await api.setup('status'));}catch(e){log(e.message);}}
  async function task(button,work){
    if(working)return;working=true;
    const buttons=[...$('runtimeDialog').querySelectorAll('[data-setup]')];buttons.forEach(b=>b.disabled=true);
    const before=button.textContent;button.textContent='Bitte warten …';
    try{await work();}catch(e){log('Fehler: '+e.message);$('setupSummary').textContent=e.message;}
    finally{working=false;buttons.forEach(b=>b.disabled=false);button.textContent=before;await refresh();}
  }
  document.addEventListener('click',event=>{
    const open=event.target.closest('[data-open-setup]');if(open){show();return;}
    const button=event.target.closest('[data-setup]');if(!button)return;
    const action=button.dataset.setup;
    task(button,async()=>{
      if(action==='refresh')return refresh();
      if(action==='prepare'){
        display(await api.setup('prepare',{device:$('setupMode').value}));
        log('Die Umgebung wurde eingerichtet und gestartet. Auswertungsmodelle lassen sich unten herunterladen.');
      }else if(action==='start'){display(await api.setup('start'));log('Lokaler Container gestartet.');}
      else if(action==='restart'){if((await window.StudioActions.flushEditor())===false)return;display(await api.setup('restart'));log('Lokale Umgebung neu gestartet und Projekt wiederhergestellt.');}
      else if(action==='workspace')await api.setup('workspace');
      else if(['wsl','docker','start-docker'].includes(action)){
        log('Windows-Einrichtung startet. Eventuelle Windows-/Installer-Dialoge bestätigen. Nach WSL-Aktivierung kann ein Neustart nötig sein.');
        await api.setup('system',{action});
      }else if(action==='gemma'||action==='qwen'){
        await api.command('model_pull',{model:action==='gemma'?'gemma4:e2b':'qwen3:14b-q4_K_M'});
        log('Download gestartet. Fortschritt unter Aktivitätsprotokoll; „Abbrechen“ stoppt den Auftrag.');
      }else if(action==='asr'){
        await api.command('warmup_asr',{model:'small'});log('Whisper-small-Download gestartet. Er wird auch für Live-Text benötigt.');
      }
    });
  });
  $('setupClose').addEventListener('click',()=>{if(!working)$('runtimeDialog').close();});
  $('runtimeDialog').addEventListener('cancel',event=>{if(working)event.preventDefault();});
  api.onEvent(event=>{
    if(event.type==='setup_log')log(event.data);
    else if(event.type==='setup_status'){display(event.data);if(!event.data.ready)show();}
    else if(event.type==='log'&&$('runtimeDialog').open)log(event.data);
    else if(event.type==='state'){
      $('setupGemma').disabled=event.data.busy||event.data.recording;
      $('setupQwen').disabled=event.data.busy||event.data.recording;
      $('setupAsr').disabled=event.data.busy||event.data.recording;
    }
  });
  // The initial IPC event can arrive before this script subscribes.
  // Read the current status as well so first launch always opens setup.
  api.setup('status').then(status=>{
    display(status);
    if(!status.ready)show();
  }).catch(error=>log(error.message));
})();
