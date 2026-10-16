[CmdletBinding()]
param([string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$toolsPath = Join-Path $ProjectRoot '.tools'
$rPath = Join-Path $toolsPath 'R'
$rLibrary = Join-Path $toolsPath 'R-library'
$installer = Join-Path $toolsPath 'R-4.6.1-win.exe'
$sourceUrl = 'https://cran.r-project.org/bin/windows/base/R-4.6.1-win.exe'
$checksumUrl = 'https://cran.r-project.org/bin/windows/base/md5sum.R-4.6.1.txt'
New-Item -ItemType Directory -Path $toolsPath -Force | Out-Null
if (-not (Test-Path -LiteralPath $installer)) {
    Invoke-WebRequest -Uri $sourceUrl -OutFile $installer
}
$signature = Get-AuthenticodeSignature -LiteralPath $installer
if ($signature.Status -ne 'Valid') { throw 'Official R installer signature is not valid.' }
$checksumDocument = (Invoke-WebRequest -Uri $checksumUrl).Content
$match = [regex]::Match($checksumDocument, '(?im)^([a-f0-9]{32})\s+\*?R-4\.6\.1-win\.exe\s*$')
if (-not $match.Success) { throw 'Published CRAN checksum could not be read.' }
$actualMd5 = (Get-FileHash -LiteralPath $installer -Algorithm MD5).Hash.ToLowerInvariant()
if ($actualMd5 -ne $match.Groups[1].Value.ToLowerInvariant()) { throw 'R installer differs from the official CRAN checksum.' }
$rscript = Join-Path $rPath 'bin/Rscript.exe'
if (-not (Test-Path -LiteralPath $rscript)) {
    $installLog = Join-Path $toolsPath 'install-R.log'
    $installArguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-',
        '/CURRENTUSER', '/NOICONS', '/TASKS=""', ('/DIR="' + $rPath + '"'),
        ('/LOG="' + $installLog + '"'))
    $installation = Start-Process -FilePath $installer -ArgumentList $installArguments `
        -WindowStyle Hidden -Wait -PassThru
    if ($installation.ExitCode -ne 0) { throw "R installer failed with exit code $($installation.ExitCode)." }
}
$installedVersion = & $rscript --version 2>&1
if ($LASTEXITCODE -ne 0 -or "$installedVersion" -notmatch '4\.6\.1') { throw 'Expected project-local R4.6.1 was not found.' }
New-Item -ItemType Directory -Path $rLibrary -Force | Out-Null
$previousLocale = $env:LC_ALL
$previousLang = $env:LANG
$previousRLibs = $env:R_LIBS_USER
try {
    $env:LC_ALL = 'C'
    $env:LANG = 'C'
    $env:R_LIBS_USER = $rLibrary
    Push-Location -LiteralPath $ProjectRoot
    try {
        $expression = 'needed<-c("survey","jsonlite"); absent<-needed[!vapply(needed,requireNamespace,logical(1),quietly=TRUE)]; if(length(absent)) install.packages(absent,lib=Sys.getenv("R_LIBS_USER"),repos="https://cloud.r-project.org",type="binary"); stopifnot(requireNamespace("survey",quietly=TRUE),requireNamespace("jsonlite",quietly=TRUE)); cat("survey=",as.character(packageVersion("survey"))," jsonlite=",as.character(packageVersion("jsonlite")),"\n",sep="")'
        & $rscript --vanilla -e $expression
        if ($LASTEXITCODE -ne 0) { throw 'CRAN binary package installation failed.' }
    } finally { Pop-Location }
} finally {
    $env:LC_ALL = $previousLocale
    $env:LANG = $previousLang
    $env:R_LIBS_USER = $previousRLibs
}
$provenance = [ordered]@{
    source_url = $sourceUrl
    checksum_url = $checksumUrl
    installed_at_utc = [DateTime]::UtcNow.ToString('o')
    version = "$installedVersion"
    md5 = $actualMd5
    sha256 = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
    authenticode_status = "$($signature.Status)"
    signer = $signature.SignerCertificate.Subject
    signer_thumbprint = $signature.SignerCertificate.Thumbprint
    runtime_path = $rPath
    library_path = $rLibrary
    configuration = 'Current-user local directory; no optional tasks/shortcuts; no global PATH changes'
}
$provenance | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $toolsPath 'R-installation.json') -Encoding utf8
Write-Output "Research R runtime ready: $rscript"
