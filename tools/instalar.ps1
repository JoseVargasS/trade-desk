param(
    [switch]$Consola
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Find-Uv {
    $command = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($command) {
        return $command.Source
    }

    foreach ($path in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe")
    )) {
        if (Test-Path $path) {
            return $path
        }
    }
}

$uv = Find-Uv
if (-not $uv) {
    Write-Host "Instalando uv para tu usuario..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $installer = Invoke-RestMethod "https://astral.sh/uv/install.ps1"
    & ([scriptblock]::Create($installer))
    $uv = Find-Uv
}
if (-not $uv) {
    throw "No se encontro uv despues de instalarlo desde astral.sh."
}

$python = & $uv python find ">=3.11" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "No se encontro Python 3.11 o superior; instalando Python 3.13..."
    & $uv python install 3.13
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo instalar Python 3.13 con uv."
    }

    $python = & $uv python find 3.13
    if ($LASTEXITCODE -ne 0) {
        throw "No se encontro Python 3.13 despues de instalarlo."
    }
}

Write-Host "Instalando las dependencias con Python: $python"
& $uv sync --locked --inexact --python $python
if ($LASTEXITCODE -ne 0) {
    throw "No se pudieron instalar las dependencias del proyecto."
}

$scripts = Join-Path $root ".venv\Scripts"
$python = Join-Path $scripts "python.exe"
$pythonw = Join-Path $scripts "pythonw.exe"
$app = Join-Path $root "app.py"
$icon = Join-Path $root "src\tradedesk\assets\icon.ico"

if ($Consola) {
    & $python $app
    exit $LASTEXITCODE
}

if (-not (Test-Path $pythonw)) {
    throw "No se encontro pythonw.exe en el entorno instalado: $pythonw"
}
if (-not (Test-Path $python)) {
    throw "No se encontro python.exe en el entorno instalado: $python"
}
if (-not (Test-Path $icon)) {
    throw "No se encontro el icono de Trade Desk: $icon"
}

$desktop = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::DesktopDirectory
)
$shortcutPath = Join-Path $desktop "Trade Desk.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"{0}"' -f $app
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$icon,0"
$shortcut.Description = "Abrir Trade Desk"
$shortcut.Save()

Write-Host "Acceso directo creado en el escritorio: $shortcutPath"
Start-Process -FilePath $pythonw -ArgumentList ('"{0}"' -f $app) -WorkingDirectory $root
