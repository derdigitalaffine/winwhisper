[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

if (-not [Environment]::Is64BitOperatingSystem) {
  throw 'WinWhisper Studio kann nur auf Windows x64 gebaut werden.'
}

$work = Join-Path ([IO.Path]::GetTempPath()) ('WinWhisper-Build-' + [guid]::NewGuid().ToString('N'))
$archive = Join-Path $work 'source.zip'
$extract = Join-Path $work 'source'
$output = (Get-Location).Path

try {
  New-Item -ItemType Directory -Path $work, $extract -Force | Out-Null
  $sourceUrl = 'https://codeload.github.com/derdigitalaffine/winwhisper/zip/refs/heads/main'
  Write-Host 'Lade den aktuellen WinWhisper-Quellcode von GitHub ...'
  Invoke-WebRequest -Uri $sourceUrl -OutFile $archive
  Expand-Archive -LiteralPath $archive -DestinationPath $extract -Force

  $sourceRoot = Join-Path $extract 'winwhisper-main'
  $builder = Join-Path $sourceRoot 'scripts/Build-Windows.ps1'
  if (-not (Test-Path -LiteralPath $builder)) {
    throw 'Das Quellarchiv enthält kein Build-Skript.'
  }

  Write-Host 'Erstelle das Windows-Setup. Falls Node.js fehlt, wird winget dafür gestartet ...'
  & $builder -InstallNode
  if ($LASTEXITCODE -ne 0) {
    throw "Der Windows-Build ist mit Fehlercode $LASTEXITCODE fehlgeschlagen."
  }

  $setups = @(Get-ChildItem -LiteralPath (Join-Path $sourceRoot 'dist') -Filter '*Setup*.exe')
  if ($setups.Count -eq 0) {
    throw 'Der Build hat keine Setup-Datei erzeugt.'
  }

  foreach ($setup in $setups) {
    $target = Join-Path $output $setup.Name
    Copy-Item -LiteralPath $setup.FullName -Destination $target -Force
    $hashFile = $setup.FullName + '.sha256'
    if (Test-Path -LiteralPath $hashFile) {
      Copy-Item -LiteralPath $hashFile -Destination ($target + '.sha256') -Force
    }
    Write-Host "Fertig: $target"
  }
}
finally {
  if (Test-Path -LiteralPath $work) {
    Remove-Item -LiteralPath $work -Recurse -Force
  }
}
