param(
    [Parameter(Mandatory=$true)][string]$DocumentPath,
    [Parameter(Mandatory=$true)][string]$PdfPath,
    [switch]$ReadOnly
)
$ErrorActionPreference = 'Stop'
$wordApp = New-Object -ComObject Word.Application
$wordApp.Visible = $false
$wordApp.DisplayAlerts = 0
try {
    $document = $wordApp.Documents.Open($DocumentPath, $false, [bool]$ReadOnly)
    if (-not $ReadOnly) {
        foreach ($styleId in @(-20,-21,-22,-23)) {
            $tocStyle = $document.Styles.Item($styleId)
            $tocStyle.Font.Size = 10.5
            $tocStyle.Font.NameFarEast = '楷体'
            $tocStyle.ParagraphFormat.SpaceBefore = 0
            $tocStyle.ParagraphFormat.SpaceAfter = 0
            $tocStyle.ParagraphFormat.LineSpacingRule = 0
        }
        $document.Fields.Update() | Out-Null
        foreach ($contents in $document.TablesOfContents) {
            $contents.Update()
        }
        $document.Repaginate()
        $document.Fields.Update() | Out-Null
        $updatedPath = Join-Path (Split-Path -Parent $PdfPath) ('word-fields-' + [guid]::NewGuid().ToString() + '.docx')
        $document.SaveAs2($updatedPath, 16)
    }
    $renderPath = Join-Path (Split-Path -Parent $PdfPath) ('word-render-' + [guid]::NewGuid().ToString() + '.pdf')
    $document.ExportAsFixedFormat($renderPath, 17)
    $pageCount = $document.ComputeStatistics(2)
    $document.Close(0)
    Copy-Item -LiteralPath $renderPath -Destination $PdfPath -Force
    if (-not $ReadOnly) {
        Copy-Item -LiteralPath $updatedPath -Destination $DocumentPath -Force
    }
    Write-Output "Pages: $pageCount"
} finally {
    $wordApp.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordApp) | Out-Null
}
