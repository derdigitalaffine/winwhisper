[CmdletBinding()]
param(
  [ValidateSet('wsl','docker','start-docker','ollama','whisperx')][string]$Action,
  [string]$Workspace = '',
  [string]$Resources = ''
)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 wird benötigt.' }
$defaultWorkspace = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'WinWhisper Studio\workspace'
if (-not $Workspace) { $Workspace = $defaultWorkspace }
if (-not $Resources) { $Resources = Split-Path -Parent $PSScriptRoot }

function Ensure-WhisperPython {
  param(
    [Parameter(Mandatory = $true)][string]$VenvPath,
    [Parameter(Mandatory = $true)][string]$EngineRoot
  )
  $local = [Environment]::GetFolderPath('LocalApplicationData')
  $candidates = @(
    @{ Command='py.exe'; Args=@('-3.12') },
    @{ Command=(Join-Path $local 'Programs\Python\Python312\python.exe'); Args=@() },
    @{ Command='python.exe'; Args=@() }
  )
  $base = $null
  foreach ($candidate in $candidates) {
    $cmd = $candidate.Command
    $args = $candidate.Args
    if (-not [string]::IsNullOrWhiteSpace($cmd) -and $cmd -notlike '*.exe') {
      $resolved = Get-Command $cmd -ErrorAction SilentlyContinue
      if (-not $resolved) { continue }
    }
    try {
      $result = & $cmd @args -c 'import platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}|{platform.architecture()[0]}")' 2>$null
      if ($LASTEXITCODE -eq 0 -and $result -match '3\.12\|64bit') { $base = $candidate; break }
    } catch {}
  }
  if (-not $base) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'Windows App Installer / winget fehlt. Python 3.12 x64 kann nicht automatisch installiert werden.' }
    & winget.exe install --id Python.Python.3.12 --exact --source winget --scope user --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -notin @(0,3010,-1978335189)) { throw "Python-Installation fehlgeschlagen: $LASTEXITCODE" }
    foreach ($candidate in $candidates) {
      $cmd = $candidate.Command
      $args = $candidate.Args
      try {
        $result = & $cmd @args -c 'import platform,sys; print(f"{sys.version_info.major}.{sys.version_info.minor}|{platform.architecture()[0]}")' 2>$null
        if ($LASTEXITCODE -eq 0 -and $result -match '3\.12\|64bit') { $base = $candidate; break }
      } catch {}
    }
  }
  if (-not $base) { throw 'Python 3.12 x64 konnte nach der Windows-Installation nicht gefunden werden.' }
  $venvExists = Test-Path -LiteralPath $VenvPath
  if (-not $venvExists) {
    Write-Output 'Erzeuge die lokale WinWhisper-Python-Umgebung …'
    & $base.Command @($base.Args + @('-m','venv',$VenvPath))
    if ($LASTEXITCODE -ne 0) { throw 'Erstellung der lokalen Python-Umgebung fehlgeschlagen.' }
  }
  $pythonExe = Join-Path $VenvPath 'Scripts\python.exe'
  if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Die lokale Python-Umgebung wurde nicht vollständig angelegt.' }
  & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade pip
  if ($LASTEXITCODE -ne 0) { throw 'Pip-Upgrade für die lokale Python-Umgebung fehlgeschlagen.' }
  $requirements = Join-Path $EngineRoot 'container\requirements-windows-py312.txt'
  if (-not (Test-Path -LiteralPath $requirements)) {
    $requirements = Join-Path $EngineRoot 'requirements-windows-py312.txt'
  }
  if (-not (Test-Path -LiteralPath $requirements)) { throw 'Die WhisperX-Requirements-Datei wurde im Installationspaket nicht gefunden.' }
  $index = 'https://download.pytorch.org/whl/cpu'
  & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade --index-url $index torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0
  if ($LASTEXITCODE -ne 0) { throw 'Installation von PyTorch für die lokale WhisperX-Umgebung fehlgeschlagen.' }
  & $pythonExe -m pip install --disable-pip-version-check --no-input --upgrade -r $requirements
  if ($LASTEXITCODE -ne 0) { throw 'Installation der WhisperX-Requirements für die lokale Umgebung fehlgeschlagen.' }
  & $pythonExe -c 'import imageio_ffmpeg,torch,ctranslate2,faster_whisper,whisperx; print("ok")'
  if ($LASTEXITCODE -ne 0) { throw 'Der WhisperX-Selbsttest nach der Einrichtung ist fehlgeschlagen.' }
  Write-Output 'WhisperX wurde über die Setup-Routine eingerichtet.'
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
    Ensure-WhisperPython -VenvPath $venvPath -EngineRoot $engineRoot
  }
}
