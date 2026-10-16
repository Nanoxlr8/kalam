# Creates Desktop + Start Menu shortcuts for Kalam (optional: -Startup to launch at sign-in)
param([switch]$Startup)
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ico = Join-Path $env:APPDATA 'Kalam\kalam.ico'
$sh = New-Object -ComObject WScript.Shell
$targets = @([Environment]::GetFolderPath('Desktop'), (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'))
if ($Startup) { $targets += [Environment]::GetFolderPath('Startup') }
foreach ($t in $targets) {
  $lnk = $sh.CreateShortcut((Join-Path $t 'Kalam.lnk'))
  $lnk.TargetPath = 'wscript.exe'
  $lnk.Arguments = '"' + (Join-Path $dir 'Kalam.vbs') + '"'
  $lnk.WorkingDirectory = $dir
  if (Test-Path $ico) { $lnk.IconLocation = $ico }
  $lnk.Description = 'Kalam dictation'
  $lnk.Save()
  Write-Output "Created $t\Kalam.lnk"
}
