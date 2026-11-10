[CmdletBinding()]
param([switch]$DryRun, [switch]$Check)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$environmentPython = Join-Path $projectRoot 'work\asr-venv\Scripts\python.exe'

function Find-SetupPython {
    $candidates = @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'))
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    # The default WindowsApps execution alias opens the Store instead of Python.
    if ($pythonCommand -and $pythonCommand.Source -notlike '*\Microsoft\WindowsApps\*') { $candidates += $pythonCommand.Source }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        try {
            $resolved = & $launcher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0) { $candidates += $resolved }
        } catch { }
    }
    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        try {
            $valid = & $candidate -c "import sys,struct; print(sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $valid -eq 'True') { return $candidate }
        } catch { }
    }
    return $null
}

function Find-SetupOllama {
    $command = Get-Command ollama.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    return $null
}

function Install-Prerequisite([string]$PackageId) {
    $manager = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $manager) { throw 'WinGet is required to install missing prerequisites. Install Microsoft App Installer, then rerun install.cmd.' }
    Write-Host "Installing $PackageId for the current user..."
    & $manager.Source install --id $PackageId --exact --source winget --scope user --architecture x64 --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "WinGet could not install $PackageId (exit $LASTEXITCODE). Resolve the reported error and rerun install.cmd." }
}

try {
    if ($DryRun -and $Check) { throw 'Choose either -DryRun or -Check.' }
    if ($DryRun) {
        [pscustomobject]@{
            project = $projectRoot
            environment = $environmentPython
            prerequisites = @('Python.Python.3.12 (x64, if missing)', 'Ollama.Ollama (if missing)')
            steps = @('Create local Python environment', 'Install CLI and OCR dependencies', 'Download or reuse pinned Whisper medium', 'Download or reuse local qwen2.5:3b using a temporary loopback runtime', 'Check CLI readiness')
            models = @('medium', 'qwen2.5:3b')
            networkUsed = $false
        } | ConvertTo-Json -Depth 4
        exit 0
    }
    if ($Check) {
        if (-not (Test-Path -LiteralPath $environmentPython)) { throw 'The local environment is missing. Run install.cmd first.' }
        & $environmentPython (Join-Path $PSScriptRoot 'setup_environment.py') --check
        exit $LASTEXITCODE
    }
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') { throw 'This installer requires Windows x64.' }
    $pythonBinary = Find-SetupPython
    if (-not $pythonBinary) {
        Install-Prerequisite 'Python.Python.3.12'
        $pythonBinary = Find-SetupPython
        if (-not $pythonBinary) { throw 'Python 3.12 x64 was not found after installation.' }
    }
    $ollamaBinary = Find-SetupOllama
    if (-not $ollamaBinary) {
        Install-Prerequisite 'Ollama.Ollama'
        $ollamaBinary = Find-SetupOllama
        if (-not $ollamaBinary) { throw 'Ollama was not found after installation.' }
    }
    & $pythonBinary (Join-Path $PSScriptRoot 'setup_environment.py') --ollama $ollamaBinary
    exit $LASTEXITCODE
} catch {
    Write-Host ('Setup failed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
