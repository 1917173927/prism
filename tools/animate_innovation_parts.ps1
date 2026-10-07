param(
 [string]$SourcePath='output/innovation-animation-20261007/candidate.pptx',
 [string]$TargetPath='output/innovation-animation-20261007/animated-candidate.pptx',
 [switch]$VerifyOnly
)
$ErrorActionPreference='Stop'
$sourceFile=(Resolve-Path -LiteralPath $SourcePath).Path
$targetFile=[IO.Path]::GetFullPath((Join-Path (Get-Location) $TargetPath))
$buildDir=Join-Path (Get-Location) 'output/innovation-animation-20261007'
$renderDir=Join-Path $buildDir $(if($VerifyOnly){'final-render'}else{'draft-render'})
[void](New-Item -ItemType Directory -Path $renderDir -Force)
$manifest=Get-Content -LiteralPath (Join-Path $buildDir 'parts-manifest.json') -Raw -Encoding utf8 | ConvertFrom-Json
$existingProcesses=@(Get-Process POWERPNT -ErrorAction SilentlyContinue)
$app=New-Object -ComObject PowerPoint.Application
$deck=$null
try {
 $deck=$app.Presentations.Open($sourceFile,-1,0,0)
 if($deck.Slides.Count -ne 5){throw 'Expected five slides'}
 $records=@()
 foreach($slide in $deck.Slides){
  $spec=$manifest.slides[$slide.SlideIndex-1]
  if($slide.Shapes.Count -ne $spec.shapeCount){throw "Unexpected shape count on slide $($slide.SlideIndex)"}
  if(-not $VerifyOnly){
   for($i=$slide.TimeLine.MainSequence.Count;$i -ge 1;$i--){$slide.TimeLine.MainSequence.Item($i).Delete()}
   for($i=1;$i -le $slide.Shapes.Count;$i++){
    $shape=$slide.Shapes.Item($i)
    $shape.Name=if($i -eq 1){'slide-title'}else{'part-{0:D2}-{1}' -f ($i-1),$spec.pieces[$i-2].name}
    $trigger=if($i -eq 1){2}else{3}
    $effect=$slide.TimeLine.MainSequence.AddEffect($shape,10,0,$trigger)
    $effect.Timing.Duration=[single]0.4
    $effect.Timing.TriggerDelayTime=[single]$(if($i -eq 1){0.0}else{0.06})
   }
   $slide.SlideShowTransition.EntryEffect=1793
   $slide.SlideShowTransition.Duration=0.5
   $slide.SlideShowTransition.AdvanceOnClick=-1
   $slide.SlideShowTransition.AdvanceOnTime=0
  }
  $sequence=$slide.TimeLine.MainSequence
  if($sequence.Count -ne $slide.Shapes.Count){throw 'Animation coverage mismatch'}
  $effects=@()
  for($i=1;$i -le $sequence.Count;$i++){
   $effect=$sequence.Item($i)
   if($effect.EffectType -ne 10 -or $effect.Exit -ne 0){throw 'Expected entrance fade'}
   if($effect.Shape.Id -ne $slide.Shapes.Item($i).Id){throw 'Unexpected reading order'}
   if([Math]::Abs($effect.Timing.Duration-0.4) -gt 0.01){throw 'Unexpected fade duration'}
   $expectedTrigger=if($i -eq 1){2}else{3}
   if($effect.Timing.TriggerType -ne $expectedTrigger){throw 'Unexpected automatic trigger'}
   $shape=$effect.Shape
   if($shape.Left -lt -0.1 -or $shape.Top -lt -0.1 -or $shape.Left+$shape.Width -gt $deck.PageSetup.SlideWidth+0.1 -or $shape.Top+$shape.Height -gt $deck.PageSetup.SlideHeight+0.1){throw 'Off-slide object'}
   if($shape.HasTextFrame -and $shape.TextFrame.HasText){
    $range=$shape.TextFrame.TextRange
    if($range.BoundWidth -gt $shape.Width+2 -or $range.BoundHeight -gt $shape.Height+2){throw 'Text overflow'}
   }
   $effects += [pscustomobject]@{order=$i;shape=$shape.Name;effect='FADE';duration=$effect.Timing.Duration;trigger=$effect.Timing.TriggerType;delay=$effect.Timing.TriggerDelayTime}
  }
  $slide.Export((Join-Path $renderDir ('slide-{0:D2}.png' -f $slide.SlideIndex)),'PNG',1920,1080)
  $records += [pscustomobject]@{slide=$slide.SlideIndex;objects=$slide.Shapes.Count;parts=$slide.Shapes.Count-1;effects=$effects}
 }
 if(-not $VerifyOnly){$deck.SaveAs($targetFile,24)}
 $reportName=if($VerifyOnly){'final-powerpoint-verification.json'}else{'draft-powerpoint-verification.json'}
 [pscustomobject]@{status='PASS';slides=$deck.Slides.Count;source=$sourceFile;records=$records} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $buildDir $reportName) -Encoding utf8
 Write-Output ('PASS: {0} slides, 42 image parts, native entrance fade in manifest reading order' -f $deck.Slides.Count)
} finally {
 if($null -ne $deck){$deck.Close()}
 if($existingProcesses.Count -eq 0){$app.Quit()}
 [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app)
}
