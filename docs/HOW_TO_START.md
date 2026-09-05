# How to Start PO Automation GIII

A practical run guide: how to launch the app, verify it's healthy, stop it, and
keep it running. For architecture and conventions see `IMPLEMENTATION_GUIDE.md`
and `CLAUDE.md`.

---

## 1. Prerequisites

- **Python interpreter — use the 3.13 one, not the default `python` on PATH:**
  ```
  C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe
  ```
  The default `python` (3.14) does **not** have the app's dependencies installed.
- **Working directory:**
  ```
  C:\Users\Administrator\Desktop\Tool\PO_Automation_GIII
  ```

> Tip: to confirm the interpreter has the deps, run
> `…\Python313\python.exe -m streamlit --version` — it should print a version,
> not a "No module named streamlit" error.

---

## 2. Start the server

### Option A — normal foreground (interactive terminal)

Open **PowerShell** (or Windows Terminal / cmd) and run:

```powershell
cd C:\Users\Administrator\Desktop\Tool\PO_Automation_GIII
C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe -m streamlit run app.py --server.headless true
```

Leave that window open — the app runs as long as the window stays open. This is
the **recommended** way to keep the app up for a work session, because the
process is owned by *your* terminal and won't be torn down by anything else.

### Option B — background, writing to a log file

```powershell
cd C:\Users\Administrator\Desktop\Tool\PO_Automation_GIII
C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe -m streamlit run app.py --server.headless true > streamlit_run.log 2>&1
```

Output (including the URL and any errors) goes to `streamlit_run.log`.

### Option C — fully detached process (survives the launching shell)

Use this when you want the app to keep running after the launching terminal
closes:

```powershell
$wd  = "C:\Users\Administrator\Desktop\Tool\PO_Automation_GIII"
$py  = "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"
$cmd = 'cmd /c "cd /d ' + $wd + ' && "' + $py + '" -m streamlit run app.py --server.headless true > streamlit_run.log 2>&1"'
$r   = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine=$cmd}
"PID = $($r.ProcessId)"
```

Note the printed **PID** — you'll need it to stop the process later.

---

## 3. Open the app

Once started, open a browser to:

```
http://localhost:8501
```

---

## 4. Health check

Confirm the server is actually serving:

```powershell
curl http://localhost:8501/_stcore/health
```

- **`ok` / HTTP 200** → healthy.
- **connection refused / HTTP 000** → not running (start it, see §2).

One-liner that prints just the status code:

```powershell
(Invoke-WebRequest http://localhost:8501/_stcore/health -UseBasicParsing).StatusCode
```

---

## 5. Stop the server

- **Option A (foreground):** press `Ctrl+C` in the terminal, or close the window.
- **Option B / C (background/detached):** stop by PID —
  ```powershell
  Stop-Process -Id <PID>
  ```
  If you don't have the PID, find the Streamlit process:
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*streamlit*' } |
    Select-Object ProcessId, CommandLine
  ```
  Then `Stop-Process -Id <ProcessId>`.

---

## 6. Restart after code changes

- **`app.py` changes** are hot-reloaded by Streamlit automatically — no restart
  needed (just "Rerun" in the browser if prompted).
- **Changes to imported modules** (anything under `po_extractor/` or `ui/`)
  require a **full restart** — Streamlit only hot-reloads `app.py`. Stop the
  server (§5) and start it again (§2).

---

## 7. Troubleshooting

**"No module named streamlit"** — you used the wrong Python. Use the full
`…\Python313\python.exe` path from §1, not bare `python`.

**Port 8501 already in use** — a server is already running (or a stale process
is holding the port). Either use the existing one, or stop it (§5) and restart.
To run a second instance on another port: add `--server.port 8502`.

**The server keeps dropping / won't stay up** — if you started it from a tool or
a shell that gets closed, the process dies with it. Use **Option A** from a
terminal window you keep open, or **Option C** to fully detach it.

**Check the log** — errors on startup are written to `streamlit_run.log`
(Options B/C). Read the tail:
```powershell
Get-Content streamlit_run.log -Tail 40
```

**Verify the running version** — the app version is shown in the UI and defined
by `APP_VERSION` near the top of `app.py`. The release history is in the
**Releases** tab (`ui/changelog_view.py`; the entries themselves live in `ui/changelog_data.py`).

---

## 8. Related

- **Run the test suite** before committing changes:
  ```powershell
  C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/ -q
  ```
- **Roll back dependencies** to the known-good snapshot:
  ```powershell
  C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe -m pip install -r requirements.lock
  ```
- **Deeper docs:** `IMPLEMENTATION_GUIDE.md` (architecture), `CLAUDE.md`
  (conventions & hard rules).
