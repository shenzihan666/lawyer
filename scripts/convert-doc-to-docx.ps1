param(
  [string]$RootPath = "D:\Project\lawyer\Resource\law_documents",
  [switch]$OverwriteExisting,
  [switch]$DeleteOriginal,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Release-ComObject {
  param(
    [Parameter(Mandatory = $true)]
    [object]$ComObject
  )

  try {
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($ComObject)
  } catch {
    Write-Warning ("Failed to release COM object: {0}" -f $_.Exception.Message)
  }
}

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

$converted = 0
$skipped = 0
$failed = 0
$word = $null

try {
  if (-not $DryRun) {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
  }

  foreach ($file in $docFiles) {
    $docPath = $file.FullName
    $docxPath = [System.IO.Path]::ChangeExtension($docPath, ".docx")

    if ((Test-Path -LiteralPath $docxPath) -and -not $OverwriteExisting) {
      $skipped++
      Write-Host ("[SKIP] {0} -> docx already exists" -f $docPath)
      continue
    }

    if ($DryRun) {
      Write-Host ("[DRYRUN] {0} -> {1}" -f $docPath, $docxPath)
      continue
    }

    $document = $null

    try {
      $document = $word.Documents.Open($docPath, $false, $true)
      $document.SaveAs([ref]$docxPath, [ref]16)
      $document.Close()
      $document = $null
      $converted++
      Write-Host ("[OK] {0} -> {1}" -f $docPath, $docxPath)

      if ($DeleteOriginal) {
        Remove-Item -LiteralPath $docPath
        Write-Host ("[DELETE] {0}" -f $docPath)
      }
    } catch {
      $failed++
      Write-Warning ("[FAIL] {0} -> {1}" -f $docPath, $_.Exception.Message)

      if ($document -ne $null) {
        try {
          $document.Close()
        } catch {
          Write-Warning ("Failed to close Word document after error: {0}" -f $_.Exception.Message)
        }
        $document = $null
      }
    }
  }
} finally {
  if ($word -ne $null) {
    try {
      $word.Quit()
    } catch {
      Write-Warning ("Failed to quit Word cleanly: {0}" -f $_.Exception.Message)
    }

    Release-ComObject -ComObject $word
    $word = $null
  }

  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}

Write-Host ""
Write-Host "Conversion summary"
Write-Host ("Converted: {0}" -f $converted)
Write-Host ("Skipped:   {0}" -f $skipped)
Write-Host ("Failed:    {0}" -f $failed)
