param(
    [Parameter(Position = 0)]
    [string]$Command = "panel"
)

$ErrorActionPreference = "Stop"

$Script:ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:Root = Split-Path -Parent $Script:ScriptRoot
$Script:StateRoot = Join-Path $Script:Root ".womap-launcher"
$Script:LogRoot = Join-Path $Script:StateRoot "logs"
$Script:UvCacheRoot = Join-Path $Script:StateRoot "uv-cache"
$Script:ConfigSource = ""
$Script:ApiHost = "127.0.0.1"
$Script:ApiPort = 8000
$Script:WebHost = "127.0.0.1"
$Script:WebPort = 5173
$Script:ApiUrl = "http://127.0.0.1:8000"
$Script:WebUrl = "http://127.0.0.1:5173"
$Script:InteractiveCleanupEnabled = $false

function Get-LauncherConfigPath {
    $localPath = Join-Path $Script:Root "config\settings.local.yaml"
    if (Test-Path -LiteralPath $localPath) {
        return $localPath
    }
    return (Join-Path $Script:Root "config\settings.example.yaml")
}

function ConvertFrom-YamlScalarText {
    param([string]$Value)
    $text = $Value.Trim()
    if ($text.StartsWith("""") -and $text.EndsWith("""") -and $text.Length -ge 2) {
        return $text.Substring(1, $text.Length - 2)
    }
    if ($text.StartsWith("'") -and $text.EndsWith("'") -and $text.Length -ge 2) {
        return $text.Substring(1, $text.Length - 2)
    }
    return $text
}

function Get-YamlScalar {
    param(
        [string]$Path,
        [string]$Default
    )
    $configPath = Get-LauncherConfigPath
    if (-not (Test-Path -LiteralPath $configPath)) {
        return $Default
    }

    $target = $Path.Split(".")
    $stack = @{}
    try {
        $lines = Get-Content -LiteralPath $configPath
    }
    catch {
        return $Default
    }

    foreach ($rawLine in $lines) {
        $line = $rawLine -replace "\s+#.*$", ""
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        if ($line -notmatch "^(\s*)([^:\s][^:]*):\s*(.*)$") {
            continue
        }

        $indent = $Matches[1].Length
        $key = $Matches[2].Trim()
        $value = $Matches[3].Trim()
        $level = [Math]::Floor($indent / 2)
        $stack[[int]$level] = $key
        foreach ($existingLevel in @($stack.Keys)) {
            if ([int]$existingLevel -gt [int]$level) {
                $stack.Remove($existingLevel)
            }
        }

        $parts = @()
        for ($index = 0; $index -le [int]$level; $index++) {
            if ($stack.ContainsKey($index)) {
                $parts += $stack[$index]
            }
        }
        if (($parts -join ".") -eq ($target -join ".") -and -not [string]::IsNullOrWhiteSpace($value)) {
            return (ConvertFrom-YamlScalarText $value)
        }
    }
    return $Default
}

function Get-YamlInt {
    param(
        [string]$Path,
        [int]$Default
    )
    $rawValue = Get-YamlScalar $Path ([string]$Default)
    $parsed = 0
    if ([int]::TryParse($rawValue, [ref]$parsed) -and $parsed -ge 1 -and $parsed -le 65535) {
        return $parsed
    }
    return $Default
}

function Read-LauncherSettings {
    $configPath = Get-LauncherConfigPath
    $Script:ConfigSource = if (Test-Path -LiteralPath $configPath) { $configPath } else { "defaults" }
    $Script:ApiHost = Get-YamlScalar "server.host" "127.0.0.1"
    $Script:ApiPort = Get-YamlInt "server.port" 8000
    $Script:WebHost = Get-YamlScalar "frontend.dev_server.host" "127.0.0.1"
    $Script:WebPort = Get-YamlInt "frontend.dev_server.port" 5173
    $Script:ApiUrl = "http://{0}:{1}" -f $Script:ApiHost, $Script:ApiPort
    $Script:WebUrl = "http://{0}:{1}" -f $Script:WebHost, $Script:WebPort
}

function Initialize-State {
    Read-LauncherSettings
    if (-not (Test-Path -LiteralPath $Script:StateRoot)) {
        New-Item -ItemType Directory -Path $Script:StateRoot | Out-Null
    }
    if (-not (Test-Path -LiteralPath $Script:LogRoot)) {
        New-Item -ItemType Directory -Path $Script:LogRoot | Out-Null
    }
    if (-not (Test-Path -LiteralPath $Script:UvCacheRoot)) {
        New-Item -ItemType Directory -Path $Script:UvCacheRoot | Out-Null
    }
    $env:UV_CACHE_DIR = $Script:UvCacheRoot
}

function Write-Color {
    param(
        [string]$Text,
        [ConsoleColor]$Color = [ConsoleColor]::Gray,
        [switch]$NoNewline
    )
    Write-Host $Text -ForegroundColor $Color -NoNewline:$NoNewline
}

function Format-Status {
    param([string]$Status)
    switch ($Status) {
        "ok" { return [ConsoleColor]::Green }
        "running" { return [ConsoleColor]::Green }
        "listening" { return [ConsoleColor]::Green }
        "foreground" { return [ConsoleColor]::Green }
        "stopped" { return [ConsoleColor]::Yellow }
        "missing" { return [ConsoleColor]::Red }
        default { return [ConsoleColor]::Gray }
    }
}

function Write-Check {
    param(
        [string]$Label,
        [string]$Status,
        [string]$Detail
    )
    Write-Color ("[{0}] " -f $Status.ToUpperInvariant()) (Format-Status $Status) -NoNewline
    Write-Host ("{0}: {1}" -f $Label, $Detail)
}

function Get-PidFile {
    param([string]$Name)
    return (Join-Path $Script:StateRoot ("{0}.pid" -f $Name))
}

function Get-LogFile {
    param([string]$Name)
    return (Join-Path $Script:LogRoot ("{0}.log" -f $Name))
}

function Get-MetadataFile {
    param([string]$Name)
    return (Join-Path $Script:StateRoot ("{0}.json" -f $Name))
}

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-CommandPathText {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        return "not found"
    }
    return $command.Source
}

function Test-PortOpen {
    param(
        [string]$HostName,
        [int]$Port
    )
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(350, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

function Get-PortProcessIds {
    param([int]$Port)
    $ids = @()
    $pattern = ":{0}\s+.*LISTENING\s+(\d+)" -f $Port
    try {
        $lines = & netstat.exe -ano -p tcp 2>$null
        foreach ($line in $lines) {
            if ($line -match $pattern) {
                $ids += [int]$Matches[1]
            }
        }
    }
    catch {
        return @()
    }
    return ($ids | Sort-Object -Unique)
}

function Get-ServiceHost {
    param([string]$Name)
    if ($Name -eq "api") {
        return $Script:ApiHost
    }
    return $Script:WebHost
}

function Get-RecordedProcess {
    param([string]$Name)
    $pidFile = Get-PidFile $Name
    $metadataFile = Get-MetadataFile $Name
    if (-not (Test-Path -LiteralPath $pidFile)) {
        return $null
    }
    if (-not (Test-Path -LiteralPath $metadataFile)) {
        return $null
    }
    $rawPid = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $processId = 0
    if (-not [int]::TryParse($rawPid, [ref]$processId)) {
        return $null
    }
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $null
    }
    try {
        $metadata = Get-Content -LiteralPath $metadataFile -Raw | ConvertFrom-Json
        $recordedStart = [DateTime]::Parse($metadata.startedAtUtc).ToUniversalTime()
        $actualStart = $process.StartTime.ToUniversalTime()
        $delta = [Math]::Abs(($actualStart - $recordedStart).TotalSeconds)
        if ($metadata.name -ne $Name -or $delta -gt 2) {
            return $null
        }
    }
    catch {
        return $null
    }
    return $process
}

function Remove-ServiceRecord {
    param([string]$Name)
    $pidFile = Get-PidFile $Name
    $metadataFile = Get-MetadataFile $Name
    if (Test-Path -LiteralPath $pidFile) {
        Remove-Item -LiteralPath $pidFile -Force
    }
    if (Test-Path -LiteralPath $metadataFile) {
        Remove-Item -LiteralPath $metadataFile -Force
    }
}

function Stop-ProcessTree {
    param([int]$RootProcessId)
    $children = @()
    try {
        $children = Get-CimInstance Win32_Process -Filter ("ParentProcessId={0}" -f $RootProcessId)
    }
    catch {
        $children = @()
    }
    foreach ($child in $children) {
        Stop-ProcessTree -RootProcessId ([int]$child.ProcessId)
    }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

function Get-ServiceStatus {
    param(
        [string]$Name,
        [int]$Port
    )
    $process = Get-RecordedProcess $Name
    if ($null -ne $process) {
        return "running"
    }
    if (Test-PortOpen (Get-ServiceHost $Name) $Port) {
        return "listening"
    }
    return "stopped"
}

function Clear-StaleServiceRecord {
    param([string]$Name)
    $pidFile = Get-PidFile $Name
    $metadataFile = Get-MetadataFile $Name
    if ((Test-Path -LiteralPath $pidFile) -or (Test-Path -LiteralPath $metadataFile)) {
        $process = Get-RecordedProcess $Name
        if ($null -eq $process) {
            Remove-ServiceRecord $Name
        }
    }
}

function ConvertTo-QuotedPowerShell {
    param([string]$Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function Repair-ProcessPathEnvironment {
    param([System.Diagnostics.ProcessStartInfo]$StartInfo)
    $pathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
    if ([string]::IsNullOrWhiteSpace($pathValue)) {
        $pathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
    }
    $pathKeys = @()
    foreach ($key in $StartInfo.EnvironmentVariables.Keys) {
        if ($key -ieq "Path") {
            $pathKeys += $key
        }
    }
    foreach ($key in $pathKeys) {
        [void]$StartInfo.EnvironmentVariables.Remove($key)
    }
    if (-not [string]::IsNullOrWhiteSpace($pathValue)) {
        $StartInfo.EnvironmentVariables["Path"] = $pathValue
    }
}

function Start-HiddenCommand {
    param(
        [string]$FilePath,
        [string]$Arguments,
        [string]$WorkingDirectory
    )
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = $Arguments
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    Repair-ProcessPathEnvironment $startInfo

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw ("Unable to start process: {0}" -f $FilePath)
    }
    return (Get-Process -Id $process.Id -ErrorAction Stop)
}

function Open-WebUrl {
    & cmd.exe /c start "" $Script:WebUrl
}

function Start-DetachedPowerShell {
    param(
        [string]$Name,
        [string]$EncodedCommand
    )
    [void](Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $EncodedCommand) `
        -WindowStyle Minimized `
        -PassThru)
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$WorkingDirectory,
        [string]$PowerShellLine
    )
    Initialize-State

    $port = if ($Name -eq "api") { $Script:ApiPort } else { $Script:WebPort }
    $hostName = Get-ServiceHost $Name
    Clear-StaleServiceRecord $Name
    $status = Get-ServiceStatus $Name $port
    if ($status -ne "stopped") {
        Write-Check $Name $status ("already available at {0}:{1}" -f $hostName, $port)
        return
    }

    $logFile = Get-LogFile $Name
    $pidFile = Get-PidFile $Name
    $metadataFile = Get-MetadataFile $Name
    $script = @"
`$ErrorActionPreference = "Stop"
try {
Set-Location -LiteralPath $(ConvertTo-QuotedPowerShell $WorkingDirectory)
`$env:UV_CACHE_DIR = $(ConvertTo-QuotedPowerShell $Script:UvCacheRoot)
Set-Content -LiteralPath $(ConvertTo-QuotedPowerShell $pidFile) -Value `$PID -Encoding ASCII
`$launcherProcess = Get-Process -Id `$PID
`$metadata = [ordered]@{
    name = $(ConvertTo-QuotedPowerShell $Name)
    pid = `$PID
    startedAtUtc = `$launcherProcess.StartTime.ToUniversalTime().ToString("o")
    workingDirectory = $(ConvertTo-QuotedPowerShell $WorkingDirectory)
    logFile = $(ConvertTo-QuotedPowerShell $logFile)
}
`$metadata | ConvertTo-Json | Set-Content -LiteralPath $(ConvertTo-QuotedPowerShell $metadataFile) -Encoding UTF8
("Starting $Name at " + (Get-Date).ToString("s")) | Out-File -LiteralPath $(ConvertTo-QuotedPowerShell $logFile) -Encoding UTF8
`$ErrorActionPreference = "Continue"
& cmd.exe /d /s /k $(ConvertTo-QuotedPowerShell ("chcp 65001 > nul && " + $PowerShellLine + " >> `"$logFile`" 2>&1"))
`$commandExit = if (`$null -eq `$LASTEXITCODE) { 0 } else { `$LASTEXITCODE }
("$Name exited with code " + `$commandExit + " at " + (Get-Date).ToString("s")) | Out-File -LiteralPath $(ConvertTo-QuotedPowerShell $logFile) -Append -Encoding UTF8
exit `$commandExit
}
catch {
    (`$_ | Out-String) | Out-File -LiteralPath $(ConvertTo-QuotedPowerShell $logFile) -Append -Encoding UTF8
    exit 1
}
"@
    Set-Content -LiteralPath (Join-Path $Script:LogRoot ("{0}.command.ps1" -f $Name)) -Value $script -Encoding UTF8
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    Remove-ServiceRecord $Name
    Start-DetachedPowerShell -Name $Name -EncodedCommand $encoded

    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        $process = Get-RecordedProcess $Name
        if ((Test-Path -LiteralPath (Get-MetadataFile $Name)) -and (Test-PortOpen $hostName $port)) {
            $detail = if ($null -ne $process) {
                "pid={0}; url={1}; log={2}" -f $process.Id, $(if ($Name -eq "api") { $Script:ApiUrl } else { $Script:WebUrl }), $logFile
            }
            else {
                "url={0}; log={1}" -f $(if ($Name -eq "api") { $Script:ApiUrl } else { $Script:WebUrl }), $logFile
            }
            Write-Check $Name "running" $detail
            return
        }
        Start-Sleep -Milliseconds 500
    }
    Remove-ServiceRecord $Name
    Write-Check $Name "missing" ("process did not become ready; log={0}" -f $logFile)
    throw ("{0} failed to stay running" -f $Name)
}

function Start-Api {
    Start-ManagedProcess `
        -Name "api" `
        -WorkingDirectory $Script:Root `
        -PowerShellLine ("uv run uvicorn app.main:app --host {0} --port {1} --reload" -f $Script:ApiHost, $Script:ApiPort)
}

function Start-Web {
    Start-ManagedProcess `
        -Name "web" `
        -WorkingDirectory (Join-Path $Script:Root "frontend") `
        -PowerShellLine ("pnpm dev -- --host {0} --port {1}" -f $Script:WebHost, $Script:WebPort)
}

function Stop-ManagedProcess {
    param([string]$Name)
    $pidFile = Get-PidFile $Name
    $metadataFile = Get-MetadataFile $Name
    $port = if ($Name -eq "api") { $Script:ApiPort } else { $Script:WebPort }
    $hostName = Get-ServiceHost $Name
    $process = Get-RecordedProcess $Name
    if ($null -ne $process) {
        Stop-ProcessTree -RootProcessId $process.Id
        Write-Check $Name "stopped" ("stopped pid={0}" -f $process.Id)
    }
    if ($null -eq $process -and (Test-Path -LiteralPath $pidFile)) {
        if (Test-Path -LiteralPath $metadataFile) {
            Write-Check $Name "stopped" "pid file existed, but process was not running"
        }
        else {
            Write-Check $Name "stopped" "legacy pid file removed without stopping any process"
        }
    }
    elseif ($null -eq $process) {
        Write-Check $Name "stopped" "no recorded process"
    }
    Remove-ServiceRecord $Name
    if (Test-PortOpen $hostName $port) {
        Write-Check $Name "listening" ("external or orphan listener remains at {0}:{1}" -f $hostName, $port)
    }
}

function Stop-AllManagedServices {
    Stop-ManagedProcess "api"
    Stop-ManagedProcess "web"
}

function Enable-InteractiveCleanup {
    if ($Script:InteractiveCleanupEnabled) {
        return
    }
    $Script:InteractiveCleanupEnabled = $true
    Register-EngineEvent -SourceIdentifier ([System.Management.Automation.PsEngineEvent]::Exiting) -Action {
        try {
            Stop-AllManagedServices
        }
        catch {
        }
    } | Out-Null
}

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Color ("> {0}" -f $Title) Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw ("Step failed: {0}" -f $Title)
    }
}

function Invoke-Doctor {
    Initialize-State
    $failed = $false
    Write-Color "WOMAP Workbench" Cyan
    Write-Host ""
    Write-Host "Checking local environment..."

    $checks = @(
        @{ Label = "uv"; Ok = (Test-CommandExists "uv"); Detail = (Get-CommandPathText "uv") },
        @{ Label = "system python"; Ok = (Test-CommandExists "python"); Detail = (Get-CommandPathText "python") },
        @{ Label = "pnpm"; Ok = (Test-CommandExists "pnpm"); Detail = (Get-CommandPathText "pnpm") },
        @{ Label = "config local yaml"; Ok = (Test-Path -LiteralPath (Join-Path $Script:Root "config\settings.local.yaml")); Detail = (Join-Path $Script:Root "config\settings.local.yaml") },
        @{ Label = ".venv"; Ok = (Test-Path -LiteralPath (Join-Path $Script:Root ".venv")); Detail = (Join-Path $Script:Root ".venv") },
        @{ Label = ".venv python"; Ok = (Test-Path -LiteralPath (Join-Path $Script:Root ".venv\Scripts\python.exe")); Detail = (Join-Path $Script:Root ".venv\Scripts\python.exe") },
        @{ Label = "frontend node_modules"; Ok = (Test-Path -LiteralPath (Join-Path $Script:Root "frontend\node_modules")); Detail = (Join-Path $Script:Root "frontend\node_modules") }
    )

    foreach ($check in $checks) {
        if ($check.Ok) {
            Write-Check $check.Label "ok" $check.Detail
        }
        else {
            Write-Check $check.Label "missing" $check.Detail
            $failed = $true
        }
    }

    $apiStatus = Get-ServiceStatus "api" $Script:ApiPort
    $webStatus = Get-ServiceStatus "web" $Script:WebPort
    $redisStatus = if (Test-PortOpen "localhost" 6379) { "ok" } else { "stopped" }
    $postgresStatus = if (Test-PortOpen "localhost" 5432) { "ok" } else { "stopped" }
    Write-Check "api port" $apiStatus ("{0}:{1}" -f $Script:ApiHost, $Script:ApiPort)
    Write-Check "web port" $webStatus ("{0}:{1}" -f $Script:WebHost, $Script:WebPort)
    Write-Check "redis port" $redisStatus "localhost:6379"
    Write-Check "postgres port" $postgresStatus "localhost:5432"

    if ($failed) {
        return 1
    }
    return 0
}

function Show-Overview {
    param([switch]$ClearScreen)
    Initialize-State
    if ($ClearScreen) {
        Clear-Host
    }
    Write-Color "WOMAP Workbench" Cyan
    Write-Host ""
    Write-Host ("Config:  {0}" -f $Script:ConfigSource)
    Write-Host ("Logs:    {0}" -f (Join-Path $Script:StateRoot "logs"))
    Write-Host ""
    Write-Host ("{0,-10} {1,-12} {2}" -f "Service", "Status", "Endpoint")
    Write-Host ("{0,-10} {1,-12} {2}" -f "API", (Get-ServiceStatus "api" $Script:ApiPort), $Script:ApiUrl)
    Write-Host ("{0,-10} {1,-12} {2}" -f "Web", (Get-ServiceStatus "web" $Script:WebPort), $Script:WebUrl)
    Write-Host ("{0,-10} {1,-12} {2}" -f "Redis", $(if (Test-PortOpen "localhost" 6379) { "ok" } else { "stopped" }), "localhost:6379 db=0")
    Write-Host ""
    Write-Host "Commands"
    Write-Host ("  {0,-8} {1}" -f "status", "refresh this panel")
    Write-Host ("  {0,-8} {1}" -f "doctor", "run local diagnostics")
    Write-Host ("  {0,-8} {1}" -f "api", "start FastAPI backend")
    Write-Host ("  {0,-8} {1}" -f "web", "start Vite frontend")
    Write-Host ("  {0,-8} {1}" -f "dev", "start API and Web")
    Write-Host ("  {0,-8} {1}" -f "open", "open Web URL")
    Write-Host ("  {0,-8} {1}" -f "stop", "stop launcher-managed services")
    Write-Host ("  {0,-8} {1}" -f "test", "run backend and frontend checks")
    Write-Host ("  {0,-8} {1}" -f "build", "build frontend")
    Write-Host ("  {0,-8} {1}" -f "quit", "stop services and exit")
}

function Invoke-Tests {
    Invoke-Step "uv run pytest" { Set-Location -LiteralPath $Script:Root; & uv run pytest }
    Invoke-Step "uv run python -m compileall app" { Set-Location -LiteralPath $Script:Root; & uv run python -m compileall app }
    Invoke-Step "pnpm test" { Set-Location -LiteralPath (Join-Path $Script:Root "frontend"); & pnpm test }
    Invoke-Step "pnpm typecheck" { Set-Location -LiteralPath (Join-Path $Script:Root "frontend"); & pnpm typecheck }
    Invoke-Step "pnpm build" { Set-Location -LiteralPath (Join-Path $Script:Root "frontend"); & pnpm build }
}

function Invoke-Build {
    Invoke-Step "pnpm build" { Set-Location -LiteralPath (Join-Path $Script:Root "frontend"); & pnpm build }
}

function Invoke-CommandName {
    param([string]$Name)
    switch ($Name.ToLowerInvariant()) {
        "panel" { Invoke-Tui; return 0 }
        "tui" { Invoke-Tui; return 0 }
        "status" { Show-Overview; return 0 }
        "overview" { Show-Overview; return 0 }
        "doctor" { return (Invoke-Doctor) }
        "api" { Start-Api; return 0 }
        "web" { Start-Web; return 0 }
        "dev" { Start-Api; Start-Web; return 0 }
        "open" { Open-WebUrl; return 0 }
        "stop" { Stop-AllManagedServices; return 0 }
        "test" { Invoke-Tests; return 0 }
        "build" { Invoke-Build; return 0 }
        "quit" { Stop-AllManagedServices; return 0 }
        default {
            Write-Host ("Unknown command: {0}" -f $Name)
            Write-Host "Run: start-womap.bat status"
            return 2
        }
    }
}

function Invoke-Tui {
    Enable-InteractiveCleanup
    try {
        Show-Overview -ClearScreen
        while ($true) {
            $inputCommand = Read-Host "womap"
            if ([string]::IsNullOrWhiteSpace($inputCommand)) {
                Show-Overview -ClearScreen
                continue
            }
            if ($inputCommand.Trim().ToLowerInvariant() -eq "quit") {
                Stop-AllManagedServices
                return
            }
            try {
                [void](Invoke-CommandName $inputCommand.Trim())
            }
            catch {
                Write-Color $_.Exception.Message Red
            }
            if ($inputCommand.Trim().ToLowerInvariant() -notin @("doctor", "test", "build")) {
                Start-Sleep -Milliseconds 250
                Show-Overview -ClearScreen
            }
        }
    }
    finally {
        Stop-AllManagedServices
    }
}

try {
    Initialize-State
    $exitCode = Invoke-CommandName $Command
    exit $exitCode
}
catch {
    Write-Color $_.Exception.Message Red
    exit 1
}
