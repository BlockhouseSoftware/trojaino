# CI-only harness. Never run on a personal machine.
param([ValidatePattern('^[0-9a-f]{40}$')][string]$CandidateSha)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') { throw 'Hosted GitHub runner required' }
$os = Get-CimInstance Win32_OperatingSystem
if ($os.ProductType -ne 1 -or $os.Caption -notmatch 'Windows 11') { throw 'Windows 11 client required' }
$parentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]::new($parentIdentity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Fixture provisioning requires runner administrator' }
$repo = Split-Path $PSScriptRoot
$userName = 'tjstd_' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
$root = Join-Path $env:PUBLIC ('TrojainoStandard-' + [Guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $root)
$securePassword = ConvertTo-SecureString ([Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)) + 'aA1!') -AsPlainText -Force
$user = $null
$process = $null
$stopped = $true
try {
    $user = New-LocalUser -Name $userName -Password $securePassword -AccountNeverExpires -PasswordNeverExpires -Description 'Ephemeral Trojaino CI fixture'
    Add-LocalGroupMember -SID 'S-1-5-32-545' -Member $user
    $acl = Get-Acl -LiteralPath $root
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($user.SID, 'Modify', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
    Set-Acl -LiteralPath $root -AclObject $acl
    $archive = Join-Path $root 'candidate.zip'
    & git -C $repo archive --format=zip "--output=$archive" $CandidateSha
    if ($LASTEXITCODE -ne 0) { throw 'Exact candidate archive failed' }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $root 'source')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'windows_standard_user_child.ps1') -Destination (Join-Path $root 'child.ps1')
    $python = (Get-Command python -CommandType Application).Source
    $nodeDir = Split-Path (Get-Command node -CommandType Application).Source
    $gitDir = Split-Path (Get-Command git -CommandType Application).Source
    $gitRoot = Split-Path $gitDir
    $info = [Diagnostics.ProcessStartInfo]::new()
    $info.FileName = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $info.Arguments = '-NoLogo -NoProfile -NonInteractive -File "' + (Join-Path $root 'child.ps1') + '" -Root "' + $root + '" -Python "' + $python + '" -CandidateSha ' + $CandidateSha + ' -ExpectedSid ' + $user.SID.Value
    $info.WorkingDirectory = $root
    $info.UserName = $userName
    $info.Domain = $env:COMPUTERNAME
    $info.Password = $securePassword
    $info.LoadUserProfile = $true
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardInput = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.EnvironmentVariables.Clear()
    foreach ($name in @('SystemRoot','WINDIR','COMPUTERNAME','ProgramFiles','ProgramData','PUBLIC')) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($value) { $info.EnvironmentVariables[$name] = $value }
    }
    $info.EnvironmentVariables['COMSPEC'] = Join-Path $env:SystemRoot 'System32\cmd.exe'
    $info.EnvironmentVariables['PATHEXT'] = '.COM;.EXE;.BAT;.CMD'
    $info.EnvironmentVariables['PATH'] = "$(Split-Path $python);$nodeDir;$gitDir;$gitRoot\usr\bin;$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\WindowsPowerShell\v1.0"
    $info.EnvironmentVariables['TROJAINO_CANDIDATE_SHA'] = $CandidateSha
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $info
    $stopped = $false
    if (-not $process.Start()) { throw 'Standard-account process did not start' }
    $process.StandardInput.Close()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(600000)) {
        $process.Kill($true)
        $stopped = $process.WaitForExit(10000)
        throw 'Standard-account lifecycle timed out'
    }
    $stopped = $true
    Write-Output $stdout.GetAwaiter().GetResult()
    Write-Output $stderr.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) { throw "Standard-account child failed with exit $($process.ExitCode)" }
    $report = Get-Content -Raw -LiteralPath (Join-Path $root 'result.json') | ConvertFrom-Json
    if ($report.candidate_sha -ne $CandidateSha -or $report.sid -ne $user.SID.Value -or $report.admin_role -ne $false -or $report.admin_group_present -ne $false -or $report.lifecycle_exit -ne 0) { throw 'Standard-account evidence mismatch' }
    $report | ConvertTo-Json -Compress
} finally {
    if ($process -and -not $stopped) {
        try { $process.Kill($true); $stopped = $process.WaitForExit(10000) } catch { Write-Warning 'Process stop uncertain; retaining fixture until runner teardown' }
    }
    if ($process) { $process.Dispose() }
    if ($user -and $stopped) { Remove-LocalUser -SID $user.SID }
    $securePassword.Dispose()
    # Disposable runner teardown owns profile/files; never delete uncertain trees.
}
