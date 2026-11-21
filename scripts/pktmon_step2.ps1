param(
    [ValidateSet('status', 'start', 'stop')]
    [string]$Action,
    [ValidateSet('pilot', 'full')]
    [string]$Capture = 'pilot'
)

$ErrorActionPreference = 'Stop'
$root = 'C:\Users\User\Documents\Articles\FHAM_HC_CIS\FHAM'
$captureDir = Join-Path $root ("results\step2\detection\{0}_capture" -f $Capture)
$etlBase = Join-Path $captureDir 'pktmon.etl'
New-Item -ItemType Directory -Path $captureDir -Force | Out-Null

if ($Action -eq 'status') {
    & "$env:SystemRoot\System32\pktmon.exe" status | Set-Content -Encoding UTF8 (Join-Path $captureDir 'pktmon_status.txt')
    & "$env:SystemRoot\System32\pktmon.exe" filter list | Set-Content -Encoding UTF8 (Join-Path $captureDir 'pktmon_filters.txt')
    & "$env:SystemRoot\System32\pktmon.exe" list | Set-Content -Encoding UTF8 (Join-Path $captureDir 'pktmon_components.txt')
    exit 0
}
if ($Action -eq 'start') {
    & "$env:SystemRoot\System32\pktmon.exe" start --capture --comp all --pkt-size 0 --file-name $etlBase --file-size 512 --log-mode multi-file
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    exit 0
}
if ($Action -eq 'stop') {
    & "$env:SystemRoot\System32\pktmon.exe" stop
    $stopExit = $LASTEXITCODE
    $etlFiles = Get-ChildItem -LiteralPath $captureDir -Filter 'pktmon*.etl' -File
    if (-not $etlFiles) { throw 'PktMon produced no ETL files.' }
    if ($stopExit -ne 0 -and -not $etlFiles) { exit $stopExit }
    foreach ($etl in $etlFiles) {
        $pcap = [System.IO.Path]::ChangeExtension($etl.FullName, '.pcapng')
        & "$env:SystemRoot\System32\pktmon.exe" etl2pcap $etl.FullName --out $pcap
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    exit 0
}
