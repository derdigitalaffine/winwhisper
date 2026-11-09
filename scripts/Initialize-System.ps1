[CmdletBinding()]
param(
  [ValidateSet('wsl','docker','start-docker','ollama','whisperx')][string]$Action,
  [string]$Workspace = '',
  [string]$Resources = '',
  [ValidateSet('auto','cpu','gpu')][string]$Device = 'auto'
)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 wird benötigt.' }
$defaultWorkspace = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'WinWhisper Studio\workspace'
if (-not $Workspace) { $Workspace = $defaultWorkspace }
if (-not $Resources) { $Resources = Split-Path -Parent $PSScriptRoot }

function Ensure-WhisperPython {
  param(
    [Parameter(Mandatory = $true)][string]$VenvPath,
    [Parameter(Mandatory = $true)][string]$EngineRoot,
    [ValidateSet('auto','cpu','gpu')][string]$Device = 'auto'
  )
  $runtimeRoot = Split-Path -Parent $VenvPath
  New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
  $manifestPath = Join-Path $runtimeRoot 'runtime.json'
  $pythonExe = Join-Path $VenvPath 'Scripts\python.exe'
  $requirements = Join-Path $EngineRoot 'container\requirements-windows-py312.txt'
  if (-not (Test-Path -LiteralPath $requirements)) {
    $requirements = Join-Path $EngineRoot 'requirements-windows-py312.txt'
  }
  if (-not (Test-Path -LiteralPath $requirements)) { throw 'Die WhisperX-Requirements-Datei wurde im Installationspaket nicht gefunden.' }

  # Never announce a partially installed/failed runtime as ready.
  Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue

  $validVenv = $false
  if (Test-Path -LiteralPath $pythonExe) {
    try {
      $version = & $pythonExe -c 'import platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}|{platform.architecture()[0]}")' 2>$null
      $validVenv = $LASTEXITCODE -eq 0 -and $version -match '3\.12\|64bit'
    } catch {}
  }
  if (-not $validVenv) {
    # A cancelled venv creation leaves a directory without a working interpreter.
    # Only delete our dedicated managed venv, never recordings or model caches.
    if (Test-Path -LiteralPath $VenvPath) {
      Write-Output 'Unvollständige Python-Umgebung wird repariert.'
      Remove-Item -LiteralPath $VenvPath -Recurse -Force
    }
    $local = [Environment]::GetFolderPath('LocalApplicationData')
    $candidates = @(
      @{ Command='py.exe'; Args=@('-3.12') },
      @{ Command=(Join-Path $local 'Programs\Python\Python312\python.exe'); Args=@() },
      @{ Command='python.exe'; Args=@() }
    )
    $base = $null
    foreach ($installAttempt in 0..1) {
      foreach ($candidate in $candidates) {
        try {
          $version = & $candidate.Command @($candidate.Args) -c 'import platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}|{platform.architecture()[0]}")' 2>$null
          if ($LASTEXITCODE -eq 0 -and $version -match '3\.12\|64bit') { $base = $candidate; break }
        } catch {}
      }
      if ($base) { break }
      if ($installAttempt -eq 0) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
          throw 'Python 3.12 x64 fehlt und winget ist nicht vorhanden. Bitte Python 3.12 x64 installieren.'
        }
        & winget.exe install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -notin @(0,3010,-1978335189)) { throw "Python-Installation fehlgeschlagen: $LASTEXITCODE" }
      }
    }
    if (-not $base) { throw 'Python 3.12 x64 wurde nach der Installation nicht gefunden. Bitte eine neue PowerShell starten und erneut versuchen.' }
    Write-Output 'Erzeuge die lokale WinWhisper-Python-Umgebung.'
    & $base.Command @($base.Args + @('-m','venv',$VenvPath))
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pythonExe)) { throw 'Erstellung der lokalen Python-Umgebung fehlgeschlagen.' }
  }

  & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade pip
  if ($LASTEXITCODE -ne 0) { throw 'Pip-Upgrade für die lokale Python-Umgebung fehlgeschlagen.' }

  $torchPackages = @('torch==2.8.0','torchaudio==2.8.0','torchvision==0.23.0')
  $hasNvidia = [bool](Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)
  if ($Device -eq 'gpu' -and -not $hasNvidia) { throw 'NVIDIA-GPU erforderlich, aber nvidia-smi wurde nicht gefunden. NVIDIA-Treiber prüfen oder CPU auswählen.' }
  $usingCuda = $Device -ne 'cpu' -and $hasNvidia
  if ($usingCuda) {
    Write-Output 'Installiere PyTorch mit CUDA 12.8 (NVIDIA-GPU erkannt).'
    & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade --index-url https://download.pytorch.org/whl/cu128 @torchPackages
    if ($LASTEXITCODE -ne 0) {
      if ($Device -eq 'gpu') { throw 'CUDA-PyTorch konnte nicht installiert werden. GPU-Modus wurde ausdrücklich angefordert.' }
      Write-Output 'CUDA-Paketinstallation fehlgeschlagen; automatischer Wechsel auf CPU.'
      $usingCuda = $false
    }
  }
  if (-not $usingCuda) {
    Write-Output 'Installiere PyTorch für die CPU-Laufzeit.'
    & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade --force-reinstall --index-url https://download.pytorch.org/whl/cpu @torchPackages
    if ($LASTEXITCODE -ne 0) { throw 'Installation von PyTorch für die lokale CPU-Umgebung fehlgeschlagen.' }
  }

  & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade -r $requirements
  if ($LASTEXITCODE -ne 0) { throw 'Installation der WhisperX-Requirements für die lokale Umgebung fehlgeschlagen.' }
  $selfTest = 'import imageio_ffmpeg,torch,ctranslate2,faster_whisper,whisperx; print("native-ok")'
  & $pythonExe -c $selfTest
  if ($LASTEXITCODE -ne 0) { throw 'Der WhisperX-Selbsttest nach der Einrichtung ist fehlgeschlagen.' }

  if ($usingCuda) {
    $cudaTest = 'import torch,ctranslate2; assert torch.cuda.is_available(), "PyTorch erkennt CUDA nicht"; assert ctranslate2.get_cuda_device_count()>0, "CTranslate2 erkennt keine GPU"; assert ctranslate2.get_supported_compute_types("cuda"), "CTranslate2 kann CUDA nicht verwenden"; print("cuda-ok")'
    & $pythonExe -c $cudaTest
    if ($LASTEXITCODE -ne 0) {
      if ($Device -eq 'gpu') { throw 'GPU-Prüfung fehlgeschlagen: PyTorch und CTranslate2 müssen beide CUDA verwenden können.' }
      Write-Output 'GPU-Prüfung fehlgeschlagen; stelle die funktionsfähige CPU-Laufzeit wieder her.'
      $usingCuda = $false
      & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade --force-reinstall --index-url https://download.pytorch.org/whl/cpu @torchPackages
      if ($LASTEXITCODE -ne 0) { throw 'CPU-Fallback nach CUDA-Fehler fehlgeschlagen.' }
      & $pythonExe -c $selfTest
      if ($LASTEXITCODE -ne 0) { throw 'Der WhisperX-Selbsttest der CPU-Ersatzlaufzeit ist fehlgeschlagen.' }
    }
  }

  # Matches desktop/runtime.cjs NATIVE_ENGINE_VERSION; write only after all tests.
  $flavor = if ($usingCuda) { 'cu128' } else { 'cpu' }
  $manifest = @{ version = 2; flavor = $flavor; gpu = [bool]$usingCuda; python = '3.12' } | ConvertTo-Json
  $tempManifest = $manifestPath + '.tmp'
  [IO.File]::WriteAllText($tempManifest, $manifest, (New-Object System.Text.UTF8Encoding($false)))
  Move-Item -LiteralPath $tempManifest -Destination $manifestPath -Force
  Write-Output "WhisperX wurde eingerichtet und geprüft ($flavor)."
}

switch ($Action) {
  'wsl' {
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $admin) {
      $argsList = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $PSCommandPath + '"'),'-Action','wsl')
      $p = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -ArgumentList $argsList
      if ($p.ExitCode -ne 0) { throw "WSL-Einrichtung fehlgeschlagen: $($p.ExitCode)" }
    } else {
      & wsl.exe --install --no-distribution
      if ($LASTEXITCODE -notin @(0,3010)) { throw "WSL-Aktivierung fehlgeschlagen: $LASTEXITCODE" }
      & wsl.exe --update
      if ($LASTEXITCODE -notin @(0,3010)) { throw "WSL-Update fehlgeschlagen: $LASTEXITCODE" }
    }
    Write-Output 'WSL eingerichtet. Falls Windows einen Neustart verlangt, danach die App erneut öffnen. Es wird kein automatischer Neustart ausgeführt.'
  }
  'docker' {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'Windows App Installer / winget fehlt. Docker Desktop über den offiziellen Link im Handbuch installieren.' }
    & winget.exe install --id Docker.DockerDesktop --exact --source winget --interactive --accept-source-agreements
    if ($LASTEXITCODE -notin @(0,3010,-1978335189)) { throw "Docker-Installation fehlgeschlagen: $LASTEXITCODE" }
    Write-Output 'Docker-Installation abgeschlossen. Docker Desktop starten und WSL-2-/Linux-Container aktivieren.'
  }
  'start-docker' {
    $candidates = @(
      (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'),
      (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\Docker Desktop.exe')
    )
    $exe = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $exe) { throw 'Docker Desktop wurde nicht gefunden. Bitte zuerst installieren.' }
    Start-Process -FilePath $exe
    Write-Output 'Docker Desktop startet. Anschließend in WinWhisper auf Prüfen klicken.'
  }
  'ollama' {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'Windows App Installer / winget fehlt. Ollama kann alternativ direkt von ollama.com für den aktuellen Benutzer installiert werden.' }
    & winget.exe install --id Ollama.Ollama --exact --source winget --scope user --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -notin @(0,3010,-1978335189)) { throw "Ollama-Installation fehlgeschlagen: $LASTEXITCODE" }
    Write-Output 'Ollama wurde für den aktuellen Windows-Benutzer installiert. WinWhisper startet für Auswertungen einen lokalen Ollama-Dienst.'
  }
  'whisperx' {
    $runtimeRoot = Join-Path $Workspace 'runtime\native'
    $venvPath = Join-Path $runtimeRoot 'venv'
    $engineRoot = $Resources
    if (-not (Test-Path -LiteralPath $engineRoot)) { throw 'Der Ressourcenpfad für die lokale WhisperX-Engine konnte nicht ermittelt werden.' }
    Ensure-WhisperPython -VenvPath $venvPath -EngineRoot $engineRoot -Device $Device
  }
}
