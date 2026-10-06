param(
    [string]$SourcePath = 'output/technical-presentation/candidate.pptx',
    [string]$TargetPath = 'output/technical-presentation/animated-candidate.pptx',
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
$sourceFile = (Resolve-Path -LiteralPath $SourcePath).Path
$targetFile = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $TargetPath))
$buildDirectory = Join-Path (Get-Location) 'output/technical-presentation'
$renderDirectory = Join-Path $buildDirectory 'powerpoint-render'
[void](New-Item -ItemType Directory -Path $renderDirectory -Force)
$existingProcess = @(Get-Process POWERPNT -ErrorAction SilentlyContinue)
$application = New-Object -ComObject PowerPoint.Application
$deck = $null
try {
    $deck = $application.Presentations.Open($sourceFile, -1, 0, 0)
    if ($deck.Slides.Count -ne 25) { throw 'Unexpected slide count' }
    if (-not $VerifyOnly) {
        # 通过 PowerPoint 原生接口设置对象淡入与三个章节。
        foreach ($slide in $deck.Slides) {
            $orderedShapes = @($slide.Shapes | Sort-Object @{Expression = {[Math]::Round($_.Top, 3)}}, @{Expression = {[Math]::Round($_.Left, 3)}}, Id)
            $position = 0
            foreach ($shape in $orderedShapes) {
                $trigger = if ($position -eq 0) { 2 } else { 3 }
                $effect = $slide.TimeLine.MainSequence.AddEffect($shape, 10, 0, $trigger)
                $effect.Timing.Duration = 0.4
                $effect.Timing.TriggerDelayTime = 0.06
                $position += 1
            }
            $slide.SlideShowTransition.EntryEffect = 1793
            $slide.SlideShowTransition.Duration = 0.5
            $slide.SlideShowTransition.AdvanceOnClick = -1
            $slide.SlideShowTransition.AdvanceOnTime = 0
        }
        [void]$deck.SectionProperties.AddBeforeSlide(1, '01 系统与核心技术')
        [void]$deck.SectionProperties.AddBeforeSlide(12, '02 算法与创新机制')
        [void]$deck.SectionProperties.AddBeforeSlide(18, '03 实际数据与验证')
        $deck.SaveAs($targetFile, 24)
    }
    $records = @()
    $overflow = @()
    foreach ($slide in $deck.Slides) {
        $ordered = @($slide.Shapes | Sort-Object @{Expression = {[Math]::Round($_.Top, 3)}}, @{Expression = {[Math]::Round($_.Left, 3)}}, Id)
        $sequence = $slide.TimeLine.MainSequence
        if ($sequence.Count -ne $ordered.Count) { throw "Animation coverage failed on slide $($slide.SlideIndex)" }
        for ($index = 1; $index -le $sequence.Count; $index++) {
            $effect = $sequence.Item($index)
            if ($effect.EffectType -ne 10 -or $effect.Exit -ne 0) { throw 'Unexpected animation effect' }
            if ($effect.Shape.Id -ne $ordered[$index - 1].Id) { throw 'Animation reading order failed' }
        }
        foreach ($shape in $slide.Shapes) {
            if ($shape.HasTextFrame -and $shape.TextFrame.HasText) {
                $range = $shape.TextFrame.TextRange
                if ($range.BoundWidth -gt $shape.Width + 4 -or $range.BoundHeight -gt $shape.Height + 4) {
                    $overflow += [pscustomobject]@{ slide = $slide.SlideIndex; shape = $shape.Name; text = $range.Text; frameWidth = $shape.Width; frameHeight = $shape.Height; textWidth = $range.BoundWidth; textHeight = $range.BoundHeight }
                }
            }
        }
        $slide.Export((Join-Path $renderDirectory ('slide-{0:D2}.png' -f $slide.SlideIndex)), 'PNG', 1920, 1080)
        $records += [pscustomobject]@{ slide = $slide.SlideIndex; shapes = $slide.Shapes.Count; fadeEffects = $sequence.Count; transition = $slide.SlideShowTransition.EntryEffect; order = 'TOP_TO_BOTTOM_LEFT_TO_RIGHT' }
    }
    if ($deck.SectionProperties.Count -ne 3) { throw 'Unexpected presentation section count' }
    [pscustomobject]@{ slides = $deck.Slides.Count; sections = $deck.SectionProperties.Count; records = $records; textOverflow = $overflow; source = $sourceFile } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $buildDirectory 'powerpoint-verification.json') -Encoding utf8
    Write-Output ('Verified {0} slides, {1} sections, {2} text overflow records' -f $deck.Slides.Count, $deck.SectionProperties.Count, $overflow.Count)
} finally {
    if ($null -ne $deck) { $deck.Close() }
    if ($existingProcess.Count -eq 0) { $application.Quit() }
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($application)
}
