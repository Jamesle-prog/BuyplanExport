# Deploying to a Persistent Windows Server

This is the runbook for moving PO Automation GIII off a developer's desktop
and onto a server where it runs on its own — starts on boot, restarts if it
crashes, and doesn't depend on anyone keeping a terminal window open. For
day-to-day operation on a machine that's already set up (start/stop/health
check), see `HOW_TO_START.md`. For architecture, see `IMPLEMENTATION_GUIDE.md`.

**Platform: Windows Server** (or a dedicated Windows 10/11 Pro machine). The
app has only ever run on Windows; nothing in its dependencies is Windows-only,
but there's no track record on Linux either, so this runbook doesn't cover it.

**Service supervisor: [NSSM](https://nssm.cc/)**, chosen over Task Scheduler
(no real crash-restart) and a hand-rolled `pywin32` service (real engineering
effort to reinvent what NSSM already does). NSSM wraps an arbitrary console
command as a Windows service with built-in auto-restart and log capture.

---

## 1. Get the code onto the server

Deploy directly from the working branch — **do not wait for a merge to
`main`**. `main` can lag significantly behind (check with
`git log --oneline main..<branch> | wc -l` before assuming otherwise); gating
a deployment on a merge just delays getting fixes to users. Merge to `main`
later, once the branch has proven itself in use.

```powershell
# On the SERVER — replace <branch> with whichever branch has the latest work
git clone https://github.com/Jamesle-prog/BuyplanExport.git C:\Apps\PO_Automation_GIII
cd C:\Apps\PO_Automation_GIII
git checkout <branch>
```

Use `C:\Apps\...`, not a per-user Desktop path — a Windows Service shouldn't
depend on a specific user profile existing or being logged in.

## 2. Python environment

```powershell
py -0p                              # confirm 3.13 is available; install if not
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m streamlit --version    # sanity check
```

Use `requirements.lock` (pinned, known-good), not `requirements.txt` (loose
`>=` pins) — the first install on a new machine should reproduce a validated
environment, not whatever versions happen to resolve that day.

## 3. Install as a Windows Service (NSSM)

```powershell
# Download NSSM directly — don't assume Chocolatey is available on the server
Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile "$env:TEMP\nssm.zip"
Expand-Archive -Path "$env:TEMP\nssm.zip" -DestinationPath "$env:TEMP\nssm" -Force
New-Item -ItemType Directory -Force -Path "C:\Apps\nssm" | Out-Null
Copy-Item "$env:TEMP\nssm\nssm-2.24\win64\nssm.exe" "C:\Apps\nssm\nssm.exe"

$nssm = "C:\Apps\nssm\nssm.exe"; $svc = "POAutomationGIII"
$py   = "C:\Apps\PO_Automation_GIII\.venv\Scripts\python.exe"
$dir  = "C:\Apps\PO_Automation_GIII"

& $nssm install $svc $py "-m streamlit run app.py --server.headless true --server.port 8501 --server.address 0.0.0.0"
& $nssm set $svc AppDirectory $dir
& $nssm set $svc DisplayName "PO Automation GIII (Streamlit)"
& $nssm set $svc Description "Internal PO extraction / buy-plan tool"
& $nssm set $svc Start SERVICE_AUTO_START

# Crash recovery
& $nssm set $svc AppExit Default Restart
& $nssm set $svc AppRestartDelay 3000

# Log capture with rotation (10 MB)
New-Item -ItemType Directory -Force -Path "$dir\logs" | Out-Null
& $nssm set $svc AppStdout "$dir\logs\streamlit_out.log"
& $nssm set $svc AppStderr "$dir\logs\streamlit_err.log"
& $nssm set $svc AppRotateFiles 1
& $nssm set $svc AppRotateOnline 1
& $nssm set $svc AppRotateBytes 10485760

Start-Service $svc
```

`logs/` is gitignored — it holds runtime output, not source.

## 4. First-run configuration (once, on the server)

```powershell
cd C:\Apps\PO_Automation_GIII

# License is per-machine (MAC + hostname fingerprint) — generate it HERE,
# never copy license.key from another machine, it will fail validation.
.\.venv\Scripts\python.exe -m auth.generate_license

# Interactive: create user accounts (up to 3, no developer secrets needed)
.\.venv\Scripts\python.exe setup_users.py

# Starting the service triggers auto-seeding of companies.json + both SQLite
# DBs + the data/ directory — nothing else to configure manually.
Start-Service POAutomationGIII
```

No environment variables are required for a working first run. `FABRIC_DB_PATH`
and `PO_SMTP_*` are optional overrides only (see `po_extractor/config.py` and
`auth/smtp_settings.py`) — skip them unless you need the fabric DB or outbound
email pointed somewhere non-default. (`PO_DB_PATH` / `PO_COMPANIES_FILE` /
`PO_USERS_FILE`, if documented elsewhere, do not exist in the current code —
paths are fixed relative to the project root.)

## 5. Network access

```powershell
New-NetFirewallRule -DisplayName "PO Automation GIII (Streamlit 8501)" `
    -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow `
    -Profile Domain,Private
```

Scoped to `Domain,Private` (not `Public`) since this is an internal-LAN tool.

Plain HTTP is acceptable for a small number of internal users on a trusted
LAN — matches the app's current risk posture (a login rate-limiter is
already in place; there has never been TLS anywhere in this app's history).
An IIS or nginx TLS-terminating reverse proxy is a reasonable fast-follow if
usage grows or the traffic ever needs to cross an untrusted network segment.

## 6. Verification checklist

Run all of these before handing the URL to anyone:

```powershell
# Service is running and set to auto-start
Get-Service POAutomationGIII | Select-Object Status, StartType

# Health endpoint responds locally
(Invoke-WebRequest http://localhost:8501/_stcore/health -UseBasicParsing).StatusCode   # expect 200

# Reachable from another machine on the LAN (run from a different PC)
Invoke-WebRequest http://<SERVER-HOST-OR-IP>:8501/_stcore/health -UseBasicParsing

# Auto-restart on crash
Stop-Process -Name python -Force
Start-Sleep -Seconds 5
Get-Service POAutomationGIII       # expect Running again

# Survives a reboot — do this last
Restart-Computer
# after reboot, with no one logged in:
Get-Service POAutomationGIII                                                          # Running
(Invoke-WebRequest http://localhost:8501/_stcore/health -UseBasicParsing).StatusCode   # 200
```

## 7. Deploying updates

Every code update should restart the service, regardless of which files
changed — Streamlit only hot-reloads `app.py` itself; changes anywhere under
`po_extractor/` or `ui/` need a full process restart to take effect.

```powershell
cd C:\Apps\PO_Automation_GIII
Stop-Service POAutomationGIII

git pull origin <branch>
.\.venv\Scripts\python.exe -m pip install -r requirements.lock   # picks up any dependency changes

Start-Service POAutomationGIII
(Invoke-WebRequest http://localhost:8501/_stcore/health -UseBasicParsing).StatusCode
```

To roll back: `git checkout <previous-commit>`, then repeat the pip install +
service restart. `requirements.lock` is version-controlled, so a rollback
reproduces the matching dependency set too, not just the matching code.

## Useful commands

```powershell
nssm status POAutomationGIII       # or: Get-Service POAutomationGIII
nssm stop POAutomationGIII         # or: Stop-Service POAutomationGIII
nssm start POAutomationGIII        # or: Start-Service POAutomationGIII
nssm remove POAutomationGIII confirm   # uninstall the service entirely
Get-Content C:\Apps\PO_Automation_GIII\logs\streamlit_err.log -Tail 40
```
