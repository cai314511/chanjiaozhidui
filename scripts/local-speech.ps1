param([Parameter(Mandatory=$true)][string]$InputFile, [Parameter(Mandatory=$true)][string]$OutputFile)
$ErrorActionPreference = 'Stop'
$voice = New-Object -ComObject SAPI.SpVoice
$voices = $voice.GetVoices()
$selected = $null
foreach ($candidate in $voices) {
    if ($candidate.GetAttribute('Language') -match '(^|;)804(;|$)') { $selected = $candidate; break }
}
if ($null -eq $selected) { throw 'A local Chinese SAPI voice is required' }
$voice.Voice = $selected
$stream = New-Object -ComObject SAPI.SpFileStream
$stream.Open($OutputFile, 3, $false)
try {
    $voice.AudioOutputStream = $stream
    $voice.Rate = 0
    $text = [System.IO.File]::ReadAllText($InputFile, [System.Text.Encoding]::UTF8)
    [void]$voice.Speak($text, 0)
} finally { $stream.Close() }
