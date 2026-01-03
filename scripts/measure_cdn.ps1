# Measure external CDN resources
$cdnResources = @{
    "Bootstrap CSS" = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
    "Bootstrap Icons" = "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css"
    "Bootstrap JS" = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
}

Write-Host "=" * 70
Write-Host "External CDN Resources Analysis"
Write-Host "=" * 70
Write-Host ""

$totalSize = 0

foreach ($name in $cdnResources.Keys) {
    $url = $cdnResources[$name]
    Write-Host "Checking: $name"
    Write-Host "URL: $url"
    
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
        $size = $response.Content.Length
        $sizeKB = [math]::Round($size/1024, 2)
        $totalSize += $size
        
        # Check headers
        $cacheControl = $response.Headers['Cache-Control']
        $encoding = $response.Headers['Content-Encoding']
        
        Write-Host "  Size: $sizeKB KB"
        Write-Host "  Cache-Control: $cacheControl"
        Write-Host "  Content-Encoding: $encoding"
        Write-Host "  Status: $($response.StatusCode)"
    }
    catch {
        Write-Host "  ERROR: $($_.Exception.Message)"
    }
    Write-Host ""
}

$totalKB = [math]::Round($totalSize/1024, 2)
$totalMB = [math]::Round($totalSize/1024/1024, 2)

Write-Host "=" * 70
Write-Host "Total External CDN Size: $totalKB KB ($totalMB MB)"
Write-Host "=" * 70

