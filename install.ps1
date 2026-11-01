# root-harness one-line installer, for Windows 10 and 11 (Windows PowerShell 5.1 or PowerShell 7).
#
# Paste this into PowerShell (no administrator needed):
#   irm https://raw.githubusercontent.com/redjohn-sudo/root-harness/main/install.ps1 | iex
#
# It installs root-harness next to your home folder, adds it to the Start menu and
# the desktop, and opens it. Your Claude is connected through your own logged-in
# Claude Code: no API key to paste, nothing billed to anyone else. Other brains
# (DeepSeek, Kimi, GLM, Ollama) stay optional and use their own keys, entered
# later in the app.
#
# What it may install for you, for your user only (winget, no administrator):
# Python 3.12 and Git when they are missing, and Claude Code with its official
# installer.
#
# Settings, all optional (set them first, e.g.  $env:ROOT_HARNESS_NO_LAUNCH = '1'):
#   ROOT_HARNESS_DIR=<folder>    where to install (default: ~\root-harness)
#   ROOT_HARNESS_NO_LAUNCH=1     install everything, do not open the app
#   ROOT_HARNESS_SKIP_CLAUDE=1   do not look for or install Claude Code
#   ROOT_HARNESS_NO_UPDATE=1     use the copy already in ROOT_HARNESS_DIR as it is
#                                (no clone, no download: for a checkout you work on)

$RootHarnessAsFile = [bool]$PSCommandPath     # run as a file (exit codes) or through iex (keep the window)

$RootHarnessOk = & {
    # Everything runs in this child scope: through `iex`, nothing leaks into your session.
    $ErrorActionPreference = 'Stop'
    try {
        $ProgressPreference = 'SilentlyContinue'
        try {
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        } catch { }

        $Repo = 'https://github.com/redjohn-sudo/root-harness'

        function Say([string]$Message) { Write-Host $Message -ForegroundColor Cyan }
        function Warn([string]$Message) { Write-Host $Message -ForegroundColor Yellow }
        function Fail([string]$Message) { throw (New-Object System.Exception $Message) }
        function On([string]$Name) { [Environment]::GetEnvironmentVariable($Name) -eq '1' }

        # Run a program, its output on screen, and give back its exit code. Native programs
        # write progress on stderr: under 'Stop', Windows PowerShell 5.1 would take that for
        # a failure, so they run under 'Continue' and only the exit code counts.
        function Invoke-Tool {
            param([string]$Exe, [string[]]$Arguments = @(), [switch]$Quiet)
            $previous = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                if ($Quiet) { & $Exe @Arguments *> $null } else { & $Exe @Arguments | Out-Host }
                return [int]$LASTEXITCODE
            } catch {
                return 1
            } finally {
                $ErrorActionPreference = $previous
            }
        }

        # A program's output as text, or $null when it fails.
        function Get-ToolOutput {
            param([string]$Exe, [string[]]$Arguments = @())
            $previous = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            try {
                $out = & $Exe @Arguments 2> $null
                if ($LASTEXITCODE -ne 0) { return $null }
                return (($out | Out-String).Trim())
            } catch {
                return $null
            } finally {
                $ErrorActionPreference = $previous
            }
        }

        # What winget just installed is on the PATH saved for your user, not yet in this window.
        function Update-SessionPath {
            $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
            $user = [Environment]::GetEnvironmentVariable('Path', 'User')
            $env:Path = (@($env:Path, $machine, $user) | Where-Object { $_ }) -join ';'
        }

        function Add-SessionPath([string]$Folder) {
            if ((Test-Path -LiteralPath $Folder) -and -not (($env:Path -split ';') -contains $Folder)) {
                $env:Path = "$Folder;$env:Path"
            }
        }

        # -- 1. A Python 3.11 or newer -------------------------------------------------------------
        $PyCheck = 'import sys; print(sys.executable) if sys.version_info[:2] >= (3, 11) else sys.exit(1)'

        function Test-PyOk([string]$Exe) {
            if (-not (Test-Path -LiteralPath $Exe)) { return $false }
            return [bool](Get-ToolOutput $Exe @('-c', $PyCheck))
        }

        function Find-Python {
            $tries = New-Object System.Collections.ArrayList
            $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            foreach ($v in '3.12', '3.13', '3.11', '3.14') {
                if ($launcher) { [void]$tries.Add([pscustomobject]@{ Exe = $launcher.Source; Pre = @("-$v") }) }
            }
            foreach ($v in '312', '313', '311', '314') {
                foreach ($root in @((Join-Path $env:LOCALAPPDATA 'Programs\Python'), $env:ProgramFiles)) {
                    if ($root) { [void]$tries.Add([pscustomobject]@{ Exe = (Join-Path $root "Python$v\python.exe"); Pre = @() }) }
                }
            }
            foreach ($name in 'python3.12.exe', 'python3.13.exe', 'python3.11.exe', 'python3.exe', 'python.exe') {
                # the Microsoft Store stub answers with an error: it is simply skipped
                foreach ($c in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
                    [void]$tries.Add([pscustomobject]@{ Exe = $c.Source; Pre = @() })
                }
            }
            foreach ($t in $tries) {
                if (-not (Test-Path -LiteralPath $t.Exe)) { continue }
                $out = Get-ToolOutput $t.Exe (@($t.Pre) + @('-c', $PyCheck))
                if ($out) {
                    $exe = (($out -split "`r?`n") | Select-Object -Last 1).Trim()
                    if (Test-Path -LiteralPath $exe) { return $exe }
                }
            }
            return $null
        }

        $Winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1

        function Install-WithWinget([string]$Id, [string]$Label) {
            if (-not $Winget) { return $false }
            Say "Installing $Label with winget, for your user only (no administrator)..."
            $code = Invoke-Tool $Winget.Source @('install', '-e', '--id', $Id, '--scope', 'user',
                '--accept-package-agreements', '--accept-source-agreements')
            Update-SessionPath
            return ($code -eq 0)
        }

        $Py = Find-Python
        if (-not $Py) {
            [void](Install-WithWinget 'Python.Python.3.12' 'Python 3.12')
            $Py = Find-Python
        }
        if (-not $Py) {
            Fail ("root-harness needs Python 3.11 or newer, and it could not be installed automatically.`n" +
                  "Install it with:  winget install -e --id Python.Python.3.12 --scope user`n" +
                  "or from https://www.python.org/downloads/windows/ , then run this again.")
        }
        Say ("Using " + (Get-ToolOutput $Py @('--version')) + " ($Py)")

        # -- 2. Git, to download root-harness and keep it up to date -------------------------------
        function Find-Git {
            $g = Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($g) { return $g.Source }
            foreach ($p in @((Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd\git.exe'), (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'))) {
                if (Test-Path -LiteralPath $p) { return $p }
            }
            return $null
        }
        $Git = $null
        if (-not (On 'ROOT_HARNESS_NO_UPDATE')) {
            $Git = Find-Git
            if (-not $Git) {
                [void](Install-WithWinget 'Git.Git' 'Git')
                $Git = Find-Git
            }
            if (-not $Git) {
                Fail ("root-harness needs Git, and it could not be installed automatically.`n" +
                      "Install it from https://git-scm.com/download/win (or: winget install -e --id Git.Git), then run this again.")
            }
        }

        # -- 3. Claude Code is what connects your Claude, through the SDK, with no key -------------
        #    If it is missing, install it (the official installer). Logging in is a browser
        #    step you do yourself: it cannot run inside this script.
        $LocalBin = Join-Path $HOME '.local\bin'
        Add-SessionPath $LocalBin
        $NeedLogin = $false
        if (On 'ROOT_HARNESS_SKIP_CLAUDE') {
            Say 'Skipping Claude Code (ROOT_HARNESS_SKIP_CLAUDE=1).'
        } elseif (Get-Command claude -ErrorAction SilentlyContinue) {
            Say 'Claude Code found: your Claude will be connected through your own login.'
        } else {
            Say 'Claude Code was not found. Installing it (this is what connects your Claude)...'
            # in its own PowerShell, so nothing it does can stop this script
            $shell = (Get-Process -Id $PID).Path
            $code = Invoke-Tool $shell @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', 'irm https://claude.ai/install.ps1 | iex')
            Add-SessionPath $LocalBin
            Update-SessionPath
            if ($code -eq 0 -and (Get-Command claude -ErrorAction SilentlyContinue)) {
                Say 'Claude Code installed.'
                $NeedLogin = $true
            } elseif ($code -eq 0) {
                Warn "Claude Code was installed but is not on your PATH yet. Open a new"
                Warn "PowerShell, run 'claude' once to log in, then start root-harness."
                $NeedLogin = $true
            } else {
                Warn 'Could not install Claude Code automatically. Install it yourself from'
                Warn "https://claude.com/claude-code , run 'claude' once to log in, then start"
                Warn 'root-harness. It will still install now; its Claude brain waits for login.'
            }
        }

        # -- 4. Clone, or update an existing copy --------------------------------------------------
        $Dest = $env:ROOT_HARNESS_DIR
        if (-not $Dest) { $Dest = Join-Path $HOME 'root-harness' }
        $Dest = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Dest)

        if (On 'ROOT_HARNESS_NO_UPDATE') {
            if (-not (Test-Path -LiteralPath (Join-Path $Dest 'app.py'))) {
                Fail "ROOT_HARNESS_NO_UPDATE=1 needs a root-harness copy in $Dest, and there is none."
            }
            Say "Using the copy in $Dest as it is (ROOT_HARNESS_NO_UPDATE=1)."
        } elseif (Test-Path -LiteralPath (Join-Path $Dest '.git')) {
            Say "Updating existing copy in $Dest"
            [void](Invoke-Tool $Git @('-C', $Dest, 'remote', 'set-url', 'origin', $Repo))
            if ((Invoke-Tool $Git @('-C', $Dest, 'fetch', '--quiet', '--depth', '1', 'origin', 'main')) -ne 0) {
                Fail "Could not reach $Repo. Check your internet and run this again."
            }
            if ((Invoke-Tool $Git @('-C', $Dest, 'merge', '--quiet', '--ff-only', 'FETCH_HEAD') -Quiet) -ne 0) {
                # an older copy (the history was rewritten on 30/10), or local edits in the way:
                # keep the edits aside, then take the published version as it is
                $changed = Get-ToolOutput $Git @('-C', $Dest, 'status', '--porcelain', '--untracked-files=no')
                if ($changed) {
                    $Backup = "$Dest.backup-" + (Get-Date -Format 'yyyyMMdd-HHmmss')
                    New-Item -ItemType Directory -Force -Path $Backup | Out-Null
                    [void](Invoke-Tool $Git @('-C', $Dest, 'diff', 'HEAD', "--output=$(Join-Path $Backup 'local-changes.patch')"))
                    $names = Get-ToolOutput $Git @('-C', $Dest, 'diff', 'HEAD', '--name-only')
                    foreach ($f in @($names -split "`r?`n")) {
                        if (-not $f) { continue }
                        $src = Join-Path $Dest $f
                        if (Test-Path -LiteralPath $src) {
                            $to = Join-Path $Backup $f
                            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $to) | Out-Null
                            Copy-Item -LiteralPath $src -Destination $to -Recurse -Force
                        }
                    }
                    Warn "Your local edits to root-harness's files are saved in $Backup"
                }
                if ((Invoke-Tool $Git @('-C', $Dest, 'reset', '--quiet', '--hard', 'FETCH_HEAD')) -ne 0) {
                    Fail "Could not update $Dest. Move it aside (or set ROOT_HARNESS_DIR) and run this again."
                }
                Say 'Your copy now matches the published root-harness. Your account and memory'
                Say '(~\.root-harness) live outside this folder: they are not touched.'
            }
        } else {
            if (Test-Path -LiteralPath $Dest) {
                Fail "$Dest already exists and is not a root-harness checkout. Set ROOT_HARNESS_DIR to another path and retry."
            }
            Say "Cloning into $Dest"
            if ((Invoke-Tool $Git @('clone', '--quiet', '--depth', '1', $Repo, $Dest)) -ne 0) {
                Fail "Could not download $Repo. Check your internet and run this again."
            }
        }

        # -- 5. A private virtual environment and the dependencies ---------------------------------
        $Venv = Join-Path $Dest '.venv'
        $VenvPy = Join-Path $Venv 'Scripts\python.exe'
        $VenvPyw = Join-Path $Venv 'Scripts\pythonw.exe'
        if ((Test-Path -LiteralPath $Venv) -and -not (Test-PyOk $VenvPy)) {
            Warn "The old .venv in $Dest no longer works with a recent Python: rebuilding it."
            Remove-Item -LiteralPath $Venv -Recurse -Force
        }
        Say 'Installing dependencies (this can take a minute)...'
        if ((Invoke-Tool $Py @('-m', 'venv', $Venv)) -ne 0) { Fail "Could not create the virtual environment in $Venv." }
        if ((Invoke-Tool $VenvPy @('-m', 'pip', 'install', '--quiet', '--disable-pip-version-check', '--upgrade', 'pip')) -ne 0) {
            Fail 'Could not update pip (see above). Check your internet and run this again.'
        }
        if ((Invoke-Tool $VenvPy @('-m', 'pip', 'install', '--quiet', '--disable-pip-version-check', '-r', (Join-Path $Dest 'requirements.txt'))) -ne 0) {
            Fail 'Installing the dependencies failed (see above). Check your internet and run this again.'
        }

        # -- 6. The window draws with Microsoft Edge WebView2 (built into Windows 11) --------------
        $WebView2 = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
        $hasWebView2 = $false
        foreach ($key in @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$WebView2",
                           "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$WebView2",
                           "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$WebView2")) {
            $pv = (Get-ItemProperty -Path $key -Name pv -ErrorAction SilentlyContinue).pv
            if ($pv -and $pv -ne '0.0.0.0') { $hasWebView2 = $true }
        }
        if (-not $hasWebView2) {
            Warn 'The window needs the Microsoft Edge WebView2 Runtime, which this computer does not seem to have.'
            Warn 'Install it from https://developer.microsoft.com/microsoft-edge/webview2/'
            Warn '(or: winget install -e --id Microsoft.EdgeWebView2Runtime), then open root-harness.'
        }

        # -- 7. Start menu and desktop shortcuts ---------------------------------------------------
        $Data = Join-Path $env:LOCALAPPDATA 'root-harness'
        New-Item -ItemType Directory -Force -Path $Data | Out-Null

        # Root's head as an .ico (PNG images inside, Windows Vista and later).
        function New-RootIcon([string]$Png, [string]$Small, [string]$Ico) {
            $images = New-Object System.Collections.ArrayList
            try {
                Add-Type -AssemblyName System.Drawing
                $src = [System.Drawing.Image]::FromFile($Png)
                try {
                    foreach ($s in 256, 48, 32, 16) {
                        $bmp = New-Object System.Drawing.Bitmap $s, $s
                        $g = [System.Drawing.Graphics]::FromImage($bmp)
                        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
                        $g.DrawImage($src, 0, 0, $s, $s)
                        $g.Dispose()
                        $ms = New-Object System.IO.MemoryStream
                        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
                        $bmp.Dispose()
                        [void]$images.Add([pscustomobject]@{ Size = $s; Data = $ms.ToArray() })
                    }
                } finally {
                    $src.Dispose()
                }
            } catch {
                $images.Clear()
                if (Test-Path -LiteralPath $Small) {
                    [void]$images.Add([pscustomobject]@{ Size = 192; Data = [System.IO.File]::ReadAllBytes($Small) })
                }
            }
            if ($images.Count -eq 0) { return $false }
            $stream = [System.IO.File]::Create($Ico)
            $w = New-Object System.IO.BinaryWriter $stream
            try {
                $w.Write([UInt16]0); $w.Write([UInt16]1); $w.Write([UInt16]$images.Count)
                $offset = 6 + 16 * $images.Count
                foreach ($im in $images) {
                    $side = $im.Size
                    if ($side -ge 256) { $side = 0 }
                    $w.Write([byte]$side); $w.Write([byte]$side); $w.Write([byte]0); $w.Write([byte]0)
                    $w.Write([UInt16]1); $w.Write([UInt16]32)
                    $w.Write([UInt32]$im.Data.Length); $w.Write([UInt32]$offset)
                    $offset += $im.Data.Length
                }
                foreach ($im in $images) { $w.Write([byte[]]$im.Data) }
            } finally {
                $w.Close()
            }
            return $true
        }

        $Icon = Join-Path $Data 'root-harness.ico'
        $hasIcon = $false
        try {
            $hasIcon = New-RootIcon (Join-Path $Dest 'mobile\dist\icon-512.png') (Join-Path $Dest 'mobile\dist\icon-192.png') $Icon
        } catch {
            $hasIcon = $false
        }

        # The shortcut starts this little script with pythonw (no console window). Started
        # from the Start menu, the app gets Explorer's PATH: Claude Code's folder is added,
        # and what it prints goes to a log, for when something goes wrong.
        $Launcher = Join-Path $Data 'root-harness.pyw'
        $destLiteral = '"' + ($Dest -replace '\\', '\\' -replace '"', '\"') + '"'
        $pyw = @(
            '# Starts root-harness. Written by install.ps1 (running it again rewrites this file).',
            'import os, runpy, sys',
            "DEST = $destLiteral",
            "LOG = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), 'root-harness', 'launch.log')",
            'if sys.stdout is None:',
            "    sys.stdout = sys.stderr = open(LOG, 'w', encoding='utf-8', buffering=1)",
            "local_bin = os.path.join(os.path.expanduser('~'), '.local', 'bin')",
            "path = os.environ.get('PATH', '')",
            'if os.path.isdir(local_bin) and os.path.normcase(local_bin) not in [os.path.normcase(p) for p in path.split(os.pathsep)]:',
            "    os.environ['PATH'] = local_bin + os.pathsep + path",
            'os.chdir(DEST)',
            'sys.path.insert(0, DEST)',
            "sys.argv = [os.path.join(DEST, 'app.py')] + sys.argv[1:]",
            "runpy.run_path(sys.argv[0], run_name='__main__')"
        ) -join "`r`n"
        [System.IO.File]::WriteAllText($Launcher, $pyw + "`r`n", (New-Object System.Text.UTF8Encoding $false))

        $Shortcuts = @()
        try {
            $wsh = New-Object -ComObject WScript.Shell
            foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
                if (-not $folder) { continue }
                $lnkPath = Join-Path $folder 'root-harness.lnk'
                $lnk = $wsh.CreateShortcut($lnkPath)
                $lnk.TargetPath = $VenvPyw
                $lnk.Arguments = '"' + $Launcher + '"'
                $lnk.WorkingDirectory = $Dest
                $lnk.Description = 'root-harness: your agents, your friends and the network, in one window'
                if ($hasIcon) { $lnk.IconLocation = "$Icon,0" }
                $lnk.Save()
                $Shortcuts += $lnkPath
            }
        } catch {
            Warn "Could not create the shortcuts ($($_.Exception.Message)); the app still works."
        }

        # -- 8. Open it, unless you still need to log in to the Claude Code just installed ---------
        $StartCmd = "& `"$VenvPy`" `"$(Join-Path $Dest 'app.py')`""
        if ($Shortcuts.Count -gt 0) { $OpenHint = 'root-harness from the Start menu or your desktop' } else { $OpenHint = "it from PowerShell: $StartCmd" }
        Say ''
        if ($NeedLogin) {
            Say 'Almost there. Two steps, once:'
            Say '  1. Log in to Claude Code: open a new PowerShell, run  claude  (then Ctrl-C after login)'
            Say "  2. Open $OpenHint"
            Say ''
            Say 'Claude Code needs a Pro, Max, Team or Console account; the free plan does not include it.'
            return $true
        }
        if (On 'ROOT_HARNESS_NO_LAUNCH') {
            Say "Installed in $Dest (not opened: ROOT_HARNESS_NO_LAUNCH=1)."
            Say "Open $OpenHint"
            return $true
        }
        Say 'Done. Opening root-harness.'
        Say "Next time, open $OpenHint"
        Start-Process -FilePath $VenvPyw -ArgumentList ('"' + $Launcher + '"') -WorkingDirectory $Dest
        return $true
    } catch {
        Write-Host ''
        Write-Host $_.Exception.Message -ForegroundColor Red
        return $false
    }
}

if (@($RootHarnessOk) -contains $true -and -not (@($RootHarnessOk) -contains $false)) {
    $global:LASTEXITCODE = 0
} else {
    $global:LASTEXITCODE = 1
    if ($RootHarnessAsFile) { exit 1 }
}
