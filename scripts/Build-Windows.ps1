[CmdletBinding()]
param([switch]$Unpacked, [switch]$InstallNode)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if (-not [Environment]::Is64BitOperatingSystem) { throw 'Windows x64 wird benötigt.' }
$hasNode = [bool](Get-Command node.exe -ErrorAction SilentlyContinue)
$nodeMajor = 0
if ($hasNode) { $nodeMajor = [int]((& node.exe --version).TrimStart('v').Split('.')[0]) }
if (-not $hasNode -or $nodeMajor -lt 22) {
  if (-not $InstallNode) { throw 'Node.js 22 oder neuer fehlt. Node.js LTS installieren oder dieses Skript mit -InstallNode ausführen.' }
  & winget.exe install --id OpenJS.NodeJS.LTS --exact --source winget --interactive --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw 'Node.js-Installation fehlgeschlagen.' }
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
}
if (Test-Path -LiteralPath 'package-lock.json') { & npm.cmd ci } else { & npm.cmd install }
if ($LASTEXITCODE -ne 0) { throw 'Build-Abhängigkeiten konnten nicht geladen werden.' }
if ($Unpacked) { & npm.cmd run pack:win } else { & npm.cmd run dist:win }
if ($LASTEXITCODE -ne 0) { throw 'Windows-Build fehlgeschlagen.' }
$exes = Get-ChildItem -LiteralPath (Join-Path $root 'dist') -Filter '*Setup*.exe'
if (-not $Unpacked -and -not $exes) { throw 'Der Build hat keine Setup-Datei erzeugt.' }
foreach ($exe in $exes) {
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $exe.FullName).Hash.ToLowerInvariant()
  [IO.File]::WriteAllText(($exe.FullName + '.sha256'), ($hash + '  ' + $exe.Name + "`n"))
  Write-Output ('Fertig: ' + $exe.FullName)
}
