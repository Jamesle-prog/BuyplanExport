# Warehouse Web Scanner (`web_scan`)

A lightweight browser scanner for warehouse PDAs / handheld barcode guns —
**separate from the Streamlit app**. It serves one mobile-first page plus a
small JSON API over the same `po_history.db`, so a PDA just opens a URL and
scans. Built on Starlette + uvicorn (both already installed — no new deps).

Why separate from the Streamlit tab: Streamlit reruns the whole page on every
interaction, which is sluggish on a cheap PDA browser. This page is a single
keyboard-wedge input with instant, no-rerun results.

## Run it

```powershell
# from the repo root, with the 3.13 interpreter
$env:PO_SCAN_PASSWORD = "choose-a-shared-password"   # REQUIRED in real use
C:/Users/Administrator/AppData/Local/Programs/Python/Python313/python.exe -m web_scan
```

On start it prints the LAN URL, e.g. `http://192.168.0.153:8502`. Open that on
the PDA browser, enter your name and the shared password once, and scan.

### Environment variables

| Var | Default | Meaning |
|-----|---------|---------|
| `PO_SCAN_PORT` | `8502` | Listen port. |
| `PO_SCAN_PASSWORD` | `scan` (with a startup warning) | Shared gate password. **Set this.** |
| `PO_SCAN_COMPANIES` | *(unset = all)* | Comma-separated company scope, e.g. `GIII`. |

## Modes (mirror the Streamlit UPC Check tab)

- **🔍 查询 Lookup** — scan a UPC → PO / style / colour / size / warehouse / units. Read-only.
- **✓ 核对 Verify** — pick a PO, scan each UPC → does it belong? Shows ✓/✗ and, when wrong, which PO(s) it actually belongs to.
- **🧮 盘点 Stocktake** — toggle +1 / −1 and scan to adjust a physical count per UPC; a live table shows the running counts, with a Clear-all button.

The scan box uses `inputmode="none"` and a document-level focus trap so a
keyboard-wedge scanner's "type + Enter" always lands in the field. A shared
session cookie (tied to a per-process token) gates every page and API call;
restarting the server invalidates all sessions. Login is throttled per IP
(8 failures / 15 min → HTTP 429) so the shared password can't be brute-forced
on the LAN. A failed scan (server/network error) shows a red error state, so an
operator always knows whether a scan was recorded.

Login also asks for a name — attribution, not a second credential; the
password is still the one shared secret that gates access. A blank name is
refused (no way to reach a session without one), it is shown in the scan
page's header, and it is stamped onto every stocktake adjustment
(`upc_stocktake.updated_by`, "who touched this count last", overwritten each
scan) and onto a stocktake **clear** (one row in the app-wide change log,
`entity=upc_stocktake` — the one action here that is global and hard to
undo, so it gets a durable record; a routine +1/-1 scan does not, for the
same reason a Sky East upload logs one summary row and not one per item).

## API (all POST JSON unless noted; all require the session cookie)

| Endpoint | Body | Returns |
|----------|------|---------|
| `POST /api/lookup` | `{upc}` | `{matched, count, rows[]}` |
| `POST /api/verify` | `{po, upc}` | `{ok, matched, rows[], other_pos[]}` |
| `POST /api/count` | `{upc, dir:"add"\|"remove"}` | `{qty, delta, known, context}` |
| `GET  /api/pos` | — | `{pos[]}` (Verify picker) |
| `GET  /api/stocktake` | — | `{rows[], total}` |
| `POST /api/stocktake/clear` | `{}` | `{cleared}` |
| `GET  /healthz` | — | `ok` (public) |

## Deploy (persistent service)

Run it the same way the Streamlit app is planned to run — as an NSSM service
so it survives reboots/crashes:

```powershell
& $nssm install POScanWeb $py "-m web_scan"
& $nssm set POScanWeb AppDirectory "C:\Apps\PO_Automation_GIII"
& $nssm set POScanWeb AppEnvironmentExtra "PO_SCAN_PASSWORD=..." "PO_SCAN_PORT=8502"
& $nssm set POScanWeb Start SERVICE_AUTO_START
Start-Service POScanWeb
```

Open the port for LAN PDAs:

```powershell
New-NetFirewallRule -DisplayName "PO Web Scanner 8502" -Direction Inbound `
  -Protocol TCP -LocalPort 8502 -Action Allow -Profile Domain,Private
```

## Notes / limits

- **Online only** — no offline queue (unlike a native PDA app). A network blip
  shows an error; the operator re-scans. Fine on a stable warehouse LAN.
- Stocktake counts live in the shared `upc_stocktake` table, same as the
  Streamlit UPC Check tab — the two stay in sync.
- UPCs come from what was captured at extraction; POs parsed before the UPC
  fix (v2.63.0) may need re-processing to populate barcodes.
- Trusted-LAN posture (plain HTTP, shared password). Put it behind a TLS
  reverse proxy if it must cross an untrusted segment.
