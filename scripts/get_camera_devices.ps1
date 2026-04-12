param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime

function Normalize-DeviceInstanceId {
    param(
        [string]$DeviceId
    )

    if ([string]::IsNullOrWhiteSpace($DeviceId)) {
        return $null
    }

    $normalized = $DeviceId.Trim()
    $normalized = $normalized -replace '^[\\?]+', ''
    $normalized = $normalized -replace '#\{[0-9A-Fa-f\-]+\}\\GLOBAL$', ''
    $normalized = $normalized -replace '#', '\\'
    return $normalized.ToUpperInvariant()
}

function Get-PreferredPnpMatches {
    param(
        [object[]]$Matches
    )

    if (-not $Matches) {
        return @()
    }

    return @(
        $Matches |
            Sort-Object
                @{ Expression = { if ($_.Present) { 0 } else { 1 } } },
                @{ Expression = { if ($_.Status -eq 'OK') { 0 } else { 1 } } },
                @{ Expression = { $_.InstanceId } }
    )
}

$camera = @(Get-PnpDevice -Class Camera -ErrorAction SilentlyContinue)
$image = @(Get-PnpDevice -Class Image -ErrorAction SilentlyContinue)
$pnpDevices = @($camera + $image) | Where-Object { $_.FriendlyName }
$nameCounts = @{}

$deviceClass = [Windows.Devices.Enumeration.DeviceClass, Windows, ContentType=WindowsRuntime]::VideoCapture
$deviceType = [Windows.Devices.Enumeration.DeviceInformation, Windows, ContentType=WindowsRuntime]
$collectionType = [Windows.Devices.Enumeration.DeviceInformationCollection, Windows, ContentType=WindowsRuntime]
$asTaskMethod = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } |
    Select-Object -First 1

$findAllTask = $asTaskMethod.MakeGenericMethod($collectionType).Invoke($null, @($deviceType::FindAllAsync($deviceClass)))
$winRtDevices = @($findAllTask.Result)
$enumerationIndex = 0

$mergedDevices = foreach ($device in $winRtDevices) {
    $friendlyName = $device.Name
    if (-not $nameCounts.ContainsKey($friendlyName)) {
        $nameCounts[$friendlyName] = 0
    }

    $occurrenceIndex = $nameCounts[$friendlyName]
    $nameCounts[$friendlyName] = $occurrenceIndex + 1

    $pnpMatches = @($pnpDevices | Where-Object { $_.FriendlyName -eq $friendlyName })
    $normalizedWinRtId = Normalize-DeviceInstanceId $device.Id
    $matchedPnp = $null

    if ($normalizedWinRtId) {
        $matchedPnp = @(
            $pnpMatches | Where-Object {
                (Normalize-DeviceInstanceId $_.InstanceId) -eq $normalizedWinRtId
            }
        ) | Select-Object -First 1
    }

    $preferredPnpMatches = Get-PreferredPnpMatches $pnpMatches

    if (-not $matchedPnp -and $occurrenceIndex -lt $preferredPnpMatches.Count) {
        $matchedPnp = $preferredPnpMatches[$occurrenceIndex]
    }
    elseif (-not $matchedPnp -and $preferredPnpMatches.Count -gt 0) {
        $matchedPnp = $preferredPnpMatches[0]
    }

    $displayName = $friendlyName
    if ($pnpMatches.Count -gt 1) {
        $displayName = "$friendlyName #$($occurrenceIndex + 1)"
    }

    [PSCustomObject]@{
        EnumerationIndex = $enumerationIndex
        FriendlyName = $friendlyName
        DisplayName = $displayName
        Status = if ($matchedPnp) { $matchedPnp.Status } else { 'Unknown' }
        Class = if ($matchedPnp) { $matchedPnp.Class } else { 'Unknown' }
        DeviceId = $device.Id
        Occurrence = $occurrenceIndex + 1
    }

    $enumerationIndex += 1
}

$mergedDevices | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $OutputPath