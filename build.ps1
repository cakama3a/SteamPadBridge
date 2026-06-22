param(
    [switch]$Sign,
    [switch]$SkipSign,
    [string]$CertificateSubject = "",
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Continue"
$PSNativeCommandUseErrorActionPreference = $false

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$appName = "SteamPadBridge"
$log = Join-Path $root "build.log"
$venv = Join-Path $root ".venv-build"
$dist = Join-Path $root "dist"
$build = Join-Path $root "build"
$out = Join-Path $root "${appName}_PyInstaller"
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

"Build started $(Get-Date -Format s)" | Set-Content -Path $log -Encoding UTF8

function Write-Log {
    param([string]$Message)
    $Message | Add-Content -Path $log -Encoding UTF8
    Write-Host $Message
}

function Sign-ReleaseExe {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string]$Subject,
        [Parameter(Mandatory = $true)][string]$Timestamp
    )

    Write-Log "Looking for code-signing certificate containing subject: $Subject"
    $now = Get-Date
    $cert = Get-ChildItem -Path Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -like "*$Subject*" -and $_.NotAfter -gt $now } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1

    if (-not $cert) {
        throw "Code signing certificate containing '$Subject' was not found in Cert:\CurrentUser\My, or it is expired."
    }

    Write-Log "Signing $FilePath"
    Write-Log "Certificate: $($cert.Subject)"
    Write-Log "Thumbprint: $($cert.Thumbprint)"
    Write-Log "If your certificate requires confirmation, complete the Windows security prompt now."

    $signature = Set-AuthenticodeSignature -FilePath $FilePath -Certificate $cert -TimestampServer $Timestamp
    $signature | Format-List | Out-String | Add-Content -Path $log -Encoding UTF8

    $verification = Get-AuthenticodeSignature -FilePath $FilePath
    $verification | Format-List | Out-String | Add-Content -Path $log -Encoding UTF8

    if ($verification.Status -ne "Valid") {
        throw "Signing finished but verification status is '$($verification.Status)'. See build.log for details."
    }

    Write-Log "EXE signature verified: Valid"
}

function Remove-DirectoryStrict {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    try {
        Remove-Item -Recurse -Force -ErrorAction Stop $Path
    } catch {
        throw "Could not remove '$Path'. Close SteamPadBridge.exe and any Explorer/window using that folder, then build again. Original error: $($_.Exception.Message)"
    }
}

$python = $null
foreach ($candidate in @("py", "python", $bundledPython)) {
    try {
        if ($candidate -eq $bundledPython) {
            if (Test-Path $candidate) { $python = $candidate; break }
        } else {
            $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
            if ($cmd) { $python = $candidate; break }
        }
    } catch {}
}
if (-not $python) {
    throw "Python was not found."
}

Push-Location $root
try {
    & $python -m venv $venv 2>&1 | Add-Content $log
    & "$venv\Scripts\python.exe" -m pip install --upgrade pip 2>&1 | Add-Content $log
    & "$venv\Scripts\pip.exe" install -r "$root\requirements.txt" 2>&1 | Add-Content $log

    & "$venv\Scripts\pyinstaller.exe" --noconfirm --clean --onedir --windowed `
        --name $appName `
        --collect-binaries hid `
        --collect-binaries vgamepad `
        --collect-all sdl2 `
        --collect-all sdl2dll `
        --add-data "$root\drivers;drivers" `
        "$root\main.py" 2>&1 | Add-Content $log
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    Remove-DirectoryStrict -Path $out
    Move-Item -Path (Join-Path $dist $appName) -Destination $out -ErrorAction Stop
    Copy-Item -Path (Join-Path $root "drivers") -Destination (Join-Path $out "drivers") -Recurse -Force -ErrorAction Stop

    if ($Sign -and -not $SkipSign) {
        if ([string]::IsNullOrWhiteSpace($CertificateSubject)) {
            throw "Use -CertificateSubject when signing, for example: -Sign -CertificateSubject `"Your Publisher Name`""
        }
        Sign-ReleaseExe -FilePath (Join-Path $out "$appName.exe") -Subject $CertificateSubject -Timestamp $TimestampServer
    } else {
        Write-Log "Skipping EXE signing. Use -Sign -CertificateSubject `"Your Publisher Name`" to sign a release build."
    }

    if (Test-Path $dist) { Remove-Item -Recurse -Force -ErrorAction Stop $dist }
    if (Test-Path $build) { Remove-Item -Recurse -Force -ErrorAction Stop $build }
    $spec = Join-Path $root "$appName.spec"
    if (Test-Path $spec) { Remove-Item -Force -ErrorAction Stop $spec }

    Write-Log "Created $out"
} finally {
    Pop-Location
}
