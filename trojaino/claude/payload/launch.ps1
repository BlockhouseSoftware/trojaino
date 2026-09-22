# Windows PowerShell 5.1 compatible. No Python is needed to report a failure.
param([ValidateSet('session-start', 'pre-tool-use', 'doctor')][string]$Mode)
$ErrorActionPreference = 'Stop'
# A manager alias may otherwise download Python on first use. This setting is
# local to this launcher process; prerequisite checks must remain offline.
$env:PYTHON_MANAGER_AUTOMATIC_INSTALL = 'false'
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = $OutputEncoding
[Console]::InputEncoding = $OutputEncoding
$operation = if ($Mode -eq 'doctor') { 'doctor' } else { 'hook' }
# PowerShell does not forward its inherited stdin to native commands. Read once
# and pipe it explicitly, in UTF-8, only after the isolated version probe.
$eventInput = if ($operation -eq 'hook') { [Console]::In.ReadToEnd() } else { $null }
$problem = 'Python was not found on PATH.'
foreach ($name in @('python3.exe', 'python.exe')) {
    $candidate = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $candidate) { continue }
    $probe = [System.Diagnostics.Process]::new()
    $probe.StartInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $probe.StartInfo.FileName = $candidate.Source
    $probe.StartInfo.Arguments = '-I -S -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 3)"'
    $probe.StartInfo.UseShellExecute = $false
    $probe.StartInfo.CreateNoWindow = $true
    $probe.StartInfo.RedirectStandardInput = $true
    $probe.StartInfo.RedirectStandardOutput = $true
    $probe.StartInfo.RedirectStandardError = $true
    $result = -1
    try {
        [void]$probe.Start()
        $probe.StandardInput.Close()
        $stdout = $probe.StandardOutput.ReadToEndAsync()
        $stderr = $probe.StandardError.ReadToEndAsync()
        if ($probe.WaitForExit(5000)) { $result = $probe.ExitCode }
        else { $probe.Kill(); $probe.WaitForExit() }
        [void]$stdout.GetAwaiter().GetResult()
        [void]$stderr.GetAwaiter().GetResult()
    } catch { $result = -1 }
    finally { $probe.Dispose() }
    if ($result -eq 0) {
        $entry = Join-Path $PSScriptRoot 'preflight.py'
        if ($operation -eq 'hook') { $eventInput | & $candidate.Source -I -S -X utf8 $entry $operation }
        else { & $candidate.Source -I -S -X utf8 $entry $operation }
        exit $LASTEXITCODE
    }
    if ($result -eq 3) { $problem = 'The available Python is older than 3.11.' }
    elseif ($problem -eq 'Python was not found on PATH.') { $problem = 'Python was found but could not run in isolated mode.' }
}
$message = "Trojaino cannot start: $problem Python 3.11 or newer is required. Trojaino is not checking installations. Install Python using https://github.com/BlockhouseSoftware/trojaino/blob/main/docs/windows-quick-start.md, restart Claude Code, then run /trojaino:doctor."
if ($Mode -eq 'doctor') {
    @{status = 'Needs attention'; actions = @($message)} | ConvertTo-Json -Compress
    exit 1
}
$eventName = if ($Mode -eq 'session-start') { 'SessionStart' } else { 'PreToolUse' }
@{systemMessage = $message; hookSpecificOutput = @{hookEventName = $eventName; additionalContext = $message}} | ConvertTo-Json -Compress -Depth 4
exit 0
