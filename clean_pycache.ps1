Write-Host "Cleaning Python cache files..." -ForegroundColor Cyan

# Delete all __pycache__ directories
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" |
    ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item $_.FullName -Recurse -Force
    }

# Delete all .pyc files
Get-ChildItem -Path . -Recurse -File -Filter "*.pyc" |
    ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item $_.FullName -Force
    }

# Delete all .pyo files
Get-ChildItem -Path . -Recurse -File -Filter "*.pyo" |
    ForEach-Object {
        Write-Host "Removing $($_.FullName)"
        Remove-Item $_.FullName -Force
    }

Write-Host "`nPython cache cleanup completed!" -ForegroundColor Green