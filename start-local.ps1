# Start Local Development Environment for Azure Durable Functions
# Prerequisites: Docker Desktop must be running

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Starting Local Development Environment" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Start Azurite (Azure Storage Emulator)
Write-Host "Starting Azurite (Azure Storage Emulator)..." -ForegroundColor Yellow
$azuriteRunning = docker ps --filter "name=azurite" --format "{{.Names}}" 2>$null
if ($azuriteRunning -eq "azurite") {
    Write-Host "  Azurite is already running" -ForegroundColor Green
} else {
    # Try to start existing container first
    docker start azurite 2>$null
    if ($LASTEXITCODE -ne 0) {
        # Container doesn't exist, create it
        Write-Host "  Creating new Azurite container..." -ForegroundColor Gray
        docker run -d `
            --name azurite `
            -p 10000:10000 `
            -p 10001:10001 `
            -p 10002:10002 `
            mcr.microsoft.com/azure-storage/azurite
    }
    Write-Host "  Azurite started" -ForegroundColor Green
}

# Start Durable Task Scheduler Emulator
Write-Host "Starting Durable Task Scheduler Emulator..." -ForegroundColor Yellow
$dtsRunning = docker ps --filter "name=dts-emulator" --format "{{.Names}}" 2>$null
if ($dtsRunning -eq "dts-emulator") {
    Write-Host "  DTS Emulator is already running" -ForegroundColor Green
} else {
    # Try to start existing container first
    docker start dts-emulator 2>$null
    if ($LASTEXITCODE -ne 0) {
        # Container doesn't exist, create it
        Write-Host "  Creating new DTS Emulator container..." -ForegroundColor Gray
        docker run -d `
            --name dts-emulator `
            -p 8080:8080 `
            -p 8082:8082 `
            mcr.microsoft.com/dts/dts-emulator:latest
    }
    Write-Host "  DTS Emulator started" -ForegroundColor Green
}

# Wait for services to be ready
Write-Host ""
Write-Host "Waiting for services to initialize..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# Display status
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Local Environment Ready" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Services running:" -ForegroundColor White
Write-Host "  - Azurite Blob:  http://localhost:10000" -ForegroundColor Gray
Write-Host "  - Azurite Queue: http://localhost:10001" -ForegroundColor Gray
Write-Host "  - Azurite Table: http://localhost:10002" -ForegroundColor Gray
Write-Host "  - DTS gRPC:      http://localhost:8080" -ForegroundColor Gray
Write-Host "  - DTS Dashboard: http://localhost:8082" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor White
Write-Host "  1. cd function_app" -ForegroundColor Gray
Write-Host "  2. pip install -r requirements.txt" -ForegroundColor Gray
Write-Host "  3. func start" -ForegroundColor Gray
Write-Host ""
Write-Host "Function app will be available at: http://localhost:7071" -ForegroundColor Green
Write-Host ""
