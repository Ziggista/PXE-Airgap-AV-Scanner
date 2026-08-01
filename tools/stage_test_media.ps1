[CmdletBinding()]
param(
    [string]$BaseDir = "C:\Users\Ziggi\AV\runtime\test-media",
    [string[]]$FileSystems = @("NTFS", "exFAT", "FAT32"),
    [string]$AttachFileSystem = "NTFS",
    [string]$VmName = "av-pxe-uefi-test-vm",
    [switch]$SkipAttach,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DetectionGenerator = Join-Path $ScriptRoot "generate_detection_corpus.py"
$PythonCommand = if (Test-Path "C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe") {
    "C:\Users\Ziggi\AppData\Local\Python\pythoncore-3.14-64\python.exe"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    "python"
} else {
    throw "Python was not found in PATH and the expected local Python path does not exist."
}

$fileSystemCodes = @{
    "NTFS" = "NTF"
    "EXFAT" = "EXF"
    "FAT32" = "FAT"
    "HFSPLUS" = "HFS"
}

$mediaSets = @(
    @{
        Name = "infected-source"
        SizeBytes = 512MB
        Populate = {
            param([string]$Root)
            & $PythonCommand $DetectionGenerator --output-dir $Root --profile infected-source
            if ($LASTEXITCODE -ne 0) {
                throw "Detection corpus generation failed for $Root"
            }
        }
    }
    @{
        Name = "benign-source"
        SizeBytes = 512MB
        Populate = {
            param([string]$Root)
            $pdfOne = @"
%PDF-1.1
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 18 Tf 36 96 Td (Public PDF sample 01) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000010 00000 n
0000000063 00000 n
0000000122 00000 n
0000000248 00000 n
0000000342 00000 n
trailer
<< /Root 1 0 R /Size 6 >>
startxref
412
%%EOF
"@
            $pdfTwo = $pdfOne -replace "01", "02"
            Set-Content -LiteralPath (Join-Path $Root "public-handout-01.pdf") -Value $pdfOne -Encoding ASCII
            Set-Content -LiteralPath (Join-Path $Root "public-handout-02.pdf") -Value $pdfTwo -Encoding ASCII
            Set-Content -LiteralPath (Join-Path $Root "readme.txt") -Value @(
                "Benign removable-media set for offline AV validation."
                "Contains only simple PDF, TXT, and CSV files."
            ) -Encoding ASCII
            Set-Content -LiteralPath (Join-Path $Root "inventory.csv") -Value @(
                "filename,type"
                "public-handout-01.pdf,pdf"
                "public-handout-02.pdf,pdf"
                "readme.txt,text"
            ) -Encoding ASCII
        }
    }
    @{
        Name = "clean-destination"
        FileSystem = "NTFS"
        SizeBytes = 512MB
        Populate = {
            param([string]$Root)
            Set-Content -LiteralPath (Join-Path $Root "DESTINATION-README.txt") -Value @(
                "Writable destination media for approved copy-out testing."
                "The PXE client should only write to this media after all active engines approve the source."
            ) -Encoding ASCII
        }
    }
)

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path | Out-Null
    }
}

function Get-FileSystemCode {
    param([string]$FileSystem)

    $normalized = $FileSystem.ToUpperInvariant()
    if (-not $fileSystemCodes.ContainsKey($normalized)) {
        throw "No short code mapping exists for filesystem [$FileSystem]"
    }

    return $fileSystemCodes[$normalized]
}

function Get-MediaLabel {
    param(
        [string]$MediaName,
        [string]$SourceFileSystem
    )

    $code = Get-FileSystemCode -FileSystem $SourceFileSystem
    switch ($MediaName) {
        "infected-source" { return "AVB-$code" }
        "benign-source" { return "AVG-$code" }
        "clean-destination" { return "AVD-$code" }
        default { throw "Unsupported media name [$MediaName]" }
    }
}

function Get-VhdName {
    param(
        [string]$MediaName,
        [string]$SourceFileSystem,
        [string]$VolumeFileSystem
    )

    $sourceSlug = $SourceFileSystem.ToLowerInvariant()
    $volumeSlug = $VolumeFileSystem.ToLowerInvariant()

    if ($MediaName -eq "clean-destination") {
        return "clean-destination-$volumeSlug-for-$sourceSlug.vhdx"
    }

    return "$MediaName-$sourceSlug.vhdx"
}

function New-MinimalVolume {
    param(
        [string]$VhdPath,
        [string]$FileSystem,
        [string]$Label,
        [UInt64]$SizeBytes,
        [scriptblock]$Populate,
        [switch]$ForceCreate
    )

    if ((Test-Path -LiteralPath $VhdPath) -and $ForceCreate) {
        Remove-Item -LiteralPath $VhdPath -Force
    }

    if (-not (Test-Path -LiteralPath $VhdPath)) {
        New-VHD -Path $VhdPath -Dynamic -SizeBytes $SizeBytes | Out-Null
    }

    $mounted = $false
    $driveLetter = $null
    try {
        $diskImage = Mount-VHD -Path $VhdPath -Passthru
        $mounted = $true
        $disk = $diskImage | Get-Disk

        if ($disk.PartitionStyle -eq "RAW") {
            Initialize-Disk -Number $disk.Number -PartitionStyle MBR | Out-Null
            $partition = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
            Format-Volume -Partition $partition -FileSystem $FileSystem -NewFileSystemLabel $Label -Confirm:$false | Out-Null
        } else {
            $partition = Get-Partition -DiskNumber $disk.Number | Where-Object DriveLetter | Select-Object -First 1
            if (-not $partition) {
                $partition = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
                Format-Volume -Partition $partition -FileSystem $FileSystem -NewFileSystemLabel $Label -Confirm:$false | Out-Null
            }
        }

        $driveLetter = ($partition | Get-Volume).DriveLetter
        if (-not $driveLetter) {
            throw "No drive letter was assigned for $VhdPath"
        }

        $root = "$driveLetter`:\"
        Get-ChildItem -LiteralPath $root -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        & $Populate $root
    }
    finally {
        if ($mounted) {
            Dismount-VHD -Path $VhdPath
        }
    }
}

function Update-Attachments {
    param(
        [string]$TargetVm,
        [string]$TargetBaseDir,
        [string]$TargetFileSystem
    )

    $existing = Get-VMHardDiskDrive -VMName $TargetVm | Where-Object { $_.Path -like "$TargetBaseDir*" }
    foreach ($disk in $existing) {
        Remove-VMHardDiskDrive -VMHardDiskDrive $disk
    }

    $attachPaths = @(
        (Join-Path (Join-Path $TargetBaseDir $TargetFileSystem.ToLowerInvariant()) (Get-VhdName -MediaName "infected-source" -SourceFileSystem $TargetFileSystem -VolumeFileSystem $TargetFileSystem)),
        (Join-Path (Join-Path $TargetBaseDir $TargetFileSystem.ToLowerInvariant()) (Get-VhdName -MediaName "benign-source" -SourceFileSystem $TargetFileSystem -VolumeFileSystem $TargetFileSystem)),
        (Join-Path (Join-Path $TargetBaseDir $TargetFileSystem.ToLowerInvariant()) (Get-VhdName -MediaName "clean-destination" -SourceFileSystem $TargetFileSystem -VolumeFileSystem "NTFS"))
    )

    foreach ($path in $attachPaths) {
        Add-VMHardDiskDrive -VMName $TargetVm -ControllerType SCSI -Path $path
    }
}

Ensure-Directory -Path $BaseDir

$manifest = @()
foreach ($fileSystem in $FileSystems) {
    $fsDir = Join-Path $BaseDir $fileSystem.ToLowerInvariant()
    Ensure-Directory -Path $fsDir

    foreach ($media in $mediaSets) {
        $volumeFileSystem = if ($media.ContainsKey("FileSystem")) { $media.FileSystem } else { $fileSystem }
        $vhdName = Get-VhdName -MediaName $media.Name -SourceFileSystem $fileSystem -VolumeFileSystem $volumeFileSystem
        $vhdPath = Join-Path $fsDir $vhdName
        $label = Get-MediaLabel -MediaName $media.Name -SourceFileSystem $fileSystem

        New-MinimalVolume `
            -VhdPath $vhdPath `
            -FileSystem $volumeFileSystem `
            -Label $label `
            -SizeBytes $media.SizeBytes `
            -Populate $media.Populate `
            -ForceCreate:$Force

        $manifest += [pscustomobject]@{
            source_filesystem = $fileSystem
            volume_filesystem = $volumeFileSystem
            media_type = $media.Name
            path = $vhdPath
            label = $label
            size_bytes = $media.SizeBytes
        }
    }
}

$manifestPath = Join-Path $BaseDir "manifest.json"
$manifest | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

if (-not $SkipAttach) {
    Update-Attachments -TargetVm $VmName -TargetBaseDir $BaseDir -TargetFileSystem $AttachFileSystem
}

Write-Host "Created test-media VHDX sets under $BaseDir"
Write-Host "Manifest: $manifestPath"
if (-not $SkipAttach) {
    Write-Host "Attached $AttachFileSystem set to $VmName"
}
