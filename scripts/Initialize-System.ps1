[CmdletBinding()]
param([ValidateSet('wsl','docker','start-docker')][string]$Action)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 wird benötigt.' }
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
}
