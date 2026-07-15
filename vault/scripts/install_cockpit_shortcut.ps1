$vault = Split-Path -Parent $PSScriptRoot
$target = Join-Path $vault "Launch Learning Cockpit.bat"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Math Learning Cockpit.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $vault
$shortcut.Description = "Open the Unified Math Learning Cockpit"
$shortcut.Save()
Write-Host "Created $shortcutPath"
