<#
.SYNOPSIS
    Windows Laptop & PC Hardware Health & Specifications Report
.DESCRIPTION
    Scans hardware specifications (CPU, RAM, GPU, Disks, Display, Battery, Audio, Network, Bluetooth, Camera)
    and checks if any hardware is failing or not working, producing an executive HTML diagnostic report.
.NOTES
    Output: HealthReport_<DeviceName>_<Date>.html
#>

[CmdletBinding()]
param (
    [string]$OutputDir = $PSScriptRoot,
    [string]$Company = "UNICOMTIC",
    [string]$CustomerName = "",
    [string]$CustomerPhone = "",
    [string]$ServerUrl = "https://healthchecklabtop.vercel.app",
    [string]$AdminPassword = "admin123",
    [switch]$AutoUpload = $true,
    [switch]$NoUpload,
    [switch]$NoBrowserOpen
)

if ($NoUpload) { $AutoUpload = $false }

# Ensure modern TLS 1.2 is enabled for HTTPS communication with Vercel
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls
} catch {}

$ErrorActionPreference = 'SilentlyContinue'

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "    Windows Laptop & PC Hardware Health & Specifications Report " -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

$StartTime = Get-Date
$DeviceName = $env:COMPUTERNAME
$CurrentUserName = "$env:USERDOMAIN\$env:USERNAME"
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

Write-Host "[*] Target Device : $DeviceName" -ForegroundColor Green
Write-Host "[*] Logged-in User: $CurrentUserName" -ForegroundColor Green
Write-Host "[*] Admin Rights  : $(if ($IsAdmin) { 'YES' } else { 'NO (Standard user - admin recommended for deep hardware access)' })" -ForegroundColor $(if ($IsAdmin) { 'Green' } else { 'Yellow' })
Write-Host ""

if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
}
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = [System.Environment]::CurrentDirectory
}

$ReportDateFormatted = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
$FileNameTimestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$ReportFileName = "HealthReport_${DeviceName}_${FileNameTimestamp}.html"
$ReportPath = [System.IO.Path]::Combine($OutputDir, $ReportFileName)
$BatReportFileName = "BatteryReport_${DeviceName}_${FileNameTimestamp}.html"
$BatReportPath = [System.IO.Path]::Combine($OutputDir, $BatReportFileName)

# Scoring & Defect Tracking
$HealthScore = 100
$FailingHardwares = [System.Collections.Generic.List[PSCustomObject]]::new()
$Warnings = [System.Collections.Generic.List[string]]::new()
$Checklist = [System.Collections.Generic.List[PSCustomObject]]::new()

# ---------------------------------------------------------
# 1. System, Motherboard & BIOS Specs
# ---------------------------------------------------------
Write-Host "[1/10] Collecting Motherboard, BIOS & System Specs..." -ForegroundColor Cyan
$cs = Get-CimInstance Win32_ComputerSystem
$bios = Get-CimInstance Win32_Bios
$os = Get-CimInstance Win32_OperatingSystem
$bb = Get-CimInstance Win32_BaseBoard

$Manufacturer = if ($cs.Manufacturer) { $cs.Manufacturer.Trim() } else { "Unknown" }
$Model = if ($cs.Model) { $cs.Model.Trim() } else { "Unknown" }
$SystemType = if ($cs.PCSystemType) {
    switch ($cs.PCSystemType) {
        1 { "Desktop" }
        2 { "Laptop / Notebook" }
        8 { "Tablet" }
        default { "PC ($($cs.PCSystemType))" }
    }
} else { "PC" }

$SerialNumber = if ($bios.SerialNumber) { $bios.SerialNumber.Trim() } else { "Unknown" }
$BiosVersion = if ($bios.SMBIOSBIOSVersion) { $bios.SMBIOSBIOSVersion } else { $bios.Version }
$BiosDate = if ($bios.ReleaseDate) { (Get-Date $bios.ReleaseDate).ToString("yyyy-MM-dd") } else { "N/A" }
$Motherboard = "$($bb.Manufacturer) $($bb.Product)"

$OSCaption = $os.Caption
$OSBuild = $os.BuildNumber
$OSArch = $os.OSArchitecture
$InstallDate = if ($os.InstallDate) { (Get-Date $os.InstallDate).ToString("yyyy-MM-dd") } else { "N/A" }

$LastBoot = if ($os.LastBootUpTime) { (Get-Date $os.LastBootUpTime) } else { $null }
$Uptime = if ($LastBoot) {
    $diff = (Get-Date) - $LastBoot
    "$($diff.Days)d $($diff.Hours)h $($diff.Minutes)m"
} else { "N/A" }

# TPM & Secure Boot
$TpmStatus = "Not Detected / Disabled"
try {
    $tpm = Get-CimInstance -Namespace "root\CIMV2\Security\MicrosoftTpm" -ClassName Win32_Tpm -ErrorAction Stop
    if ($tpm.IsEnabled_InitialValue) {
        $TpmStatus = "Enabled (v$($tpm.SpecVersion))"
    } else {
        $TpmStatus = "Present but Disabled"
    }
} catch {
    $TpmStatus = "Not Available / Standard User"
}

$SecureBootStatus = "Unknown"
try {
    $sb = Confirm-SecureBootUEFI -ErrorAction Stop
    $SecureBootStatus = if ($sb) { "Enabled" } else { "Disabled" }
} catch {
    $SecureBootStatus = "Not Supported / Legacy BIOS"
}

# ---------------------------------------------------------
# 2. Processor (CPU) Detailed Specs & Health
# ---------------------------------------------------------
Write-Host "[2/10] Inspecting CPU Specifications & Load..." -ForegroundColor Cyan
$proc = Get-CimInstance Win32_Processor | Select-Object -First 1
$CpuName = $proc.Name.Trim()
$CpuCores = $proc.NumberOfCores
$CpuThreads = $proc.NumberOfLogicalProcessors
$CpuMaxSpeedGHz = if ($proc.MaxClockSpeed) { [math]::Round(($proc.MaxClockSpeed / 1000), 2) } else { "N/A" }
$CpuCurrentSpeedGHz = if ($proc.CurrentClockSpeed) { [math]::Round(($proc.CurrentClockSpeed / 1000), 2) } else { "N/A" }
$CpuL3CacheMB = if ($proc.L3CacheSize) { [math]::Round(($proc.L3CacheSize / 1024), 1) } else { "N/A" }
$CpuSocket = if ($proc.SocketDesignation) { $proc.SocketDesignation } else { "N/A" }

$cpuMeasure = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average
$CpuLoad = if ($cpuMeasure.Average -ne $null) { [math]::Round($cpuMeasure.Average, 1) } else { 0 }

# CPU Health Check
$cpuHealth = "PASS"
$cpuStatusMsg = "Operating Normally ($CpuLoad% Load)"
if ($CpuLoad -gt 92) {
    $cpuHealth = "WARN"
    $cpuStatusMsg = "High CPU Load ($CpuLoad%)"
    $HealthScore -= 5
    $Warnings.Add("CPU load is very high ($CpuLoad%). Check background processes.")
}

$Checklist.Add([PSCustomObject]@{
    Component = "Processor (CPU)"
    Icon      = "&#9881;"
    Summary   = "$CpuName ($CpuCores C / $CpuThreads T @ $CpuMaxSpeedGHz GHz)"
    Status    = $cpuHealth
    Detail    = $cpuStatusMsg
})

# ---------------------------------------------------------
# 3. RAM (Memory) Detailed Specs & Slot Configuration
# ---------------------------------------------------------
Write-Host "[3/10] Analyzing RAM Hardware, Modules & Slots..." -ForegroundColor Cyan
$TotalRamGB = [math]::Round(($os.TotalVisibleMemorySize / 1MB), 2)
$FreeRamGB = [math]::Round(($os.FreePhysicalMemory / 1MB), 2)
$UsedRamGB = [math]::Round(($TotalRamGB - $FreeRamGB), 2)
$RamUsagePercent = if ($TotalRamGB -gt 0) { [math]::Round((($UsedRamGB / $TotalRamGB) * 100), 1) } else { 0 }

# Motherboard slots available vs used
$memArray = Get-CimInstance Win32_PhysicalMemoryArray | Select-Object -First 1
$TotalRamSlots = if ($memArray.MemoryDevices) { [int]$memArray.MemoryDevices } else { 0 }

$ramModules = Get-CimInstance Win32_PhysicalMemory
$PopulatedSlots = ($ramModules | Measure-Object).Count

$RamModulesList = [System.Collections.Generic.List[PSCustomObject]]::new()
$ramSpeedsList = @()
$ramMakersList = @()

foreach ($rm in $ramModules) {
    $capGB = [math]::Round(($rm.Capacity / 1GB), 1)
    $speed = if ($rm.Speed) { "$($rm.Speed) MHz" } else { "N/A" }
    $maker = if ($rm.Manufacturer) { $rm.Manufacturer.Trim() } else { "Unknown" }
    $part = if ($rm.PartNumber) { $rm.PartNumber.Trim() } else { "N/A" }
    $slot = if ($rm.DeviceLocator) { $rm.DeviceLocator } else { "Slot" }
    
    $ramSpeedsList += $speed
    $ramMakersList += $maker

    $RamModulesList.Add([PSCustomObject]@{
        Slot         = $slot
        CapacityGB   = "$capGB GB"
        Speed        = $speed
        Manufacturer = $maker
        PartNumber   = $part
    })
}

$RamSpeedSummary = ($ramSpeedsList | Select-Object -Unique) -join ", "
$SlotSummary = "$PopulatedSlots of $TotalRamSlots slots populated"

# RAM Health Check
$ramHealth = "PASS"
$ramStatusMsg = "$UsedRamGB GB / $TotalRamGB GB Used ($RamUsagePercent%)"
if ($RamUsagePercent -gt 90) {
    $ramHealth = "WARN"
    $ramStatusMsg = "Critically High RAM Usage ($RamUsagePercent%)"
    $HealthScore -= 10
    $Warnings.Add("RAM is nearly full ($RamUsagePercent% used). Consider closing heavy apps or upgrading RAM.")
} elseif ($RamUsagePercent -gt 80) {
    $ramHealth = "WARN"
    $ramStatusMsg = "High RAM Usage ($RamUsagePercent%)"
    $HealthScore -= 5
    $Warnings.Add("Moderate to high memory load ($RamUsagePercent%).")
}

$Checklist.Add([PSCustomObject]@{
    Component = "Memory (RAM)"
    Icon      = "&#129504;"
    Summary   = "$TotalRamGB GB Installed ($SlotSummary, $RamSpeedSummary)"
    Status    = $ramHealth
    Detail    = $ramStatusMsg
})

# ---------------------------------------------------------
# 4. Storage (NVMe / SSD / HDD) Physical & Logical Specs
# ---------------------------------------------------------
Write-Host "[4/10] Querying Physical Disks, NVMe, SSD Health & Partitions..." -ForegroundColor Cyan
$PhysicalDisks = [System.Collections.Generic.List[PSCustomObject]]::new()
$diskFailingCount = 0

try {
    $pDisks = Get-PhysicalDisk
    foreach ($pd in $pDisks) {
        $sizeGB = [math]::Round(($pd.Size / 1GB), 1)
        $mType = if ($pd.MediaType) { $pd.MediaType } else { "SSD/HDD" }
        $bus = if ($pd.BusType) { $pd.BusType } else { "Internal" }
        $health = $pd.HealthStatus
        $op = ($pd.OperationalStatus -join ", ")

        $isDiskBad = ($health -ne 'Healthy' -and $health -ne 'OK')
        if ($isDiskBad) {
            $diskFailingCount++
            $HealthScore -= 25
            $FailingHardwares.Add([PSCustomObject]@{
                Category    = "Storage Disk"
                DeviceName  = "$($pd.FriendlyName) ($mType, $sizeGB GB)"
                ErrorCode   = $health
                Description = "Physical disk health failure reported: $health ($op)"
                Severity    = "CRITICAL"
            })
        }

        $PhysicalDisks.Add([PSCustomObject]@{
            FriendlyName = $pd.FriendlyName
            MediaType    = $mType
            BusType      = $bus
            SizeGB       = $sizeGB
            HealthStatus = $health
            Operational  = $op
        })
    }
} catch {
    $dDrives = Get-CimInstance Win32_DiskDrive
    foreach ($dd in $dDrives) {
        $sizeGB = [math]::Round(($dd.Size / 1GB), 1)
        $stat = $dd.Status
        $isDiskBad = ($stat -ne 'OK')
        if ($isDiskBad) {
            $diskFailingCount++
            $HealthScore -= 20
            $FailingHardwares.Add([PSCustomObject]@{
                Category    = "Storage Disk"
                DeviceName  = "$($dd.Model) ($sizeGB GB)"
                ErrorCode   = $stat
                Description = "Physical drive reported hardware status: $stat"
                Severity    = "CRITICAL"
            })
        }
        $PhysicalDisks.Add([PSCustomObject]@{
            FriendlyName = $dd.Model
            MediaType    = "Disk Drive"
            BusType      = $dd.InterfaceType
            SizeGB       = $sizeGB
            HealthStatus = $stat
            Operational  = $stat
        })
    }
}

# Logical Partitions
$Partitions = [System.Collections.Generic.List[PSCustomObject]]::new()
$lowSpaceCount = 0
$logicalDrives = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"

foreach ($ld in $logicalDrives) {
    $tot = [math]::Round(($ld.Size / 1GB), 1)
    $fre = [math]::Round(($ld.FreeSpace / 1GB), 1)
    $usd = [math]::Round(($tot - $fre), 1)
    $freePct = if ($tot -gt 0) { [math]::Round((($fre / $tot) * 100), 1) } else { 0 }
    
    $cond = "Good"
    if ($freePct -lt 10) {
        $cond = "Critical Low"
        $lowSpaceCount++
        $HealthScore -= 15
        $Warnings.Add("Drive $($ld.DeviceID) has critically low free space: $freePct% ($fre GB free).")
    } elseif ($freePct -lt 20) {
        $cond = "Warning Low"
        $HealthScore -= 5
        $Warnings.Add("Drive $($ld.DeviceID) is running low: $freePct% remaining ($fre GB free).")
    }

    $Partitions.Add([PSCustomObject]@{
        DriveLetter = $ld.DeviceID
        VolumeName  = if ($ld.VolumeName) { $ld.VolumeName } else { "Local Disk" }
        FileSystem  = $ld.FileSystem
        TotalGB     = $tot
        UsedGB      = $usd
        FreeGB      = $fre
        FreePercent = $freePct
        Condition   = $cond
    })
}

$storageHealth = "PASS"
$storageMsg = "All $($PhysicalDisks.Count) Disks Healthy"
if ($diskFailingCount -gt 0) {
    $storageHealth = "FAIL"
    $storageMsg = "$diskFailingCount Physical Disk(s) Failing!"
} elseif ($lowSpaceCount -gt 0) {
    $storageHealth = "WARN"
    $storageMsg = "$lowSpaceCount Partition(s) Low Free Space"
}

$Checklist.Add([PSCustomObject]@{
    Component = "Storage (SSD/HDD)"
    Icon      = "&#128190;"
    Summary   = "$($PhysicalDisks.Count) Physical Drive(s) Detected"
    Status    = $storageHealth
    Detail    = $storageMsg
})

# ---------------------------------------------------------
# 5. Graphics / Video Cards (GPU) & Displays
# ---------------------------------------------------------
Write-Host "[5/10] Detecting Video Controllers (GPU) & Displays..." -ForegroundColor Cyan
$GpuList = [System.Collections.Generic.List[PSCustomObject]]::new()
$gpuCim = Get-CimInstance Win32_VideoController
$gpuWorkingCount = 0

foreach ($g in $gpuCim) {
    $vramMB = if ($g.AdapterRAM -and $g.AdapterRAM -gt 0) {
        $mb = [math]::Round(($g.AdapterRAM / 1MB), 0)
        if ($mb -ge 1024) { "$([math]::Round(($mb / 1024), 1)) GB" } else { "$mb MB" }
    } else { "Dynamic / Shared" }
    
    $res = if ($g.VideoModeDescription) { $g.VideoModeDescription } else { "Connected" }
    $dVer = if ($g.DriverVersion) { $g.DriverVersion } else { "N/A" }
    $stat = if ($g.Status) { $g.Status } else { "OK" }

    if ($stat -eq "OK") { $gpuWorkingCount++ }

    $GpuList.Add([PSCustomObject]@{
        Name          = $g.Name.Trim()
        VRAM          = $vramMB
        DriverVersion = $dVer
        Resolution    = $res
        Status        = $stat
    })
}

$gpuHealth = if ($gpuWorkingCount -gt 0) { "PASS" } else { "WARN" }
$Checklist.Add([PSCustomObject]@{
    Component = "Graphics (GPU)"
    Icon      = "&#127918;"
    Summary   = ($GpuList | Select-Object -ExpandProperty Name) -join " + "
    Status    = $gpuHealth
    Detail    = "$gpuWorkingCount Active Display Adapter(s)"
})

# ---------------------------------------------------------
# 6. Battery Health & Capacity (Laptop vs Desktop)
# ---------------------------------------------------------
Write-Host "[6/10] Checking Battery condition, capacity & wear..." -ForegroundColor Cyan
$HasBattery = $false
$BatteryStatus = "Not Installed (Desktop PC)"
$BatteryCharge = "N/A"
$DesignCapacity = "N/A"
$FullChargeCap = "N/A"
$BatteryHealthPercent = "N/A"
$BatteryRuntime = "N/A"
$BatteryWearNum = 100
$BatteryCycleCount = "N/A"
$BatteryChemistry = "Li-Ion"
$BatteryManufacturer = "N/A"
$BatteryReportGenerated = $false

$batteries = Get-CimInstance Win32_Battery
$isLaptop = ($batteries -or ($SystemType -match "Laptop|Notebook|Portable"))

if ($isLaptop) {
    $HasBattery = $true
    if ($batteries) {
        $b = $batteries | Select-Object -First 1
        $BatteryStatus = switch ($b.BatteryStatus) {
            1 { "Discharging" }
            2 { "AC Connected (Unknown)" }
            3 { "Fully Charged" }
            4 { "Low Battery" }
            5 { "Critical Battery" }
            6 { "Charging" }
            7 { "Charging & High" }
            8 { "Charging & Low" }
            9 { "Charging & Critical" }
            default { "Normal / AC Connected" }
        }
        $BatteryCharge = "$($b.EstimatedChargeRemaining)%"
        $BatteryRuntime = if ($b.EstimatedRunTime -and $b.EstimatedRunTime -lt 71582788) { "$($b.EstimatedRunTime) mins" } else { "AC Connected" }
    } else {
        $BatteryStatus = "Battery Installed (AC Connected)"
        $BatteryCharge = "100%"
    }

    $designVal = $null
    $fullVal = $null

    # Method 1: Official Windows Battery Diagnostic Report (HTML) via powercfg
    try {
        Write-Host "    -> Generating official Windows Battery Report ($BatReportFileName)..." -ForegroundColor DarkGray
        $pinfo = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo.FileName = "powercfg.exe"
        $pinfo.Arguments = "/batteryreport /output `"$BatReportPath`""
        $pinfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $pinfo.CreateNoWindow = $true
        $pinfo.UseShellExecute = $false
        $proc = [System.Diagnostics.Process]::Start($pinfo)
        if ($proc.WaitForExit(15000)) {
            if (Test-Path $BatReportPath) {
                $BatteryReportGenerated = $true
                Write-Host "    -> Battery Report saved: $BatReportFileName" -ForegroundColor DarkGreen
            }
        }
    } catch {}

    # Method 2: Extract structured battery metrics from XML
    try {
        $xmlTemp = [System.IO.Path]::Combine($env:TEMP, "bat_diag_$([System.IO.Path]::GetRandomFileName()).xml")
        $pinfo2 = New-Object System.Diagnostics.ProcessStartInfo
        $pinfo2.FileName = "powercfg.exe"
        $pinfo2.Arguments = "/batteryreport /xml /output `"$xmlTemp`""
        $pinfo2.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
        $pinfo2.CreateNoWindow = $true
        $pinfo2.UseShellExecute = $false
        $proc2 = [System.Diagnostics.Process]::Start($pinfo2)
        if ($proc2.WaitForExit(10000)) {
            if (Test-Path $xmlTemp) {
                [xml]$batXml = [System.IO.File]::ReadAllText($xmlTemp)
                $batNode = $batXml.BatteryReport.Batteries.Battery | Select-Object -First 1
                if ($batNode) {
                    if ($batNode.DesignCapacity -and [double]$batNode.DesignCapacity -gt 0) {
                        $designVal = [double]$batNode.DesignCapacity
                    }
                    if ($batNode.FullChargeCapacity -and [double]$batNode.FullChargeCapacity -gt 0) {
                        $fullVal = [double]$batNode.FullChargeCapacity
                    }
                    if ($batNode.CycleCount -and "$($batNode.CycleCount)" -ne "" -and "$($batNode.CycleCount)" -ne "0") {
                        $BatteryCycleCount = "$($batNode.CycleCount)"
                    }
                    if ($batNode.Chemistry) { $BatteryChemistry = "$($batNode.Chemistry)" }
                    if ($batNode.Manufacturer) { $BatteryManufacturer = "$($batNode.Manufacturer)" }
                }
                Remove-Item -Path $xmlTemp -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {}

    # Method 3: Parse HTML report directly with regex if XML did not give capacities
    if ((-not $designVal -or -not $fullVal -or $BatteryCycleCount -eq "N/A") -and (Test-Path $BatReportPath)) {
        try {
            $batHtmlContent = [System.IO.File]::ReadAllText($BatReportPath)
            if (-not $designVal -and $batHtmlContent -match 'DESIGN CAPACITY\s*<\/td>\s*<td[^>]*>\s*([\d,]+)\s*mWh') {
                $designVal = [double]($matches[1] -replace ',', '')
            }
            if (-not $fullVal -and $batHtmlContent -match 'FULL CHARGE CAPACITY\s*<\/td>\s*<td[^>]*>\s*([\d,]+)\s*mWh') {
                $fullVal = [double]($matches[1] -replace ',', '')
            }
            if ($BatteryCycleCount -eq "N/A" -and $batHtmlContent -match 'CYCLE COUNT\s*<\/td>\s*<td[^>]*>\s*(\d+)') {
                $BatteryCycleCount = $matches[1]
            }
            if ($BatteryChemistry -eq "Li-Ion" -and $batHtmlContent -match 'CHEMISTRY\s*<\/td>\s*<td[^>]*>\s*([^<]+)<\/td>') {
                $BatteryChemistry = $matches[1].Trim()
            }
        } catch {}
    }

    # Method 4: Fallback to Root/WMI BatteryStaticData and BatteryFullChargedCapacity
    if (-not $designVal -or -not $fullVal) {
        try {
            $staticData = Get-CimInstance -Namespace root/wmi -ClassName BatteryStaticData -ErrorAction Stop | Select-Object -First 1
            $fullData = Get-CimInstance -Namespace root/wmi -ClassName BatteryFullChargedCapacity -ErrorAction Stop | Select-Object -First 1
            if ($staticData -and $fullData) {
                if (-not $designVal) { $designVal = [double]$staticData.DesignedCapacity }
                if (-not $fullVal) { $fullVal = [double]$fullData.FullChargedCapacity }
            }
        } catch {}
    }

    # Method 5: Root/WMI BatteryCycleCount
    if ($BatteryCycleCount -eq "N/A") {
        try {
            $cyc = Get-CimInstance -Namespace root/wmi -ClassName BatteryCycleCount -ErrorAction Stop | Select-Object -First 1
            if ($cyc -and $cyc.CycleCount -ne $null) {
                $BatteryCycleCount = "$($cyc.CycleCount)"
            }
        } catch {}
    }

    if ($designVal -and $fullVal -and $designVal -gt 0) {
        $calcHealth = [math]::Round((($fullVal / $designVal) * 100), 1)
        if ($calcHealth -gt 100) { $calcHealth = 100 }
        $BatteryWearNum = $calcHealth
        $BatteryHealthPercent = "$calcHealth%"
        $DesignCapacity = "$([math]::Round($designVal)) mWh"
        $FullChargeCap = "$([math]::Round($fullVal)) mWh"

        if ($calcHealth -lt 50) {
            $HealthScore -= 15
            $FailingHardwares.Add([PSCustomObject]@{
                Category    = "Battery"
                DeviceName  = "Laptop Battery"
                ErrorCode   = "Severe Wear ($calcHealth%)"
                Description = "Battery health degraded to $calcHealth% (Design: $DesignCapacity, Full: $FullChargeCap, Cycles: $BatteryCycleCount). Battery replacement recommended."
                Severity    = "CRITICAL"
            })
        } elseif ($calcHealth -lt 70) {
            $HealthScore -= 8
            $Warnings.Add("Battery health degraded to $calcHealth% ($FullChargeCap remaining of $DesignCapacity, Cycles: $BatteryCycleCount).")
        }
    } else {
        $BatteryHealthPercent = "Good (100%)"
        $BatteryWearNum = 100
    }

    $batHealth = "PASS"
    $batMsg = "Wear Health: $BatteryHealthPercent ($BatteryStatus)"
    if ($BatteryWearNum -lt 50) {
        $batHealth = "FAIL"
        $batMsg = "Degraded / Failing ($BatteryHealthPercent)"
    } elseif ($BatteryWearNum -lt 70) {
        $batHealth = "WARN"
        $batMsg = "Degraded ($BatteryHealthPercent)"
    }

    $Checklist.Add([PSCustomObject]@{
        Component = "Battery (Laptop)"
        Icon      = "&#128267;"
        Summary   = "Health: $BatteryHealthPercent | Cycles: $BatteryCycleCount | Charge: $BatteryCharge"
        Status    = $batHealth
        Detail    = "$batMsg (Design: $DesignCapacity, Full: $FullChargeCap)"
    })
} else {
    $Checklist.Add([PSCustomObject]@{
        Component = "Battery"
        Icon      = "&#128267;"
        Summary   = "Desktop PC (Direct AC Power)"
        Status    = "PASS"
        Detail    = "No Battery Required"
    })
}

# ---------------------------------------------------------
# 7. Audio & Sound Devices
# ---------------------------------------------------------
Write-Host "[7/10] Checking Audio output & sound controllers..." -ForegroundColor Cyan
$AudioDevices = [System.Collections.Generic.List[PSCustomObject]]::new()
$soundCim = Get-CimInstance Win32_SoundDevice
$audioWorking = 0

foreach ($s in $soundCim) {
    if ($s.Status -eq "OK") { $audioWorking++ }
    $AudioDevices.Add([PSCustomObject]@{
        Name   = $s.Name.Trim()
        Status = $s.Status
    })
}

$audioHealth = "PASS"
$audioMsg = "$audioWorking Sound Device(s) Active"
if ($audioWorking -eq 0) {
    $audioHealth = "FAIL"
    $audioMsg = "No Working Sound Device Found!"
    $HealthScore -= 10
    $FailingHardwares.Add([PSCustomObject]@{
        Category    = "Audio"
        DeviceName  = "Audio Controller"
        ErrorCode   = "No Audio Devices"
        Description = "No working sound output or audio device detected."
        Severity    = "CRITICAL"
    })
}

$Checklist.Add([PSCustomObject]@{
    Component = "Audio / Sound"
    Icon      = "&#128266;"
    Summary   = ($AudioDevices | Select-Object -ExpandProperty Name -Unique) -join ", "
    Status    = $audioHealth
    Detail    = $audioMsg
})

# ---------------------------------------------------------
# 8. Network Adapters, Wi-Fi & Bluetooth
# ---------------------------------------------------------
Write-Host "[8/10] Inspecting Wi-Fi, Ethernet & Bluetooth adapters..." -ForegroundColor Cyan
$NetAdaptersList = [System.Collections.Generic.List[PSCustomObject]]::new()
$allNet = Get-NetAdapter -ErrorAction SilentlyContinue

$hasEthernet = $false
$hasWifi = $false
$hasBluetooth = $false

foreach ($na in $allNet) {
    $desc = $na.InterfaceDescription
    $stat = $na.Status
    $speed = if ($na.LinkSpeed) { $na.LinkSpeed } else { "N/A" }
    
    $type = "Other"
    if ($na.PhysicalMediaType -match "802.3" -or $desc -match "Ethernet|GbE|LAN|Realtek PCIe|Intel.*Ethernet") {
        $type = "Ethernet (LAN)"
        $hasEthernet = $true
    } elseif ($na.PhysicalMediaType -match "Wireless|Native802.11" -or $desc -match "Wi-Fi|Wireless|802.11|WLAN") {
        $type = "Wi-Fi (Wireless)"
        $hasWifi = $true
    } elseif ($na.PhysicalMediaType -match "BlueTooth" -or $desc -match "Bluetooth") {
        $type = "Bluetooth PAN"
        $hasBluetooth = $true
    }

    $NetAdaptersList.Add([PSCustomObject]@{
        Name        = $na.Name
        Description = $desc
        Type        = $type
        Status      = $stat
        LinkSpeed   = $speed
    })
}

# Dedicated Bluetooth hardware PnP check
$btPnp = Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -eq 'Bluetooth' -and $_.ConfigManagerErrorCode -eq 0 } | Select-Object -First 1
if ($btPnp) { $hasBluetooth = $true }

# Internet connectivity check
$InternetStatus = "Offline / No Connection"
try {
    $ping = Test-Connection -ComputerName 8.8.8.8 -Count 1 -Quiet -TimeoutSeconds 2
    if ($ping) {
        $InternetStatus = "Connected (Online)"
    } else {
        $pingDns = Test-Connection -ComputerName 1.1.1.1 -Count 1 -Quiet -TimeoutSeconds 2
        if ($pingDns) { $InternetStatus = "Connected (Online)" }
    }
} catch {}

# Network Checklist
$netHealth = if ($InternetStatus -like "*Online*") { "PASS" } else { "WARN" }
$Checklist.Add([PSCustomObject]@{
    Component = "Network (LAN / Wi-Fi)"
    Icon      = "&#127760;"
    Summary   = "LAN: $(if ($hasEthernet) { 'Present' } else { 'None' }) | Wi-Fi: $(if ($hasWifi) { 'Present' } else { 'None' })"
    Status    = $netHealth
    Detail    = "Internet: $InternetStatus"
})

# Bluetooth Checklist
$btHealth = if ($hasBluetooth) { "PASS" } else { "INFO" }
$Checklist.Add([PSCustomObject]@{
    Component = "Bluetooth"
    Icon      = "&#128246;"
    Summary   = if ($btPnp) { $btPnp.Name } else { if ($hasBluetooth) { "Bluetooth Supported" } else { "No Bluetooth Hardware Detected" } }
    Status    = $btHealth
    Detail    = if ($hasBluetooth) { "Working / Ready" } else { "Not Installed" }
})

# ---------------------------------------------------------
# 9. Camera / Webcam & Input Devices
# ---------------------------------------------------------
Write-Host "[9/10] Checking Webcam & Input Devices..." -ForegroundColor Cyan
$camPnp = Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in @('Camera', 'Image') }
$hasCam = ($camPnp | Measure-Object).Count -gt 0
$camName = if ($hasCam) { ($camPnp | Select-Object -First 1).Name } else { "No Integrated Webcam Detected" }

$camHealth = if ($hasCam) { "PASS" } else { "INFO" }
$Checklist.Add([PSCustomObject]@{
    Component = "Camera / Webcam"
    Icon      = "&#128247;"
    Summary   = $camName
    Status    = $camHealth
    Detail    = if ($hasCam) { "Detected & Ready" } else { "Desktop / No Webcam" }
})

# ---------------------------------------------------------
# 10. Device Manager Fault Detection (What is NOT Working!)
# ---------------------------------------------------------
Write-Host "[10/10] Scanning Device Manager for Broken / Non-working Hardware..." -ForegroundColor Cyan
$problemDevs = Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 -and $_.ConfigManagerErrorCode -ne $null }

foreach ($pd in $problemDevs) {
    $errCode = $pd.ConfigManagerErrorCode
    $errDesc = switch ($errCode) {
        1  { "Device not configured correctly (Code 1)" }
        10 { "Device cannot start - Driver or Hardware Fault (Code 10)" }
        14 { "Computer restart required to use device (Code 14)" }
        22 { "Device manually disabled by user/system (Code 22)" }
        28 { "Drivers for this device are missing/not installed (Code 28)" }
        31 { "Device not working properly - Windows cannot load driver (Code 31)" }
        43 { "Device stopped because it reported problems - Possible Hardware Fault (Code 43)" }
        default { "Device Error Code $errCode" }
    }

    $cat = if ($pd.PNPClass) { $pd.PNPClass } else { "Hardware Component" }
    $sev = if ($errCode -eq 22) { "WARNING" } else { "CRITICAL" }

    if ($errCode -ne 22) {
        $HealthScore -= 10
    } else {
        $HealthScore -= 2
    }

    $FailingHardwares.Add([PSCustomObject]@{
        Category    = $cat
        DeviceName  = $pd.Name
        ErrorCode   = "Code $errCode"
        Description = $errDesc
        Severity    = $sev
    })
}

# ---------------------------------------------------------
# Health Score & Verdict Calculation
# ---------------------------------------------------------
if ($HealthScore -lt 0) { $HealthScore = 0 }
if ($HealthScore -gt 100) { $HealthScore = 100 }

$Verdict = "EXCELLENT - ALL HARDWARE HEALTHY"
$VerdictBadgeClass = "badge-healthy"
$VerdictColor = "#10b981"

if ($FailingHardwares.Count -gt 0 -or $HealthScore -lt 65) {
    $Verdict = "HARDWARE ATTENTION REQUIRED"
    $VerdictBadgeClass = "badge-critical"
    $VerdictColor = "#ef4444"
} elseif ($Warnings.Count -gt 0 -or $HealthScore -lt 85) {
    $Verdict = "MINOR WARNINGS / UPGRADES RECOMMENDED"
    $VerdictBadgeClass = "badge-warning"
    $VerdictColor = "#f59e0b"
}

# ---------------------------------------------------------
# Assemble Modern HTML Report
# ---------------------------------------------------------
$lines = [System.Collections.Generic.List[string]]::new()

$lines.Add('<!DOCTYPE html>')
$lines.Add('<html lang="en">')
$lines.Add('<head>')
$lines.Add('    <meta charset="UTF-8">')
$lines.Add('    <meta name="viewport" content="width=device-width, initial-scale=1.0">')
$lines.Add("    <title>Hardware Health & Specs - $DeviceName</title>")
$lines.Add('    <style>')
$lines.Add('        :root {')
$lines.Add('            --bg: #0b1329;')
$lines.Add('            --surface: #152238;')
$lines.Add('            --surface-card: #1c2e4a;')
$lines.Add('            --border: #2a3f63;')
$lines.Add('            --text: #f1f5f9;')
$lines.Add('            --text-muted: #94a3b8;')
$lines.Add('            --accent: #38bdf8;')
$lines.Add('            --green: #10b981;')
$lines.Add('            --amber: #f59e0b;')
$lines.Add('            --red: #ef4444;')
$lines.Add("            --font: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;")
$lines.Add('        }')
$lines.Add('        * { box-sizing: border-box; margin: 0; padding: 0; }')
$lines.Add('        body { background-color: var(--bg); color: var(--text); font-family: var(--font); line-height: 1.5; padding: 24px; }')
$lines.Add('        .container { max-width: 1200px; margin: 0 auto; }')
$lines.Add('        header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px; padding-bottom: 20px; border-bottom: 1px solid var(--border); margin-bottom: 24px; }')
$lines.Add('        .header-title h1 { font-size: 1.8rem; font-weight: 700; display: flex; align-items: center; gap: 10px; }')
$lines.Add('        .header-title p { color: var(--text-muted); font-size: 0.9rem; margin-top: 4px; }')
$lines.Add('        .btn { background: var(--surface-card); border: 1px solid var(--border); color: var(--text); padding: 9px 18px; border-radius: 6px; font-size: 0.88rem; font-weight: 600; cursor: pointer; transition: all 0.2s ease; }')
$lines.Add('        .btn:hover { background: var(--accent); color: #0b1329; border-color: var(--accent); }')

$lines.Add('        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }')
$lines.Add('        .kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 18px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.25); }')
$lines.Add('        .kpi-title { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 8px; }')
$lines.Add('        .kpi-value { font-size: 1.55rem; font-weight: 700; color: var(--text); }')
$lines.Add('        .kpi-sub { font-size: 0.8rem; color: var(--text-muted); margin-top: 6px; }')

$lines.Add('        .score-hero { grid-column: span 2; background: linear-gradient(135deg, #152238 0%, #1e3a5f 100%); border-color: #3b82f6; display: flex; align-items: center; justify-content: space-between; }')
$lines.Add('        @media (max-width: 768px) { .score-hero { grid-column: span 1; } }')
$lines.Add("        .score-number { font-size: 3rem; font-weight: 800; color: $VerdictColor; line-height: 1; }")
$lines.Add('        .score-badge { display: inline-block; padding: 4px 12px; border-radius: 9999px; font-size: 0.82rem; font-weight: 600; margin-top: 8px; }')
$lines.Add('        .badge-healthy { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }')
$lines.Add('        .badge-warning { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }')
$lines.Add('        .badge-critical { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #ef4444; }')

$lines.Add('        .alert-box { border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; border-left: 5px solid; font-size: 0.92rem; }')
$lines.Add('        .alert-failing { background: rgba(239, 68, 68, 0.15); border-color: var(--red); color: #fecaca; }')
$lines.Add('        .alert-failing strong { color: #f87171; font-size: 1.05rem; }')
$lines.Add('        .alert-healthy { background: rgba(16, 185, 129, 0.12); border-color: var(--green); color: #a7f3d0; }')
$lines.Add('        .alert-warnings { background: rgba(245, 158, 11, 0.12); border-color: var(--amber); color: #fde68a; }')
$lines.Add('        .alert-box ul { margin-left: 24px; margin-top: 8px; }')

$lines.Add('        .section-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 24px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2); }')
$lines.Add('        .section-header { padding: 14px 20px; background: var(--surface-card); border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }')
$lines.Add('        .section-header h2 { font-size: 1.05rem; font-weight: 600; color: var(--accent); display: flex; align-items: center; gap: 8px; }')
$lines.Add('        .section-body { padding: 20px; }')

$lines.Add('        .details-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px 24px; }')
$lines.Add('        .detail-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.9rem; }')
$lines.Add('        .detail-label { color: var(--text-muted); }')
$lines.Add('        .detail-value { font-weight: 500; color: var(--text); text-align: right; max-width: 65%; word-break: break-word; }')

$lines.Add('        table { width: 100%; border-collapse: collapse; font-size: 0.88rem; text-align: left; }')
$lines.Add('        th { background: rgba(0, 0, 0, 0.25); color: var(--text-muted); padding: 10px 12px; font-weight: 600; border-bottom: 1px solid var(--border); }')
$lines.Add('        td { padding: 10px 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.05); }')
$lines.Add('        tr:hover td { background: rgba(255, 255, 255, 0.02); }')

$lines.Add('        .status-badge { display: inline-block; padding: 3px 9px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; }')
$lines.Add('        .status-pass { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #10b981; }')
$lines.Add('        .status-warn { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid #f59e0b; }')
$lines.Add('        .status-fail { background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid #ef4444; }')
$lines.Add('        .status-info { background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid #0284c7; }')

$lines.Add('        .progress-bar-bg { background: rgba(255, 255, 255, 0.1); border-radius: 9999px; height: 8px; overflow: hidden; width: 100%; margin-top: 6px; }')
$lines.Add('        .progress-bar-fill { height: 100%; border-radius: 9999px; }')
$lines.Add('        footer { margin-top: 36px; padding-top: 18px; border-top: 1px solid var(--border); text-align: center; font-size: 0.82rem; color: var(--text-muted); }')
$lines.Add('        @media print { body { background: #fff !important; color: #000 !important; } .section-card, .kpi-card { background: #fff !important; color: #000 !important; border: 1px solid #ccc !important; box-shadow: none !important; } .detail-label, .kpi-title, .kpi-sub, th { color: #555 !important; } .detail-value, .kpi-value, .header-title h1 { color: #000 !important; } .btn { display: none !important; } }')
$lines.Add('    </style>')
$lines.Add('</head>')
$lines.Add('<body>')
$lines.Add('<div class="container">')

# Header
$adminLabel = if ($IsAdmin) { 'Yes' } else { 'No' }
$lines.Add('    <header>')
$lines.Add('        <div class="header-title">')
$lines.Add("            <h1>&#128187; $DeviceName &bull; Hardware Health & Diagnostic Report</h1>")
$lines.Add("            <p>System Type: $SystemType | Generated: $ReportDateFormatted | User: $CurrentUserName | Admin Rights: $adminLabel</p>")
$lines.Add('        </div>')
$lines.Add('        <div>')
$lines.Add('            <button class="btn" onclick="window.print()">&#128424; Print / Save PDF</button>')
$lines.Add('        </div>')
$lines.Add('    </header>')

# Top KPIs
$cpuBarColor = if ($CpuLoad -gt 85) { "var(--red)" } elseif ($CpuLoad -gt 60) { "var(--amber)" } else { "var(--green)" }
$ramBarColor = if ($RamUsagePercent -gt 85) { "var(--red)" } elseif ($RamUsagePercent -gt 70) { "var(--amber)" } else { "var(--green)" }
$gpuSummaryName = if ($GpuList.Count -gt 0) { $GpuList[0].Name } else { "GPU Detected" }

$lines.Add('    <div class="kpi-grid">')
$lines.Add('        <div class="kpi-card score-hero">')
$lines.Add('            <div>')
$lines.Add('                <div class="kpi-title">Overall Hardware Score</div>')
$lines.Add("                <div class=""score-badge $VerdictBadgeClass"">$Verdict</div>")
$lines.Add('                <div class="kpi-sub">Automated component diagnostic test</div>')
$lines.Add('            </div>')
$lines.Add("            <div class=""score-number"">$HealthScore<span style=""font-size: 1.4rem;"">/100</span></div>")
$lines.Add('        </div>')

$lines.Add('        <div class="kpi-card">')
$lines.Add('            <div class="kpi-title">Processor (CPU)</div>')
$lines.Add("            <div class=""kpi-value"">$CpuLoad%</div>")
$lines.Add('            <div class="progress-bar-bg">')
$lines.Add("                <div class=""progress-bar-fill"" style=""width: $CpuLoad%; background: $cpuBarColor;""></div>")
$lines.Add('            </div>')
$lines.Add("            <div class=""kpi-sub"">$CpuCores Cores / $CpuThreads Threads @ $CpuMaxSpeedGHz GHz</div>")
$lines.Add('        </div>')

$lines.Add('        <div class="kpi-card">')
$lines.Add('            <div class="kpi-title">Memory (RAM)</div>')
$lines.Add("            <div class=""kpi-value"">$TotalRamGB GB</div>")
$lines.Add('            <div class="progress-bar-bg">')
$lines.Add("                <div class=""progress-bar-fill"" style=""width: $RamUsagePercent%; background: $ramBarColor;""></div>")
$lines.Add('            </div>')
$lines.Add("            <div class=""kpi-sub"">$UsedRamGB GB Used ($RamUsagePercent%) | $SlotSummary</div>")
$lines.Add('        </div>')

$lines.Add('        <div class="kpi-card">')
$lines.Add('            <div class="kpi-title">Storage (Disks)</div>')
$lines.Add("            <div class=""kpi-value"">$($PhysicalDisks.Count) Drive(s)</div>")
$lines.Add("            <div class=""kpi-sub"" style=""color: $(if ($diskFailingCount -gt 0) { 'var(--red)' } else { 'var(--green)' }); font-weight: 600;"">$storageMsg</div>")
$lines.Add('        </div>')

$lines.Add('        <div class="kpi-card">')
$lines.Add('            <div class="kpi-title">Battery / Power</div>')
$lines.Add("            <div class=""kpi-value"">$(if ($HasBattery) { ""$BatteryHealthPercent"" } else { 'AC Power' })</div>")
$lines.Add("            <div class=""kpi-sub"">$(if ($HasBattery) { ""Charge: $BatteryCharge | Cycles: $BatteryCycleCount ($BatteryStatus)"" } else { 'Desktop PC' })</div>")
$lines.Add('        </div>')

$lines.Add('        <div class="kpi-card">')
$lines.Add('            <div class="kpi-title">Hardware Issues</div>')
$lines.Add("            <div class=""kpi-value"" style=""color: $(if ($FailingHardwares.Count -gt 0) { 'var(--red)' } else { 'var(--green)' });"">$($FailingHardwares.Count) Fault(s)</div>")
$lines.Add("            <div class=""kpi-sub"">$(if ($FailingHardwares.Count -gt 0) { 'Check Defect Table Below' } else { 'All Hardware Operational' })</div>")
$lines.Add('        </div>')
$lines.Add('    </div>')

# ---------------------------------------------------------
# SECTION: FAILING / NOT WORKING HARDWARE (PROMINENT RED BANNER)
# ---------------------------------------------------------
if ($FailingHardwares.Count -gt 0) {
    $lines.Add('    <div class="alert-box alert-failing">')
    $lines.Add("        <strong>&#9888; ATTENTION: $($FailingHardwares.Count) Hardware Component(s) Reported Errors or Are NOT Working!</strong>")
    $lines.Add('        <p style="margin: 6px 0 10px 0; font-size: 0.88rem;">The following physical hardware devices have missing drivers, failed to start, or reported hardware malfunction:</p>')
    $lines.Add('        <table style="background: rgba(0,0,0,0.25); border-radius: 6px; overflow: hidden;">')
    $lines.Add('            <thead><tr><th>Category</th><th>Device Name</th><th>Error / Code</th><th>Diagnostic Problem Detail</th></tr></thead>')
    $lines.Add('            <tbody>')
    foreach ($fh in $FailingHardwares) {
        $lines.Add("                <tr>")
        $lines.Add("                    <td><span class=""status-badge status-fail"">$($fh.Category)</span></td>")
        $lines.Add("                    <td><strong>$($fh.DeviceName)</strong></td>")
        $lines.Add("                    <td><code style=""color: #fca5a5;"">$($fh.ErrorCode)</code></td>")
        $lines.Add("                    <td>$($fh.Description)</td>")
        $lines.Add("                </tr>")
    }
    $lines.Add('            </tbody>')
    $lines.Add('        </table>')
    $lines.Add('    </div>')
} else {
    $lines.Add('    <div class="alert-box alert-healthy">')
    $lines.Add('        <strong>&#9989; 100% Operational:</strong> No hardware failures, missing drivers, or defective components detected. All subsystems are functioning properly.')
    $lines.Add('    </div>')
}

# Warnings Banner if any
if ($Warnings.Count -gt 0) {
    $lines.Add('    <div class="alert-box alert-warnings">')
    $lines.Add("        <strong>&#9889; Performance & Capacity Warnings ($($Warnings.Count)):</strong><ul>")
    foreach ($wrn in $Warnings) {
        $lines.Add("            <li>$wrn</li>")
    }
    $lines.Add('        </ul></div>')
}

# ---------------------------------------------------------
# SECTION 1: HARDWARE OPERATIONAL STATUS CHECKLIST
# ---------------------------------------------------------
$lines.Add('    <div class="section-card">')
$lines.Add('        <div class="section-header"><h2>&#128736; Hardware Operational Status & Diagnostic Checklist</h2><span style="font-size: 0.85rem; color: var(--text-muted);">Quick Pass/Fail Matrix</span></div>')
$lines.Add('        <div class="section-body">')
$lines.Add('            <table>')
$lines.Add('                <thead><tr><th>Subsystem</th><th>Component Summary</th><th>Status</th><th>Diagnostic Detail</th></tr></thead>')
$lines.Add('                <tbody>')

foreach ($chk in $Checklist) {
    $badgeClass = switch ($chk.Status) {
        "PASS" { "status-pass" }
        "WARN" { "status-warn" }
        "FAIL" { "status-fail" }
        default { "status-info" }
    }
    $lines.Add("                <tr>")
    $lines.Add("                    <td><strong>$($chk.Icon) $($chk.Component)</strong></td>")
    $lines.Add("                    <td>$($chk.Summary)</td>")
    $lines.Add("                    <td><span class=""status-badge $badgeClass"">$($chk.Status)</span></td>")
    $lines.Add("                    <td>$($chk.Detail)</td>")
    $lines.Add("                </tr>")
}

$lines.Add('                </tbody>')
$lines.Add('            </table>')
$lines.Add('        </div>')
$lines.Add('    </div>')

# ---------------------------------------------------------
# SECTION 2: FULL HARDWARE SPECIFICATIONS
# ---------------------------------------------------------

# CPU Specs
$lines.Add('    <div class="section-card">')
$lines.Add('        <div class="section-header"><h2>&#9881; Processor (CPU) Specifications</h2></div>')
$lines.Add('        <div class="section-body"><div class="details-grid">')
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Processor Model</span><span class=""detail-value"" style=""font-weight: 700; color: var(--accent);"">$CpuName</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Physical Cores</span><span class=""detail-value"">$CpuCores Cores</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Logical Processors (Threads)</span><span class=""detail-value"">$CpuThreads Threads</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Base / Max Frequency</span><span class=""detail-value"">$CpuMaxSpeedGHz GHz</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">L3 Cache Memory</span><span class=""detail-value"">$CpuL3CacheMB MB</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Socket Designation</span><span class=""detail-value"">$CpuSocket</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Architecture</span><span class=""detail-value"">$OSArch</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Current Load</span><span class=""detail-value"">$CpuLoad%</span></div>")
$lines.Add('        </div></div>')
$lines.Add('    </div>')

# RAM Specs & Modules
$lines.Add('    <div class="section-card">')
$lines.Add("        <div class=""section-header""><h2>&#129504; Memory (RAM) Specifications & Slot Details</h2><span style=""font-size: 0.85rem; color: var(--text-muted);"">$SlotSummary</span></div>")
$lines.Add('        <div class="section-body">')
$lines.Add('            <div class="details-grid" style="margin-bottom: 20px;">')
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Total Installed RAM</span><span class=""detail-value"" style=""font-weight: 700; color: var(--accent);"">$TotalRamGB GB</span></div>")
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Motherboard RAM Slots</span><span class=""detail-value"">$TotalRamSlots Total ($PopulatedSlots in use, $([math]::Max(0, $TotalRamSlots - $PopulatedSlots)) free for upgrade)</span></div>")
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Memory Clock Speed</span><span class=""detail-value"">$RamSpeedSummary</span></div>")
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Current Memory Usage</span><span class=""detail-value"">$UsedRamGB GB / $TotalRamGB GB ($RamUsagePercent%)</span></div>")
$lines.Add('            </div>')
$lines.Add('            <h3 style="font-size: 0.95rem; margin-bottom: 10px; color: var(--text-muted);">Installed RAM Modules</h3>')
$lines.Add('            <table>')
$lines.Add('                <thead><tr><th>Slot Locator</th><th>Capacity</th><th>Speed</th><th>Manufacturer</th><th>Part Number</th></tr></thead>')
$lines.Add('                <tbody>')
foreach ($rm in $RamModulesList) {
    $lines.Add("                    <tr><td><strong>$($rm.Slot)</strong></td><td>$($rm.CapacityGB)</td><td>$($rm.Speed)</td><td>$($rm.Manufacturer)</td><td><code>$($rm.PartNumber)</code></td></tr>")
}
$lines.Add('                </tbody>')
$lines.Add('            </table>')
$lines.Add('        </div>')
$lines.Add('    </div>')

# Graphics & Display Specs
$lines.Add('    <div class="section-card">')
$lines.Add('        <div class="section-header"><h2>&#127918; Graphics (GPU) & Video Display Specs</h2></div>')
$lines.Add('        <div class="section-body">')
$lines.Add('            <table>')
$lines.Add('                <thead><tr><th>Graphics Card Name</th><th>VRAM / Memory</th><th>Driver Version</th><th>Display Mode / Resolution</th><th>Status</th></tr></thead>')
$lines.Add('                <tbody>')
foreach ($gp in $GpuList) {
    $lines.Add("                    <tr><td><strong>$($gp.Name)</strong></td><td>$($gp.VRAM)</td><td>$($gp.DriverVersion)</td><td>$($gp.Resolution)</td><td><span class=""status-badge status-pass"">$($gp.Status)</span></td></tr>")
}
$lines.Add('                </tbody>')
$lines.Add('            </table>')
$lines.Add('        </div>')
$lines.Add('    </div>')

# Storage Drives & Partitions Specs
$lines.Add('    <div class="section-card">')
$lines.Add('        <div class="section-header"><h2>&#128190; Storage Disks & Partitions Specifications</h2></div>')
$lines.Add('        <div class="section-body">')
$lines.Add('            <h3 style="font-size: 0.95rem; margin-bottom: 10px; color: var(--text-muted);">Physical Drives (NVMe / SSD / HDD)</h3>')
$lines.Add('            <table>')
$lines.Add('                <thead><tr><th>Drive Model</th><th>Type</th><th>Interface (Bus)</th><th>Capacity</th><th>Health Status</th><th>Operational Status</th></tr></thead>')
$lines.Add('                <tbody>')
foreach ($pd in $PhysicalDisks) {
    $statCol = if ($pd.HealthStatus -eq 'Healthy' -or $pd.HealthStatus -eq 'OK') { 'var(--green)' } else { 'var(--red)' }
    $lines.Add("                    <tr><td><strong>$($pd.FriendlyName)</strong></td><td>$($pd.MediaType)</td><td>$($pd.BusType)</td><td>$($pd.SizeGB) GB</td><td><span style=""color: $statCol; font-weight: 600;"">$($pd.HealthStatus)</span></td><td>$($pd.Operational)</td></tr>")
}
$lines.Add('                </tbody>')
$lines.Add('            </table>')

$lines.Add('            <h3 style="font-size: 0.95rem; margin: 24px 0 10px 0; color: var(--text-muted);">Logical Partitions & Free Space</h3>')
$lines.Add('            <table>')
$lines.Add('                <thead><tr><th>Drive</th><th>Label</th><th>File System</th><th>Total Size</th><th>Used</th><th>Free</th><th>Free %</th><th>Condition</th></tr></thead>')
$lines.Add('                <tbody>')
foreach ($vol in $Partitions) {
    $vCol = if ($vol.FreePercent -lt 10) { 'var(--red)' } elseif ($vol.FreePercent -lt 20) { 'var(--amber)' } else { 'var(--green)' }
    $lines.Add('                    <tr>')
    $lines.Add("                        <td><strong>$($vol.DriveLetter)</strong></td>")
    $lines.Add("                        <td>$($vol.VolumeName)</td>")
    $lines.Add("                        <td>$($vol.FileSystem)</td>")
    $lines.Add("                        <td>$($vol.TotalGB) GB</td>")
    $lines.Add("                        <td>$($vol.UsedGB) GB</td>")
    $lines.Add("                        <td>$($vol.FreeGB) GB</td>")
    $lines.Add("                        <td><div style=""display: flex; align-items: center; gap: 8px;""><span>$($vol.FreePercent)%</span><div class=""progress-bar-bg"" style=""width: 80px; margin: 0;""><div class=""progress-bar-fill"" style=""width: $($vol.FreePercent)%; background: $vCol;""></div></div></div></td>")
    $lines.Add("                        <td><span style=""color: $vCol; font-weight: 600;"">$($vol.Condition)</span></td>")
    $lines.Add('                    </tr>')
}
$lines.Add('                </tbody>')
$lines.Add('            </table>')
$lines.Add('        </div>')
$lines.Add('    </div>')

# Battery Specs (if laptop)
if ($HasBattery) {
    $batWearColor = if ($BatteryWearNum -lt 60) { 'var(--red)' } elseif ($BatteryWearNum -lt 80) { 'var(--amber)' } else { 'var(--green)' }
    $lines.Add('    <div class="section-card">')
    $lines.Add('        <div class="section-header" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">')
    $lines.Add('            <h2>&#128267; Battery Specifications & Wear Diagnostics</h2>')
    if ($BatteryReportGenerated -or (Test-Path $BatReportPath)) {
        $lines.Add("            <a href=""$BatReportFileName"" target=""_blank"" style=""display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981; border-radius: 6px; font-weight: 600; font-size: 0.82rem; text-decoration: none;"">&#128267; View Official Battery Report</a>")
    }
    $lines.Add('        </div>')
    $lines.Add('        <div class="section-body">')
    
    # Progress bar for battery health
    $lines.Add('            <div style="background: rgba(255,255,255,0.03); padding: 14px 18px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08); margin-bottom: 16px;">')
    $lines.Add("                <div style=""display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 0.9rem;"">")
    $lines.Add("                    <span><strong>Battery Health (Full vs Design Capacity):</strong></span>")
    $lines.Add("                    <span style=""font-weight: 700; color: $batWearColor;"">$BatteryHealthPercent</span>")
    $lines.Add('                </div>')
    $lines.Add('                <div style="width: 100%; height: 10px; background: rgba(255,255,255,0.1); border-radius: 5px; overflow: hidden;">')
    $lines.Add("                    <div style=""width: $BatteryWearNum%; height: 100%; background: $batWearColor; border-radius: 5px;""></div>")
    $lines.Add('                </div>')
    $lines.Add('            </div>')
    
    $lines.Add('            <div class="details-grid">')
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Power Status</span><span class=""detail-value"">$BatteryStatus</span></div>")
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Current Charge</span><span class=""detail-value"">$BatteryCharge</span></div>")
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Battery Health (Wear)</span><span class=""detail-value"" style=""font-weight: 700; color: $batWearColor;"">$BatteryHealthPercent</span></div>")
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Battery Cycle Count</span><span class=""detail-value"" style=""font-weight: 700; color: var(--accent);"">$BatteryCycleCount Cycles</span></div>")
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Factory Design Capacity</span><span class=""detail-value"">$DesignCapacity</span></div>")
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Current Full Charge Capacity</span><span class=""detail-value"">$FullChargeCap</span></div>")
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Battery Chemistry</span><span class=""detail-value"">$BatteryChemistry</span></div>")
    $lines.Add("                <div class=""detail-row""><span class=""detail-label"">Estimated Runtime</span><span class=""detail-value"">$BatteryRuntime</span></div>")
    $lines.Add('            </div>')

    if ($BatteryReportGenerated -or (Test-Path $BatReportPath)) {
        $lines.Add('            <div style="margin-top: 16px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; justify-content: flex-end;">')
        $lines.Add("                <a href=""$BatReportFileName"" target=""_blank"" style=""display: inline-flex; align-items: center; gap: 8px; padding: 10px 20px; background: linear-gradient(135deg, #10b981, #059669); color: white; border-radius: 6px; font-weight: 600; font-size: 0.88rem; text-decoration: none; box-shadow: 0 4px 12px rgba(16,185,129,0.3);"">&#128267; Open Official Windows Battery Report (Detailed Lifespan & Drainage History)</a>")
        $lines.Add('            </div>')
    }

    $lines.Add('        </div></div>')
    $lines.Add('    </div>')
}

# Network, Audio & Multimedia Specs
$lines.Add('    <div class="section-card">')
$lines.Add('        <div class="section-header"><h2>&#127760; Network, Audio & Multimedia Hardware</h2></div>')
$lines.Add('        <div class="section-body">')
$lines.Add('            <h3 style="font-size: 0.95rem; margin-bottom: 10px; color: var(--text-muted);">Network Adapters</h3>')
$lines.Add('            <table>')
$lines.Add('                <thead><tr><th>Adapter Name</th><th>Hardware Type</th><th>Device Description</th><th>Status</th><th>Link Speed</th></tr></thead>')
$lines.Add('                <tbody>')
foreach ($na in $NetAdaptersList) {
    $sCol = if ($na.Status -eq "Up") { 'status-pass' } else { 'status-warn' }
    $lines.Add("                    <tr><td><strong>$($na.Name)</strong></td><td>$($na.Type)</td><td>$($na.Description)</td><td><span class=""status-badge $sCol"">$($na.Status)</span></td><td>$($na.LinkSpeed)</td></tr>")
}
$lines.Add('                </tbody>')
$lines.Add('            </table>')

$lines.Add('            <h3 style="font-size: 0.95rem; margin: 20px 0 10px 0; color: var(--text-muted);">Audio & Camera Devices</h3>')
$lines.Add('            <div class="details-grid">')
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Sound Controller(s)</span><span class=""detail-value"">$(($AudioDevices | Select-Object -ExpandProperty Name) -join ', ')</span></div>")
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Webcam / Camera</span><span class=""detail-value"">$camName</span></div>")
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Bluetooth Device</span><span class=""detail-value"">$(if ($hasBluetooth) { if ($btPnp) { $btPnp.Name } else { 'Bluetooth Controller Active' } } else { 'Not Detected' })</span></div>")
$lines.Add("                <div class=""detail-row""><span class=""detail-label"">Internet Connection</span><span class=""detail-value"" style=""color: $(if ($InternetStatus -like '*Online*') { 'var(--green)' } else { 'var(--red)' });"">$InternetStatus</span></div>")
$lines.Add('            </div>')
$lines.Add('        </div>')
$lines.Add('    </div>')

# Motherboard, BIOS & Security Specs
$lines.Add('    <div class="section-card">')
$lines.Add('        <div class="section-header"><h2>&#128187; Motherboard, BIOS & System Specifications</h2></div>')
$lines.Add('        <div class="section-body"><div class="details-grid">')
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Client / Company</span><span class=""detail-value"" style=""font-weight: 700; color: #38bdf8;"">$Company</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Device Name</span><span class=""detail-value"" style=""font-weight: 700; color: var(--accent);"">$DeviceName</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Manufacturer & Model</span><span class=""detail-value"">$Manufacturer $Model</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Motherboard Model</span><span class=""detail-value"">$Motherboard</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Serial Number</span><span class=""detail-value"" style=""font-family: monospace;"">$SerialNumber</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">BIOS Version & Date</span><span class=""detail-value"">$BiosVersion ($BiosDate)</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">TPM 2.0 Security Chip</span><span class=""detail-value"">$TpmStatus</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Secure Boot State</span><span class=""detail-value"">$SecureBootStatus</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">Operating System</span><span class=""detail-value"">$OSCaption (Build $OSBuild, $OSArch)</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">OS Installation Date</span><span class=""detail-value"">$InstallDate</span></div>")
$lines.Add("            <div class=""detail-row""><span class=""detail-label"">System Uptime</span><span class=""detail-value"">$Uptime</span></div>")
$lines.Add('        </div></div>')
$lines.Add('    </div>')

# Footer
$lines.Add('    <footer>')
$lines.Add("        <p>Windows Laptop & PC Hardware Health & Specs Report &bull; <strong>$DeviceName</strong> &bull; Generated on $ReportDateFormatted</p>")
$lines.Add("        <p style=""margin-top: 4px; font-size: 0.78rem;"">Click 'Print / Save PDF' or press <strong>Ctrl + P</strong> to save a permanent copy.</p>")
$lines.Add('    </footer>')

$lines.Add('</div>')
$lines.Add('</body>')
$lines.Add('</html>')

# Save HTML File
[System.IO.File]::WriteAllLines($ReportPath, $lines, [System.Text.Encoding]::UTF8)

# Save Structured JSON File for Dashboard Import
$JsonFileName = "HealthReport_${DeviceName}_${FileNameTimestamp}.json"
$JsonPath = [System.IO.Path]::Combine($OutputDir, $JsonFileName)

$ReportJsonObj = [PSCustomObject]@{
    id                   = "${DeviceName}_${FileNameTimestamp}"
    company              = $Company
    deviceName           = $DeviceName
    manufacturer         = $Manufacturer
    model                = $Model
    serialNumber         = $SerialNumber
    systemType           = $SystemType
    os                   = "$OSCaption (Build $OSBuild, $OSArch)"
    cpu                  = "$CpuName ($CpuCores C / $CpuThreads T @ $CpuMaxSpeedGHz GHz)"
    cpuLoad              = $CpuLoad
    ramTotalGB           = $TotalRamGB
    ramUsedGB            = $UsedRamGB
    ramUsagePercent      = $RamUsagePercent
    ramSlots             = $SlotSummary
    ramSpeed             = $RamSpeedSummary
    gpu                  = (($GpuList | Select-Object -ExpandProperty Name) -join " + ")
    disks                = ($PhysicalDisks | ForEach-Object { "$($_.FriendlyName) ($($_.SizeGB) GB $($_.MediaType))" }) -join ", "
    batteryStatus        = $BatteryStatus
    batteryHealthPercent = $BatteryHealthPercent
    batteryCycleCount    = $BatteryCycleCount
    batteryDesignCap     = $DesignCapacity
    batteryFullChargeCap = $FullChargeCap
    batteryCharge        = $BatteryCharge
    hasBattery           = $HasBattery
    healthScore          = $HealthScore
    verdict              = $Verdict
    failingHardwares     = $FailingHardwares
    warnings             = $Warnings
    checklist            = $Checklist
    scannedAt            = $ReportDateFormatted
    reportFileName       = $ReportFileName
}

$ReportJson = $ReportJsonObj | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($JsonPath, $ReportJson, [System.Text.Encoding]::UTF8)

$Duration = [math]::Round(((Get-Date) - $StartTime).TotalSeconds, 1)
Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host " [OK] Hardware Diagnostic Report Generated Successfully!" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host " Device Name    : $DeviceName" -ForegroundColor White
Write-Host " Hardware Score : $HealthScore/100 ($Verdict)" -ForegroundColor $(if ($HealthScore -ge 80) { 'Green' } else { 'Yellow' })
Write-Host " Failing Devices: $($FailingHardwares.Count) detected" -ForegroundColor $(if ($FailingHardwares.Count -eq 0) { 'Green' } else { 'Red' })
Write-Host " Time Taken     : $Duration seconds" -ForegroundColor White
Write-Host " HTML Report    : $ReportPath" -ForegroundColor Cyan
Write-Host " JSON Summary   : $JsonPath" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""

if (-not $NoBrowserOpen) {
    Write-Host "Opening report in your default web browser..." -ForegroundColor Yellow
    Start-Process $ReportPath
}

# =========================================================
# Automatic Project Upload (Direct Sync to Dashboard)
# =========================================================
if ($AutoUpload -and $ServerUrl) {
    Write-Host ""
    Write-Host "[*] Syncing Diagnostic Report to Dashboard ($ServerUrl)..." -ForegroundColor Cyan
    try {
        $complaintsList = @()
        if ($FailingHardwares) {
            foreach ($fh in $FailingHardwares) {
                if ($fh.Device) { $complaintsList += $fh.Device }
            }
        }
        if ($Warnings) {
            foreach ($w in $Warnings) {
                $complaintsList += $w
            }
        }
        if ($complaintsList.Count -eq 0) {
            $complaintsList += "Hardware diagnostic scan completed."
        }

        $BatReportContent = ""
        if ($HasBattery -and (Test-Path $BatReportPath)) {
            try {
                $BatReportContent = [System.IO.File]::ReadAllText($BatReportPath)
            } catch {}
        }

        $UploadPayload = @{
            filename                = $ReportFileName
            raw_content             = $HtmlReport
            battery_report_filename = if ($BatReportContent) { $BatReportFileName } else { "" }
            battery_report_html     = $BatReportContent
            battery_cycle_count     = $BatteryCycleCount
            company_name            = if ($Company) { $Company } else { "UNICOMTIC" }
            customer_name           = if ($CustomerName) { $CustomerName } else { "$CurrentUserName" }
            customer_phone          = $CustomerPhone
            service_status          = "Diagnosing"
            admin_password          = $AdminPassword
            parsed                  = @{
                device_name             = $DeviceName
                model                   = "$Manufacturer $Model"
                serial_number           = $SerialNumber
                cpu                     = "$CpuName"
                ram                     = "$TotalRamGB GB"
                storage                 = ($PhysicalDisks | ForEach-Object { "$($_.FriendlyName) ($($_.SizeGB) GB)" }) -join ", "
                gpu                     = (($GpuList | Select-Object -ExpandProperty Name) -join " + ")
                battery_health          = $BatteryWearNum
                battery_health_text     = $BatteryHealthPercent
                battery_cycle_count     = $BatteryCycleCount
                battery_report_filename = if ($BatReportContent) { $BatReportFileName } else { "" }
                battery_status          = $BatteryStatus
                overall_status          = if ($HealthScore -ge 80) { "Healthy" } elseif ($HealthScore -ge 50) { "Warning" } else { "Critical" }
                complaints              = $complaintsList
            }
        }
        
        $JsonBody = $UploadPayload | ConvertTo-Json -Depth 6
        $ApiUrl = "$ServerUrl/api/reports/upload-import".Replace("//api", "/api")
        
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11 -bor [Net.SecurityProtocolType]::Tls
        } catch {}

        $Response = Invoke-RestMethod -Uri $ApiUrl -Method Post -Body $JsonBody -ContentType "application/json; charset=utf-8" -TimeoutSec 60 -ErrorAction Stop
        
        if ($Response.success) {
            Write-Host "================================================================" -ForegroundColor Green
            Write-Host " [SUCCESS] Report Automatically Added to Project Dashboard! " -ForegroundColor Green
            Write-Host "================================================================" -ForegroundColor Green
            Write-Host " Laptop ID    : $($Response.laptop.id)" -ForegroundColor White
            Write-Host " Company      : $($Response.laptop.company_name)" -ForegroundColor White
            Write-Host " User Name    : $($Response.laptop.customer_name)" -ForegroundColor White
            if ($Response.gdrive -and $Response.gdrive.success) {
                Write-Host " Google Drive : Synced successfully!" -ForegroundColor Green
            }
            Write-Host " Dashboard    : $ServerUrl/Dashboard.html" -ForegroundColor Cyan
            Write-Host "================================================================" -ForegroundColor Green
        } else {
            Write-Host "[-] Upload Notice: $($Response.error)" -ForegroundColor Yellow
        }
    } catch {
        $errMessage = $_.Exception.Message
        try {
            if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
                $jsonErr = $_.ErrorDetails.Message | ConvertFrom-Json
                if ($jsonErr.error) { $errMessage = $jsonErr.error }
            } elseif ($_.Exception.Response) {
                $stream = $_.Exception.Response.GetResponseStream()
                if ($stream) {
                    $reader = [System.IO.StreamReader]::new($stream)
                    $errBody = $reader.ReadToEnd()
                    $jsonErr = $errBody | ConvertFrom-Json
                    if ($jsonErr.error) { $errMessage = $jsonErr.error }
                }
            }
        } catch {}
        Write-Host "[-] Auto-sync notice: $errMessage" -ForegroundColor Yellow
        Write-Host "    (Report file is safely saved locally at $ReportPath)" -ForegroundColor DarkGray
    }
}
