(function(){
  'use strict';
  const api=window.studio,$=id=>document.getElementById(id);if(!api)return;
  let working=false,stateBusy=false,lastStatus={},activeWhisperStatus='',serviceState={};

  const body=document.querySelector('#runtimeDialog .setup-body');
  body.innerHTML=`
    <p>WhisperX kann direkt unter Windows laufen. <strong>Windows nativ</strong> ist der empfohlene Weg und benötigt weder WSL noch Docker. Docker/WSL bleibt als Kompatibilitätsmodus verfügbar.</p>
    <label class="input-group"><span>Lokale Laufzeit</span><select id="setupRuntime"><option value="native">Windows nativ · empfohlen</option><option value="docker">Docker / WSL 2 · erweitert</option></select></label>
    <div class="setup-status"><span id="setupDocker"></span><span id="setupEngine"></span><span id="setupDevice"></span><span id="setupOllama"></span></div>
    <section data-runtime-native>
      <h3>1 · WhisperX direkt unter Windows</h3>
      <p>WinWhisper richtet eine eigene Python-3.12-Umgebung im Arbeitsordner ein. Fehlt Python, wird die Benutzer-Version über winget installiert. Dafür sind keine Linux-VM und kein Docker Desktop nötig.</p>
      <label>Verarbeitung <select id="setupMode"><option value="auto">Automatisch · NVIDIA-GPU prüfen, sonst CPU</option><option value="cpu">Nur CPU · maximale Kompatibilität</option><option value="gpu">NVIDIA-GPU erforderlich</option></select></label>
      <p>Die erste Einrichtung lädt WhisperX und PyTorch. Bei NVIDIA wird CUDA 12.8 getestet; schlägt der Test im Automatikmodus fehl, bleibt die CPU-Laufzeit verwendbar.</p>
      <div class="setup-actions"><button id="setupPrepare" class="btn btn-teal" data-setup="prepare">Windows-Laufzeit einrichten / reparieren</button><button class="btn btn-white" data-setup="start">Vorhandene Umgebung starten</button><button class="btn btn-white" data-setup="restart">Umgebung neu starten</button><button class="btn btn-white" data-setup="refresh">Prüfen</button></div>
      <h3>2 · Auswertungen optional</h3>
      <p>Aufnahme und Transkription funktionieren ohne Ollama. Für Protokolle, Zusammenfassungen und Aufgabenlisten kann Ollama nativ für den aktuellen Windows-Benutzer installiert werden.</p>
      <div class="setup-actions"><button class="btn btn-white" data-setup="ollama">Ollama optional installieren</button></div>
    </section>
    <section data-runtime-docker hidden>
      <h3>1 · Docker-Kompatibilitätsmodus</h3>
      <p>Nur verwenden, wenn die native Laufzeit auf diesem Rechner nicht eingesetzt werden kann. Dieser Modus benötigt WSL 2, Docker Desktop und Linux-Container.</p>
      <div class="setup-actions"><button class="btn btn-white" data-setup="wsl">WSL 2 einrichten</button><button class="btn btn-white" data-setup="docker">Docker Desktop installieren</button><button class="btn btn-white" data-setup="start-docker">Docker Desktop starten</button><button class="btn btn-white" data-setup="refresh">Prüfen</button></div>
      <label>Verarbeitung <select id="setupDockerMode"><option value="auto">Automatisch · NVIDIA-GPU, sonst CPU</option><option value="cpu">Nur CPU</option><option value="gpu">NVIDIA-GPU erforderlich</option></select></label>
      <div class="setup-actions"><button class="btn btn-teal" data-setup="prepare">Docker-Laufzeit einrichten</button><button class="btn btn-white" data-setup="start">Vorhandene Umgebung starten</button><button class="btn btn-white" data-setup="restart">Umgebung neu starten</button></div>
    </section>
    <h3>3 · Whisper-Modell verwalten</h3>
    <p>Wähle das Modell, das für neue Transkriptionen verwendet werden soll. Die Auswahl wird sofort gespeichert. <strong>Tiny</strong> ist die kleinste und schnellste Variante; Small bleibt der ausgewogene Standard.</p>
    <label class="input-group"><span>Aktives Whisper-Modell</span><select id="setupAsrModel"><option value="tiny">Tiny · kleinster Download, sehr schnell</option><option value="base">Base · klein und kompakt</option><option value="small" selected>Small · ausgewogen, Standard</option><option value="medium">Medium · genauer, größer</option><option value="large-v3">Large v3 · höchste Qualität, sehr groß</option></select></label>
    <p id="setupAsrState" class="setup-workspace">Modellstatus wird gelesen …</p>
    <div class="setup-actions"><button id="setupAsr" class="btn btn-teal" data-setup="asr">Ausgewähltes Whisper-Modell installieren / prüfen</button><button id="setupAsrRemove" class="btn btn-white" data-setup="asr-remove">Ausgewähltes Whisper-Modell entfernen</button><button id="setupGemma" class="btn btn-white" data-setup="gemma">Gemma e2b laden</button><button id="setupQwen" class="btn btn-white" data-setup="qwen">Qwen 14B laden</button></div>
    <p>Auch ein abgebrochener oder unvollständiger Whisper-Download kann über „entfernen“ aus dem lokalen Cache gelöscht und danach sauber neu installiert werden.</p>
    <p>Beim Whisper-Download öffnet sich das Einrichtungsprotokoll automatisch. Dort siehst du Quelle, Cache-Prüfung, Downloadfortschritt, Verifikation und eine konkrete Fehlermeldung.</p>
    <p>Für Sprechertrennung anschließend in den Transkriptionseinstellungen „Sprechermodell einrichten“ wählen.</p>
    <details><summary>Einrichtungsprotokoll</summary><pre id="setupLog" class="activity-log"></pre></details>
    <p id="setupWorkspace" class="setup-workspace"></p><button class="text-button" data-setup="workspace">Aufnahmen, Projekte und Modelle im Explorer öffnen</button>`;

  const runtimeSelect=document.getElementById('setupRuntime');
  const ollamaStatus=document.getElementById('setupOllama');
  const nativeSection=body.querySelector('[data-runtime-native]');
  const dockerSection=body.querySelector('[data-runtime-docker]');
  const dockerMode=document.getElementById('setupDockerMode');
  const asrModel=document.getElementById('setupAsrModel');
  const logDetails=body.querySelector('details');
  const asrNames={tiny:'Tiny',base:'Base',small:'Small',medium:'Medium','large-v3':'Large v3'};

  function log(text){const box=$('setupLog');box.textContent=(box.textContent+String(text)+'\n').slice(-24000);box.scrollTop=box.scrollHeight;}
  async function show(){if(window.StudioActions&&(await window.StudioActions.flushEditor())===false)return;const dialog=$('runtimeDialog');if(!dialog.open)dialog.showModal();refresh();}
  function currentWhisperInfo(){return (serviceState.whisper_models||{})[asrModel.value]||{};}
  function updateWhisperUi(){
    const saved=serviceState.settings&&serviceState.settings.asr_model;
    if(saved&&[...asrModel.options].some(option=>option.value===saved))asrModel.value=saved;
    const info=currentWhisperInfo(),name=asrNames[asrModel.value]||asrModel.value;
    if(info.installed){$('setupAsrState').textContent=`Whisper ${name} · installiert${info.size_mb?` · model.bin ${info.size_mb} MB`:''} · für Transkriptionen ausgewählt`;}
    else if(info.cached){$('setupAsrState').textContent=`Whisper ${name} · unvollständiger lokaler Cache vorhanden · entfernen und neu installieren empfohlen`;}
    else{$('setupAsrState').textContent=`Whisper ${name} · nicht lokal installiert${saved===asrModel.value?' · ausgewählt':''}`;}
    updateDisabled();
  }
  function updateDisabled(){
    const ready=!!lastStatus.ready,hasOllama=lastStatus.mode==='docker'||!!lastStatus.ollama,info=currentWhisperInfo();
    $('setupAsr').disabled=working||stateBusy||!ready;
    $('setupAsrRemove').disabled=working||stateBusy||!ready||!info.cached;
    asrModel.disabled=working||stateBusy||!ready;
    $('setupGemma').disabled=working||stateBusy||!ready||!hasOllama;
    $('setupQwen').disabled=working||stateBusy||!ready||!hasOllama;
  }
  function display(status){
    lastStatus=status||{};
    const mode=status.mode||'native';runtimeSelect.value=mode;
    nativeSection.hidden=mode!=='native';dockerSection.hidden=mode!=='docker';
    $('setupSummary').textContent=activeWhisperStatus||(status.ready?`${status.runtimeLabel||'Lokale Umgebung'} bereit.`:(status.error||'Lokale Umgebung muss noch eingerichtet werden.'));
    $('setupDocker').textContent=mode==='native'?'Laufzeit · Windows nativ':(status.docker?(status.linux?'Docker · Linux bereit':'Docker · Linux-Container fehlen'):'Docker · nicht bereit');
    $('setupEngine').textContent=(status.engine||status.image)?'WhisperX · installiert':'WhisperX · noch nicht installiert';
    $('setupDevice').textContent=status.gpu?'Verarbeitung · NVIDIA-GPU':'Verarbeitung · CPU / noch ungeprüft';
    ollamaStatus.textContent=mode==='docker'?(status.ollama?'Ollama · im Container':'Ollama · noch nicht bereit'):(status.ollama?'Ollama · installiert':'Ollama · optional, nicht installiert');
    $('setupWorkspace').textContent=status.workspace||'';
    updateWhisperUi();
  }
  async function refresh(){try{display(await api.setup('status'));}catch(e){log(e.message);}}
  async function task(button,work){
    if(working)return;working=true;
    const buttons=[...$('runtimeDialog').querySelectorAll('[data-setup]')];buttons.forEach(b=>b.disabled=true);runtimeSelect.disabled=true;asrModel.disabled=true;
    const before=button?.textContent;if(button)button.textContent='Bitte warten …';
    try{await work();}catch(e){log('Fehler: '+e.message);$('setupSummary').textContent=e.message;}
    finally{working=false;buttons.forEach(b=>b.disabled=false);runtimeSelect.disabled=false;if(button)button.textContent=before;await refresh();updateWhisperUi();}
  }
  runtimeSelect.addEventListener('change',()=>{
    const selected=runtimeSelect.value;
    task(null,async()=>{display(await api.setup('select',{mode:selected}));log(selected==='native'?'Windows nativ ausgewählt. Docker und WSL werden hierfür nicht benötigt.':'Docker / WSL 2 als Kompatibilitätsmodus ausgewählt.');});
  });
  asrModel.addEventListener('change',()=>{
    const model=asrModel.value;
    task(null,async()=>{
      await api.command('settings',{asr_model:model});
      serviceState.settings={...(serviceState.settings||{}),asr_model:model};
      log(`Whisper ${asrNames[model]||model} als aktives Transkriptionsmodell ausgewählt.`);
      updateWhisperUi();
    });
  });
  document.addEventListener('click',event=>{
    const open=event.target.closest('[data-open-setup]');if(open){show();return;}
    const button=event.target.closest('[data-setup]');if(!button)return;
    const action=button.dataset.setup;
    task(button,async()=>{
      if(action==='refresh')return refresh();
      if(action==='prepare'){
        const mode=runtimeSelect.value,device=mode==='docker'?dockerMode.value:$('setupMode').value;
        display(await api.setup('prepare',{device}));
        log(mode==='native'?'Native Windows-Laufzeit eingerichtet und gestartet.':'Docker-Laufzeit eingerichtet und gestartet.');
      }else if(action==='start'){display(await api.setup('start'));log('Lokaler Hintergrunddienst gestartet.');}
      else if(action==='restart'){if((await window.StudioActions.flushEditor())===false)return;display(await api.setup('restart'));log('Lokale Umgebung neu gestartet und Projekt wiederhergestellt.');}
      else if(action==='workspace')await api.setup('workspace');
      else if(['wsl','docker','start-docker','ollama'].includes(action)){
        log(action==='ollama'?'Ollama wird als optionale Windows-Anwendung für den aktuellen Benutzer eingerichtet.':'Windows-Einrichtung startet. Eventuelle Windows-/Installer-Dialoge bestätigen.');
        await api.setup('system',{action});
        if(action==='ollama')log('Ollama eingerichtet. Der lokale Hintergrunddienst wurde bei Bedarf neu gestartet.');
      }else if(action==='gemma'||action==='qwen'){
        await api.command('model_pull',{model:action==='gemma'?'gemma4:e2b':'qwen3:14b-q4_K_M'});
        log('Download gestartet. Fortschritt unter Aktivitätsprotokoll; „Abbrechen“ stoppt den Auftrag.');
      }else if(action==='asr'){
        const model=asrModel.value;
        logDetails.open=true;
        log(`Whisper-${model}-Download wird gestartet. Der Cache wird zuerst geprüft; danach folgen Download und lokale Verifikation.`);
        await api.command('settings',{asr_model:model});
        serviceState.settings={...(serviceState.settings||{}),asr_model:model};
        log(`Whisper-${model} ist als Transkriptionsmodell ausgewählt.`);
        await api.command('warmup_asr',{model});
        log(`Whisper-${model} läuft im Hintergrund. Alle Fortschritts- und Fehlermeldungen erscheinen hier.`);
      }else if(action==='asr-remove'){
        const model=asrModel.value,name=asrNames[model]||model;
        if(!window.confirm(`Whisper ${name} wirklich vom lokalen Rechner entfernen? Das Modell kann später erneut installiert werden.`))return;
        logDetails.open=true;
        log(`Whisper-${model} wird aus dem lokalen Modell-Cache entfernt.`);
        await api.command('remove_asr',{model});
      }
    });
  });
  $('setupClose').addEventListener('click',()=>{if(!working)$('runtimeDialog').close();});
  $('runtimeDialog').addEventListener('cancel',event=>{if(working)event.preventDefault();});
  api.onEvent(event=>{
    if(event.type==='setup_log')log(event.data);
    else if(event.type==='setup_status'){display(event.data);if(!event.data.ready)show();}
    else if(event.type==='log'&&$('runtimeDialog').open)log(event.data);
    else if(event.type==='error'&&$('runtimeDialog').open){log('Fehler: '+event.data);$('setupSummary').textContent='Fehler: '+event.data;logDetails.open=true;}
    else if(event.type==='state'){
      serviceState=event.data||{};
      stateBusy=!!(serviceState.busy||serviceState.recording);
      updateWhisperUi();
      if(serviceState.busy&&['Whisper-Modell herunterladen','Whisper-Modell entfernen'].includes(serviceState.operation)){
        activeWhisperStatus=serviceState.status||(serviceState.operation==='Whisper-Modell entfernen'?'Whisper-Modell wird entfernt …':'Whisper-Modell wird heruntergeladen …');
        $('setupSummary').textContent=activeWhisperStatus;
        logDetails.open=true;
      }else if(!serviceState.busy){
        activeWhisperStatus='';
        if(serviceState.status&&(/Whisper .*lokal bereit/.test(serviceState.status)||/Whisper .*lokal entfernt/.test(serviceState.status)||/Whisper .*nicht lokal installiert/.test(serviceState.status)||serviceState.status.startsWith('Fehler:'))){
          $('setupSummary').textContent=serviceState.status;
          if(serviceState.status.startsWith('Fehler:'))logDetails.open=true;
        }
      }
      updateDisabled();
    }
  });
  api.setup('status').then(status=>{display(status);if(!status.ready)show();}).catch(error=>log(error.message));
})();
