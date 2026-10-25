# Run a generated .jsx in the running Adobe app (Windows, COM).
# Usage: run_jsx.ps1 <file.jsx> [indesign|illustrator]
param([string]$jsx, [string]$app = 'indesign')
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$code = [IO.File]::ReadAllText($jsx, [Text.Encoding]::UTF8)
$file = $jsx.Replace([string][char]92, '/')
# eval wrapper: a syntax error reports its line instead of an opaque COM exception
$wrap = "var __JSX_FILE__ = " + (ConvertTo-Json $file) + "; try{ eval(" + (ConvertTo-Json $code) + "); }catch(e){ 'ERR line ' + e.line + ': ' + e; }"
if ($app -eq 'illustrator') {
  $ids = @('Illustrator.Application', 'Illustrator.Application.29', 'Illustrator.Application.28', 'Illustrator.Application.27')
} else {
  $ids = @('InDesign.Application', 'InDesign.Application.2026', 'InDesign.Application.2025', 'InDesign.Application.2024', 'InDesign.Application.2023')
}
$o = $null
foreach ($v in $ids) { try { $o = New-Object -ComObject $v -ErrorAction Stop; break } catch {} }
if (-not $o) { Write-Output "$app COM not found: run the .jsx from the app's Scripts menu"; exit 1 }
try {
  if ($app -eq 'illustrator') { $r = $o.DoJavaScript($wrap) } else { $r = $o.DoScript($wrap, 1246973031) }
  Write-Output $r
} catch {
  $m = $_.Exception.Message
  if ($m.Length -gt 400) { $m = $m.Substring(0, 400) + ' ...' }
  Write-Output ("COM error: " + $m)
}

