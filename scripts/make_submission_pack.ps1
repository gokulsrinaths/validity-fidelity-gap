param(
  [string]$OutZip = "paper_submission_pack.zip"
)

$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$paper = Join-Path $root "Paper\Association_for_Computational_Linguistics__ACL__conference__3_\latex"
$art = Join-Path $root "paper_artifacts"

if (-not (Test-Path $paper)) { throw "Missing ACL paper dir: $paper" }
if (-not (Test-Path $art)) { throw "Missing paper_artifacts dir: $art" }

$tmp = Join-Path $root ".tmp_submission_pack"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

Copy-Item -Recurse -Force $paper (Join-Path $tmp "acl_latex")
Copy-Item -Recurse -Force $art (Join-Path $tmp "paper_artifacts")

if (Test-Path $OutZip) { Remove-Item -Force $OutZip }
Compress-Archive -Path (Join-Path $tmp "*") -DestinationPath $OutZip

Write-Output ("Wrote: " + (Resolve-Path $OutZip))

