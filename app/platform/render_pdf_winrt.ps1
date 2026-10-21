# HTML Report Studio HF6 - Windows native PDF->PNG (page 1 only).
# Requires Windows 10+ Windows PowerShell 5.1 and Windows.Data.Pdf (OS-supplied).
# Source PDF is never modified. Outputs only PNG into the caller's temp folder.
# Never requests network access or invokes installed Office products.
# This is an isolated subprocess with a Python-enforced timeout.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$InputPath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [ValidateRange(72,600)][int]$Dpi=300,
    [ValidateRange(512,4096)][int]$MaxEdge=4096,
    [ValidateRange(1000000,12000000)][int]$MaxPixels=12000000
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$doc=$null;$page=$null;$memory=$null;$stream=$null;$bitmap=$null
try {
    Add-Type -AssemblyName System.Drawing
    $null=[Windows.Data.Pdf.PdfDocument,Windows.Data.Pdf,ContentType=WindowsRuntime]
    $null=[Windows.Data.Pdf.PdfPageRenderOptions,Windows.Data.Pdf,ContentType=WindowsRuntime]
    $null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
    $null=[Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    function Invoke-WinRTResult($operation,[type]$resultType) {
        $method=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
        } | Select-Object -First 1
        if (-not $method) { throw 'WinRT AsTask<T> is unavailable' }
        $task=$method.MakeGenericMethod($resultType).Invoke($null,@($operation))
        if (-not $task.Wait(18000)) { throw 'Windows PDF loading timed out' }
        return $task.Result
    }
    function Invoke-WinRTAction($operation) {
        $method=[System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
            $_.Name -eq 'AsTask' -and -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1
        } | Select-Object -First 1
        if (-not $method) { throw 'WinRT AsTask is unavailable' }
        $task=$method.Invoke($null,@($operation))
        if (-not $task.Wait(18000)) { throw 'Windows PDF rasterizing timed out' }
    }
    $inputFull=[System.IO.Path]::GetFullPath($InputPath)
    $file=Invoke-WinRTResult ([Windows.Storage.StorageFile]::GetFileFromPathAsync($inputFull)) ([Windows.Storage.StorageFile])
    $doc=Invoke-WinRTResult ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
    $pages=[int]$doc.PageCount
    if ($pages -lt 1 -or $pages -gt 80) { throw 'PDF has invalid page count or too many pages' }
    $page=$doc.GetPage([uint32]0)
    $w=[Math]::Max(1.0,[double]$page.Size.Width*$Dpi/96.0)
    $h=[Math]::Max(1.0,[double]$page.Size.Height*$Dpi/96.0)
    $scale=[Math]::Min(1.0,[Math]::Min($MaxEdge/[Math]::Max($w,$h),[Math]::Sqrt($MaxPixels/($w*$h))))
    $w=[uint32][Math]::Max(1,[Math]::Floor($w*$scale))
    $h=[uint32][Math]::Max(1,[Math]::Floor($h*$scale))
    if ([double]$w*$h -gt $MaxPixels) { throw 'Rendered image too large' }
    $opt=New-Object Windows.Data.Pdf.PdfPageRenderOptions
    $opt.DestinationWidth=$w
    $opt.DestinationHeight=$h
    $memory=New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    Invoke-WinRTAction ($page.RenderToStreamAsync($memory,$opt))
    $stream=[System.IO.WindowsRuntimeStreamExtensions]::AsStream([Windows.Storage.Streams.IRandomAccessStream]$memory)
    if ($stream.CanSeek) { $stream.Position=0 }
    $bitmap=[System.Drawing.Bitmap]::FromStream($stream)
    $bitmap.Save([System.IO.Path]::GetFullPath($OutputPath),[System.Drawing.Imaging.ImageFormat]::Png)
    $effective=[Math]::Round([Math]::Min($bitmap.Width/[double]$page.Size.Width,$bitmap.Height/[double]$page.Size.Height)*96,2)
    Write-Output ([string]::Format([Globalization.CultureInfo]::InvariantCulture,"HF6_PDF|{0}|{1}|{2}|{3}",$bitmap.Width,$bitmap.Height,$pages,$effective))
} catch {
    [Console]::Error.WriteLine('PDF preview error: '+$_.Exception.Message)
    exit 2
} finally {
    foreach ($o in @($bitmap,$stream,$memory,$page,$doc)) {
        if ($null -ne $o -and $o -is [System.IDisposable]) { $o.Dispose() }
    }
}
