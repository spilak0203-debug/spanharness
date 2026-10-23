# spanharness.ps1 - recorder, report and lint for the spanharness plugin.
#
# This file implements docs/lessons-format.md (the specification) for Windows
# PowerShell 5.1 and PowerShell 7. It uses only what ships with them, and it is
# pure ASCII: every non-ASCII output character is built from its code point.
#
#   spanharness.ps1 record                          hook JSON on stdin; always exits 0
#   spanharness.ps1 report [OUT.md] [--months N]
#   spanharness.ps1 lint [--root DIR]
#   common: --claude-dir D --lessons-dir D --plugin-root D --project-dir D --now ISO8601

[System.Threading.Thread]::CurrentThread.CurrentCulture = [System.Globalization.CultureInfo]::InvariantCulture
[System.Threading.Thread]::CurrentThread.CurrentUICulture = [System.Globalization.CultureInfo]::InvariantCulture
[System.Globalization.CultureInfo]::DefaultThreadCurrentCulture = [System.Globalization.CultureInfo]::InvariantCulture
[System.Globalization.CultureInfo]::DefaultThreadCurrentUICulture = [System.Globalization.CultureInfo]::InvariantCulture

$script:Inv = [System.Globalization.CultureInfo]::InvariantCulture
$script:Ord = [System.StringComparer]::Ordinal
$script:Utf8Out = [System.Text.UTF8Encoding]::new($false)
$script:Utf8In = [System.Text.UTF8Encoding]::new($false, $false)
$script:SelfPath = $MyInvocation.MyCommand.Path
$script:ScriptDir = $PSScriptRoot
if (-not $script:ScriptDir) { $script:ScriptDir = [System.IO.Path]::GetDirectoryName($script:SelfPath) }

# non-ASCII characters used in the report, from code points
$script:U_MID = [string][char]0x00B7
$script:U_EN = [string][char]0x2013
$script:U_EM = [string][char]0x2014
$script:U_ARR = [string][char]0x2192
$script:U_TIMES = [string][char]0x00D7
$script:U_GE = [string][char]0x2265
$script:LF = [string][char]10

# whitespace of section 0
$script:WS = [char[]](@(9, 10, 11, 12, 13, 32, 0x85, 0xA0, 0x1680) + @(0x2000..0x200A) + @(0x2028, 0x2029, 0x202F, 0x205F, 0x3000))
$script:LMin = [decimal][long]::MinValue
$script:LMax = [decimal][long]::MaxValue

# Windows PowerShell 5.1 has no $IsWindows (it only runs on Windows)
$script:OnWindows = $true
if ($PSVersionTable.PSVersion.Major -ge 6) { $script:OnWindows = [bool]$IsWindows }
$script:UseStj = ($PSVersionTable.PSVersion.Major -ge 7)
if ($script:UseStj) {
    $script:KStr = [System.Text.Json.JsonValueKind]::String
    $script:KNum = [System.Text.Json.JsonValueKind]::Number
    $script:KTrue = [System.Text.Json.JsonValueKind]::True
}
$script:JssLoaded = $false
$script:JssByLimit = @{}
$script:StjOptByLimit = @{}
$script:JsonValue = $null
$script:FixedNow = $null
$script:LessonsDir = $null

# ---------------------------------------------------------------- small helpers

function Test-StartsO($s, [string]$p) { return ([string]$s).StartsWith($p, [System.StringComparison]::Ordinal) }
function Test-EndsO($s, [string]$p) { return ([string]$s).EndsWith($p, [System.StringComparison]::Ordinal) }
function Find-O($s, [string]$p, [int]$from) { return ([string]$s).IndexOf($p, $from, [System.StringComparison]::Ordinal) }
function Test-Blank($s) { return ($null -eq $s) -or (([string]$s).Trim($script:WS).Length -eq 0) }
function Format-Int($n) { return ([long]$n).ToString($script:Inv) }

function Test-Dict($o) { return $o -is [System.Collections.IDictionary] }

# text(object, key): a non-blank string, as it is; else $null
function Get-JText($o, [string]$key) {
    if ($o -is [System.Collections.IDictionary]) {
        if ($o.ContainsKey($key)) {
            $v = $o[$key]
            if (($v -is [string]) -and ($v.Trim($script:WS).Length -gt 0)) { return $v }
        }
    }
    return $null
}

# number(value): signed 64-bit integer by truncation, else $null
function Get-Number($v) {
    if ($v -is [int]) { return [long]$v }
    if ($v -is [long]) { return $v }
    if ($v -is [decimal]) {
        $t = [decimal]::Truncate($v)
        if ($t -ge $script:LMin -and $t -le $script:LMax) { return [long]$t }
        return $null
    }
    if ($v -is [double]) {
        if ([double]::IsNaN($v) -or [double]::IsInfinity($v)) { return $null }
        if ($v -ge -9.2233720368547758E+18 -and $v -lt 9.2233720368547758E+18) { return [long][Math]::Truncate($v) }
        return $null
    }
    return $null
}

# a JSON number as an exact decimal (prices); $null when it is not a number
function ConvertTo-ExactDecimal($v) {
    if (($v -is [int]) -or ($v -is [long])) { return [decimal][long]$v }
    if ($v -is [decimal]) { return $v }
    if ($v -is [double]) {
        if ([double]::IsNaN($v) -or [double]::IsInfinity($v)) { return $null }
        try { return [decimal]::Parse($v.ToString('R', $script:Inv), [System.Globalization.NumberStyles]::Float, $script:Inv) } catch { return $null }
    }
    return $null
}

# sum(values) of a list of decimals: the exact sum, or $null outside the 64-bit range
function Get-SumOrNull($values) {
    $total = [decimal]0
    foreach ($x in $values) { $total += $x }
    if ($total -ge $script:LMin -and $total -le $script:LMax) { return $total }
    return $null
}

function Test-BadNameChars([string]$s) {
    if ($s -ceq '.' -or $s -ceq '..') { return $true }
    foreach ($ch in $s.ToCharArray()) {
        $c = [int]$ch
        if ($c -lt 32 -or $c -eq 34 -or $c -eq 60 -or $c -eq 62 -or $c -eq 124 -or $c -eq 58 -or $c -eq 42 -or $c -eq 63 -or $c -eq 92 -or $c -eq 47) { return $true }
    }
    return $false
}

function ConvertTo-SafeName([string]$s) {
    $sb = [System.Text.StringBuilder]::new()
    foreach ($ch in $s.ToCharArray()) {
        $c = [int]$ch
        if ($c -lt 32 -or $c -eq 34 -or $c -eq 60 -or $c -eq 62 -or $c -eq 124 -or $c -eq 58 -or $c -eq 42 -or $c -eq 63 -or $c -eq 92 -or $c -eq 47) { [void]$sb.Append('-') } else { [void]$sb.Append($ch) }
    }
    $trimChars = [char[]]@(32, 46)
    $r = $sb.ToString().Trim($trimChars)
    if ($r.Length -gt 60) { $r = $r.Substring(0, 60).TrimEnd($trimChars) }
    if ($r.Length -eq 0) { return 'skill' }
    return $r
}

# ---------------------------------------------------------------- time

# days since 0001-01-01 of a proleptic Gregorian date
function Get-DayNumber([long]$y, [long]$m, [long]$d) {
    if ($m -le 2) { $y = $y - 1 }
    if ($y -ge 0) { $era = [long][Math]::Floor($y / 400) } else { $era = [long][Math]::Floor(($y - 399) / 400) }
    $yoe = $y - $era * 400
    if ($m -gt 2) { $mp = $m - 3 } else { $mp = $m + 9 }
    $doy = [long][Math]::Floor((153 * $mp + 2) / 5) + $d - 1
    $doe = $yoe * 365 + [long][Math]::Floor($yoe / 4) - [long][Math]::Floor($yoe / 100) + $doy
    return $era * 146097 + $doe - 719468 + 719162
}

function Get-DaysInMonth([int]$y, [int]$m) {
    if ($m -eq 2) {
        if ((($y % 4) -eq 0 -and ($y % 100) -ne 0) -or (($y % 400) -eq 0)) { return 29 }
        return 28
    }
    if ($m -eq 4 -or $m -eq 6 -or $m -eq 9 -or $m -eq 11) { return 30 }
    return 31
}

$script:TsRx = [regex]::new('^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]+))?(?:(Z)|([+-])([0-9]{2}):([0-9]{2}))?\z', [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)

# a timestamp of section 0 as parts, or $null
function ConvertFrom-Timestamp($s) {
    if ($s -isnot [string]) { return $null }
    $m = $script:TsRx.Match($s)
    if (-not $m.Success) { return $null }
    $g = $m.Groups
    $y = [int]$g[1].Value; $mo = [int]$g[2].Value; $d = [int]$g[3].Value
    $h = [int]$g[4].Value; $mi = [int]$g[5].Value; $sec = [int]$g[6].Value
    if ($mo -lt 1 -or $mo -gt 12) { return $null }
    if ($d -lt 1 -or $d -gt (Get-DaysInMonth $y $mo)) { return $null }
    if ($h -gt 23 -or $mi -gt 59 -or $sec -gt 59) { return $null }
    $offMin = 0
    $hasOffset = $false
    if ($g[8].Success) { $hasOffset = $true }
    elseif ($g[9].Success) {
        $hasOffset = $true
        $oh = [int]$g[10].Value; $om = [int]$g[11].Value
        if ($om -gt 59) { return $null }
        $offMin = $oh * 60 + $om
        if ($offMin -gt 840) { return $null }
        if ($g[9].Value -eq '-') { $offMin = -$offMin }
    }
    $frac = [long]0
    if ($g[7].Success) {
        $fd = $g[7].Value
        if ($fd.Length -gt 7) { $fd = $fd.Substring(0, 7) }
        $frac = [long]$fd.PadRight(7, '0')
    }
    return @{ Y = $y; Mo = $mo; D = $d; H = $h; Mi = $mi; S = $sec; Frac = $frac; HasOffset = $hasOffset; OffMin = $offMin }
}

# UTC ticks (100 ns, from 0001-01-01) of a timestamp, or $null
function ConvertTo-UtcTicks($s) {
    $p = ConvertFrom-Timestamp $s
    if ($null -eq $p) { return $null }
    $days = Get-DayNumber $p.Y $p.Mo $p.D
    $secs = $days * 86400 + $p.H * 3600 + $p.Mi * 60 + $p.S - [long]$p.OffMin * 60
    return $secs * 10000000 + $p.Frac
}

function New-NowInfo([int]$y, [int]$mo, [int]$d, [int]$h, [int]$mi, [int]$s, [int]$offMin, [long]$utcTicks) {
    $i = $script:Inv
    if ($offMin -lt 0) { $sign = '-'; $a = -$offMin } else { $sign = '+'; $a = $offMin }
    $off = $sign + ([int][Math]::Floor($a / 60)).ToString('00', $i) + ':' + ($a % 60).ToString('00', $i)
    $date = $y.ToString('0000', $i) + '-' + $mo.ToString('00', $i) + '-' + $d.ToString('00', $i)
    $time = $h.ToString('00', $i) + ':' + $mi.ToString('00', $i) + ':' + $s.ToString('00', $i)
    return @{
        Stamp = $date + 'T' + $time + $off
        Month = $y.ToString('0000', $i) + '-' + $mo.ToString('00', $i)
        Log = $date + ' ' + $time
        Year = $y
        MonthNo = $mo
        UtcTicks = $utcTicks
    }
}

# --now: YYYY-MM-DDTHH:MM:SS followed by Z or +HH:MM or -HH:MM (the offset is required)
function ConvertFrom-NowText($text) {
    if ($text -isnot [string]) { return $null }
    $p = ConvertFrom-Timestamp $text
    if ($null -eq $p -or -not $p.HasOffset -or $text.IndexOf('.') -ge 0) { return $null }
    return New-NowInfo $p.Y $p.Mo $p.D $p.H $p.Mi $p.S $p.OffMin (ConvertTo-UtcTicks $text)
}

function Get-NowInfo {
    if ($null -ne $script:FixedNow) { return $script:FixedNow }
    $d = [System.DateTimeOffset]::Now
    $offMin = [int][Math]::Round($d.Offset.TotalMinutes)
    return New-NowInfo $d.Year $d.Month $d.Day $d.Hour $d.Minute $d.Second $offMin $d.UtcDateTime.Ticks
}

# ---------------------------------------------------------------- JSON

function Get-Jss([int]$recursionLimit) {
    if (-not $script:JssLoaded) {
        Add-Type -AssemblyName System.Web.Extensions
        $script:JssLoaded = $true
    }
    if (-not $script:JssByLimit.ContainsKey($recursionLimit)) {
        $j = [System.Web.Script.Serialization.JavaScriptSerializer]::new()
        $j.MaxJsonLength = [int]::MaxValue
        $j.RecursionLimit = $recursionLimit
        $script:JssByLimit[$recursionLimit] = $j
    }
    return $script:JssByLimit[$recursionLimit]
}

# --- JSON text escapes (a string with a lone surrogate escape such as "\ud83d" is valid JSON
# --- and valid for Python; JsonElement.GetString refuses it, so those strings are decoded here)

$script:JsonUnescRx = [regex]::new('\\(?:u([0-9a-fA-F]{4})|(.))', [System.Text.RegularExpressions.RegexOptions]::Singleline)
$script:JsonUnescEval = [System.Text.RegularExpressions.MatchEvaluator]{
    param($m)
    if ($m.Groups[1].Success) { return [string][char][Convert]::ToInt32($m.Groups[1].Value, 16) }
    $c = $m.Groups[2].Value
    if ($c -ceq 'b') { return [string][char]8 }
    if ($c -ceq 'f') { return [string][char]12 }
    if ($c -ceq 'n') { return [string][char]10 }
    if ($c -ceq 'r') { return [string][char]13 }
    if ($c -ceq 't') { return [string][char]9 }
    return $c
}
$script:JsonLiteralRx = [regex]::new('^"(?:[^"\\]|\\.)*"', [System.Text.RegularExpressions.RegexOptions]::Singleline)

# the value of a valid JSON string literal (quotes included)
function ConvertFrom-JsonLiteral([string]$lit) {
    $body = $lit.Substring(1, $lit.Length - 2)
    if ($body.IndexOf([char]92) -lt 0) { return $body }
    return $script:JsonUnescRx.Replace($body, $script:JsonUnescEval)
}

# PowerShell 7: the string of a JsonElement of kind String
function Get-StjString($el) {
    try { return $el.GetString() }
    catch { return (ConvertFrom-JsonLiteral $el.GetRawText()) }
}

function Get-StjName($p) {
    try { return $p.Name }
    catch { return (ConvertFrom-JsonLiteral ($script:JsonLiteralRx.Match($p.ToString()).Value)) }
}

# PowerShell 7: a JsonElement of kind Number as long, decimal or double (as the serializer of 5.1 gives them)
function Convert-JsonNumber($el) {
    $l = [long]0
    if ($el.TryGetInt64([ref]$l)) { return $l }
    $dec = [decimal]0
    if ($el.TryGetDecimal([ref]$dec)) { return $dec }
    $dbl = [double]0
    if ($el.TryGetDouble([ref]$dbl)) { return $dbl }
    return [double]::PositiveInfinity
}

# PowerShell 7: the whole tree of an element as dictionaries, arrays and scalars. Used for the small
# files (hook input, settings, plugin.json ...); a transcript line is read field by field instead.
function Convert-JsonElement($el) {
    $k = $el.ValueKind
    if ($k -eq [System.Text.Json.JsonValueKind]::Object) {
        $d = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        foreach ($p in $el.EnumerateObject()) { $d[(Get-StjName $p)] = Convert-JsonElement $p.Value }
        return $d
    }
    if ($k -eq [System.Text.Json.JsonValueKind]::Array) {
        $list = [System.Collections.Generic.List[object]]::new()
        foreach ($e in $el.EnumerateArray()) { $list.Add((Convert-JsonElement $e)) }
        return , $list.ToArray()
    }
    if ($k -eq [System.Text.Json.JsonValueKind]::String) { return (Get-StjString $el) }
    if ($k -eq [System.Text.Json.JsonValueKind]::Number) { return (Convert-JsonNumber $el) }
    if ($k -eq [System.Text.Json.JsonValueKind]::True) { return $true }
    if ($k -eq [System.Text.Json.JsonValueKind]::False) { return $false }
    return $null
}

function Get-StjOptions([int]$limit) {
    if (-not $script:StjOptByLimit.ContainsKey($limit)) {
        $o = [System.Text.Json.JsonDocumentOptions]::new()
        $o.MaxDepth = $limit
        $script:StjOptByLimit[$limit] = $o
    }
    return $script:StjOptByLimit[$limit]
}

# --- Windows PowerShell 5.1: the serializer accepts more than JSON (NaN, Infinity, single quotes,
# --- unquoted names, +1, .5, trailing commas ...) and turns "\/Date(..)\/" into a DateTime, so a text is
# --- first checked against RFC 8259 and then parsed. The check is made by regular expressions only (no
# --- loop over the tokens): the text is read as a token sequence, every token is replaced by one letter,
# --- and the skeleton is reduced from the inside, one nesting level per pass.
# S string  N number or true/false/null  V a finished array or object

$script:JsonStrPat = '"[^"\\\u0000-\u001f]*(?:\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4})[^"\\\u0000-\u001f]*)*"'
$script:JsonNumPat = '-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null'
$script:JsonLexRx = $null

# built on first use: only Windows PowerShell 5.1 needs them
function Initialize-StrictJson {
    if ($null -ne $script:JsonLexRx) { return }
    $ci = [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
    $script:JsonStrRx = [regex]::new($script:JsonStrPat, $ci)
    $script:JsonNumRx = [regex]::new($script:JsonNumPat, $ci)
    $script:JsonWsRx = [regex]::new('[ \t\r\n]+', $ci)
    $script:JsonReduceRx = [regex]::new('\[(?:[SNV](?:,[SNV])*)?\]|\{(?:S:[SNV](?:,S:[SNV])*)?\}', $ci)
    $script:JsonDoneRx = [regex]::new('\A[SNV]\z', $ci)
    # a string that the serializer would read as a date: it starts with /Date( in any spelling
    $script:JsonDateRx = [regex]::new('"(?:/|\\/|\\u002[fF])(?:D|\\u0044)(?:a|\\u0061)(?:t|\\u0074)(?:e|\\u0065)(?:\(|\\u0028)', $ci)
    # a surrogate escape: the serializer turns a lone one into U+FFFD, and 6.2 keeps it as it is
    $script:JsonSurrogateRx = [regex]::new('\\u[dD][89a-fA-F][0-9a-fA-F]{2}', $ci)
    $script:StrictTokRx = [regex]::new('\G[ \t\r\n]*(?:(?<s>' + $script:JsonStrPat + ')|(?<n>' + $script:JsonNumPat + ')|(?<p>[{}\[\],:]))', $ci)
    $script:JsonLexRx = [regex]::new('\A(?>[ \t\r\n]+|' + $script:JsonStrPat + '|' + $script:JsonNumPat + '|[{}\[\],:])*\z', $ci)
}

# true when $text is one JSON value (RFC 8259) that is not nested deeper than $limit
function Test-StrictJson([string]$text, [int]$limit) {
    Initialize-StrictJson
    if (-not $script:JsonLexRx.IsMatch($text)) { return $false }
    $s = $script:JsonStrRx.Replace($text, 'S')
    $s = $script:JsonNumRx.Replace($s, 'N')
    $s = $script:JsonWsRx.Replace($s, '')
    for ($pass = 0; $pass -le $limit; $pass++) {
        if ($s.Length -eq 1) { return $script:JsonDoneRx.IsMatch($s) }
        $r = $script:JsonReduceRx.Replace($s, 'V')
        if ($r.Length -eq $s.Length) { return $false }
        $s = $r
    }
    return $false
}

$script:StrictText = ''
$script:StrictPos = 0

function Read-StrictToken {
    $m = $script:StrictTokRx.Match($script:StrictText, $script:StrictPos)
    $script:StrictPos = $m.Index + $m.Length
    return $m
}

function Read-StrictValue($m) {
    if ($m.Groups['s'].Success) { return (ConvertFrom-JsonLiteral $m.Groups['s'].Value) }
    if ($m.Groups['n'].Success) {
        $v = $m.Groups['n'].Value
        if ($v -ceq 'true') { return $true }
        if ($v -ceq 'false') { return $false }
        if ($v -ceq 'null') { return $null }
        $l = [long]0
        if ($v.IndexOfAny([char[]]'.eE') -lt 0) {
            if ([long]::TryParse($v, [System.Globalization.NumberStyles]::AllowLeadingSign, $script:Inv, [ref]$l)) { return $l }
            $dec = [decimal]0
            if ([decimal]::TryParse($v, [System.Globalization.NumberStyles]::AllowLeadingSign, $script:Inv, [ref]$dec)) { return $dec }
        }
        $dbl = [double]0
        if ([double]::TryParse($v, [System.Globalization.NumberStyles]::Float, $script:Inv, [ref]$dbl)) { return $dbl }
        return [double]::PositiveInfinity
    }
    if ($m.Groups['p'].Value -ceq '[') {
        $list = [System.Collections.Generic.List[object]]::new()
        $m = Read-StrictToken
        if ($m.Groups['p'].Value -ceq ']') { return , $list.ToArray() }
        while ($true) {
            $list.Add((Read-StrictValue $m))
            $m = Read-StrictToken
            if ($m.Groups['p'].Value -ceq ']') { return , $list.ToArray() }
            $m = Read-StrictToken
        }
    }
    $d = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
    $m = Read-StrictToken
    if ($m.Groups['p'].Value -ceq '}') { return $d }
    while ($true) {
        $key = Read-StrictValue $m
        [void](Read-StrictToken)
        $d[$key] = Read-StrictValue (Read-StrictToken)
        $m = Read-StrictToken
        if ($m.Groups['p'].Value -ceq '}') { return $d }
        $m = Read-StrictToken
    }
}

# A parser for a text that Test-StrictJson accepted; slow (one call per value), so it is used only
# for the rare text that the serializer would misread.
function ConvertFrom-StrictJson([string]$text) {
    Initialize-StrictJson
    $script:StrictText = $text
    $script:StrictPos = 0
    return , (Read-StrictValue (Read-StrictToken))
}

# The one JSON reader. Sets $script:JsonValue and returns $true, or returns $false on
# any failure, including nesting deeper than $limit. Duplicate keys: the last wins.
function Try-ParseJson($text, [int]$limit) {
    $script:JsonValue = $null
    if ($text -isnot [string] -or $text.Length -eq 0) { return $false }
    try {
        if ($script:UseStj) {
            $doc = [System.Text.Json.JsonDocument]::Parse($text, (Get-StjOptions $limit))
            try { $v = Convert-JsonElement $doc.RootElement } finally { $doc.Dispose() }
            $script:JsonValue = $v
            return $true
        }
        # Windows PowerShell 5.1. Test-StrictJson has already limited the nesting; the serializer's own
        # limit (it counts scalars as a level too) is set far above it.
        if (-not (Test-StrictJson $text $limit)) { return $false }
        if ($script:JsonDateRx.IsMatch($text) -or $script:JsonSurrogateRx.IsMatch($text)) { $v = ConvertFrom-StrictJson $text }
        else { $v = (Get-Jss 1000).DeserializeObject($text) }
        $script:JsonValue = $v
        return $true
    }
    catch {
        $script:JsonValue = $null
        return $false
    }
}

$script:JsonEscRx = [regex]::new('["\\\u0000-\u001f]')

function ConvertTo-JsonString([string]$s) {
    if (-not $script:JsonEscRx.IsMatch($s)) { return '"' + $s + '"' }
    $sb = [System.Text.StringBuilder]::new($s.Length + 8)
    [void]$sb.Append('"')
    foreach ($ch in $s.ToCharArray()) {
        $c = [int]$ch
        if ($c -eq 34) { [void]$sb.Append('\"') }
        elseif ($c -eq 92) { [void]$sb.Append('\\') }
        elseif ($c -lt 32) {
            if ($c -eq 8) { [void]$sb.Append('\b') }
            elseif ($c -eq 9) { [void]$sb.Append('\t') }
            elseif ($c -eq 10) { [void]$sb.Append('\n') }
            elseif ($c -eq 12) { [void]$sb.Append('\f') }
            elseif ($c -eq 13) { [void]$sb.Append('\r') }
            else { [void]$sb.Append('\u00' + $c.ToString('x2', $script:Inv)) }
        }
        else { [void]$sb.Append($ch) }
    }
    [void]$sb.Append('"')
    return $sb.ToString()
}

# what Python json.dumps(obj, ensure_ascii=False, separators=(",", ":")) writes
function ConvertTo-JsonText($v) {
    if ($null -eq $v) { return 'null' }
    if ($v -is [string]) { return (ConvertTo-JsonString $v) }
    if ($v -is [bool]) { if ($v) { return 'true' } else { return 'false' } }
    if (($v -is [int]) -or ($v -is [long])) { return ([long]$v).ToString($script:Inv) }
    if ($v -is [System.Collections.IDictionary]) {
        $parts = [System.Collections.Generic.List[string]]::new()
        foreach ($k in $v.Keys) { $parts.Add((ConvertTo-JsonString ([string]$k)) + ':' + (ConvertTo-JsonText $v[$k])) }
        return '{' + ($parts -join ',') + '}'
    }
    if ($v -is [System.Collections.IEnumerable]) {
        $parts = [System.Collections.Generic.List[string]]::new()
        foreach ($x in $v) { $parts.Add((ConvertTo-JsonText $x)) }
        return '[' + ($parts -join ',') + ']'
    }
    throw 'cannot write this value as JSON'
}

# ---------------------------------------------------------------- files and text

function Read-FileBytes([string]$path) {
    return , [System.IO.File]::ReadAllBytes($path)
}

# bytes, leading UTF-8 byte order mark removed, decoded with replacement (section 6, rule 2)
function ConvertFrom-Utf8Bytes($bytes, [int]$start, [int]$count) {
    if ($count -ge 3 -and $bytes[$start] -eq 0xEF -and $bytes[$start + 1] -eq 0xBB -and $bytes[$start + 2] -eq 0xBF) { $start += 3; $count -= 3 }
    if ($count -le 0) { return '' }
    return $script:Utf8In.GetString($bytes, $start, $count)
}

function Read-TextFile([string]$path) {
    $b = [System.IO.File]::ReadAllBytes($path)
    return (ConvertFrom-Utf8Bytes $b 0 $b.Length)
}

# the file hash of 4.1: SHA-256 of the bytes without a BOM and with CRLF as LF
function Get-NormalizedHash($bytes) {
    $start = 0
    $len = $bytes.Length
    if ($len -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { $start = 3 }
    $data = $bytes
    $count = $len - $start
    if ([Array]::IndexOf($bytes, [byte]13, $start) -ge 0) {
        $out = [byte[]]::new($count)
        $j = 0
        for ($i = $start; $i -lt $len; $i++) {
            $b = $bytes[$i]
            if ($b -eq 13 -and ($i + 1) -lt $len -and $bytes[$i + 1] -eq 10) { continue }
            $out[$j] = $b
            $j++
        }
        $data = $out
        $start = 0
        $count = $j
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $h = $sha.ComputeHash($data, $start, $count) } finally { $sha.Dispose() }
    return ([System.BitConverter]::ToString($h).Replace('-', '')).ToLowerInvariant()
}

function Get-TextHash([string]$text) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { $h = $sha.ComputeHash($script:Utf8Out.GetBytes($text)) } finally { $sha.Dispose() }
    return ([System.BitConverter]::ToString($h).Replace('-', '')).ToLowerInvariant()
}

function Write-StdStream([string]$text, [bool]$toErr) {
    try {
        if ($toErr) { $s = [Console]::OpenStandardError() } else { $s = [Console]::OpenStandardOutput() }
        $b = $script:Utf8Out.GetBytes($text)
        $s.Write($b, 0, $b.Length)
        $s.Flush()
    }
    catch { }
}

function Write-Out([string]$text) { Write-StdStream $text $false }
function Write-Err([string]$text) { Write-StdStream $text $true }

function Get-OrdinalSorted($values) {
    $arr = [string[]]@($values)
    [Array]::Sort($arr, $script:Ord)
    return , $arr
}

# ---------------------------------------------------------------- frontmatter (4.3)

$script:FmKeyRx = [regex]::new('^([A-Za-z0-9_][A-Za-z0-9_.-]*)[ \t]*:([ \t]|\z)', [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)
$script:FmTrim = [char[]]@(32, 9, 13)

# Parse the block. Returns $null when there is no frontmatter, else a Dictionary of
# key -> @{ Rest = text after the first colon; Cont = continuation lines }.
function ConvertFrom-Frontmatter([string]$text) {
    $lines = $text.Split([char]10)
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i].EndsWith([string][char]13, [System.StringComparison]::Ordinal)) { $lines[$i] = $lines[$i].Substring(0, $lines[$i].Length - 1) }
    }
    if ($lines.Length -eq 0 -or -not ($lines[0].TrimEnd($script:FmTrim) -ceq '---')) { return $null }
    $end = -1
    for ($i = 1; $i -lt $lines.Length; $i++) {
        $t = $lines[$i].TrimEnd($script:FmTrim)
        if ($t -ceq '---' -or $t -ceq '...') { $end = $i; break }
    }
    if ($end -lt 0) { return $null }
    $entries = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
    $cur = $null
    for ($i = 1; $i -lt $end; $i++) {
        $l = $lines[$i]
        $m = $script:FmKeyRx.Match($l)
        if ($m.Success) {
            $key = $m.Groups[1].Value
            $entry = @{ Rest = $l.Substring($l.IndexOf(':') + 1); Cont = [System.Collections.Generic.List[string]]::new() }
            if (-not $entries.ContainsKey($key)) { $entries[$key] = $entry }
            $cur = $entry
        }
        elseif ($null -ne $cur -and ($l.Length -eq 0 -or $l[0] -eq ' ' -or $l[0] -eq "`t" -or $l -ceq '-' -or (Test-StartsO $l '- '))) {
            $cur.Cont.Add($l)
        }
        else { $cur = $null }
    }
    return , $entries
}

function ConvertFrom-FmValue([string]$s) {
    $s = $s.Trim($script:WS)
    if ($s.Length -gt 0 -and $s[0] -eq '"') {
        $sb = [System.Text.StringBuilder]::new()
        $i = 1
        while ($i -lt $s.Length) {
            $ch = $s[$i]
            if ($ch -eq '"') { break }
            if ($ch -eq '\' -and ($i + 1) -lt $s.Length) {
                $n = $s[$i + 1]
                $i += 2
                if ($n -eq 'n') { [void]$sb.Append([char]10) }
                elseif ($n -eq 't') { [void]$sb.Append([char]9) }
                elseif ($n -eq 'r') { [void]$sb.Append([char]13) }
                elseif ($n -eq '0') { [void]$sb.Append([char]0) }
                elseif ($n -eq 'u' -and ($i + 4) -le $s.Length -and [regex]::IsMatch($s.Substring($i, 4), '^[0-9A-Fa-f]{4}\z')) {
                    [void]$sb.Append([char][Convert]::ToInt32($s.Substring($i, 4), 16))
                    $i += 4
                }
                else { [void]$sb.Append($n) }
                continue
            }
            [void]$sb.Append($ch)
            $i++
        }
        return $sb.ToString()
    }
    if ($s.Length -gt 0 -and $s[0] -eq "'") {
        $sb = [System.Text.StringBuilder]::new()
        $i = 1
        while ($i -lt $s.Length) {
            $ch = $s[$i]
            if ($ch -eq "'") {
                if (($i + 1) -lt $s.Length -and $s[$i + 1] -eq "'") { [void]$sb.Append("'"); $i += 2; continue }
                break
            }
            [void]$sb.Append($ch)
            $i++
        }
        return $sb.ToString()
    }
    $cut = $s.IndexOf(' #', [System.StringComparison]::Ordinal)
    if ($cut -ge 0) { $s = $s.Substring(0, $cut) }
    return $s.Trim($script:WS)
}

function Get-FmValue($entries, [string]$key) {
    if ($null -eq $entries -or -not $entries.ContainsKey($key)) { return $null }
    $e = $entries[$key]
    $v = $e.Rest.Trim($script:WS)
    foreach ($c in $e.Cont) {
        $t = $c.Trim($script:WS)
        if ($t.Length -gt 0) { $v = $v + ' ' + $t }
    }
    return (ConvertFrom-FmValue ($v.Trim($script:WS)))
}

function Get-FmList($entries, [string]$key) {
    $items = [System.Collections.Generic.List[string]]::new()
    if ($null -eq $entries -or -not $entries.ContainsKey($key)) { return , $items }
    $e = $entries[$key]
    $a = $e.Rest.Trim($script:WS)
    if (Test-StartsO $a '#') { $a = '' }
    else {
        $cut = $a.IndexOf(' #', [System.StringComparison]::Ordinal)
        if ($cut -ge 0) { $a = $a.Substring(0, $cut).Trim($script:WS) }
    }
    if ($a.Length -gt 0) {
        if ((Test-StartsO $a '[') -and (Test-EndsO $a ']')) { $a = $a.Substring(1, $a.Length - 2) }
        foreach ($part in $a.Split(',')) {
            $v = ConvertFrom-FmValue $part
            if ($v.Length -gt 0) { $items.Add($v) }
        }
    }
    foreach ($c in $e.Cont) {
        $t = $c.Trim($script:WS)
        if ($t -ceq '-') { continue }
        if (Test-StartsO $t '- ') {
            $v = ConvertFrom-FmValue $t.Substring(2)
            if ($v.Length -gt 0) { $items.Add($v) }
        }
    }
    return , $items
}

# ---------------------------------------------------------------- places and options

function Get-HomeDir {
    $h = $null
    if ($script:OnWindows) { $h = [Environment]::GetEnvironmentVariable('USERPROFILE') }
    if (Test-Blank $h) { $h = [Environment]::GetEnvironmentVariable('HOME') }
    if (Test-Blank $h) { $h = [Environment]::GetFolderPath('UserProfile') }
    return $h
}

# Builds the folders of section 1/2 from the options. Returns a hashtable.
function New-Places($opt, $cwdOfInput) {
    $claude = $opt.ClaudeDir
    if ($null -eq $claude) {
        $env1 = [Environment]::GetEnvironmentVariable('CLAUDE_CONFIG_DIR')
        if (-not (Test-Blank $env1)) { $claude = $env1 } else { $claude = [System.IO.Path]::Combine((Get-HomeDir), '.claude') }
    }
    $lessons = $opt.LessonsDir
    if ($null -eq $lessons) { $lessons = [System.IO.Path]::Combine($claude, 'lessons') }
    $plugin = $opt.PluginRoot
    if ($null -eq $plugin) { $plugin = [System.IO.Path]::GetDirectoryName($script:ScriptDir) }
    $project = $null
    if (-not (Test-Blank $opt.ProjectDir)) { $project = $opt.ProjectDir }
    else {
        $env2 = [Environment]::GetEnvironmentVariable('CLAUDE_PROJECT_DIR')
        if (-not (Test-Blank $env2)) { $project = $env2 }
        elseif ($null -ne $cwdOfInput) { $project = $cwdOfInput }
    }
    return @{ Claude = $claude; Lessons = $lessons; Plugin = $plugin; Project = $project }
}

$script:ValueFlags = @('--claude-dir', '--lessons-dir', '--plugin-root', '--project-dir', '--now', '--months', '--root', '--group')

# Returns a hashtable; Error is set for bad arguments.
function Read-Options($argv) {
    $o = @{
        Positional = [System.Collections.Generic.List[string]]::new()
        ClaudeDir = $null; LessonsDir = $null; PluginRoot = $null; ProjectDir = $null
        NowText = $null; HasNow = $false; MonthsText = $null; Root = $null
        Groups = [System.Collections.Generic.List[string]]::new()
        Error = $null
    }
    $i = 0
    while ($i -lt $argv.Count) {
        $a = [string]$argv[$i]
        if (Test-StartsO $a '--') {
            if ($script:ValueFlags -cnotcontains $a) { $o.Error = 'unknown flag ' + $a; return $o }
            if (($i + 1) -ge $argv.Count) { $o.Error = 'flag ' + $a + ' needs a value'; return $o }
            $v = [string]$argv[$i + 1]
            $i += 2
            if ($a -ceq '--claude-dir') { $o.ClaudeDir = $v }
            elseif ($a -ceq '--lessons-dir') { $o.LessonsDir = $v }
            elseif ($a -ceq '--plugin-root') { $o.PluginRoot = $v }
            elseif ($a -ceq '--project-dir') { $o.ProjectDir = $v }
            elseif ($a -ceq '--now') { $o.NowText = $v; $o.HasNow = $true }
            elseif ($a -ceq '--months') { $o.MonthsText = $v }
            elseif ($a -ceq '--root') { $o.Root = $v }
            elseif ($a -ceq '--group') { $o.Groups.Add($v) }
        }
        else {
            $o.Positional.Add($a)
            $i++
        }
    }
    return $o
}

# ---------------------------------------------------------------- errors.log (3.6)

function Write-ErrLog([string]$what, $detail) {
    try {
        if ($null -eq $script:LessonsDir) { return }
        $path = [System.IO.Path]::Combine($script:LessonsDir, 'errors.log')
        [void][System.IO.Directory]::CreateDirectory($script:LessonsDir)
        if ([System.IO.File]::Exists($path)) {
            if (([System.IO.FileInfo]::new($path)).Length -gt 262144) { [System.IO.File]::Delete($path) }
        }
        $line = (Get-NowInfo).Log + ' ' + $what
        if (-not (Test-Blank $detail)) {
            $d = ([string]$detail).Replace([string][char]13, ' ').Replace([string][char]10, ' ')
            $line = $line + ' ' + $script:U_EM + ' ' + $d
        }
        $bytes = $script:Utf8Out.GetBytes($line + $script:LF)
        $fs = [System.IO.FileStream]::new($path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
        try { $fs.Write($bytes, 0, $bytes.Length) } finally { $fs.Dispose() }
    }
    catch { }
}

# The detail of an errors.log line (3.6): the exception type and a short reason in fixed words. Never
# $ex.Message of a file error: it names the file, and file names come from the hook input (session and
# agent ids, cwd), which the log must not hold. Only our own `throw 'cannot read <key>'` keeps its text.
function Get-ErrDetail($ex) {
    if ($null -eq $ex) { return $null }
    while ($ex -is [System.Management.Automation.RuntimeException] -and $null -ne $ex.InnerException) { $ex = $ex.InnerException }
    $name = $ex.GetType().Name
    if ($ex.GetType().FullName -ceq 'System.Management.Automation.RuntimeException') {
        if (Test-StartsO $ex.Message 'cannot read ') { return $ex.Message }
        return $name
    }
    $why = $null
    if ($ex -is [System.UnauthorizedAccessException]) { $why = 'access denied' }
    elseif (($ex -is [System.IO.FileNotFoundException]) -or ($ex -is [System.IO.DirectoryNotFoundException])) { $why = 'no such file or directory' }
    elseif ($ex -is [System.IO.PathTooLongException]) { $why = 'file name too long' }
    elseif ($ex -is [System.IO.IOException]) {
        if ($ex.HResult -eq -2147024864) { $why = 'file in use' }
        elseif ($ex.HResult -eq -2147024784 -or $ex.HResult -eq -2147024857) { $why = 'disk full' }
        else { $why = 'I/O error' }
    }
    if ($null -eq $why) { return $name }
    return ($name + ': ' + $why)
}

# ---------------------------------------------------------------- harness fingerprint (4)

# Reads JSON from a file; returns the value or $null (missing, unreadable, not JSON)
function Read-JsonFile([string]$path, [int]$limit) {
    try {
        if (-not [System.IO.File]::Exists($path)) { return $null }
        $t = Read-TextFile $path
        if (Try-ParseJson $t $limit) { return $script:JsonValue }
    }
    catch { }
    return $null
}

# 4.2: the value of the active output style
function Get-ActiveStyle($places) {
    $paths = [System.Collections.Generic.List[string]]::new()
    if ($null -ne $places.Project) {
        $paths.Add([System.IO.Path]::Combine($places.Project, '.claude', 'settings.local.json'))
        $paths.Add([System.IO.Path]::Combine($places.Project, '.claude', 'settings.json'))
    }
    $paths.Add([System.IO.Path]::Combine($places.Claude, 'settings.json'))
    foreach ($p in $paths) {
        $o = Read-JsonFile $p 100
        if ($o -is [System.Collections.IDictionary] -and $o.ContainsKey('outputStyle')) {
            $v = $o['outputStyle']
            if (($v -is [string]) -and -not (Test-Blank $v)) { return $v }
        }
    }
    return 'default'
}

# the file name of the style file that matches the value, with its folder; $null when none
function Find-StyleFile($places, [string]$value) {
    $folders = [System.Collections.Generic.List[string]]::new()
    if ($null -ne $places.Project) { $folders.Add([System.IO.Path]::Combine($places.Project, '.claude', 'output-styles')) }
    $folders.Add([System.IO.Path]::Combine($places.Claude, 'output-styles'))
    $lv = $value.ToLowerInvariant()
    foreach ($f in $folders) {
        if (-not [System.IO.Directory]::Exists($f)) { continue }
        $names = [System.Collections.Generic.List[string]]::new()
        foreach ($p in [System.IO.Directory]::GetFiles($f)) {
            $n = [System.IO.Path]::GetFileName($p)
            if ($n.EndsWith('.md', [System.StringComparison]::OrdinalIgnoreCase)) { $names.Add($n) }
        }
        $sorted = Get-OrdinalSorted $names
        foreach ($n in $sorted) {
            $base = $n.Substring(0, $n.Length - 3)
            if ($base.ToLowerInvariant() -ceq $lv) { return @{ Name = $n; Path = [System.IO.Path]::Combine($f, $n) } }
            try {
                $fm = ConvertFrom-Frontmatter (Read-TextFile ([System.IO.Path]::Combine($f, $n)))
                $nm = Get-FmValue $fm 'name'
                if ($null -ne $nm -and $nm.ToLowerInvariant() -ceq $lv) { return @{ Name = $n; Path = [System.IO.Path]::Combine($f, $n) } }
            }
            catch { }
        }
    }
    return $null
}

function Add-FileHash($files, [string]$key, [string]$path) {
    try { $bytes = [System.IO.File]::ReadAllBytes($path) } catch { throw ('cannot read ' + $key) }
    $files[$key] = Get-NormalizedHash $bytes
}

# Returns @{ Hash; Files } or throws 'cannot read {key}'
function Get-Fingerprint($places) {
    $files = [System.Collections.Generic.Dictionary[string, string]]::new($script:Ord)
    $preloaded = [System.Collections.Generic.List[string]]::new()
    $seen = [System.Collections.Generic.HashSet[string]]::new($script:Ord)

    $agents = [System.IO.Path]::Combine($places.Plugin, 'agents')
    if ([System.IO.Directory]::Exists($agents)) {
        foreach ($p in [System.IO.Directory]::GetFiles($agents)) {
            $n = [System.IO.Path]::GetFileName($p)
            if (-not $n.EndsWith('.md', [System.StringComparison]::OrdinalIgnoreCase)) { continue }
            $key = 'plugin/agents/' + $n
            try { $bytes = [System.IO.File]::ReadAllBytes($p) } catch { throw ('cannot read ' + $key) }
            $files[$key] = Get-NormalizedHash $bytes
            $fm = ConvertFrom-Frontmatter (ConvertFrom-Utf8Bytes $bytes 0 $bytes.Length)
            $skills = Get-FmList $fm 'skills'
            foreach ($s in $skills) { if ($seen.Add($s)) { $preloaded.Add($s) } }
        }
    }
    $styles = [System.IO.Path]::Combine($places.Plugin, 'output-styles')
    if ([System.IO.Directory]::Exists($styles)) {
        foreach ($p in [System.IO.Directory]::GetFiles($styles)) {
            $n = [System.IO.Path]::GetFileName($p)
            if (-not $n.EndsWith('.md', [System.StringComparison]::OrdinalIgnoreCase)) { continue }
            Add-FileHash $files ('plugin/output-styles/' + $n) $p
        }
    }
    $skillsDir = [System.IO.Path]::Combine($places.Plugin, 'skills')
    if ([System.IO.Directory]::Exists($skillsDir)) {
        foreach ($d in [System.IO.Directory]::GetDirectories($skillsDir)) {
            $n = [System.IO.Path]::GetFileName($d)
            $f = [System.IO.Path]::Combine($d, 'SKILL.md')
            if ([System.IO.File]::Exists($f)) { Add-FileHash $files ('plugin/skills/' + $n + '/SKILL.md') $f }
        }
    }
    foreach ($s in $preloaded) {
        if (Test-BadNameChars $s) { continue }
        $f = [System.IO.Path]::Combine($places.Claude, 'skills', $s, 'SKILL.md')
        if ([System.IO.File]::Exists($f)) { Add-FileHash $files ('skills/' + $s + '/SKILL.md') $f }
    }
    $active = Get-ActiveStyle $places
    $files['output-style'] = Get-NormalizedHash ($script:Utf8Out.GetBytes($active))
    $sf = Find-StyleFile $places $active
    if ($null -ne $sf) { Add-FileHash $files ('output-styles/' + $sf.Name) $sf.Path }
    $cm = [System.IO.Path]::Combine($places.Claude, 'CLAUDE.md')
    if ([System.IO.File]::Exists($cm)) { Add-FileHash $files 'CLAUDE.md' $cm }

    $keys = Get-Sorted-Keys $files
    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($k in $keys) { $lines.Add($k + "`t" + $files[$k]) }
    $hash = (Get-TextHash ($lines -join $script:LF)).Substring(0, 8)
    return @{ Hash = $hash; Files = $files }
}

function Get-Sorted-Keys($dict) {
    $arr = [string[]]::new($dict.Count)
    $dict.Keys.CopyTo($arr, 0)
    [Array]::Sort($arr, $script:Ord)
    return , $arr
}

function Compare-Prints($before, $after) {
    $ch = [System.Collections.Generic.List[string]]::new()
    $ad = [System.Collections.Generic.List[string]]::new()
    $rm = [System.Collections.Generic.List[string]]::new()
    foreach ($k in $after.Keys) {
        if ($null -ne $before -and $before.ContainsKey($k)) {
            if (-not [string]::Equals($before[$k], $after[$k])) { $ch.Add($k) }
        }
        else { $ad.Add($k) }
    }
    if ($null -ne $before) { foreach ($k in $before.Keys) { if (-not $after.ContainsKey($k)) { $rm.Add($k) } } }
    $ch.Sort($script:Ord)
    $ad.Sort($script:Ord)
    $rm.Sort($script:Ord)
    return @{ Changed = $ch; Added = $ad; Removed = $rm }
}

# ---------------------------------------------------------------- transcript summary (3.3)

function Test-IsPrompt($o) {
    if ($o.ContainsKey('isMeta') -and ($o['isMeta'] -is [bool]) -and $o['isMeta']) { return $false }
    if ($o.ContainsKey('isCompactSummary') -and ($o['isCompactSummary'] -is [bool]) -and $o['isCompactSummary']) { return $false }
    $origin = $null
    if ($o.ContainsKey('origin')) { $origin = $o['origin'] }
    $kind = Get-JText $origin 'kind'
    if ($null -ne $kind -and -not ($kind -ceq 'human')) { return $false }
    $message = $null
    if ($o.ContainsKey('message')) { $message = $o['message'] }
    if ($message -isnot [System.Collections.IDictionary] -or -not $message.ContainsKey('content')) { return $false }
    $content = $message['content']
    if ($content -is [string]) { return ($content.Trim($script:WS).Length -gt 0) }
    if ($content -is [System.Collections.IList]) {
        foreach ($el in $content) {
            if ($el -is [System.Collections.IDictionary]) {
                $t = Get-JText $el 'type'
                if (-not ($t -ceq 'tool_result')) { return $true }
            }
        }
    }
    return $false
}

$script:UsageKeys = @('input_tokens', 'output_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')

$script:NonWsRx = [regex]::new('[^\t-\r \u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]')

$script:TsFastRx = [regex]::new('\A([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}):([0-5][0-9])\.([0-9]{3})Z\z', [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)

# PowerShell 7.4 and later read a transcript line through JsonNode: the parser is .NET, and looking up a
# field of the result costs one indexer call, where the dictionaries of Try-ParseJson cost a call for every
# node of the line (a line has hundreds of nodes, the summary needs a dozen). Older versions have no
# JsonNode.GetValueKind and use Add-TranscriptLineDict, which is slower and gives the same result.
$script:UseNodes = $false
if ($script:UseStj) {
    $script:JNode = 'System.Text.Json.Nodes.JsonNode' -as [type]
    if ($null -ne $script:JNode -and $null -ne $script:JNode.GetMethod('GetValueKind')) {
        $script:UseNodes = $true
        $script:TObj = [System.Text.Json.Nodes.JsonObject]
        $script:TArr = [System.Text.Json.Nodes.JsonArray]
        $script:TVal = [System.Text.Json.Nodes.JsonValue]
        $script:StjOpt200 = Get-StjOptions 200
        # GetValue<long> through reflection: Windows PowerShell 5.1 cannot parse the generic call syntax
        $script:GetLong = $script:JNode.GetMethod('GetValue').MakeGenericMethod([long])
    }
}

# Is this transcript line a prompt: a JSON object line of type user that is typed by the person? (3.3)
function Test-PromptLine([string]$t) {
    # the type can only read "user" when the line holds "user" or a \u escape; a cheap test, though most lines pass it
    if ($t.IndexOf('user', [System.StringComparison]::Ordinal) -lt 0 -and $t.IndexOf('\u', [System.StringComparison]::Ordinal) -lt 0) { return $false }
    if (-not $script:UseNodes) { return (Test-PromptLineDict $t) }
    try {
        $root = $script:JNode::Parse($t, $null, $script:StjOpt200)
        if ($root -isnot $script:TObj) { return $false }
        $n = $root['type']
        if ($n -isnot $script:TVal -or $n.GetValueKind() -ne $script:KStr -or [string]$n -cne 'user') { return $false }
        $n = $root['isMeta']
        if ($n -is $script:TVal -and $n.GetValueKind() -eq $script:KTrue) { return $false }
        $n = $root['isCompactSummary']
        if ($n -is $script:TVal -and $n.GetValueKind() -eq $script:KTrue) { return $false }
        $n = $root['origin']
        if ($n -is $script:TObj) {
            $n = $n['kind']
            if ($n -is $script:TVal -and $n.GetValueKind() -eq $script:KStr) {
                $k = [string]$n
                if ($k -cne 'human' -and $k.Trim($script:WS).Length -gt 0) { return $false }
            }
        }
        $n = $root['message']
        if ($n -isnot $script:TObj) { return $false }
        $n = $n['content']
        if ($n -is $script:TVal) {
            if ($n.GetValueKind() -ne $script:KStr) { return $false }
            return $script:NonWsRx.IsMatch([string]$n)
        }
        if ($n -is $script:TArr) {
            foreach ($el in $n) {
                if ($el -isnot $script:TObj) { continue }
                $ty = $el['type']
                if ($ty -is $script:TVal -and $ty.GetValueKind() -eq $script:KStr -and ([string]$ty -ceq 'tool_result')) { continue }
                return $true
            }
        }
        return $false
    }
    catch {
        # a line the node reader does not take (equal keys, a lone surrogate ...): the general reader
        return (Test-PromptLineDict $t)
    }
}

function Test-PromptLineDict([string]$t) {
    if (-not (Try-ParseJson $t 200) -or $script:JsonValue -isnot [System.Collections.IDictionary]) { return $false }
    return ((Get-JText $script:JsonValue 'type') -ceq 'user') -and (Test-IsPrompt $script:JsonValue)
}

# One transcript line through JsonNode (see $script:UseNodes). 0 blank line, 1 a JSON object, 2 broken.
# This is the hot loop of `record`, where a call of a function costs more than a method call: an
# ordinary line calls none. Every value is read into a variable first and $c is changed at the end, so
# that a line which throws half way (and is then read again by Add-TranscriptLineDict) has changed nothing.
function Add-TranscriptLineNode($c, [string]$text) {
    $t = $text.Trim($script:WS)
    if ($t.Length -eq 0) { return 0 }
    try {
        $root = $script:JNode::Parse($t, $null, $script:StjOpt200)
        if ($root -isnot $script:TObj) { return (Add-TranscriptLineDict $c $t) }
        $n = $root['type']
        if ($n -isnot $script:TVal) { return 1 }
        $type = [string]$n
        $isUser = ($type -ceq 'user')
        if (-not $isUser -and $type -cne 'assistant') { return 1 }

        $tk = $null
        $n = $root['timestamp']
        if ($n -is $script:TVal) {
            # the form Claude Code writes is read through a per-minute base; anything else by the general reader
            $ts = [string]$n
            $m = $script:TsFastRx.Match($ts)
            if ($m.Success) {
                $key = $m.Groups[1].Value
                $base = $c.Minutes[$key]
                if ($null -eq $base) {
                    $base = ConvertTo-UtcTicks ($key + ':00.000Z')
                    if ($null -eq $base) { $base = [long]-1 }
                    $c.Minutes[$key] = $base
                }
                if ($base -ge 0) { $tk = $base + [long]$m.Groups[2].Value * 10000000 + [long]$m.Groups[3].Value * 10000 }
            }
            elseif ($n.GetValueKind() -eq $script:KStr) { $tk = ConvertTo-UtcTicks $ts }
        }

        if (-not $isUser) {
            $message = $root['message']
            if ($message -is $script:TObj) {
                $un = $c.Unnamed
                $id = $null
                $n = $message['id']
                if ($n -is $script:TVal -and $n.GetValueKind() -eq $script:KStr) {
                    $id = [string]$n
                    if (-not $script:NonWsRx.IsMatch($id)) { $id = $null }
                }
                if ($null -eq $id) { $un++; $id = 'line-' + $un }
                $model = $null
                $n = $message['model']
                if ($n -is $script:TVal -and $n.GetValueKind() -eq $script:KStr) {
                    $model = [string]$n
                    if ($model -ceq '<synthetic>' -or -not $script:NonWsRx.IsMatch($model)) { $model = $null }
                }
                $vals = $null
                $u = $message['usage']
                if ($u -is $script:TObj) {
                    $vals = [object[]]::new(4)
                    for ($i = 0; $i -lt 4; $i++) {
                        $n = $u[$script:UsageKeys[$i]]
                        if ($n -is $script:TVal -and $n.GetValueKind() -eq $script:KNum) { $vals[$i] = $script:GetLong.Invoke($n, $null) }
                    }
                }
                $tools = $null
                $ct = $message['content']
                if ($ct -is $script:TArr) {
                    foreach ($b in $ct) {
                        if ($b -isnot $script:TObj) { continue }
                        $n = $b['type']
                        if ($n -is $script:TVal -and [string]$n -ceq 'tool_use') {
                            $tid = $null
                            $n = $b['id']
                            if ($n -is $script:TVal -and $n.GetValueKind() -eq $script:KStr) {
                                $tid = [string]$n
                                if (-not $script:NonWsRx.IsMatch($tid)) { $tid = $null }
                            }
                            if ($null -eq $tid) { $un++; $tid = 'tool-' + $un }
                            if ($null -eq $tools) { $tools = [System.Collections.Generic.List[string]]::new() }
                            $tools.Add($tid)
                        }
                    }
                }
                $c.Unnamed = $un
                [void]$c.Answers.Add($id)
                if ($null -ne $model) { $c.Model = $model }
                if ($null -ne $vals) {
                    $arr = $c.Usage[$id]
                    if ($null -eq $arr) { $arr = [object[]]::new(4); $c.Usage[$id] = $arr }
                    for ($i = 0; $i -lt 4; $i++) { if ($null -ne $vals[$i]) { $arr[$i] = $vals[$i] } }
                }
                if ($null -ne $tools) { foreach ($x in $tools) { [void]$c.Tools.Add($x) } }
            }
        }
        if ($null -ne $tk) {
            if ($null -eq $c.First -or $tk -lt $c.First) { $c.First = $tk }
            if ($null -eq $c.Last -or $tk -gt $c.Last) { $c.Last = $tk }
        }
        return 1
    }
    catch {
        # not an ordinary line (broken, equal keys, a lone surrogate, a number that is not an integer ...)
        return (Add-TranscriptLineDict $c $t)
    }
}

# The general reader (Windows PowerShell 5.1, older PowerShell 7, and the lines that Add-TranscriptLineNode
# hands over): Try-ParseJson has built the dictionaries; only the fields that are needed are looked at.
function Add-TranscriptLineDict($c, [string]$text) {
    $t = $text.Trim($script:WS)
    if ($t.Length -eq 0) { return 0 }
    if (-not (Try-ParseJson $t 200)) { return 2 }
    $o = $script:JsonValue
    if ($o -isnot [System.Collections.IDictionary]) { return 2 }

    $type = Get-JText $o 'type'
    $isUser = [string]::Equals($type, 'user')
    $isAsst = [string]::Equals($type, 'assistant')
    if (($isUser -or $isAsst) -and $o.ContainsKey('timestamp')) {
        $tk = ConvertTo-UtcTicks $o['timestamp']
        if ($null -ne $tk) {
            if ($null -eq $c.First -or $tk -lt $c.First) { $c.First = $tk }
            if ($null -eq $c.Last -or $tk -gt $c.Last) { $c.Last = $tk }
        }
    }
    if (-not $isAsst) { return 1 }
    if (-not $o.ContainsKey('message') -or $o['message'] -isnot [System.Collections.IDictionary]) { return 1 }
    $message = $o['message']

    $id = Get-JText $message 'id'
    if ($null -eq $id) { $c.Unnamed++; $id = 'line-' + $c.Unnamed }
    [void]$c.Answers.Add($id)
    $m = Get-JText $message 'model'
    if ($null -ne $m -and -not ($m -ceq '<synthetic>')) { $c.Model = $m }
    if ($message.ContainsKey('usage') -and $message['usage'] -is [System.Collections.IDictionary]) {
        $u = $message['usage']
        if (-not $c.Usage.ContainsKey($id)) { $c.Usage[$id] = [object[]]::new(4) }
        $arr = $c.Usage[$id]
        for ($i = 0; $i -lt 4; $i++) {
            if ($u.ContainsKey($script:UsageKeys[$i])) {
                $n = Get-Number $u[$script:UsageKeys[$i]]
                if ($null -ne $n) { $arr[$i] = $n }
            }
        }
    }
    if ($message.ContainsKey('content') -and $message['content'] -is [System.Collections.IList]) {
        foreach ($b in $message['content']) {
            if ($b -is [System.Collections.IDictionary] -and ([string]::Equals((Get-JText $b 'type'), 'tool_use'))) {
                $tid = Get-JText $b 'id'
                if ($null -eq $tid) { $c.Unnamed++; $tid = 'tool-' + $c.Unnamed }
                [void]$c.Tools.Add($tid)
            }
        }
    }
    return 1
}

function Get-UsageSum($usage, [int]$i) {
    $any = $false
    $total = [decimal]0
    foreach ($arr in $usage.Values) {
        if ($null -ne $arr[$i]) { $any = $true; $total += [decimal][long]$arr[$i] }
    }
    if (-not $any) { return $null }
    if ($total -ge $script:LMin -and $total -le $script:LMax) { return [long]$total }
    return $null
}

# A transcript is opened only when it is a regular file (3.3): a directory, a pipe or a device is
# unreadable. Windows: a directory is refused here and FileStream itself refuses a pipe or a device
# (and CanSeek is the last check). Other hosts (the tests only): FileStream would wait for a writer
# on a pipe, so a file of length 0 is not opened at all; it has nothing to read either way, and $null
# stands for it.
function Open-TranscriptFile([string]$path) {
    if (([System.IO.File]::GetAttributes($path) -band [System.IO.FileAttributes]::Directory) -ne 0) { throw 'not a regular file' }
    if (-not $script:OnWindows -and ([System.IO.FileInfo]::new($path)).Length -eq 0) { return $null }
    $fs = [System.IO.FileStream]::new($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
    if (-not $fs.CanSeek) { $fs.Dispose(); throw 'not a regular file' }
    return $fs
}

# summarize(path, offset)
function Get-TranscriptSummary($path, [long]$offset) {
    $given = $offset
    $c = @{
        Answers = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
        Tools = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
        Usage = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        Minutes = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        Unnamed = 0; First = $null; Last = $null; Model = $null
    }
    $res = @{ Offset = $given; Model = $null; In = $null; Out = $null; CacheRead = $null; CacheWrite = $null
              Tools = $null; Turns = $null; Ms = $null; Unchanged = $false; Broken = 0 }
    $fs = $null
    $ok = $false
    $newOffset = $given
    $unchanged = $false
    $broken = 0
    try {
        $fs = Open-TranscriptFile ([string]$path)
        $len = [long]0
        if ($null -ne $fs) { $len = $fs.Length }
        if ($offset -lt 0 -or $offset -gt $len) { $offset = 0 }
        $newOffset = $offset
        $unchanged = ($len -eq $offset)
        # never more than the length seen now: a file that grows meanwhile is read to that length only
        $buf = [byte[]]::new($len - $offset)
        $total = 0
        if ($buf.Length -gt 0) {
            [void]$fs.Seek($offset, [System.IO.SeekOrigin]::Begin)
            while ($total -lt $buf.Length) {
                $got = $fs.Read($buf, $total, $buf.Length - $total)
                if ($got -le 0) { break }
                $total += $got
            }
        }
        $pos = 0
        if ($script:UseNodes) { $adder = 'Add-TranscriptLineNode' } else { $adder = 'Add-TranscriptLineDict' }
        while ($pos -lt $total) {
            $nl = [Array]::IndexOf($buf, [byte]10, $pos, $total - $pos)
            $lineStart = $offset + $pos
            if ($nl -lt 0) { $cnt = $total - $pos } else { $cnt = $nl - $pos }
            # a byte order mark is removed at the start of the file only (6.2)
            if ($lineStart -eq 0) { $text = ConvertFrom-Utf8Bytes $buf $pos $cnt }
            elseif ($cnt -le 0) { $text = '' }
            else { $text = $script:Utf8In.GetString($buf, $pos, $cnt) }
            $r = & $adder $c $text
            if ($nl -lt 0) {
                if ($r -ne 2) { $newOffset = $offset + $total }
                break
            }
            if ($r -eq 2) { $broken++ }
            $newOffset = $offset + $nl + 1
            $pos = $nl + 1
        }
        $ok = $true
    }
    catch { $ok = $false }
    finally { if ($null -ne $fs) { $fs.Dispose() } }
    if (-not $ok) { return $res }

    $res.Offset = $newOffset
    $res.Unchanged = $unchanged
    $res.Broken = $broken
    $res.Model = $c.Model
    $res.In = Get-UsageSum $c.Usage 0
    $res.Out = Get-UsageSum $c.Usage 1
    $res.CacheRead = Get-UsageSum $c.Usage 2
    $res.CacheWrite = Get-UsageSum $c.Usage 3
    if ($c.Answers.Count -gt 0) { $res.Turns = [long]$c.Answers.Count; $res.Tools = [long]$c.Tools.Count }
    if ($null -ne $c.First) { $res.Ms = [long][Math]::Floor([decimal]($c.Last - $c.First) / 10000) }
    return $res
}

# The byte position where the last prompt line starts, or $null when there is none or the file cannot be read (3.3).
# Blocks are read from the end of the file, so the part before the prompt is not read.
function Get-LastPromptStart($path) {
    $fs = $null
    try {
        $fs = Open-TranscriptFile ([string]$path)
        if ($null -eq $fs) { return $null }
        $pos = [long]$fs.Length
        $block = [byte[]]::new(65536)
        $tail = [System.Collections.Generic.List[byte[]]]::new()     # the pieces of the line that is cut by a block start, last piece first
        while ($pos -gt 0) {
            $n = [int][Math]::Min([long]$block.Length, $pos)
            $pos -= $n
            [void]$fs.Seek($pos, [System.IO.SeekOrigin]::Begin)
            $got = 0
            while ($got -lt $n) {
                $r = $fs.Read($block, $got, $n - $got)
                if ($r -le 0) { break }
                $got += $r
            }
            if ($got -lt $n) { return $null }
            $hi = $n
            while ($true) {
                if ($hi -gt 0) { $i = [Array]::LastIndexOf($block, [byte]10, $hi - 1, $hi) } else { $i = -1 }
                if ($i -lt 0) {
                    if ($hi -gt 0) {
                        $piece = [byte[]]::new($hi)
                        [Array]::Copy($block, 0, $piece, 0, $hi)
                        $tail.Add($piece)
                    }
                    break
                }
                $cnt = $hi - $i - 1
                if ($tail.Count -eq 0) { $text = $script:Utf8In.GetString($block, $i + 1, $cnt) }
                else {
                    $ms = [System.IO.MemoryStream]::new()
                    if ($cnt -gt 0) { $ms.Write($block, $i + 1, $cnt) }
                    for ($j = $tail.Count - 1; $j -ge 0; $j--) { $ms.Write($tail[$j], 0, $tail[$j].Length) }
                    $text = $script:Utf8In.GetString($ms.ToArray())
                    $tail.Clear()
                }
                if (Test-PromptLine ($text.Trim($script:WS))) { return ($pos + $i + 1) }
                $hi = $i
            }
        }
        # the first line of the file (the only one that may start with a byte order mark)
        if ($tail.Count -gt 0) {
            $ms = [System.IO.MemoryStream]::new()
            for ($j = $tail.Count - 1; $j -ge 0; $j--) { $ms.Write($tail[$j], 0, $tail[$j].Length) }
            $all = $ms.ToArray()
            if (Test-PromptLine ((ConvertFrom-Utf8Bytes $all 0 $all.Length).Trim($script:WS))) { return [long]0 }
        }
        return $null
    }
    catch { return $null }
    finally { if ($null -ne $fs) { $fs.Dispose() } }
}

function Get-TurnSummary($path, $offset) {
    if ($null -ne $offset) { return (Get-TranscriptSummary $path ([long]$offset)) }
    # no saved position: the turn starts at the last prompt; what comes before it is not read (3.3)
    $start = Get-LastPromptStart $path
    if ($null -eq $start) { $start = [long]0 }
    return (Get-TranscriptSummary $path ([long]$start))
}

# ---------------------------------------------------------------- record (3)

function Get-ProjectName($cwd) {
    if ($null -eq $cwd) { return $null }
    $slashes = [char[]]@([char]92, [char]47)
    $trimmed = ([string]$cwd).TrimEnd($slashes)
    try {
        $dir = $trimmed
        while (-not [string]::IsNullOrEmpty($dir)) {
            $name = [System.IO.Path]::GetFileName($dir)
            if ($name.Length -gt 0) {
                $git = [System.IO.Path]::Combine($dir, '.git')
                if ([System.IO.Directory]::Exists($git) -or [System.IO.File]::Exists($git)) { return $name }
            }
            $dir = [System.IO.Path]::GetDirectoryName($dir)
        }
    }
    catch { }
    $last = $trimmed.Substring($trimmed.LastIndexOfAny($slashes) + 1)
    if ($last.Length -gt 0) { return $last }
    return $null
}

# 4.4: model and effort of the role file
function Get-RoleInfo($agentType, $places) {
    $info = @{ Model = $null; Effort = $null }
    try {
        if ($null -eq $agentType) { return $info }
        $file = $null
        $pluginPrefix = 'spanharness:'
        if (Test-StartsO $agentType $pluginPrefix) {
            $name = $agentType.Substring($pluginPrefix.Length)
            if (-not (Test-BadNameChars $name)) {
                $f = [System.IO.Path]::Combine($places.Plugin, 'agents', $name + '.md')
                if ([System.IO.File]::Exists($f)) { $file = $f }
            }
        }
        elseif (-not (Test-BadNameChars $agentType)) {
            $cands = [System.Collections.Generic.List[string]]::new()
            if ($null -ne $places.Project) { $cands.Add([System.IO.Path]::Combine($places.Project, '.claude', 'agents', $agentType + '.md')) }
            $cands.Add([System.IO.Path]::Combine($places.Claude, 'agents', $agentType + '.md'))
            $cands.Add([System.IO.Path]::Combine($places.Plugin, 'agents', $agentType + '.md'))
            foreach ($f in $cands) { if ([System.IO.File]::Exists($f)) { $file = $f; break } }
        }
        if ($null -eq $file) { return $info }
        $fm = ConvertFrom-Frontmatter (Read-TextFile $file)
        $info.Model = Get-FmValue $fm 'model'
        $info.Effort = Get-FmValue $fm 'effort'
    }
    catch { }
    return $info
}

# step 6: if the last byte of the transcript is not a line feed, wait for it (1 s at most)
function Wait-TranscriptLine($path) {
    if ($null -eq $path -or $path.Length -eq 0) { return }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        $last = 10
        try {
            $fs = Open-TranscriptFile $path
            if ($null -ne $fs) {
                try {
                    if ($fs.Length -gt 0) {
                        [void]$fs.Seek($fs.Length - 1, [System.IO.SeekOrigin]::Begin)
                        $last = $fs.ReadByte()
                    }
                }
                finally { $fs.Dispose() }
            }
        }
        catch { return }
        if ($last -eq 10) { return }
        if ($sw.ElapsedMilliseconds -ge 1000) { return }
        [System.Threading.Thread]::Sleep(50)
    }
}

function Enter-Lock([string]$stateDir) {
    [void][System.IO.Directory]::CreateDirectory($stateDir)
    $path = [System.IO.Path]::Combine($stateDir, 'lock')
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        try {
            return [System.IO.FileStream]::new($path, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        }
        catch {
            if ($sw.ElapsedMilliseconds -ge 10000) { return $null }
            [System.Threading.Thread]::Sleep(50)
        }
    }
}

# UTF-8 text through <path>.tmp and a replace, retrying 3 times 150 ms apart (4 tries)
function Save-TextAtomic([string]$path, [string]$text) {
    $tmp = $path + '.tmp'
    $bytes = $script:Utf8Out.GetBytes($text)
    for ($attempt = 1; ; $attempt++) {
        try {
            [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($path))
            [System.IO.File]::WriteAllBytes($tmp, $bytes)
            if ([System.IO.File]::Exists($path)) { [System.IO.File]::Replace($tmp, $path, [NullString]::Value) } else { [System.IO.File]::Move($tmp, $path) }
            return
        }
        catch {
            if ($attempt -ge 4) {
                try { if ([System.IO.File]::Exists($tmp)) { [System.IO.File]::Delete($tmp) } } catch { }
                throw
            }
            [System.Threading.Thread]::Sleep(150)
        }
    }
}

function Add-ToFile([string]$path, [string]$text) {
    $bytes = $script:Utf8Out.GetBytes($text)
    [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($path))
    for ($attempt = 1; ; $attempt++) {
        try {
            $fs = [System.IO.FileStream]::new($path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
            try { $fs.Write($bytes, 0, $bytes.Length) } finally { $fs.Dispose() }
            return
        }
        catch [System.IO.IOException] {
            if ($attempt -gt 5) { throw }
            [System.Threading.Thread]::Sleep(100)
        }
    }
}

function Remove-OldStates([string]$stateDir) {
    if (-not [System.IO.Directory]::Exists($stateDir)) { return }
    $limit = (Get-NowInfo).UtcTicks - [long]30 * 24 * 3600 * 10000000
    foreach ($p in [System.IO.Directory]::GetFiles($stateDir)) {
        $n = [System.IO.Path]::GetFileName($p)
        if (-not (Test-EndsO $n '.json')) { continue }
        if (-not ((Test-StartsO $n 'turn-') -or (Test-StartsO $n 'agent-'))) { continue }
        if ([System.IO.File]::GetLastWriteTimeUtc($p).Ticks -lt $limit) { [System.IO.File]::Delete($p) }
    }
}

# step 9: the saved offset of the state file for this transcript, or $null
function Get-SavedOffset($stateFile, $transcript) {
    if ($null -eq $stateFile -or $null -eq $transcript) { return $null }
    $st = Read-JsonFile $stateFile 100
    if ($st -is [System.Collections.IDictionary]) {
        $sp = Get-JText $st 'path'
        if ($null -ne $sp -and ($sp.ToLowerInvariant() -ceq $transcript.ToLowerInvariant()) -and $st.ContainsKey('offset')) {
            return (Get-Number $st['offset'])
        }
    }
    return $null
}

$script:OptimisticTries = 3

# Test-only (3.9): with SPANHARNESS_TEST_GATE naming a folder, say that try $attempt has made its summary
# (reached-N) and wait for go-N (60 s at most).
function Wait-TestGate([int]$attempt) {
    $dir = [Environment]::GetEnvironmentVariable('SPANHARNESS_TEST_GATE')
    if (Test-Blank $dir) { return }
    try {
        [System.IO.File]::WriteAllBytes([System.IO.Path]::Combine($dir, 'reached-' + (Format-Int $attempt)), [byte[]]::new(0))
        $go = [System.IO.Path]::Combine($dir, 'go-' + (Format-Int $attempt))
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        while (-not [System.IO.File]::Exists($go) -and $sw.ElapsedMilliseconds -lt 60000) { [System.Threading.Thread]::Sleep(10) }
    }
    catch { }
}

function Invoke-Record($argv) {
    try {
        $ErrorActionPreference = 'Stop'
        if ([Environment]::GetEnvironmentVariable('SPANHARNESS_RECORD') -ceq '0') { return 0 }
        if (-not $script:OnWindows) { return 0 }
        if (-not [Console]::IsInputRedirected) {
            Write-Err ('usage: spanharness.ps1 record   (hook JSON on stdin)' + $script:LF)
            return 0
        }
        $opt = Read-Options $argv
        $problem = $opt.Error
        if ($null -eq $problem -and $opt.Positional.Count -gt 0) { $problem = 'unexpected argument' }
        if ($null -eq $problem -and $opt.HasNow) {
            $script:FixedNow = ConvertFrom-NowText $opt.NowText
            if ($null -eq $script:FixedNow) { $problem = 'bad --now value' }
        }
        if ($null -ne $problem) {
            Write-Err ('spanharness record: ' + $problem + $script:LF)
            return 0
        }
        $places0 = New-Places $opt $null
        $script:LessonsDir = $places0.Lessons

        $ms = [System.IO.MemoryStream]::new()
        $stdin = [Console]::OpenStandardInput()
        $stdin.CopyTo($ms)
        $raw = $ms.ToArray()
        $skip = 0
        if ($raw.Length -ge 3 -and $raw[0] -eq 0xEF -and $raw[1] -eq 0xBB -and $raw[2] -eq 0xBF) { $skip = 3 }
        $n = $raw.Length - $skip
        $text = ConvertFrom-Utf8Bytes $raw 0 $raw.Length
        if (-not (Try-ParseJson $text 100) -or $script:JsonValue -isnot [System.Collections.IDictionary]) {
            Write-ErrLog ('hook input is not a JSON object (' + (Format-Int $n) + ' bytes)') $null
            return 0
        }
        $input1 = $script:JsonValue

        $hookEvent = Get-JText $input1 'hook_event_name'
        $session = Get-JText $input1 'session_id'
        $cwd = Get-JText $input1 'cwd'
        $agentId = Get-JText $input1 'agent_id'
        $agentType = Get-JText $input1 'agent_type'
        $effort = $null
        if ($input1.ContainsKey('effort')) { $effort = Get-JText $input1['effort'] 'level' }

        $isAgent = ([string]::Equals($hookEvent, 'SubagentStop') -and ($null -ne $agentType))
        $isTurn = ([string]::Equals($hookEvent, 'Stop') -and ($null -eq $agentId))
        if (-not $isAgent -and -not $isTurn) { return 0 }

        if ($isAgent) { $transcript = Get-JText $input1 'agent_transcript_path' } else { $transcript = Get-JText $input1 'transcript_path' }
        $stateId = $null
        if ($isAgent) { $stateId = $agentId } else { $stateId = $session }
        $places = New-Places $opt $cwd
        $stateDir = [System.IO.Path]::Combine($places.Lessons, 'state')
        $stateFile = $null
        if ($null -ne $stateId) {
            if ($isAgent) { $prefix = 'agent-' } else { $prefix = 'turn-' }
            $stateFile = [System.IO.Path]::Combine($stateDir, $prefix + (ConvertTo-SafeName $stateId) + '.json')
        }

        Wait-TranscriptLine $transcript

        $fp = $null
        try { $fp = Get-Fingerprint $places }
        catch { Write-ErrLog 'harness fingerprint failed' (Get-ErrDetail $_.Exception); $fp = $null }

        $roleModel = $null
        $roleEffort = $null
        if ($isAgent) {
            $ri = Get-RoleInfo $agentType $places
            $roleModel = $ri.Model
            $roleEffort = $ri.Effort
        }

        # The summary is made without the lock (it can take long); the lock covers only the commit below.
        # A record that finds the saved position moved by another record in the meantime sums up again
        # from the new position. The last try holds the lock from the start, so a record cannot starve.
        $lock = $null
        try {
            for ($attempt = 0; $attempt -le $script:OptimisticTries; $attempt++) {
                if ($attempt -eq $script:OptimisticTries) {
                    $lock = Enter-Lock $stateDir
                    if ($null -eq $lock) {
                        Write-ErrLog 'could not take the lock; record skipped' $null
                        return 0
                    }
                }
                $saved = Get-SavedOffset $stateFile $transcript
                if ($isTurn) { $sum = Get-TurnSummary $transcript $saved }
                else {
                    $o0 = [long]0
                    if ($null -ne $saved) { $o0 = [long]$saved }
                    $sum = Get-TranscriptSummary $transcript $o0
                }
                if ($null -ne $saved -and $sum.Unchanged) { return 0 }
                Wait-TestGate ($attempt + 1)
                if ($null -eq $lock) {
                    $lock = Enter-Lock $stateDir
                    if ($null -eq $lock) {
                        Write-ErrLog 'could not take the lock; record skipped' $null
                        return 0
                    }
                    $again = Get-SavedOffset $stateFile $transcript
                    if (($null -eq $saved) -ne ($null -eq $again) -or ($null -ne $saved -and $saved -ne $again)) {
                        $lock.Dispose()
                        $lock = $null
                        continue
                    }
                }
                break
            }

            $now = Get-NowInfo
            $stamp = $now.Stamp
            $rec = [ordered]@{}
            $rec['t'] = $stamp
            if ($isAgent) { $rec['kind'] = 'agent' } else { $rec['kind'] = 'turn' }
            $rec['project'] = Get-ProjectName $cwd
            $rec['cwd'] = $cwd
            $rec['session'] = $session
            if ($isAgent) { $rec['agent'] = $agentType; $rec['agent_id'] = $agentId }
            $rec['model'] = $sum.Model
            if ($isAgent) { $rec['role_model'] = $roleModel }
            $rec['effort'] = $effort
            if ($isAgent) { $rec['role_effort'] = $roleEffort }
            $rec['in'] = $sum.In
            $rec['out'] = $sum.Out
            $rec['cache_read'] = $sum.CacheRead
            $rec['cache_write'] = $sum.CacheWrite
            $rec['tools'] = $sum.Tools
            $rec['turns'] = $sum.Turns
            $rec['ms'] = $sum.Ms
            if ($null -ne $fp) { $rec['harness'] = $fp.Hash } else { $rec['harness'] = $null }
            $missing = [System.Collections.Generic.List[string]]::new()
            foreach ($k in $rec.Keys) {
                if ($null -eq $rec[$k] -and $k -cne 'effort' -and $k -cne 'role_model' -and $k -cne 'role_effort') { $missing.Add($k) }
            }
            $rec['missing'] = $missing

            $pluginVersion = $null
            $pj = Read-JsonFile ([System.IO.Path]::Combine($places.Plugin, '.claude-plugin', 'plugin.json')) 100
            if ($pj -is [System.Collections.IDictionary]) { $pluginVersion = Get-JText $pj 'version' }

            $harnessLine = $null
            if ($null -ne $fp) {
                $hs = Read-JsonFile ([System.IO.Path]::Combine($places.Lessons, 'state', 'harness.json')) 100
                $before = $null
                $beforeHash = $null
                $beforeVersion = $null
                if ($hs -is [System.Collections.IDictionary] -and ($hs.ContainsKey('harness')) -and ($hs['harness'] -is [string]) -and $hs.ContainsKey('files') -and ($hs['files'] -is [System.Collections.IDictionary])) {
                    $beforeHash = $hs['harness']
                    $before = [System.Collections.Generic.Dictionary[string, string]]::new($script:Ord)
                    foreach ($k in $hs['files'].Keys) {
                        $fv = $hs['files'][$k]
                        if ($fv -is [string]) { $before[[string]$k] = $fv } else { $before[[string]$k] = '' }
                    }
                    $beforeVersion = Get-JText $hs 'plugin_version'
                }
                if ($null -eq $before -or -not [string]::Equals($beforeHash, $fp.Hash) -or -not [string]::Equals($beforeVersion, $pluginVersion)) {
                    $cmp = Compare-Prints $before $fp.Files
                    $h = [ordered]@{}
                    $h['t'] = $stamp
                    $h['kind'] = 'harness'
                    $h['harness'] = $fp.Hash
                    $h['prev'] = $beforeHash
                    $h['changed'] = $cmp.Changed
                    $h['added'] = $cmp.Added
                    $h['removed'] = $cmp.Removed
                    $h['plugin_version'] = $pluginVersion
                    $harnessLine = $h
                }
            }

            $out = ''
            if ($null -ne $harnessLine) { $out = (ConvertTo-JsonText $harnessLine) + $script:LF }
            $out = $out + (ConvertTo-JsonText $rec) + $script:LF
            $runsFile = [System.IO.Path]::Combine($places.Lessons, 'runs', $now.Month + '.jsonl')
            try { Add-ToFile $runsFile $out }
            catch {
                Write-ErrLog 'could not write the record' (Get-ErrDetail $_.Exception)
                return 0
            }

            if ($null -ne $harnessLine) {
                try {
                    $fl = [System.Collections.Generic.List[string]]::new()
                    foreach ($k in (Get-Sorted-Keys $fp.Files)) { $fl.Add((ConvertTo-JsonString $k) + ':' + (ConvertTo-JsonString $fp.Files[$k])) }
                    $json = '{"harness":' + (ConvertTo-JsonString $fp.Hash) + ',"files":{' + ($fl -join ',') + '},"plugin_version":' + (ConvertTo-JsonText $pluginVersion) + '}'
                    Save-TextAtomic ([System.IO.Path]::Combine($places.Lessons, 'state', 'harness.json')) $json
                }
                catch { Write-ErrLog 'could not save the harness state' (Get-ErrDetail $_.Exception) }
            }
            if ($null -ne $stateFile) {
                try {
                    $json = '{"path":' + (ConvertTo-JsonText $transcript) + ',"offset":' + (Format-Int $sum.Offset) + '}'
                    Save-TextAtomic $stateFile $json
                }
                catch { Write-ErrLog 'could not save the read position' (Get-ErrDetail $_.Exception) }
            }
            try { Remove-OldStates $stateDir }
            catch { Write-ErrLog 'could not remove old read positions' (Get-ErrDetail $_.Exception) }
        }
        finally { if ($null -ne $lock) { $lock.Dispose() } }
        return 0
    }
    catch {
        try { Write-ErrLog 'record failed' (Get-ErrDetail $_.Exception) } catch { }
        return 0
    }
}

# ---------------------------------------------------------------- report (5)

$script:MainRole = 'main conversation'
$script:UnknownHarness = '(unknown)'
$script:UnknownModel = '(model unknown)'
$script:ValKeys = @('in', 'out', 'cache_read', 'cache_write', 'tools', 'turns', 'ms')
$script:ModelSignals = @('fix-request', 'review-block', 'review-wrong', 'repeated-failure', 'redone')
$script:DateRx = [regex]::new('^[0-9]{4}-[0-9]{2}-[0-9]{2}\z', [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)
$script:RunFileRx = [regex]::new('^([0-9]{4}-(?:0[1-9]|1[0-2]))\.jsonl\z', [System.Text.RegularExpressions.RegexOptions]::CultureInvariant -bor [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
$script:ModelIdRx = [regex]::new('^claude-(fable|opus|sonnet|haiku)-([0-9]+)-([0-9]{1,2})(?=\z|[-\[@\t-\r \u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000])', [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)
$script:Prices = $null

# ---- number formats (5.4)

function Format-Fmt1([decimal]$x) {
    $r = [Math]::Round($x, 1, [System.MidpointRounding]::AwayFromZero)
    if ($r -eq 0) { return '0' }
    $s = $r.ToString('0.0', $script:Inv)
    if (Test-EndsO $s '.0') { $s = $s.Substring(0, $s.Length - 2) }
    return $s
}

function Format-Fmt2([decimal]$x) {
    $r = [Math]::Round($x, 2, [System.MidpointRounding]::AwayFromZero)
    if ($r -eq 0) { return '0' }
    $s = $r.ToString('0.00', $script:Inv)
    if ($s.IndexOf('.') -ge 0) { $s = $s.TrimEnd('0').TrimEnd('.') }
    return $s
}

function Format-Usd([decimal]$v) {
    if ($v -gt 0 -and $v -lt [decimal]0.01) { return '<$0.01' }
    return '$' + ([Math]::Round($v, 2, [System.MidpointRounding]::AwayFromZero)).ToString('0.00', $script:Inv)
}

function Get-SortedDecimals($list) {
    $arr = $list.ToArray()
    [Array]::Sort($arr)
    return , $arr
}

function Get-Quantile($sorted, [decimal]$q) {
    $n = $sorted.Length
    $at = ($n - 1) * $q
    $low = [int][Math]::Floor($at)
    $high = [Math]::Min($low + 1, $n - 1)
    return [decimal]($sorted[$low] + ($sorted[$high] - $sorted[$low]) * ($at - $low))
}

function Get-Median($list) {
    $s = Get-SortedDecimals $list
    return (Get-Quantile $s ([decimal]0.5))
}

function Get-Spread($list) {
    $s = Get-SortedDecimals $list
    if ($s.Length -ge 4) {
        return @{ Label = 'p25' + $script:U_EN + 'p75'; Lo = (Get-Quantile $s ([decimal]0.25)); Hi = (Get-Quantile $s ([decimal]0.75)) }
    }
    return @{ Label = 'min' + $script:U_EN + 'max'; Lo = $s[0]; Hi = $s[$s.Length - 1] }
}

function Get-SpreadText($list) {
    $sp = Get-Spread $list
    return $sp.Label + ' ' + (Format-Fmt1 $sp.Lo) + $script:U_EN + (Format-Fmt1 $sp.Hi)
}

# stat(values): three cells
function Get-StatCells($list) {
    if ($list.Count -eq 0) { return , @('0', '-', '-') }
    return , @((Format-Int $list.Count), (Format-Fmt1 (Get-Median $list)), (Get-SpreadText $list))
}

function Get-SpanText($first, $last) {
    if ($null -eq $first) { return '-' }
    if ([string]::Equals($first, $last)) { return $first }
    return $first + ' ' + $script:U_EN + ' ' + $last
}

function Get-Cell([string]$s) {
    return $s.Replace('|', '\|').Replace([string][char]13, ' ').Replace([string][char]10, ' ')
}

function Get-TableRow($cells) {
    $esc = [System.Collections.Generic.List[string]]::new()
    foreach ($c in $cells) { $esc.Add((Get-Cell ([string]$c))) }
    return '| ' + ($esc -join ' | ') + ' |'
}

function Add-Line($sb, [string]$s) { [void]$sb.Append($s).Append($script:LF) }

function Get-StringList($o, [string]$key) {
    $r = [System.Collections.Generic.List[string]]::new()
    if ($o -is [System.Collections.IDictionary] -and $o.ContainsKey($key)) {
        $v = $o[$key]
        if ($v -is [System.Collections.IList]) {
            foreach ($x in $v) { if (($x -is [string]) -and -not (Test-Blank $x)) { $r.Add($x) } }
        }
    }
    return , $r
}

function Format-RoleName([string]$role) {
    $p = 'spanharness:'
    if ($role.Length -gt $p.Length -and $role.Substring(0, $p.Length).ToLowerInvariant() -ceq $p) { return $role.Substring($p.Length) }
    return $role
}

# ---- prices (5.9)

function Read-Prices($places) {
    $p = @{ AsOf = 'unknown'; Models = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord); Ok = $false }
    try {
        $path = [System.IO.Path]::Combine($places.Plugin, 'scripts', 'prices.json')
        $t = Read-TextFile $path
        if (-not (Try-ParseJson $t 100) -or $script:JsonValue -isnot [System.Collections.IDictionary]) { return $p }
        $o = $script:JsonValue
        $p.Ok = $true
        if ($o.ContainsKey('as_of') -and $o['as_of'] -is [string]) { $p.AsOf = $o['as_of'] }
        if ($o.ContainsKey('models') -and $o['models'] -is [System.Collections.IDictionary]) {
            $models = $o['models']
            foreach ($k in $models.Keys) {
                $e = $models[$k]
                if ($e -isnot [System.Collections.IDictionary]) { continue }
                $in = $null; $out = $null; $cr = $null; $cw = $null
                if ($e.ContainsKey('input')) { $in = ConvertTo-ExactDecimal $e['input'] }
                if ($e.ContainsKey('output')) { $out = ConvertTo-ExactDecimal $e['output'] }
                if ($e.ContainsKey('cache_read')) { $cr = ConvertTo-ExactDecimal $e['cache_read'] }
                if ($e.ContainsKey('cache_write_5m')) { $cw = ConvertTo-ExactDecimal $e['cache_write_5m'] }
                if ($null -eq $in -or $null -eq $out -or $null -eq $cr -or $null -eq $cw) { continue }
                $name = '-'
                if ($e.ContainsKey('name') -and $e['name'] -is [string]) { $name = $e['name'] }
                $p.Models[[string]$k] = @{ Name = $name; In = $in; Out = $out; CacheRead = $cr; CacheWrite = $cw }
            }
        }
    }
    catch { $p.Ok = $false }
    return $p
}

function Get-PriceOf([string]$model) {
    $m = $script:ModelIdRx.Match($model.Trim($script:WS).ToLowerInvariant())
    if (-not $m.Success) { return $null }
    $key = $m.Groups[1].Value + '-' + $m.Groups[2].Value + '-' + $m.Groups[3].Value
    if ($script:Prices.Models.ContainsKey($key)) { return $script:Prices.Models[$key] }
    return $null
}

# ---- reading the runs (5.2)

function New-Row([string]$project, [string]$role, [bool]$isMain) {
    $vals = New-Object 'object[]' 7
    for ($i = 0; $i -lt 7; $i++) { $vals[$i] = [System.Collections.Generic.List[decimal]]::new() }
    return @{
        Project = $project; Role = $role; Main = $isMain; Count = 0; Unread = 0
        Models = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
        Efforts = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
        Values = $vals
    }
}

function Add-ReportLine($st, [string]$line) {
    $o = $null
    if ((Try-ParseJson $line 100) -and ($script:JsonValue -is [System.Collections.IDictionary])) { $o = $script:JsonValue }
    $kind = Get-JText $o 'kind'
    if (-not ([string]::Equals($kind, 'agent') -or [string]::Equals($kind, 'turn') -or [string]::Equals($kind, 'harness'))) {
        $st.Skipped++
        return
    }
    $t = Get-JText $o 't'
    if ($null -ne $t) {
        $tk = ConvertTo-UtcTicks $t
        if ($null -ne $tk) {
            if ($null -eq $st.FirstTicks -or $tk -lt $st.FirstTicks) { $st.FirstTicks = $tk; $st.FirstText = $t }
            if ($null -eq $st.LastTicks -or $tk -gt $st.LastTicks) { $st.LastTicks = $tk; $st.LastText = $t }
        }
    }
    if ([string]::Equals($kind, 'harness')) {
        $st.Changes.Add(@{
            When = $t; Prev = (Get-JText $o 'prev'); Hash = (Get-JText $o 'harness')
            Changed = (Get-StringList $o 'changed'); Added = (Get-StringList $o 'added'); Removed = (Get-StringList $o 'removed')
            Version = (Get-JText $o 'plugin_version')
        })
        return
    }
    $isAgent = [string]::Equals($kind, 'agent')
    $project = Get-JText $o 'project'
    if ($null -eq $project) { $project = '(project unknown)' }
    if ($isAgent) {
        $role = Get-JText $o 'agent'
        if ($null -eq $role) { $role = '(role name unknown)' } else { $role = Format-RoleName $role }
        $st.Agents++
    }
    else { $role = $script:MainRole; $st.Turns++ }
    $nul = [string][char]0
    if ($isAgent) { $kc = 'a' } else { $kc = 't' }
    $rowKey = $kc + $nul + $project + $nul + $role
    if (-not $st.Rows.ContainsKey($rowKey)) { $st.Rows[$rowKey] = New-Row $project $role (-not $isAgent) }
    $row = $st.Rows[$rowKey]
    $row.Count++

    $counts = New-Object 'object[]' 4
    $allRead = $true
    for ($i = 0; $i -lt 4; $i++) {
        if ($o.ContainsKey($script:ValKeys[$i])) { $counts[$i] = Get-Number $o[$script:ValKeys[$i]] }
        if ($null -eq $counts[$i]) { $allRead = $false }
    }
    $tokens = $null
    if ($allRead) {
        $tokens = Get-SumOrNull @([decimal][long]$counts[0], [decimal][long]$counts[1], [decimal][long]$counts[2], [decimal][long]$counts[3])
    }
    $date = $null
    if ($null -ne $t -and $t.Length -ge 10 -and $script:DateRx.IsMatch($t.Substring(0, 10))) { $date = $t.Substring(0, 10) }
    $harness = Get-JText $o 'harness'
    if ($null -eq $harness) { $harness = $script:UnknownHarness }
    $modelText = Get-JText $o 'model'
    $model = $null
    if ($null -ne $modelText) { $model = $modelText.Trim($script:WS).ToLowerInvariant() }
    $ms = $null
    if ($o.ContainsKey('ms')) { $ms = Get-Number $o['ms'] }
    $st.Runs.Add(@{
        Seq = $st.Runs.Count; Main = (-not $isAgent); Project = $project; Role = $role; Date = $date
        Harness = $harness; Model = $model; Counts = $counts; Tokens = $tokens; Ms = $ms
    })
    if ($null -ne $model) { [void]$row.Models.Add($model) }
    $effort = Get-JText $o 'effort'
    if ($null -ne $effort) { [void]$row.Efforts.Add($effort) }
    for ($i = 0; $i -lt 7; $i++) {
        if ($o.ContainsKey($script:ValKeys[$i])) {
            $n = Get-Number $o[$script:ValKeys[$i]]
            if ($null -ne $n) { $row.Values[$i].Add([decimal]$n) }
        }
    }
    $missing = Get-StringList $o 'missing'
    if ($missing.Count -gt 0) {
        $row.Unread++
        $st.Unread++
        foreach ($k in $missing) {
            if ($st.UnreadKeys.ContainsKey($k)) { $st.UnreadKeys[$k] = $st.UnreadKeys[$k] + 1 } else { $st.UnreadKeys[$k] = 1 }
        }
    }
}

# ---- events.md (5.3) and harness-log.md (5.8)

function Read-Events($places, [string]$from, [string]$to) {
    $log = @{ Problem = $null; Events = [System.Collections.Generic.List[object]]::new(); Expected = 0; Bad = 0 }
    $path = [System.IO.Path]::Combine($places.Lessons, 'events.md')
    if (-not [System.IO.File]::Exists($path)) { $log.Problem = 'events.md not found: no outcome signals.'; return $log }
    try { $text = Read-TextFile $path }
    catch { $log.Problem = 'events.md could not be read.'; return $log }
    $sep = [string[]]@(' | ')
    foreach ($raw in $text.Split([char]10)) {
        $line = $raw.Trim($script:WS)
        if (-not (Test-StartsO $line '- ')) { continue }
        $parts = $line.Substring(2).Split($sep, 6, [System.StringSplitOptions]::None)
        for ($i = 0; $i -lt $parts.Length; $i++) { $parts[$i] = $parts[$i].Trim($script:WS) }
        if ($parts.Length -lt 5 -or -not $script:DateRx.IsMatch($parts[0]) -or $parts[1].Length -eq 0 -or $parts[2].Length -eq 0 -or $parts[4].Length -eq 0) {
            $log.Bad++
            continue
        }
        $month = $parts[0].Substring(0, 7)
        if ([string]::CompareOrdinal($month, $from) -lt 0 -or [string]::CompareOrdinal($month, $to) -gt 0) { continue }
        $signal = $parts[2].ToLowerInvariant()
        $work = $parts[3].Split([char]0x00B7)[0].Trim($script:WS)
        if ($work.ToLowerInvariant() -ceq 'experiment' -and ($signal -ceq 'repeated-failure' -or $signal -ceq 'redone')) {
            $log.Expected++
            continue
        }
        $role = Format-RoleName $parts[4]
        $lr = $role.ToLowerInvariant()
        $log.Events.Add(@{ Date = $parts[0]; Project = $parts[1]; Signal = $signal; Role = $role
                           Main = ($lr -ceq 'main' -or $lr -ceq 'main conversation' -or $lr -ceq 'orchestrator') })
    }
    return $log
}

function Read-AppliedBy($places) {
    $by = [System.Collections.Generic.Dictionary[string, string]]::new($script:Ord)
    try {
        $path = [System.IO.Path]::Combine($places.Lessons, 'harness-log.md')
        if (-not [System.IO.File]::Exists($path)) { return , $by }
        $text = Read-TextFile $path
        $sep = [string[]]@(' | ')
        foreach ($raw in $text.Split([char]10)) {
            $line = $raw.Trim($script:WS)
            if (-not (Test-StartsO $line '- ')) { continue }
            $f = $line.Substring(2).Split($sep, [System.StringSplitOptions]::None)
            if ($f.Length -ge 6) {
                $key = $f[$f.Length - 1].Trim($script:WS)
                if (-not $by.ContainsKey($key)) { $by[$key] = $f[0].Trim($script:WS) + ' ' + $f[1].Trim($script:WS) }
            }
        }
    }
    catch { }
    return , $by
}

function Get-DayKey($date, [string]$project, [bool]$isMain, [string]$role) {
    $nul = [string][char]0
    if ($isMain) { return $date + $nul + $project.ToLowerInvariant() + $nul + 't' + $nul }
    return $date + $nul + $project.ToLowerInvariant() + $nul + 'a' + $nul + $role.ToLowerInvariant()
}

# ---- sections

function Get-VersionId([bool]$isMain, [string]$role, [string]$harness) {
    $nul = [string][char]0
    if ($isMain) { $k = 't' } else { $k = 'a' }
    return $k + $nul + $role + $nul + $harness
}

function Get-CompareText($prev, $latest) {
    if ($prev.Count -eq 0 -or $latest.Count -eq 0) {
        if ($prev.Count -eq 0) { $side = 'previous' } else { $side = 'latest' }
        return 'not measured (no readable value on the ' + $side + ' side)'
    }
    $a = Get-Median $prev
    $b = Get-Median $latest
    $head = 'median ' + (Format-Fmt1 $a) + ' (n=' + (Format-Int $prev.Count) + ') ' + $script:U_ARR + ' ' + (Format-Fmt1 $b) + ' (n=' + (Format-Int $latest.Count) + '): '
    $reasons = [System.Collections.Generic.List[string]]::new()
    if ($prev.Count -lt 5 -or $latest.Count -lt 5) { $reasons.Add('n < 5') }
    $s1 = Get-Spread $prev
    $s2 = Get-Spread $latest
    if ($s1.Lo -le $s2.Hi -and $s2.Lo -le $s1.Hi) { $reasons.Add('spreads overlap') }
    if ($reasons.Count -gt 0) { return $head + 'noise / inconclusive (' + ($reasons -join '; ') + ')' }
    if ($b -gt $a) { $plus = '+' } else { $plus = '' }
    return $head + 'finding, median difference ' + $plus + (Format-Fmt1 ($b - $a))
}

function Get-CostText($runs, $price) {
    $costed = [System.Collections.Generic.List[object]]::new()
    foreach ($r in $runs) {
        $all = $true
        foreach ($c in $r.Counts) { if ($null -eq $c) { $all = $false } }
        if ($all) { $costed.Add($r) }
    }
    if ($null -eq $price -or $costed.Count -eq 0) { return '-' }
    $sums = New-Object 'object[]' 4
    for ($i = 0; $i -lt 4; $i++) {
        $vals = [System.Collections.Generic.List[decimal]]::new()
        foreach ($r in $costed) { $vals.Add([decimal][long]$r.Counts[$i]) }
        $sums[$i] = Get-SumOrNull $vals
        if ($null -eq $sums[$i]) { return '-' }
    }
    $money = ([decimal]$sums[0] * $price.In + [decimal]$sums[1] * $price.Out + [decimal]$sums[2] * $price.CacheRead + [decimal]$sums[3] * $price.CacheWrite) / [decimal]1000000
    return (Format-Usd $money)
}

function Get-CostedCount($runs) {
    $n = 0
    foreach ($r in $runs) {
        $all = $true
        foreach ($c in $r.Counts) { if ($null -eq $c) { $all = $false } }
        if ($all) { $n++ }
    }
    return $n
}

function Get-DateSpan($runs) {
    $first = $null; $last = $null
    foreach ($r in $runs) {
        if ($null -ne $r.Date) {
            if ($null -eq $first -or [string]::CompareOrdinal($r.Date, $first) -lt 0) { $first = $r.Date }
            if ($null -eq $last -or [string]::CompareOrdinal($r.Date, $last) -gt 0) { $last = $r.Date }
        }
    }
    return (Get-SpanText $first $last)
}

function Get-ReportText($places, [int]$months, $now) {
    $nul = [string][char]0
    $y = $now.Year; $mo = $now.MonthNo
    $total = $y * 12 + ($mo - 1) - ($months - 1)
    $fy = [int][Math]::Floor($total / 12)
    $fm = $total - $fy * 12 + 1
    $from = $fy.ToString('0000', $script:Inv) + '-' + $fm.ToString('00', $script:Inv)
    $to = $now.Month

    $script:Prices = Read-Prices $places
    if (-not $script:Prices.Ok) { Write-Err ('warning: prices.json could not be read; prices and costs are unknown' + $script:LF) }
    $asOf = $script:Prices.AsOf

    # files
    $files = [System.Collections.Generic.List[string]]::new()
    $runsDir = [System.IO.Path]::Combine($places.Lessons, 'runs')
    if ([System.IO.Directory]::Exists($runsDir)) {
        $names = [System.Collections.Generic.List[string]]::new()
        foreach ($p in [System.IO.Directory]::GetFiles($runsDir)) {
            $n = [System.IO.Path]::GetFileName($p)
            $m = $script:RunFileRx.Match($n)
            if ($m.Success) {
                $mm = $m.Groups[1].Value
                if ([string]::CompareOrdinal($mm, $from) -ge 0 -and [string]::CompareOrdinal($mm, $to) -le 0) { $names.Add($n) }
            }
        }
        $sorted = Get-OrdinalSorted $names
        foreach ($n in $sorted) { $files.Add($n) }
    }

    $st = @{
        Rows = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        Runs = [System.Collections.Generic.List[object]]::new()
        Changes = [System.Collections.Generic.List[object]]::new()
        UnreadKeys = [System.Collections.Generic.Dictionary[string, int]]::new($script:Ord)
        Agents = 0; Turns = 0; Skipped = 0; Unread = 0
        FirstTicks = $null; LastTicks = $null; FirstText = $null; LastText = $null
    }
    $unreadable = [System.Collections.Generic.List[string]]::new()
    $lineSplit = [regex]::new('\r\n|\n|\r')
    foreach ($n in $files) {
        try {
            $text = Read-TextFile ([System.IO.Path]::Combine($runsDir, $n))
            foreach ($line in $lineSplit.Split($text)) {
                if ($line.Trim($script:WS).Length -eq 0) { continue }
                Add-ReportLine $st $line
            }
        }
        catch { $unreadable.Add($n) }
    }
    $runs = $st.Runs

    $sb = [System.Text.StringBuilder]::new()
    Add-Line $sb '# Lessons record summary'
    Add-Line $sb ''
    Add-Line $sb ('- Period: ' + $from + ' ~ ' + $to + ' (last ' + (Format-Int $months) + ' month(s), this month included)')
    if ($files.Count -gt 0) {
        $fl = [System.Collections.Generic.List[string]]::new()
        foreach ($n in $files) { $fl.Add('runs/' + $n) }
        Add-Line $sb ('- Files read: ' + ($fl -join ', '))
    }
    else { Add-Line $sb '- Files read: none' }
    if ($unreadable.Count -gt 0) { Add-Line $sb ('- Files that could not be opened: ' + ($unreadable -join ', ')) }
    Add-Line $sb ('- Lines: role runs ' + (Format-Int $st.Agents) + ' ' + $script:U_MID + ' main-conversation turns ' + (Format-Int $st.Turns) + ' ' + $script:U_MID + ' harness changes ' + (Format-Int $st.Changes.Count) + ' ' + $script:U_MID + ' skipped lines ' + (Format-Int $st.Skipped) + ' (not JSON, or unknown kind)')
    if ($null -ne $st.FirstTicks) { Add-Line $sb ('- Record times: ' + $st.FirstText + ' ~ ' + $st.LastText) }
    try {
        $fp = Get-Fingerprint $places
        Add-Line $sb ('- Current harness fingerprint: ' + $fp.Hash + ' (' + (Format-Int $fp.Files.Count) + ' files)')
    }
    catch {
        $why = $_.Exception.Message.Replace([string][char]13, ' ').Replace([string][char]10, ' ')
        Add-Line $sb ('- Current harness fingerprint: unknown (' + $why + ')')
    }

    # ---- Project x role
    Add-Line $sb ''
    Add-Line $sb ('## Project ' + $script:U_TIMES + ' role')
    Add-Line $sb ''
    if ($st.Rows.Count -eq 0) { Add-Line $sb 'No role runs or turns recorded.' }
    else {
        Add-Line $sb ('The role is the `agent` name; the main conversation comes from turn lines. Token columns are `median / total`; the tools, turns and ms columns are medians. Unreadable values (`null`) are left out of the counts; a total too large for 64 bits is shown as `-`.')
        Add-Line $sb ''
        Add-Line $sb '| Project | Role | Count | Model | effort | in | out | cache_read | cache_write | tools | turns | ms | Read failures |'
        Add-Line $sb '|---|---|---|---|---|---|---|---|---|---|---|---|---|'
        $keys = [System.Collections.Generic.List[string]]::new()
        $rowList = [System.Collections.Generic.List[object]]::new()
        foreach ($r in $st.Rows.Values) {
            if ($r.Main) { $mk = '0' } else { $mk = '1' }
            $keys.Add($r.Project + $nul + $mk + $nul + $r.Role)
            $rowList.Add($r)
        }
        $ka = $keys.ToArray(); $ra = $rowList.ToArray()
        [Array]::Sort([array]$ka, [array]$ra, [System.Collections.IComparer]$script:Ord)
        foreach ($r in $ra) {
            $models = Get-OrdinalSorted $r.Models
            $efforts = Get-OrdinalSorted $r.Efforts
            if ($models.Length -gt 0) { $mt = $models -join ', ' } else { $mt = '-' }
            if ($efforts.Length -gt 0) { $et = $efforts -join ', ' } else { $et = '-' }
            $cells = [System.Collections.Generic.List[string]]::new()
            $cells.Add($r.Project); $cells.Add($r.Role); $cells.Add((Format-Int $r.Count)); $cells.Add($mt); $cells.Add($et)
            for ($i = 0; $i -lt 7; $i++) {
                $vals = $r.Values[$i]
                if ($vals.Count -eq 0) { $cells.Add('-'); continue }
                if ($i -lt 4) {
                    $sum = Get-SumOrNull $vals
                    if ($null -eq $sum) { $sumText = '-' } else { $sumText = ([long]$sum).ToString($script:Inv) }
                    $cells.Add((Format-Fmt1 (Get-Median $vals)) + ' / ' + $sumText)
                }
                else { $cells.Add((Format-Fmt1 (Get-Median $vals))) }
            }
            $cells.Add((Format-Int $r.Unread))
            Add-Line $sb (Get-TableRow $cells)
        }
    }

    # ---- versions
    $vmap = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
    foreach ($r in $runs) {
        $id = Get-VersionId $r.Main $r.Role $r.Harness
        if (-not $vmap.ContainsKey($id)) {
            $vmap[$id] = @{ Role = $r.Role; Harness = $r.Harness; Main = $r.Main; Runs = 0; FirstSeq = $r.Seq; LastSeq = $r.Seq
                            RunList = [System.Collections.Generic.List[object]]::new()
                            Tokens = [System.Collections.Generic.List[decimal]]::new(); Times = [System.Collections.Generic.List[decimal]]::new()
                            Signals = [System.Collections.Generic.Dictionary[string, int]]::new($script:Ord) }
        }
        $g = $vmap[$id]
        $g.Runs++
        $g.LastSeq = $r.Seq
        $g.RunList.Add($r)
        if ($null -ne $r.Tokens) { $g.Tokens.Add([decimal]$r.Tokens) }
        if ($null -ne $r.Ms) { $g.Times.Add([decimal]$r.Ms) }
    }
    $vkeys = [System.Collections.Generic.List[string]]::new()
    $vlist = [System.Collections.Generic.List[object]]::new()
    foreach ($g in $vmap.Values) {
        if ($g.Main) { $mk = '0' } else { $mk = '1' }
        $vkeys.Add($mk + $nul + $g.Role + $nul + $g.FirstSeq.ToString('0000000000', $script:Inv))
        $vlist.Add($g)
    }
    $ka = $vkeys.ToArray(); $va = $vlist.ToArray()
    [Array]::Sort([array]$ka, [array]$va, [System.Collections.IComparer]$script:Ord)

    Add-Line $sb ''
    Add-Line $sb ('## Role ' + $script:U_TIMES + ' harness version')
    Add-Line $sb ''
    if ($va.Length -eq 0) { Add-Line $sb 'No role runs or turns recorded.' }
    else {
        Add-Line $sb ('Runs grouped by role and the harness fingerprint written on each run (all projects together), oldest version of a role first. Tokens = in + out + cache_read + cache_write of one run; time = ms. A run with an unread value is left out of that column''s n. Spread is min' + $script:U_EN + 'max when n < 4 and p25' + $script:U_EN + 'p75 when n ' + $script:U_GE + ' 4. The runs are different tasks, so this is observation, not a controlled test. The fingerprint covers the whole setup: a change may come from a file other than the role''s own (see Harness changes).')
        Add-Line $sb ''
        $hdr = 'Role | Harness | Runs | First ' + $script:U_EN + ' last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread'
        Add-Line $sb ('| ' + $hdr + ' |')
        Add-Line $sb '|---|---|---|---|---|---|---|---|---|---|'
        foreach ($g in $va) {
            $cells = [System.Collections.Generic.List[string]]::new()
            $cells.Add($g.Role); $cells.Add($g.Harness); $cells.Add((Format-Int $g.Runs)); $cells.Add((Get-DateSpan $g.RunList))
            foreach ($c in (Get-StatCells $g.Tokens)) { $cells.Add($c) }
            foreach ($c in (Get-StatCells $g.Times)) { $cells.Add($c) }
            Add-Line $sb (Get-TableRow $cells)
        }
        Add-Line $sb ''
        Add-Line $sb '### Version comparisons'
        Add-Line $sb ''
        Add-Line $sb ('For each role whose latest harness version differs from the previous one. A difference is printed as a finding only when both sides have n ' + $script:U_GE + ' 5 and the spreads do not overlap; otherwise it is labelled noise / inconclusive and no difference is given.')
        Add-Line $sb ''
        $applied = Read-AppliedBy $places
        $groupOrder = [System.Collections.Generic.List[string]]::new()
        $groups = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        foreach ($g in $va) {
            if ([string]::Equals($g.Harness, $script:UnknownHarness)) { continue }
            if ($g.Main) { $gk = 't' } else { $gk = 'a' }
            $gk = $gk + $nul + $g.Role
            if (-not $groups.ContainsKey($gk)) { $groups[$gk] = [System.Collections.Generic.List[object]]::new(); $groupOrder.Add($gk) }
            $groups[$gk].Add($g)
        }
        $written = 0
        foreach ($gk in $groupOrder) {
            $all = $groups[$gk]
            if ($all.Count -lt 2) { continue }
            $latest = $all[0]
            foreach ($v in $all) { if ($v.LastSeq -gt $latest.LastSeq) { $latest = $v } }
            $prev = $null
            foreach ($v in $all) {
                if ([object]::ReferenceEquals($v, $latest)) { continue }
                if ($null -eq $prev -or $v.LastSeq -gt $prev.LastSeq) { $prev = $v }
            }
            $written++
            $line = '- ' + $latest.Role + ': ' + $prev.Harness + ' ' + $script:U_ARR + ' ' + $latest.Harness + ' | runs ' + (Format-Int $prev.Runs) + ' ' + $script:U_ARR + ' ' + (Format-Int $latest.Runs) + ' | tokens ' + (Get-CompareText $prev.Tokens $latest.Tokens) + ' | time (ms) ' + (Get-CompareText $prev.Times $latest.Times)
            if ($applied.ContainsKey($latest.Harness)) { $line = $line + ' | applied by ' + $applied[$latest.Harness] }
            Add-Line $sb $line
        }
        if ($written -eq 0) { Add-Line $sb 'none: no role has two harness versions in this period.' }
    }

    # ---- events
    $log = Read-Events $places $from $to
    $days = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
    foreach ($r in $runs) {
        if ($null -eq $r.Date) { continue }
        $dk = Get-DayKey $r.Date $r.Project $r.Main $r.Role
        if (-not $days.ContainsKey($dk)) { $days[$dk] = [System.Collections.Generic.List[object]]::new() }
        $days[$dk].Add($r)
    }

    # ---- Role x model
    Add-Line $sb ''
    Add-Line $sb ('## Role ' + $script:U_TIMES + ' model')
    Add-Line $sb ''
    if ($runs.Count -eq 0) { Add-Line $sb 'No role runs or turns recorded.' }
    else {
        Add-Line $sb ('Runs grouped by role and the model written on each run (all projects and harness versions together): the main conversation''s model changes per session, so the harness fingerprint alone mixes models. Model ids that differ only in case are one row (shown in lower case). Columns as in the harness table: tokens = in + out + cache_read + cache_write of one run, time = ms; a run with an unread value is left out of that column''s n; spread is min' + $script:U_EN + 'max when n < 4 and p25' + $script:U_EN + 'p75 when n ' + $script:U_GE + ' 4. A run without a model is listed as `(model unknown)`. The runs are different tasks, so this is observation, not a controlled test.')
        Add-Line $sb ''
        Add-Line $sb ('The signal columns count the `events.md` events of that role ' + $script:U_TIMES + ' model (see Outcome signals for the signals). An event is joined to the runs of the same date + project + role (case does not matter; `main` is the main conversation) and counted under the model of those runs, whatever the harness version. When the runs it matches that day used more than one model, the model is not guessed: the event is counted in no row and shows in the `Ambiguous model` line under the table. An event with no run to match is not here either (it is counted under Outcome signals). `other signals` sums signal words with no column of its own. `repeated-failure` and `redone` with work type `experiment` are expected iterations and are left out; the other signals with that work type are counted. Events are self-reported, so the counts are a lower bound. `Cost n` is the number of runs the cost adds up (a run with any unread token value is left out), and the cost uses the prices and rules of the cost table below; `-` for a model with no known price or a token total that does not fit in 64 bits.')
        Add-Line $sb ''
        $perRow = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        $ambiguous = [System.Collections.Generic.Dictionary[string, int]]::new($script:Ord)
        $ambTotal = 0
        if ($null -eq $log.Problem) {
            foreach ($e in $log.Events) {
                $dk = Get-DayKey $e.Date $e.Project $e.Main $e.Role
                if (-not $days.ContainsKey($dk)) { continue }
                $rowKeys = [System.Collections.Generic.List[string]]::new()
                foreach ($r in $days[$dk]) {
                    if ($null -eq $r.Model) { $mdl = $script:UnknownModel } else { $mdl = $r.Model }
                    $rk = (Get-VersionId $r.Main $r.Role $mdl)
                    if (-not $rowKeys.Contains($rk)) { $rowKeys.Add($rk) }
                }
                if ($rowKeys.Count -eq 1) {
                    if (-not $perRow.ContainsKey($rowKeys[0])) { $perRow[$rowKeys[0]] = [System.Collections.Generic.Dictionary[string, int]]::new($script:Ord) }
                    $own = $perRow[$rowKeys[0]]
                    if ($own.ContainsKey($e.Signal)) { $own[$e.Signal] = $own[$e.Signal] + 1 } else { $own[$e.Signal] = 1 }
                }
                else {
                    $ambTotal++
                    if ($ambiguous.ContainsKey($e.Signal)) { $ambiguous[$e.Signal] = $ambiguous[$e.Signal] + 1 } else { $ambiguous[$e.Signal] = 1 }
                }
            }
        }
        $mhdr = 'Role | Model | Runs | First ' + $script:U_EN + ' last run | Tokens n | Tokens median | Tokens spread | Time n | Time median | Time spread | fix-request | review-block | review-wrong | repeated-failure | redone | other signals | Cost n | Approx. cost (USD)'
        Add-Line $sb ('| ' + $mhdr + ' |')
        Add-Line $sb '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|'
        $mrows = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        foreach ($r in $runs) {
            if ($null -eq $r.Model) { $mdl = $script:UnknownModel } else { $mdl = $r.Model }
            $rk = Get-VersionId $r.Main $r.Role $mdl
            if (-not $mrows.ContainsKey($rk)) { $mrows[$rk] = @{ Main = $r.Main; Role = $r.Role; Model = $mdl; Runs = [System.Collections.Generic.List[object]]::new(); Key = $rk } }
            $mrows[$rk].Runs.Add($r)
        }
        $mk2 = [System.Collections.Generic.List[string]]::new()
        $ml = [System.Collections.Generic.List[object]]::new()
        foreach ($g in $mrows.Values) {
            if ($g.Main) { $x = '0' } else { $x = '1' }
            $mk2.Add($x + $nul + $g.Role + $nul + $g.Model)
            $ml.Add($g)
        }
        $ka = $mk2.ToArray(); $ma = $ml.ToArray()
        [Array]::Sort([array]$ka, [array]$ma, [System.Collections.IComparer]$script:Ord)
        foreach ($g in $ma) {
            $tokens = [System.Collections.Generic.List[decimal]]::new()
            $times = [System.Collections.Generic.List[decimal]]::new()
            foreach ($r in $g.Runs) {
                if ($null -ne $r.Tokens) { $tokens.Add([decimal]$r.Tokens) }
                if ($null -ne $r.Ms) { $times.Add([decimal]$r.Ms) }
            }
            $cells = [System.Collections.Generic.List[string]]::new()
            $cells.Add($g.Role); $cells.Add($g.Model); $cells.Add((Format-Int $g.Runs.Count)); $cells.Add((Get-DateSpan $g.Runs))
            foreach ($c in (Get-StatCells $tokens)) { $cells.Add($c) }
            foreach ($c in (Get-StatCells $times)) { $cells.Add($c) }
            $own = $null
            if ($perRow.ContainsKey($g.Key)) { $own = $perRow[$g.Key] }
            foreach ($sig in $script:ModelSignals) {
                if ($null -ne $log.Problem) { $cells.Add('-') }
                elseif ($null -ne $own -and $own.ContainsKey($sig)) { $cells.Add((Format-Int $own[$sig])) }
                else { $cells.Add('0') }
            }
            if ($null -ne $log.Problem) { $cells.Add('-') }
            else {
                $other = 0
                if ($null -ne $own) { foreach ($kv in $own.GetEnumerator()) { if ($script:ModelSignals -cnotcontains $kv.Key) { $other += $kv.Value } } }
                $cells.Add((Format-Int $other))
            }
            $cells.Add((Format-Int (Get-CostedCount $g.Runs)))
            $cells.Add((Get-CostText $g.Runs (Get-PriceOf $g.Model)))
            Add-Line $sb (Get-TableRow $cells)
        }
        Add-Line $sb ''
        if ($null -ne $log.Problem) { Add-Line $sb ('- Signal columns show `-`: ' + $log.Problem) }
        else {
            $line = '- Ambiguous model: ' + (Format-Int $ambTotal) + ' event(s) matched runs of more than one model that day, so they are in no row above'
            if ($ambTotal -gt 0) {
                $sk = Get-OrdinalSorted $ambiguous.Keys
                $ps = [System.Collections.Generic.List[string]]::new()
                foreach ($k in $sk) { $ps.Add($k + ' ' + (Format-Int $ambiguous[$k])) }
                $line = $line + ' (' + ($ps -join (' ' + $script:U_MID + ' ')) + ')'
            }
            Add-Line $sb $line
        }

        Add-Line $sb ''
        Add-Line $sb '### Approximate cost per model'
        Add-Line $sb ''
        Add-Line $sb ('Approximate: tokens ' + $script:U_TIMES + ' list price (USD per million tokens as of ' + $asOf + '), summed per model over all projects and roles; the cost column of the role ' + $script:U_TIMES + ' model table above splits the same sum by role. Cache writes are priced at the 5-minute rate because the 1-hour split is not recorded. Haiku 5.5 is priced at the rate for prompts up to 100K tokens, so its cost is a lower bound. A model id is matched by family and version (`claude-opus-5-5`, with or without a date or `[1m]` after it); an id with no known price shows `-`, never a guess, and so does a model with no run to count or a token total that does not fit in 64 bits. A run with any unread token value is left out of the cost and counted under `Left out`.')
        Add-Line $sb ''
        Add-Line $sb '| Model | Priced as | List price per M tokens (in / out / cache write / cache read) | Runs | Left out | Approx. cost (USD) |'
        Add-Line $sb '|---|---|---|---|---|---|'
        $byModel = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord)
        foreach ($r in $runs) {
            if ($null -eq $r.Model) { $mdl = $script:UnknownModel } else { $mdl = $r.Model }
            if (-not $byModel.ContainsKey($mdl)) { $byModel[$mdl] = [System.Collections.Generic.List[object]]::new() }
            $byModel[$mdl].Add($r)
        }
        $mkeys = Get-OrdinalSorted $byModel.Keys
        foreach ($mdl in $mkeys) {
            $price = Get-PriceOf $mdl
            $rl = $byModel[$mdl]
            $cells = [System.Collections.Generic.List[string]]::new()
            $cells.Add($mdl)
            if ($null -eq $price) { $cells.Add('-'); $cells.Add('-') }
            else {
                $cells.Add($price.Name)
                $pp = [System.Collections.Generic.List[string]]::new()
                foreach ($x in @($price.In, $price.Out, $price.CacheWrite, $price.CacheRead)) {
                    $pp.Add(([Math]::Round([decimal]$x, 3, [System.MidpointRounding]::AwayFromZero)).ToString('0.###', $script:Inv))
                }
                $cells.Add($pp -join ' / ')
            }
            $cn = Get-CostedCount $rl
            $cells.Add((Format-Int $rl.Count)); $cells.Add((Format-Int ($rl.Count - $cn))); $cells.Add((Get-CostText $rl $price))
            Add-Line $sb (Get-TableRow $cells)
        }
    }

    # ---- Outcome signals
    Add-Line $sb ''
    Add-Line $sb '## Outcome signals (events.md)'
    Add-Line $sb ''
    if ($null -ne $log.Problem) { Add-Line $sb $log.Problem }
    else {
        $joined = 0; $noRun = 0; $changedDay = 0
        foreach ($e in $log.Events) {
            $dk = Get-DayKey $e.Date $e.Project $e.Main $e.Role
            if (-not $days.ContainsKey($dk)) { $noRun++; continue }
            $seen = [System.Collections.Generic.List[string]]::new()
            foreach ($r in $days[$dk]) {
                $vid = Get-VersionId $r.Main $r.Role $r.Harness
                if (-not $seen.Contains($vid)) { $seen.Add($vid) }
            }
            if ($seen.Count -gt 1) { $changedDay++; continue }
            $joined++
            $sg = $vmap[$seen[0]].Signals
            if ($sg.ContainsKey($e.Signal)) { $sg[$e.Signal] = $sg[$e.Signal] + 1 } else { $sg[$e.Signal] = 1 }
        }
        Add-Line $sb ('events.md is written by the orchestrator about its own work, so these counts are a lower bound, not everything that went wrong. Each event is joined by date + project + role (case does not matter; `main` is the main conversation) to the harness version of that role''s runs that day. Per run = events of that signal / runs of that role under that version. A `repeated-failure` or `redone` event whose work type is `experiment` is an expected iteration, not a harness failure: it is left out of the counts and rates here and shown on a line of its own. The other signals (`fix-request` ' + $script:U_MID + ' `review-block` ' + $script:U_MID + ' `review-wrong`) with work type `experiment` are harness signals and are counted as usual.')
        Add-Line $sb ''
        if ($joined -gt 0) {
            Add-Line $sb '| Role | Harness | Runs | Signal | Events | Per run |'
            Add-Line $sb '|---|---|---|---|---|---|'
            foreach ($g in $va) {
                if ($g.Signals.Count -eq 0) { continue }
                $sk = Get-OrdinalSorted $g.Signals.Keys
                foreach ($s in $sk) {
                    $cnt = $g.Signals[$s]
                    Add-Line $sb (Get-TableRow @($g.Role, $g.Harness, (Format-Int $g.Runs), $s, (Format-Int $cnt), (Format-Fmt2 ([decimal]$cnt / [decimal]$g.Runs))))
                }
            }
            Add-Line $sb ''
        }
        Add-Line $sb ('- Events in the period: ' + (Format-Int $log.Events.Count) + ' ' + $script:U_MID + ' joined to a harness version ' + (Format-Int $joined) + ' ' + $script:U_MID + ' no run of that role in that project that day ' + (Format-Int $noRun) + ' ' + $script:U_MID + ' harness changed that day, so not attributed ' + (Format-Int $changedDay))
        Add-Line $sb ('- Expected experiment iterations (`repeated-failure` ' + $script:U_MID + ' `redone` with work type `experiment`; not in the counts above): ' + (Format-Int $log.Expected))
        Add-Line $sb ('- Lines starting with `- ` that are not in the format (`- YYYY-MM-DD | project | signal | work type ' + $script:U_MID + ' size | role | fact`): ' + (Format-Int $log.Bad))
    }

    # ---- Read failures
    Add-Line $sb ''
    Add-Line $sb '## Read failures'
    Add-Line $sb ''
    Add-Line $sb ('- Lines with unread keys: ' + (Format-Int $st.Unread) + ' / ' + (Format-Int ($st.Agents + $st.Turns)) + ' (role-run and turn lines whose `missing` is not empty)')
    if ($st.UnreadKeys.Count -gt 0) {
        $uk = Get-OrdinalSorted $st.UnreadKeys.Keys
        $ps = [System.Collections.Generic.List[string]]::new()
        foreach ($k in $uk) { $ps.Add($k + ' ' + (Format-Int $st.UnreadKeys[$k])) }
        Add-Line $sb ('- Unread keys: ' + ($ps -join (' ' + $script:U_MID + ' ')))
    }
    else { Add-Line $sb '- Unread keys: none' }

    # ---- Harness changes
    Add-Line $sb ''
    Add-Line $sb '## Harness changes'
    Add-Line $sb ''
    if ($st.Changes.Count -eq 0) { Add-Line $sb 'none' }
    foreach ($c in $st.Changes) {
        $parts = [System.Collections.Generic.List[string]]::new()
        if ($null -ne $c.When) { $parts.Add($c.When) } else { $parts.Add('(time unknown)') }
        if ($null -ne $c.Prev) { $pv = $c.Prev } else { $pv = '(first)' }
        if ($null -ne $c.Hash) { $hv = $c.Hash } else { $hv = '?' }
        $parts.Add($pv + ' ' + $script:U_ARR + ' ' + $hv)
        if ($c.Changed.Count -gt 0) { $parts.Add('changed ' + ($c.Changed -join ', ')) }
        if ($c.Added.Count -gt 0) { $parts.Add('added ' + ($c.Added -join ', ')) }
        if ($c.Removed.Count -gt 0) { $parts.Add('removed ' + ($c.Removed -join ', ')) }
        if ($null -ne $c.Version) { $parts.Add('plugin ' + $c.Version) }
        Add-Line $sb ('- ' + ($parts -join ' | '))
    }
    return $sb.ToString()
}

function Invoke-Report($argv) {
    $usage = 'usage: spanharness.ps1 report [OUT.md] [--months N] [--claude-dir D] [--lessons-dir D] [--plugin-root D] [--project-dir D] [--now ISO8601]' + $script:LF
    $opt = Read-Options $argv
    if ($null -ne $opt.Error -or $opt.Positional.Count -gt 1) { Write-Err $usage; return 2 }
    $months = 2
    if ($null -ne $opt.MonthsText) {
        $mt = $opt.MonthsText
        if (-not [regex]::IsMatch($mt, '^[0-9]+\z')) { Write-Err $usage; return 2 }
        $mt = $mt.TrimStart('0')
        if ($mt.Length -eq 0 -or $mt.Length -gt 3) { Write-Err $usage; return 2 }
        $months = [int]$mt
        if ($months -lt 1 -or $months -gt 120) { Write-Err $usage; return 2 }
    }
    if ($opt.HasNow) {
        $script:FixedNow = ConvertFrom-NowText $opt.NowText
        if ($null -eq $script:FixedNow) { Write-Err $usage; return 2 }
    }
    $places = New-Places $opt $null
    if ($null -eq $places.Project) { $places.Project = [System.IO.Directory]::GetCurrentDirectory() }
    $outPath = $null
    try {
        if ($opt.Positional.Count -eq 1) {
            if ($opt.Positional[0].IndexOf([char]0) -ge 0) { Write-Err $usage; return 2 }
            $outPath = [System.IO.Path]::GetFullPath($opt.Positional[0])
        }
        else { $outPath = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($places.Lessons, 'report.md')) }
    }
    catch { Write-Err $usage; return 2 }
    try {
        $text = Get-ReportText $places $months (Get-NowInfo)
        Save-TextAtomic $outPath $text
    }
    catch {
        Write-Err ('could not write the report (' + $outPath + '): ' + $_.Exception.Message.Replace([string][char]13, ' ').Replace([string][char]10, ' ') + $script:LF)
        return 1
    }
    Write-Out ($outPath + $script:LF)
    return 0
}

# ---------------------------------------------------------------- lint (tests/harness-rules.md)

# glob of the rules file as a regex over relative paths with '/' separators
function ConvertTo-GlobRegex([string]$pattern) {
    $parts = $pattern.Split([char]47)
    $sb = [System.Text.StringBuilder]::new()
    [void]$sb.Append('^')
    for ($i = 0; $i -lt $parts.Length; $i++) {
        $p = $parts[$i]
        $isLast = ($i -eq $parts.Length - 1)
        if ($p -ceq '**') {
            if ($isLast) { [void]$sb.Append('.+') } else { [void]$sb.Append('(?:[^/]+/)*') }
            continue
        }
        $segs = $p.Split([char]42)
        for ($j = 0; $j -lt $segs.Length; $j++) {
            if ($j -gt 0) { [void]$sb.Append('[^/]*') }
            [void]$sb.Append([regex]::Escape($segs[$j]))
        }
        if (-not $isLast) { [void]$sb.Append('/') }
    }
    [void]$sb.Append('\z')
    return [regex]::new($sb.ToString(), [System.Text.RegularExpressions.RegexOptions]::CultureInvariant)
}

# every regular file under the root except .git/, as relative paths with '/'
function Get-LintFiles([string]$root) {
    $out = [System.Collections.Generic.List[string]]::new()
    $stack = [System.Collections.Generic.Stack[string]]::new()
    $stack.Push('')
    while ($stack.Count -gt 0) {
        $rel = $stack.Pop()
        if ($rel.Length -eq 0) { $dir = $root } else { $dir = [System.IO.Path]::Combine($root, $rel) }
        foreach ($f in [System.IO.Directory]::GetFiles($dir)) {
            $n = [System.IO.Path]::GetFileName($f)
            if ($rel.Length -eq 0) { $out.Add($n) } else { $out.Add($rel + '/' + $n) }
        }
        foreach ($d in [System.IO.Directory]::GetDirectories($dir)) {
            $n = [System.IO.Path]::GetFileName($d)
            if ($rel.Length -eq 0 -and $n -ceq '.git') { continue }
            if ($rel.Length -eq 0) { $stack.Push($n) } else { $stack.Push($rel + '/' + $n) }
        }
    }
    $arr = $out.ToArray()
    [Array]::Sort($arr, $script:Ord)
    return , $arr
}

function Get-RuleList($rule, [string]$key) {
    $r = [System.Collections.Generic.List[string]]::new()
    if ($rule.ContainsKey($key)) {
        $v = $rule[$key]
        if ($v -is [System.Collections.IList]) { foreach ($x in $v) { $r.Add([string]$x) } }
        elseif ($v -is [string]) { $r.Add($v) }
    }
    return , $r
}

# targets of a rule: @{ Targets; Errors }
function Get-RuleTargets($rule, $allFiles, [string]$root) {
    $errors = [System.Collections.Generic.List[string]]::new()
    $targets = [System.Collections.Generic.List[string]]::new()
    $set = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
    foreach ($p in (Get-RuleList $rule 'paths')) {
        if ($p.IndexOf('*') -ge 0) {
            $rx = ConvertTo-GlobRegex $p
            foreach ($f in $allFiles) { if ($rx.IsMatch($f)) { [void]$set.Add($f) } }
        }
        elseif ([System.IO.File]::Exists([System.IO.Path]::Combine($root, $p))) { [void]$set.Add($p) }
        else { $errors.Add($p + ': missing file') }
    }
    $excl = [System.Collections.Generic.List[object]]::new()
    foreach ($p in (Get-RuleList $rule 'exclude')) { $excl.Add((ConvertTo-GlobRegex $p)) }
    foreach ($f in $allFiles) {
        if (-not $set.Contains($f)) { continue }
        $skip = $false
        foreach ($rx in $excl) { if ($rx.IsMatch($f)) { $skip = $true } }
        if (-not $skip) { $targets.Add($f) }
    }
    if ($targets.Count -eq 0 -and $errors.Count -eq 0) { $errors.Add('-: no files match') }
    return @{ Targets = $targets; Errors = $errors }
}

function Get-LintText([string]$root, [string]$rel) {
    $b = [System.IO.File]::ReadAllBytes([System.IO.Path]::Combine($root, $rel))
    $t = ConvertFrom-Utf8Bytes $b 0 $b.Length
    return $t.Replace("`r`n", "`n").Replace("`r", "`n")
}

# the section of a heading line: the heading and the lines up to the next line starting with '## '
function Get-LintSection([string]$text, [string]$heading) {
    $lines = $text.Split([char]10)
    $idx = -1
    $count = 0
    for ($i = 0; $i -lt $lines.Length; $i++) {
        if ($lines[$i] -ceq $heading) { $count++; $idx = $i }
    }
    if ($count -ne 1) { return $null }
    $endLine = $lines.Length
    for ($i = $idx + 1; $i -lt $lines.Length; $i++) {
        if (Test-StartsO $lines[$i] '## ') { $endLine = $i; break }
    }
    $sel = [System.Collections.Generic.List[string]]::new()
    for ($i = $idx; $i -lt $endLine; $i++) { $sel.Add($lines[$i]) }
    $res = $sel -join "`n"
    if ($endLine -lt $lines.Length) { $res = $res + "`n" }
    return $res
}

function Get-OccurrenceCount([string]$text, [string]$lit) {
    if ($lit.Length -eq 0) { return 0 }
    $n = 0
    $pos = 0
    while ($true) {
        $i = $text.IndexOf($lit, $pos, [System.StringComparison]::Ordinal)
        if ($i -lt 0) { break }
        $n++
        $pos = $i + $lit.Length
    }
    return $n
}

function Remove-LintQuotes([string]$v) {
    if ($v.Length -ge 2 -and $v[0] -eq '"' -and $v[$v.Length - 1] -eq '"') { return $v.Substring(1, $v.Length - 2) }
    return $v
}

# the frontmatter of the lint rules: @{ Ok; Error; Keys; Map } (Map values: string or List[string])
function ConvertFrom-LintFrontmatter([string]$text) {
    $r = @{ Ok = $false; Error = $null; Keys = [System.Collections.Generic.List[string]]::new(); Map = [System.Collections.Generic.Dictionary[string, object]]::new($script:Ord) }
    $lines = $text.Split([char]10)
    if ($lines.Length -eq 0 -or -not ($lines[0] -ceq '---')) { $r.Error = 'no frontmatter'; return $r }
    $end = -1
    for ($i = 1; $i -lt $lines.Length; $i++) { if ($lines[$i] -ceq '---') { $end = $i; break } }
    if ($end -lt 0) { $r.Error = 'frontmatter is not closed'; return $r }
    $keyRx = [regex]::new('^([A-Za-z0-9_-]+):(.*)\z')
    $itemRx = [regex]::new('^ +- (.*)\z')
    $cur = $null
    for ($i = 1; $i -lt $end; $i++) {
        $l = $lines[$i]
        if ($l.Trim($script:WS).Length -eq 0) { continue }
        $m = $keyRx.Match($l)
        if ($m.Success) {
            $k = $m.Groups[1].Value
            if ($r.Map.ContainsKey($k)) { $r.Error = 'duplicate key ' + $k; return $r }
            $v = Remove-LintQuotes $m.Groups[2].Value.Trim($script:WS)
            $r.Keys.Add($k)
            $r.Map[$k] = $v
            $cur = $k
            continue
        }
        $m2 = $itemRx.Match($l)
        if ($m2.Success -and $null -ne $cur) {
            $existing = $r.Map[$cur]
            if ($existing -is [string]) {
                if ($existing.Length -gt 0) { $r.Error = 'list item after a value at line ' + ($i + 1); return $r }
                $existing = [System.Collections.Generic.List[string]]::new()
                $r.Map[$cur] = $existing
            }
            $existing.Add((Remove-LintQuotes $m2.Groups[1].Value.Trim($script:WS)))
            continue
        }
        $r.Error = 'cannot parse frontmatter line ' + ($i + 1)
        return $r
    }
    $r.Ok = $true
    return $r
}

function Get-JsonPathValues($node, $segs, [int]$i, $acc) {
    if ($i -ge $segs.Length) { $acc.Add($node); return }
    $s = $segs[$i]
    if ($s -ceq '*') {
        if ($node -is [System.Collections.IDictionary]) { foreach ($v in @($node.Values)) { Get-JsonPathValues $v $segs ($i + 1) $acc } }
        elseif ($node -is [System.Collections.IList]) { foreach ($v in $node) { Get-JsonPathValues $v $segs ($i + 1) $acc } }
        return
    }
    if ($node -is [System.Collections.IDictionary]) {
        if ($node.ContainsKey($s)) { Get-JsonPathValues $node[$s] $segs ($i + 1) $acc }
        return
    }
    if ($node -is [System.Collections.IList]) {
        if ([regex]::IsMatch($s, '^[0-9]+\z')) {
            $idx = [decimal]$s
            if ($idx -lt $node.Count) { Get-JsonPathValues $node[[int]$idx] $segs ($i + 1) $acc }
        }
    }
}

function Test-JsonEqual($a, $b) {
    if ($null -eq $a -and $null -eq $b) { return $true }
    if ($null -eq $a -or $null -eq $b) { return $false }
    if (($a -is [string]) -and ($b -is [string])) { return [string]::Equals($a, $b) }
    if (($a -is [bool]) -and ($b -is [bool])) { return ($a -eq $b) }
    if (($a -is [System.Collections.IDictionary]) -and ($b -is [System.Collections.IDictionary])) {
        if ($a.Count -ne $b.Count) { return $false }
        foreach ($k in @($a.Keys)) { if (-not $b.Contains($k)) { return $false }; if (-not (Test-JsonEqual $a[$k] $b[$k])) { return $false } }
        return $true
    }
    if (($a -is [System.Collections.IList]) -and ($b -is [System.Collections.IList])) {
        if ($a.Count -ne $b.Count) { return $false }
        for ($i = 0; $i -lt $a.Count; $i++) { if (-not (Test-JsonEqual $a[$i] $b[$i])) { return $false } }
        return $true
    }
    $da = ConvertTo-ExactDecimal $a
    $db = ConvertTo-ExactDecimal $b
    if ($null -ne $da -and $null -ne $db -and ($a -isnot [bool]) -and ($b -isnot [bool])) { return ($da -eq $db) }
    return $false
}

# runs one rule; returns the list of failure reasons (empty = pass)
function Test-LintRule($rule, [string]$root, $allFiles) {
    $fails = [System.Collections.Generic.List[string]]::new()
    $kind = [string]$rule['kind']

    if ($kind -ceq 'files') {
        if ($rule.ContainsKey('dir')) {
            $dir = [string]$rule['dir']
            $dp = [System.IO.Path]::Combine($root, $dir)
            if (-not [System.IO.Directory]::Exists($dp)) { $fails.Add('missing folder ' + $dir); return , $fails }
            $have = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
            foreach ($f in [System.IO.Directory]::GetFiles($dp)) {
                $n = [System.IO.Path]::GetFileName($f)
                if (-not (Test-StartsO $n '.')) { [void]$have.Add($n) }
            }
            $only = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
            foreach ($n in (Get-RuleList $rule 'only')) { [void]$only.Add($n) }
            foreach ($n in $have) { if (-not $only.Contains($n)) { $fails.Add($dir + '/' + $n + ': not in the list') } }
            foreach ($n in $only) { if (-not $have.Contains($n)) { $fails.Add($dir + '/' + $n + ': missing') } }
        }
        else {
            foreach ($p in (Get-RuleList $rule 'paths')) {
                if (-not [System.IO.File]::Exists([System.IO.Path]::Combine($root, $p))) { $fails.Add($p + ': missing') }
            }
        }
        return , $fails
    }

    $tg = Get-RuleTargets $rule $allFiles $root
    foreach ($e in $tg.Errors) { $fails.Add($e) }
    foreach ($rel in $tg.Targets) {
        try { $reasons = Test-LintTarget $rule $kind $root $rel }
        catch { $reasons = [System.Collections.Generic.List[string]]::new(); $reasons.Add('cannot read: ' + $_.Exception.Message) }
        foreach ($x in $reasons) { $fails.Add($rel + ': ' + $x) }
    }
    return , $fails
}

function Test-LintTarget($rule, [string]$kind, [string]$root, [string]$rel) {
    $f = [System.Collections.Generic.List[string]]::new()

    if ($kind -ceq 'asciiOnly') {
        $b = [System.IO.File]::ReadAllBytes([System.IO.Path]::Combine($root, $rel))
        for ($i = 0; $i -lt $b.Length; $i++) {
            $x = $b[$i]
            if (-not ($x -eq 9 -or $x -eq 10 -or $x -eq 13 -or ($x -ge 32 -and $x -le 126))) { $f.Add('non-ASCII byte at offset ' + $i); break }
        }
        return , $f
    }

    if ($kind -ceq 'json') {
        $t = Read-TextFile ([System.IO.Path]::Combine($root, $rel))
        if (-not (Try-ParseJson $t 200)) { $f.Add('not valid JSON'); return , $f }
        $doc = $script:JsonValue
        $path = [string]$rule['path']
        $segs = $path.Split([char]46)
        $vals = [System.Collections.Generic.List[object]]::new()
        Get-JsonPathValues $doc $segs 0 $vals
        if ($rule.ContainsKey('equals')) {
            if ($vals.Count -ne 1) { $f.Add('path ' + $path + ' gives ' + $vals.Count + ' values') }
            elseif (-not (Test-JsonEqual $vals[0] $rule['equals'])) { $f.Add('path ' + $path + ' differs from the expected value') }
        }
        elseif ($rule.ContainsKey('anyContains')) {
            $lit = [string]$rule['anyContains']
            $any = $false
            foreach ($v in $vals) { if (($v -is [string]) -and $v.Contains($lit)) { $any = $true } }
            if (-not $any) { $f.Add('no value at ' + $path + ' contains ' + $lit) }
        }
        return , $f
    }

    $text = Get-LintText $root $rel

    if ($kind -ceq 'frontmatter') {
        $fm = ConvertFrom-LintFrontmatter $text
        if (-not $fm.Ok) { $f.Add($fm.Error); return , $f }
        if ($rule.ContainsKey('keys')) {
            $want = Get-RuleList $rule 'keys'
            if (($want -join "`n") -cne ($fm.Keys -join "`n") -or $want.Count -ne $fm.Keys.Count) { $f.Add('keys are ' + ($fm.Keys -join ',')) }
        }
        if ($rule.ContainsKey('equals')) {
            $eq = $rule['equals']
            foreach ($k in $eq.Keys) {
                if (-not $fm.Map.ContainsKey($k)) { $f.Add('missing key ' + $k); continue }
                $have = $fm.Map[$k]
                $exp = $eq[$k]
                if ($exp -is [string]) {
                    if (-not (($have -is [string]) -and [string]::Equals($have, $exp))) { $f.Add('key ' + $k + ' differs') }
                }
                elseif ($exp -is [System.Collections.IList]) {
                    $okList = ($have -is [System.Collections.Generic.List[string]]) -and ($have.Count -eq $exp.Count)
                    if ($okList) { for ($i = 0; $i -lt $exp.Count; $i++) { if (-not [string]::Equals($have[$i], [string]$exp[$i])) { $okList = $false } } }
                    if (-not $okList) { $f.Add('key ' + $k + ' differs') }
                }
            }
        }
        foreach ($k in (Get-RuleList $rule 'absent')) { if ($fm.Map.ContainsKey($k)) { $f.Add('key ' + $k + ' must be absent') } }
        foreach ($k in (Get-RuleList $rule 'nonEmpty')) {
            if (-not $fm.Map.ContainsKey($k)) { $f.Add('missing key ' + $k); continue }
            $have = $fm.Map[$k]
            if ((($have -is [string]) -and $have.Length -eq 0) -or (($have -is [System.Collections.IList]) -and $have.Count -eq 0)) { $f.Add('key ' + $k + ' is empty') }
        }
        return , $f
    }

    if ($kind -ceq 'sectionsInOrder') {
        $heads = [System.Collections.Generic.List[string]]::new()
        foreach ($l in $text.Split([char]10)) { if (Test-StartsO $l '## ') { $heads.Add($l) } }
        $want = Get-RuleList $rule 'sections'
        $exact = $rule.ContainsKey('exact') -and ($rule['exact'] -is [bool]) -and $rule['exact']
        if ($exact) {
            if (($want -join "`n") -cne ($heads -join "`n") -or $want.Count -ne $heads.Count) { $f.Add('headings are ' + ($heads -join ' / ')) }
        }
        else {
            $pos = 0
            foreach ($w in $want) {
                $found = $false
                while ($pos -lt $heads.Count) {
                    $h = $heads[$pos]
                    $pos++
                    if ($h -ceq $w) { $found = $true; break }
                }
                if (-not $found) { $f.Add('heading missing or out of order: ' + $w) }
            }
        }
        return , $f
    }

    if ($kind -ceq 'endsWithLine') {
        $line = [string]$rule['line']
        if (-not ((Test-EndsO $text ("`n" + $line + "`n")) -and -not (Test-EndsO $text "`n`n"))) { $f.Add('the last line is not the expected line') }
        return , $f
    }

    # contains, containsOnce, mustNotContain: optionally within one section
    $scope = $text
    if ($rule.ContainsKey('section')) {
        $scope = Get-LintSection $text ([string]$rule['section'])
        if ($null -eq $scope) { $f.Add('section heading must occur exactly once: ' + $rule['section']); return , $f }
    }
    $lits = [System.Collections.Generic.List[string]]::new()
    if ($rule.ContainsKey('text')) { $lits.Add([string]$rule['text']) }
    foreach ($x in (Get-RuleList $rule 'texts')) { $lits.Add($x) }

    if ($kind -ceq 'contains') {
        foreach ($l in $lits) { if ($scope.IndexOf($l, [System.StringComparison]::Ordinal) -lt 0) { $f.Add('missing text: ' + $l) } }
    }
    elseif ($kind -ceq 'containsOnce') {
        foreach ($l in $lits) {
            $n = Get-OccurrenceCount $scope $l
            if ($n -ne 1) { $f.Add('text occurs ' + $n + ' times: ' + $l) }
        }
    }
    elseif ($kind -ceq 'mustNotContain') {
        $ic = $rule.ContainsKey('ignoreCase') -and ($rule['ignoreCase'] -is [bool]) -and $rule['ignoreCase']
        foreach ($l in $lits) {
            if ($ic) { $hit = ($scope.IndexOf($l, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) }
            else { $hit = ($scope.IndexOf($l, [System.StringComparison]::Ordinal) -ge 0) }
            if ($hit) { $f.Add('forbidden text: ' + $l) }
        }
        if ($rule.ContainsKey('regex')) {
            $opts = [System.Text.RegularExpressions.RegexOptions]::CultureInvariant
            if ($ic) { $opts = $opts -bor [System.Text.RegularExpressions.RegexOptions]::IgnoreCase }
            $rx = [regex]::new([string]$rule['regex'], $opts)
            if ($rx.IsMatch($scope)) { $f.Add('forbidden pattern: ' + $rule['regex']) }
        }
    }
    else { $f.Add('unknown rule kind ' + $kind) }
    return , $f
}

function Invoke-Lint($argv) {
    $usage = 'usage: spanharness.ps1 lint [--root DIR] [--group NAME]' + $script:LF
    $opt = Read-Options $argv
    if ($null -ne $opt.Error -or $opt.Positional.Count -gt 0) { Write-Err $usage; return 2 }
    $places = New-Places $opt $null
    $root = $opt.Root
    if ($null -eq $root) { $root = $places.Plugin }
    try { $root = [System.IO.Path]::GetFullPath($root) } catch { Write-Err $usage; return 2 }
    try {
        $rulesPath = [System.IO.Path]::Combine($root, 'tests', 'harness-rules.json')
        $rt = Read-TextFile $rulesPath
        if (-not (Try-ParseJson $rt 200) -or $script:JsonValue -isnot [System.Collections.IDictionary]) { throw 'harness-rules.json is not a JSON object' }
        $doc = $script:JsonValue
        $groups = [System.Collections.Generic.HashSet[string]]::new($script:Ord)
        [void]$groups.Add('core')
        foreach ($g in $opt.Groups) { [void]$groups.Add($g) }
        $known = $doc['groups']
        foreach ($g in $groups) {
            if ($known -isnot [System.Collections.IDictionary] -or -not $known.ContainsKey($g)) { Write-Err ('unknown group ' + $g + $script:LF); return 2 }
        }
        $allFiles = Get-LintFiles $root
        $failedRules = 0
        $skipped = 0
        $ran = 0
        foreach ($rule in $doc['rules']) {
            $grp = 'core'
            if ($rule.ContainsKey('group')) { $grp = [string]$rule['group'] }
            if ($known -isnot [System.Collections.IDictionary] -or -not $known.ContainsKey($grp)) { throw ('rule ' + $rule['id'] + ' has an unknown group ' + $grp) }
            if (-not $groups.Contains($grp)) { $skipped++; continue }
            $ran++
            $fails = Test-LintRule $rule $root $allFiles
            if ($fails.Count -gt 0) {
                $failedRules++
                $more = ''
                if ($fails.Count -gt 1) { $more = ' (and ' + ($fails.Count - 1) + ' more)' }
                $msg = $fails[0].Replace([string][char]13, '\r').Replace([string][char]10, '\n')
                Write-Out ([string]$rule['id'] + ' ' + $msg + $more + $script:LF)
            }
        }
        Write-Err ('lint: ' + $ran + ' rules checked, ' + $failedRules + ' failed, ' + $skipped + ' skipped' + $script:LF)
        if ($failedRules -gt 0) { return 1 }
        return 0
    }
    catch {
        Write-Err ('lint failed: ' + $_.Exception.Message.Replace([string][char]13, ' ').Replace([string][char]10, ' ') + $script:LF)
        return 1
    }
}

# ---------------------------------------------------------------- main

function Invoke-Main($argv) {
    $usage = 'usage: spanharness.ps1 record | report [OUT.md] [--months N] | lint [--root DIR]' + $script:LF
    if ($argv.Count -eq 0) { Write-Err $usage; return 2 }
    $cmd = [string]$argv[0]
    $rest = [System.Collections.Generic.List[string]]::new()
    for ($i = 1; $i -lt $argv.Count; $i++) { $rest.Add([string]$argv[$i]) }
    $code = $null
    if ($cmd -ceq 'record') { $code = Invoke-Record $rest }
    elseif ($cmd -ceq 'report') { $code = Invoke-Report $rest }
    elseif ($cmd -ceq 'lint') { $code = Invoke-Lint $rest }
    if ($null -ne $code) {
        if ($code -is [array]) { $code = $code[$code.Length - 1] }
        return [int]$code
    }
    Write-Err $usage
    return 2
}

$script:ExitCode = 0
try { $script:ExitCode = [int](Invoke-Main $args) }
catch { $script:ExitCode = 1 }
exit $script:ExitCode
