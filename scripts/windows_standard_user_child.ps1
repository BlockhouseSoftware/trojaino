# Executed only in the disposable standard account created by the CI parent.
param([string]$Root, [string]$Python, [ValidatePattern('^[0-9a-f]{40}$')][string]$CandidateSha, [string]$ExpectedSid)
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
$admin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$adminGroup = @($identity.Groups | Where-Object { $_.Value -eq 'S-1-5-32-544' }).Count -gt 0
if ($identity.User.Value -ne $ExpectedSid -or $admin -or $adminGroup) { throw 'Child must be the new standard account, not a filtered administrator' }
$profile = [Environment]::GetFolderPath('UserProfile')
$registered = (Get-ItemProperty -LiteralPath ("HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\" + $ExpectedSid)).ProfileImagePath
if (-not $profile -or $profile -ne [Environment]::ExpandEnvironmentVariables($registered)) { throw 'Loaded OS profile does not match fixture account' }
$env:USERPROFILE = $profile
$env:HOME = $profile
$env:APPDATA = Join-Path $profile 'AppData\Roaming'
$env:LOCALAPPDATA = Join-Path $profile 'AppData\Local'
$env:TEMP = Join-Path $env:LOCALAPPDATA 'Temp'
$env:TMP = $env:TEMP
$env:USERNAME = $identity.Name.Split('\')[-1]
$env:USERDOMAIN = $env:COMPUTERNAME
$env:CI = 'true'
$env:DISABLE_TELEMETRY = '1'
$env:DISABLE_ERROR_REPORTING = '1'
$env:CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = '1'
foreach ($dir in @($env:APPDATA, $env:LOCALAPPDATA, $env:TEMP)) { [void](New-Item -ItemType Directory -Path $dir -Force) }
if (Test-Path -LiteralPath (Join-Path $profile '.claude')) { throw 'Fixture profile is not fresh' }
$prefix = Join-Path $env:APPDATA 'npm'
$env:npm_config_cache = Join-Path $env:LOCALAPPDATA 'npm-cache'
$env:PATH = $prefix + ';' + $env:PATH
Set-Location -LiteralPath (Join-Path $Root 'source')
Write-Output ('STANDARD_USER identity verified: ' + $identity.User.Value + '; administrator role/group absent')
& $Python -c "import platform,sys; print({'python':sys.version.split()[0],'machine':platform.machine()}); assert platform.machine().lower()=='arm64'"
if ($LASTEXITCODE -ne 0) { throw 'Native ARM Python unavailable to standard account' }
& $Python -m unittest discover -s tests -p test_native_launcher.py -v
if ($LASTEXITCODE -ne 0) { throw 'Non-admin native launcher regression failed' }
# Pin the CLI already qualified by PR59; installation is user-scoped, no elevation.
& npm.cmd install --global --prefix $prefix '@anthropic-ai/claude-code@2.1.312' --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { throw 'User-scoped Claude CLI installation failed' }
$claudePath = (Get-Command claude.cmd -CommandType Application).Source
if ($claudePath -ne (Join-Path $prefix 'claude.cmd')) { throw 'Claude CLI was not installed in this account' }
& claude.cmd --version
if ($LASTEXITCODE -ne 0) { throw 'User-scoped Claude CLI failed to start' }
# Existing model-free harness exercises install/update, doctor, actual hooks,
# disable/re-enable/uninstall and settings preservation, in this standard token.
& $Python scripts/smoke_plugin_install.py --candidate-git
$lifecycleExit = $LASTEXITCODE
if ($lifecycleExit -ne 0) { throw 'Standard-account marketplace lifecycle failed' }
[ordered]@{
    candidate_sha = $CandidateSha
    sid = $identity.User.Value
    admin_role = $admin
    admin_group_present = $adminGroup
    loaded_profile_verified = $true
    claude_version = '2.1.312'
    lifecycle_exit = $lifecycleExit
    qualification = 'Hosted Windows11 ARM standard-account engineering test; provisioned Python/Node/Git, no visual first-install or x64 acceptance'
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Root 'result.json') -Encoding UTF8
Write-Output 'STANDARD_USER lifecycle PASS'
