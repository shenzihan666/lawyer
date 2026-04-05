param(
  [string]$RootPath = "D:\Project\lawyer\Resource\law_documents",
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $RootPath)) {
  throw "Root path does not exist: $RootPath"
}

$rootItem = Get-Item -LiteralPath $RootPath
$resolvedRoot = $rootItem.FullName

$docFiles = Get-ChildItem -LiteralPath $resolvedRoot -Recurse -File |
  Where-Object { $_.Extension -ieq ".doc" } |
  Sort-Object FullName

if (-not $docFiles) {
  Write-Host "No .doc files found under $resolvedRoot"
  exit 0
}

Write-Host ("Found {0} .doc files under {1}" -f $docFiles.Count, $resolvedRoot)

$deleted = 0

foreach ($file in $docFiles) {
  if ($DryRun) {
    Write-Host ("[DRYRUN] {0}" -f $file.FullName)
    continue
  }

  Remove-Item -LiteralPath $file.FullName
  $deleted++
  Write-Host ("[DELETE] {0}" -f $file.FullName)
}

Write-Host ""
Write-Host "Removal summary"
Write-Host ("Deleted: {0}" -f $deleted)
Write-Host ("Matched: {0}" -f $docFiles.Count)
