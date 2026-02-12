# =============================================================================
# surge-test.ps1 — Fire N claims, wait for HITL, bulk-approve
#
# Usage:
#   .\surge-test.ps1              # 10 claims (default)
#   .\surge-test.ps1 -N 5         # 5 claims
#   .\surge-test.ps1 -N 15 -Port 7071
#   .\surge-test.ps1 -SkipApprove # Fire only, don't auto-approve
# =============================================================================

param(
    [int]$N = 10,
    [int]$Port = 7071,
    [switch]$SkipApprove,
    [int]$PollIntervalSec = 3,
    [int]$TimeoutMinutes = 10
)

$BaseUrl = "http://localhost:$Port/api"
$AttachmentUrl = "https://pdfazuredocaitest.blob.core.windows.net/test/Claim_Baker_015.pdf"
$ErrorActionPreference = "Stop"

# Timestamp prefix for unique claim IDs
$Batch = (Get-Date -Format "HHmmss")

# --- Sample claim variations ------------------------------------------------
$ClaimTemplates = @(
    @{
        email = "Dear Claims Team,`n`nI am submitting a claim for my 2022 Honda Civic (VIN: 1HGBH41JXMN109186). The transmission failed while driving on I-35. Current mileage: 34,500. Contract: VSC-2024-88421.`n`nThe vehicle is at AutoFix Pro, Dallas TX. Estimate: `$4,750.`n`nThanks,`nJohn Smith`njohn.smith@email.com`n(555) 123-4567"
        sender = "john.smith@email.com"
        name = "John Smith"
    },
    @{
        email = "Hi,`n`nMy 2023 Toyota RAV4 hit a pothole and two tires plus one rim are damaged. VIN: JTMRWRFV5ND123456. Mileage: 18,200. Contract: TW-2025-55678.`n`nDiscount Tire quoted `$890 for replacements.`n`nMike Johnson`n(555) 987-6543"
        sender = "mike.johnson@email.com"
        name = "Mike Johnson"
    },
    @{
        email = "Hello Claims Dept,`n`nMy 2021 Ford F-150 engine is making loud knocking noises. Mechanic says it needs a new engine block. VIN: 1FTFW1E50MFA00001. Mileage: 52,300. Contract: VSC-2023-77100.`n`nEstimate from Ford dealer: `$8,200.`n`nSarah Williams`nsarah.w@email.com"
        sender = "sarah.w@email.com"
        name = "Sarah Williams"
    },
    @{
        email = "To whom it may concern,`n`nSubmitting a GAP claim for my 2020 Chevy Malibu totaled in an accident on Feb 1. VIN: 1G1ZD5ST0LF000002. Loan balance: `$18,500. Insurance payout: `$14,200. GAP contract: GAP-2024-33210.`n`nRobert Baker`nrobert.b@email.com"
        sender = "robert.b@email.com"
        name = "Robert Baker"
    },
    @{
        email = "Hi Claims,`n`nAC compressor failed on my 2022 Hyundai Tucson. VIN: KM8J3CA46NU000003. Mileage: 28,100. Contract: VSC-2024-11567.`n`nCooling Systems Inc quoted `$1,950 for parts and labor.`n`nLisa Chen`nlisa.chen@email.com"
        sender = "lisa.chen@email.com"
        name = "Lisa Chen"
    },
    @{
        email = "Dear Claims,`n`nMy 2023 Kia Sportage has a cracked windshield from road debris. VIN: KNDPM3AC7P7000004. Mileage: 15,600. Contract: TW-2025-99321.`n`nSafelite quote: `$650 for replacement.`n`nDavid Park`ndavid.park@email.com"
        sender = "david.park@email.com"
        name = "David Park"
    },
    @{
        email = "Hello,`n`nI need to file a claim for my 2021 BMW X3. The turbocharger failed. VIN: 5UXTY5C00M9000005. Mileage: 41,800. Contract: VSC-2023-66890.`n`nBMW service center estimate: `$6,500.`n`nMaria Garcia`nmaria.g@email.com"
        sender = "maria.g@email.com"
        name = "Maria Garcia"
    },
    @{
        email = "Claims Team,`n`nMy 2022 Nissan Altima CVT transmission is slipping. VIN: 1N4BL4BV4NN000006. Mileage: 38,900. Contract: VSC-2024-22345.`n`nTransmission shop estimate: `$3,800 for rebuild.`n`nJames Wilson`njames.w@email.com"
        sender = "james.w@email.com"
        name = "James Wilson"
    },
    @{
        email = "Hi,`n`nFiling a claim for hail damage to all four tires on my 2023 Mazda CX-5. VIN: JM3KFBCM8P0000007. Mileage: 12,400. Contract: TW-2025-44567.`n`nTire Kingdom quote: `$1,100 for four new tires.`n`nAmanda Brown`namanda.b@email.com"
        sender = "amanda.b@email.com"
        name = "Amanda Brown"
    },
    @{
        email = "Dear Claims Department,`n`nMy 2020 Jeep Wrangler transfer case is failing. VIN: 1C4HJXDG5LW000008. Mileage: 55,200. Contract: VSC-2023-88900.`n`nJeep dealer estimate: `$4,200 for replacement.`n`nKevin Thompson`nkevin.t@email.com"
        sender = "kevin.t@email.com"
        name = "Kevin Thompson"
    },
    @{
        email = "Hello Claims,`n`nElectrical system failure on my 2022 Tesla Model 3. Main control unit is unresponsive. VIN: 5YJ3E1EA1NF000009. Mileage: 29,700. Contract: VSC-2024-55123.`n`nTesla service estimate: `$5,800.`n`nPriya Sharma`npriya.s@email.com"
        sender = "priya.s@email.com"
        name = "Priya Sharma"
    },
    @{
        email = "Hi Claims Team,`n`nPower steering pump failed on my 2021 Dodge Ram 1500. VIN: 1C6SRFFT2MN000010. Mileage: 47,600. Contract: VSC-2023-99876.`n`nLocal mechanic estimate: `$2,100.`n`nTom Martinez`ntom.m@email.com"
        sender = "tom.m@email.com"
        name = "Tom Martinez"
    },
    @{
        email = "Dear Claims,`n`nBrake rotor and caliper failure on my 2023 Subaru Outback. VIN: 4S4BTAPC7P3000011. Mileage: 21,300. Contract: VSC-2025-12340.`n`nSubaru dealer estimate: `$2,800.`n`nEmily Davis`nemily.d@email.com"
        sender = "emily.d@email.com"
        name = "Emily Davis"
    },
    @{
        email = "Hello,`n`nMy 2022 Volkswagen Tiguan has a failed water pump causing overheating. VIN: 3VV2B7AX7NM000012. Mileage: 33,500. Contract: VSC-2024-78901.`n`nVW dealer estimate: `$1,650.`n`nChris Lee`nchris.lee@email.com"
        sender = "chris.lee@email.com"
        name = "Chris Lee"
    },
    @{
        email = "Claims Dept,`n`nAll four wheels curb-damaged on my 2023 Audi Q5. VIN: WA1BNAFY1P2000013. Mileage: 16,800. Contract: TW-2025-34567.`n`nWheel repair shop quote: `$2,200.`n`nNatalie Kim`nnatalie.k@email.com"
        sender = "natalie.k@email.com"
        name = "Natalie Kim"
    }
)

# =============================================================================
# Helper: pretty-print with color
# =============================================================================
function Write-Phase($msg) { Write-Host "`n========================================" -ForegroundColor Cyan; Write-Host " $msg" -ForegroundColor Cyan; Write-Host "========================================" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Wait($msg)  { Write-Host "  [..] $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "  [!!] $msg" -ForegroundColor Red }
function Write-Info($msg)  { Write-Host "  [i]  $msg" -ForegroundColor Gray }

# =============================================================================
# Phase 0: Health check
# =============================================================================
Write-Phase "Phase 0: Health Check"
try {
    $health = Invoke-RestMethod -Uri "$BaseUrl/health" -Method Get
    Write-Ok "Function app is $($health.status) at port $Port"
} catch {
    Write-Err "Function app not reachable at $BaseUrl. Is 'func start' running?"
    exit 1
}

# =============================================================================
# Phase 1: Fire N claims as fast as possible
# =============================================================================
Write-Phase "Phase 1: Firing $N claims (batch $Batch)"

$claimIds = @()
$instanceIds = @()
$jobs = @()

for ($i = 1; $i -le $N; $i++) {
    $claimId = "SURGE-$Batch-$($i.ToString('D3'))"
    $claimIds += $claimId

    # Cycle through templates
    $template = $ClaimTemplates[($i - 1) % $ClaimTemplates.Count]

    $body = @{
        claim_id       = $claimId
        email_content  = $template.email
        attachment_url = $AttachmentUrl
        sender_email   = $template.sender
    } | ConvertTo-Json -Depth 5

    # Fire each claim as a background job for max parallelism
    $jobs += Start-Job -ScriptBlock {
        param($url, $jsonBody, $id)
        try {
            $resp = Invoke-RestMethod -Uri $url -Method Post -Body $jsonBody -ContentType "application/json"
            return @{ claim_id = $id; instance_id = $resp.instance_id; status = "ok"; error = $null }
        } catch {
            return @{ claim_id = $id; instance_id = $null; status = "error"; error = $_.Exception.Message }
        }
    } -ArgumentList "$BaseUrl/claims/start", $body, $claimId
}

Write-Info "Waiting for all $N requests to complete..."
$results = $jobs | Wait-Job | Receive-Job
$jobs | Remove-Job -Force

$successCount = 0
foreach ($r in $results) {
    if ($r.status -eq "ok") {
        $instanceIds += $r.instance_id
        Write-Ok "$($r.claim_id) -> $($r.instance_id)"
        $successCount++
    } else {
        Write-Err "$($r.claim_id) FAILED: $($r.error)"
    }
}

Write-Host ""
Write-Info "$successCount / $N claims started successfully"

if ($successCount -eq 0) {
    Write-Err "No claims started. Exiting."
    exit 1
}

# =============================================================================
# Phase 2: Poll contractor state (show Bob spawning)
# =============================================================================
Write-Phase "Phase 2: Watching contractor pools"

try {
    $state = Invoke-RestMethod -Uri "$BaseUrl/contractors/state" -Method Get
    foreach ($stageKey in @("classifier", "adjudicator", "email_composer")) {
        $stage = $state.stages.$stageKey
        $contractors = ($stage.active_contractors | ForEach-Object { "$($_.name)($($_.slots_used)/$($_.capacity))" }) -join ", "
        $icon = if ($stage.contractor_count -gt 1) { " ** BOB IS HERE **" } else { "" }
        Write-Info "$($stage.display_name): $($stage.contractor_count) contractors [$contractors] | in-flight=$($stage.total_jobs_in_flight)$icon"
    }
} catch {
    Write-Wait "Could not read contractor state: $($_.Exception.Message)"
}

# =============================================================================
# Phase 3: Poll until all reach awaiting_approval
# =============================================================================
Write-Phase "Phase 3: Waiting for all claims to reach HITL pause"

$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$awaitingCount = 0

while ($awaitingCount -lt $successCount -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $PollIntervalSec

    $awaitingCount = 0
    $statusSummary = @{}

    foreach ($instId in $instanceIds) {
        try {
            $s = Invoke-RestMethod -Uri "$BaseUrl/claims/status/$instId" -Method Get
            $step = $s.custom_status.step
            if (-not $statusSummary.ContainsKey($step)) { $statusSummary[$step] = 0 }
            $statusSummary[$step]++
            if ($step -eq "awaiting_approval") { $awaitingCount++ }
        } catch {
            if (-not $statusSummary.ContainsKey("unknown")) { $statusSummary["unknown"] = 0 }
            $statusSummary["unknown"]++
        }
    }

    $summary = ($statusSummary.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join " | "
    Write-Wait "$awaitingCount / $successCount at HITL  [$summary]"

    # Show contractor state
    try {
        $state = Invoke-RestMethod -Uri "$BaseUrl/contractors/state" -Method Get
        $classifierPool = $state.stages.classifier
        $contractors = ($classifierPool.active_contractors | ForEach-Object { "$($_.name)($($_.slots_used)/$($_.capacity))" }) -join ", "
        $bobMsg = if ($classifierPool.contractor_count -gt 1) { " << BOB SPAWNED!" } else { "" }
        Write-Info "  Classifier: [$contractors] queue=$($classifierPool.pending_count)$bobMsg"
        Write-Info "  HITL waiting: $($state.hitl.waiting_count)"
    } catch {}
}

if ($awaitingCount -lt $successCount) {
    Write-Err "Timeout: only $awaitingCount / $successCount reached HITL after $TimeoutMinutes minutes"
    Write-Info "Continuing with available claims..."
}

Write-Ok "All $awaitingCount claims are at HITL pause"

if ($SkipApprove) {
    Write-Phase "Done (SkipApprove flag set)"
    Write-Info "Claims are waiting at HITL. Approve manually via:"
    Write-Info "  POST $BaseUrl/claims/approve/<instanceId>"
    exit 0
}

# =============================================================================
# Phase 4: Bulk-approve all claims (parallel)
# =============================================================================
Write-Phase "Phase 4: Bulk-approving $awaitingCount claims"

$approveJobs = @()
$estimates = @(4750, 890, 8200, 3200, 1950, 650, 6500, 3800, 1100, 4200, 5800, 2100, 2800, 1650, 2200)

for ($i = 0; $i -lt $instanceIds.Count; $i++) {
    $instId = $instanceIds[$i]
    $template = $ClaimTemplates[$i % $ClaimTemplates.Count]
    $est = $estimates[$i % $estimates.Count]
    $partsCost = [math]::Round($est * 0.6, 2)
    $laborCost = [math]::Round($est * 0.4, 2)

    $approveBody = @{
        decision     = "approved"
        reviewer     = "surge-tester@company.com"
        comments     = "Bulk approved by surge-test.ps1"
        claim_amounts = @{
            total_parts_cost = $partsCost
            total_labor_cost = $laborCost
            total_estimate   = $est
            deductible       = 100
        }
        claim_data = @{
            claimant = @{
                name  = $template.name
                email = $template.sender
            }
            contract = @{
                contract_number = "VSC-2024-SURGE-$($i+1)"
                coverage_type   = "VSC - Comprehensive"
                deductible      = 100
            }
            vehicle = @{
                year  = 2022
                make  = "Test"
                model = "Vehicle $($i+1)"
            }
            repair = @{
                facility_name      = "Test Repair Shop"
                facility_authorized = $true
                total_estimate     = $est
                parts_cost         = $partsCost
                labor_cost         = $laborCost
            }
            documents = @{
                claim_form    = $true
                damage_photos = $true
            }
        }
    } | ConvertTo-Json -Depth 10

    $approveJobs += Start-Job -ScriptBlock {
        param($url, $jsonBody, $id)
        try {
            $resp = Invoke-RestMethod -Uri $url -Method Post -Body $jsonBody -ContentType "application/json"
            return @{ instance_id = $id; status = "ok"; error = $null }
        } catch {
            return @{ instance_id = $id; status = "error"; error = $_.Exception.Message }
        }
    } -ArgumentList "$BaseUrl/claims/approve/$instId", $approveBody, $instId
}

Write-Info "Waiting for all approvals to submit..."
$approveResults = $approveJobs | Wait-Job | Receive-Job
$approveJobs | Remove-Job -Force

$approvedCount = 0
foreach ($r in $approveResults) {
    if ($r.status -eq "ok") {
        Write-Ok "$($r.instance_id) approved"
        $approvedCount++
    } else {
        Write-Err "$($r.instance_id) FAILED: $($r.error)"
    }
}

Write-Host ""
Write-Info "$approvedCount / $($instanceIds.Count) approvals submitted"

# =============================================================================
# Phase 5: Watch Agent2/Agent3 contractor pools (Bob in adjudicator)
# =============================================================================
Write-Phase "Phase 5: Watching post-approval processing"

$completedCount = 0
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)

while ($completedCount -lt $approvedCount -and (Get-Date) -lt $deadline) {
    Start-Sleep -Seconds $PollIntervalSec

    $completedCount = 0
    $statusSummary = @{}

    foreach ($instId in $instanceIds) {
        try {
            $s = Invoke-RestMethod -Uri "$BaseUrl/claims/status/$instId" -Method Get
            $step = if ($s.runtime_status -eq "Completed") { "completed" } else { $s.custom_status.step }
            if (-not $statusSummary.ContainsKey($step)) { $statusSummary[$step] = 0 }
            $statusSummary[$step]++
            if ($s.runtime_status -eq "Completed") { $completedCount++ }
        } catch {
            if (-not $statusSummary.ContainsKey("unknown")) { $statusSummary["unknown"] = 0 }
            $statusSummary["unknown"]++
        }
    }

    $summary = ($statusSummary.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join " | "
    Write-Wait "$completedCount / $approvedCount completed  [$summary]"

    # Show all 3 contractor pools
    try {
        $state = Invoke-RestMethod -Uri "$BaseUrl/contractors/state" -Method Get
        foreach ($stageKey in @("classifier", "adjudicator", "email_composer")) {
            $stage = $state.stages.$stageKey
            $contractors = ($stage.active_contractors | ForEach-Object { "$($_.name)($($_.slots_used)/$($_.capacity))" }) -join ", "
            $bobMsg = if ($stage.contractor_count -gt 1) { " << SCALED!" } else { "" }
            Write-Info "  $($stage.display_name): [$contractors] done=$($stage.total_completed)$bobMsg"
        }
        Write-Info "  Emails sent: $($state.email_sender.sent_count)"
    } catch {}

    Write-Host ""
}

# =============================================================================
# Phase 6: Summary
# =============================================================================
Write-Phase "SURGE TEST COMPLETE"

try {
    $state = Invoke-RestMethod -Uri "$BaseUrl/contractors/state" -Method Get
    Write-Host ""
    Write-Info "Final Contractor Stats:"
    foreach ($stageKey in @("classifier", "adjudicator", "email_composer")) {
        $stage = $state.stages.$stageKey
        Write-Info "  $($stage.display_name): $($stage.total_completed) completed, $($stage.contractor_count) contractors active"
    }
    Write-Info "  Emails sent: $($state.email_sender.sent_count)"
    Write-Host ""

    Write-Info "Recent events:"
    $state.events | Select-Object -First 15 | ForEach-Object {
        $icon = switch ($_.type) {
            "spawn"         { "+" }
            "terminate"     { "-" }
            "job_assigned"  { ">" }
            "job_completed" { "<" }
            default         { " " }
        }
        Write-Host "    $($_.timestamp) [$icon] $($_.message)" -ForegroundColor DarkGray
    }
} catch {}

Write-Host ""
Write-Ok "Batch: $Batch | Claims: $successCount | Approved: $approvedCount | Completed: $completedCount"
Write-Host ""
