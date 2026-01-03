# Measure page load time and size using PowerShell
$urls = @(
    "https://batteryrental-3.onrender.com/admin/",
    "https://batteryrental-3.onrender.com/admin/dashboard/"
)

Write-Host "=" * 70
Write-Host "Performance Benchmark - Battery Rental Admin"
Write-Host "=" * 70
Write-Host ""

foreach ($url in $urls) {
    Write-Host "Testing: $url"
    Write-Host "-" * 70
    
    # Measure 3 times and average
    $times = @()
    $sizes = @()
    
    for ($i = 1; $i -le 3; $i++) {
        try {
            $start = Get-Date
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30
            $end = Get-Date
            $duration = ($end - $start).TotalSeconds
            $size = $response.Content.Length
            
            $times += $duration
            $sizes += $size
            
            Write-Host "  Run $i : $([math]::Round($duration, 2))s | $([math]::Round($size/1024, 2))KB | Status: $($response.StatusCode)"
        }
        catch {
            Write-Host "  Run $i : ERROR - $($_.Exception.Message)"
        }
        
        Start-Sleep -Milliseconds 500
    }
    
    if ($times.Count -gt 0) {
        $avgTime = ($times | Measure-Object -Average).Average
        $avgSize = ($sizes | Measure-Object -Average).Average
        Write-Host "  Average: $([math]::Round($avgTime, 2))s | $([math]::Round($avgSize/1024, 2))KB"
    }
    Write-Host ""
}

Write-Host "=" * 70
Write-Host "Benchmark Complete!"
Write-Host "=" * 70

