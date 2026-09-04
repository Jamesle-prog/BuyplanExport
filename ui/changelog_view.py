"""Release changelog tab — version history for PO Extractor."""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
# Changelog data — newest first
# Each entry: {version, date, entries: [{type, text}]}
# Types: feat | fix | perf | refactor | security | docs
# ---------------------------------------------------------------------------
_CHANGELOG: list[dict] = [
    {
        "version": "2.124.1",
        "date": "2026-09-04",
        "entries": [
            {"type": "fix", "text": "**Sky East buy plan now shows the client's PO colour exactly as they wrote it** — brackets, casing and all. A colour stored as `(dark blue)` prints as `(dark blue)`, not `Dark Blue`, on the style sheet, the Overview sheet and the 核料 sheet, so the buy plan reads straight against the client's own PO document. **Matching is unchanged**: the bracket-stripped, title-cased form is still what gets looked up against 大货进度表 and the colour DB, so `(dark blue)` continues to resolve to 藏青/503 exactly as before — the two forms are now kept as separate values rather than one doing both jobs. On the 核料 sheet the grouping key also stays the normalised colour, so `(black)` and `BLACK` still total into a single row (labelled with the first spelling seen) instead of splitting in two"},
        ],
    },
    {
        "version": "2.124.0",
        "date": "2026-09-04",
        "entries": [
            {"type": "feat", "text": "**Fabric presentation sheets (面料推荐单) — new section in 🧵 Fabric DB.** Pick fabrics out of the master database, build a customer recommendation sheet from them, and export it as the HHN Presentation layout (title block · one row per fabric · type legend). The quoted **USD/Y** is computed from the internal RMB/M cost with the workbook's own formula — `CEILING(RMB/M × markup ÷ FX × 0.9144, step)` — verified to reproduce all 18 prices in the GIII 5.13 sheet exactly. Markup (1.1), FX rate (6.7) and rounding step (0.05) are editable per sheet and **stored with it**, so an old quote stays reproducible after the rate moves"},
            {"type": "feat", "text": "**Which price to print is chosen at export time.** USD/Y only (customer copy), RMB/M only, or both (internal review copy) — picking an internal-cost mode shows a warning that the file is not for sending out. Prices are **frozen onto the sheet when it is built**, not re-read at export: a quote you sent in May must not silently change when someone edits a cost in June"},
            {"type": "feat", "text": "**Each sheet carries its own QR code, and scanning it is recorded.** The code points at the `web_scan` service's new `/p/<id>` page (same LAN login gate as the scanner); opening it logs the time, IP and device against that sheet, so when a sheet went out and which fabrics were on it is always answerable. The scan page deliberately shows USD/Y only — never the internal RMB cost — because the sheet it is printed on may be in a customer's hands. Set the scanner URL once in the new ⚙️ QR scanner URL box; sheets still export fine without it, just without a QR code"},
            {"type": "chore", "text": "New optional dependency `segno` (pure Python, no dependencies) for QR generation — `pip install segno`. Without it the export still works and says so instead of failing"},
        ],
    },
    {
        "version": "2.123.0",
        "date": "2026-07-30",
        "entries": [
            {"type": "feat", "text": "**New 📏 Fabric Condition module (面料情况).** The shop-floor width/weight/shrinkage log is read into the system: measured net and gross width against nominal, weight, fabric- and pattern-paper shrinkage (径向/纬向 each), cutting requirements (max plies, max length, direction), net consumption, and remaining stock (rolls/kg/m). Own permission, granted explicitly, matching every other module added this way."},
            {"type": "feat", "text": "**Every value is shown exactly as the sheet has it — nothing is rounded or converted.** This is a hand-typed running log, not a structured export: 'numeric' columns are full of ranges ('176-178'), approximations ('100层左右'), typo'd signs ('负0.6%' — the Chinese word for negative instead of a minus sign), and words instead of numbers ('无', '同上' — \"ditto\", referring to the row above, never resolved here since that would be a guess this module has no business making). Coercing any of these to a number would silently discard whichever part didn't fit."},
            {"type": "feat", "text": "The one exception: the date column's cells carry a plain Excel serial number with **General** formatting rather than a date format, so a clean integer is converted to an ISO date — a deterministic, lossless read of what Excel's own encoding means, not a guess. Anything that isn't a clean integer (one row has the typo '2023/215') is kept exactly as typed."},
            {"type": "feat", "text": "The sheet repeats 径向/纬向 twice — once under 面料缩率 (fabric shrinkage), once under 纸板缩率 (pattern-paper shrinkage) — reading identically on their own row. Resolved by the merged group heading above them rather than position, so it doesn't matter which one is wider in a given upload."},
            {"type": "feat", "text": "Import replaces the whole table on each upload: unlike Settlement (several client-years in one workbook), this is a single running log from one sheet, so there is nothing to preserve selectively across a re-upload."},
        ],
    },
    {
        "version": "2.122.1",
        "date": "2026-07-30",
        "entries": [
            {"type": "fix", "text": "**The remembered cut-plan folder is no longer overwritten by running the test suite.** Two tests exercised the real `save_copy_to_folder` with a genuine (pytest-created) folder, so every full test run recorded that throwaway path as \"the last folder used\" in the same file the app reads on the Standard output / plan export / PDF screens — pushing the real shared-drive folder further down the list each time until it was evicted outright. \"Also save a copy to this folder\" was showing a `pytest-of-Administrator\\...` path as a result. The two tests now write to a scratch file instead of the real one, and the real `data/image_folder_history.json` has been cleaned of the pytest entries that had already piled up."},
        ],
    },
    {
        "version": "2.122.0",
        "date": "2026-07-30",
        "entries": [
            {"type": "feat", "text": "**📐 Reference Data → Style-Fabric Mapping now has a full-table view.** \"View stored styles\" only ever listed style names; a new **View full fabric mapping table** expander alongside it shows every stored fabric row — combo, sequence, body part, HHN No., composition, weight and width — with a filter box for style or HHN No. A style with two fabrics (shell + lining) or two combos now visibly has two rows instead of being folded into one name in a list."},
        ],
    },
    {
        "version": "2.121.0",
        "date": "2026-07-29",
        "entries": [
            {"type": "feat", "text": "**New 💰 Settlement module (结算统计表).** Angel's settlement workbook is read into the system: one row per invoice line — what was contracted, what shipped, what was invoiced and received, and everything paid back out in 面料款 / 辅料款 / 加工费 and 港杂费 / 其他 / 税金. Excel stays the master; re-upload to refresh. Its own permission, granted explicitly — these rows carry factory cost, margin and money received."},
            {"type": "feat", "text": "**The views a spreadsheet makes awkward.** Outstanding by client and year, oldest ex-factory first; discount-risk lines; sample cost per style; and totals that are always grouped by currency — the SC book is in GBP and adding it to the USD one would produce a number that is not an amount of anything."},
            {"type": "feat", "text": "**Cross-checked against the orders already in the system.** Each line is matched on the client's PO *and* the style — a PO covers several styles and each is invoiced separately, so the PO alone would fan one line across all of them. Lines naming a PO/style pair no contract has are listed, as are lines whose quantity disagrees with the order they match."},
            {"type": "feat", "text": "**Colour is read as data, not decoration.** Discount risk exists in the workbook only as a red fill on the invoice number, and contract status only as a fill on 合同号. Both are read from the sheet's own legend rows rather than a hardcoded colour, so a re-themed book still parses."},
            {"type": "feat", "text": "Import replaces only the sheets the uploaded file carries, so a book holding one client-year cannot delete the years it doesn't mention — the summary says which sheets moved and which were left alone. 到期未付款明细 and 折扣风险明细 are deliberately not imported: they are views of the same rows, and this tab recomputes them so they cannot fall behind."},
            {"type": "feat", "text": "Every field is resolved by its heading, never by position: Zalando2026 puts 辅助列/款号/PO# where Zalando2025 puts PO#/辅助列/款号, and each payment's 日期 column is bound to the payment on its left, which is the only thing that says which date it is."},
        ],
    },
    {
        "version": "2.120.0",
        "date": "2026-07-29",
        "entries": [
            {"type": "fix", "text": "**Plan qty and Cut qty are right for a single-style plan.** A plan covering one style is laid out differently in two ways, and both were read as if it covered several: the header writes plain `Style file` / `Style name` with no number, and there is no band of style names between the 尺码 heading and the size labels — because there is only one style to name. Read with a band assumed, every size label was taken for a style name and the first data row for the sizes. `1237_撞色` therefore showed **Plan qty 0** (no style totals parsed at all) and **Cut qty 4062**, which was 563 + 3499 — two mis-keyed size buckets added together, not a quantity from the file. It now reads 3457 ordered and 3499 cut, matching the workbook."},
            {"type": "fix", "text": "The unnumbered `Style file` / `Style name` pair was also being numbered by arrival order, so the two lines landed in different slots and one style came out as two — one with only a filename, one with only a name."},
            {"type": "fix", "text": "With no style band, 颜色 and 层数 share the size row, and 层数 was read as a size — filing each marker's ply count as a garment quantity. Sizes are now taken only from the 尺码 heading rightwards, and the ply count is found on the row it is actually on (it was reading 0 for every marker on these plans)."},
            {"type": "feat", "text": "**🔄 Re-read from the original file**, on a plan's detail screen. A parser fix otherwise reaches only plans uploaded after it, since the figures are worked out at upload time — the original upload is kept, so re-reading it is enough. Links, notes and the upload record are left alone, and a plan whose file is missing or no longer parses is left exactly as it was rather than blanked."},
        ],
    },
    {
        "version": "2.119.0",
        "date": "2026-07-29",
        "entries": [
            {"type": "feat", "text": "**The export folder is remembered.** \"Also save a copy to this folder\" comes back pre-filled with the folder last saved to, across restarts — it is the same shared drive on every export, and retyping it each time was pure friction. Once more than one folder has been used, a **Recent folders** picker appears above the box. Clearing the field still sticks for the rest of the session; the remembered path is only filled in when the box is empty."},
            {"type": "feat", "text": "**One memory, shared by every cut-plan export.** A folder entered on the Standard output screen is already filled in on a plan's own export and on the PDF panel — the destination is a property of the machine, not of the particular screen that asked for it."},
            {"type": "fix", "text": "A folder is remembered only once a file has actually landed in it. Recording paths as they are typed would have filled the suggestions with half-finished paths, typos and folders that turned out not to exist."},
        ],
    },
    {
        "version": "2.118.0",
        "date": "2026-07-29",
        "entries": [
            {"type": "feat", "text": "**X-factory date on the saved-plans table.** The date the cutting room is actually working to — when the linked PO has to leave the factory (离厂时间) — now sits next to Cut vs PO %, and on the plan's own detail line. It is read from the linked PO's items, so it needs no extra typing and cannot drift out of step with the contract."},
            {"type": "feat", "text": "A plan can cover POs that ship on different days, so the column shows the **span** (`earliest → latest`) rather than one date silently chosen out of several — picking the later one would overstate the deadline, and picking the earlier without saying so would hide that a later one exists. Undated items are ignored rather than collapsing the span, and the cell is blank when no PO is linked."},
        ],
    },
    {
        "version": "2.117.0",
        "date": "2026-07-29",
        "entries": [
            {"type": "feat", "text": "**Photos inserted the ordinary Excel way are extracted too.** A picture reaches a cell two different ways, and one client PO routinely has both: pasted as a WPS cell image (`=DISPIMG(\"ID_…\")`), or inserted with Insert ▸ Picture — which anchors it *over* the cell and leaves the cell itself empty. Only the first form was ever read, so a style whose photo was inserted normally came through with no picture at all, and was then reported as having no photo with the picture sitting visibly in the file that was just uploaded. Both the client PO and the 大货进度表 now read both forms."},
            {"type": "fix", "text": "**Real case:** in `HHPPC053 SS27`, rows 1 and 3 (`ZLD060/S24DTR003`, `JS5013`) carried WPS cell images and extracted fine; row 2 (`DR5108`) carried an anchored picture and extracted nothing. It now comes through — and its bytes are identical to the `DR5108.png` someone had already copied onto the share by hand."},
            {"type": "fix", "text": "An anchored picture has no id of its own, so one is derived from its content. Two consequences that both matter: the same photo re-uploaded keeps its id instead of being filed twice, and two POs that each call their picture `image1.png` cannot collide — a picture id becomes a filename in a shared folder, so a collision would attach one client's photo to another's style."},
        ],
    },
    {
        "version": "2.116.3",
        "date": "2026-07-29",
        "entries": [
            {"type": "fix", "text": "**A style filed as a single photo is found again.** The buy plan only ever looked for `<style>_front.png` / `<style>_back.png`, so a style stored as a plain `<style>.png` was reported as having no photo at all — with the file sitting right there in the folder. On the Zalando share that was **286 of 427 files** (DR5108, DR4468A, DR4501, DR4521, DR5316, DR5430 …). A lone photo is now used as the front one, which is how the GIII side has always read it. An explicit `_front` still wins wherever it is, so nothing that worked before changes."},
            {"type": "fix", "text": "**Filename case no longer decides whether a photo is found.** The folder listing was matched exactly, so `dr5108_front.png` missed `DR5108`. Windows and the WebDAV mount are both case-insensitive — the lookup now is too."},
            {"type": "docs", "text": "The “no photo” warning and the 🖼 Photo issues note now name `<style>.png` as an accepted filename, so they stop pointing at a file you don’t need to create."},
        ],
    },
    {
        "version": "2.116.2",
        "date": "2026-07-29",
        "entries": [
            {"type": "fix", "text": "**The empty column is closed in every block, not just the widest one.** Each fabric writes its metrics immediately to the right of *its own* size columns, so a plan with a 10-size fabric and a 5-size one puts 裁剪长度 on two different sheet columns — and the column one fabric uses for a metric the other uses for a size. Clearing the cells and deleting the empty sheet column could therefore only ever come out right for the widest fabric; every narrower one kept a blank bordered cell between 利用率,% and 版长,cm. The gap is now closed inside each block instead, moving that block's own metrics left over its own rows — values, borders and merged headings together — and leaving the rest of the sheet untouched."},
            {"type": "fix", "text": "**No stray 平均版长 under the totals.** A fabric's 平均版长 is printed one row below its own 总台数, which put it outside the block being removed — so exporting a single fabric left the other one's figure sitting on its own beneath the plan totals. Each block now reaches past its end marker to claim it."},
        ],
    },
    {
        "version": "2.116.1",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**The empty column really is gone this time.** Clearing a column left its own one-cell heading merge behind, and the rule that protects merged headings was holding the emptied column open. A merge confined to a single line is that line’s own, not structure, so it no longer pins it — 面料长度, 利用率 and 版长 now sit side by side and the sheet is 15 columns wide instead of 17."},
            {"type": "feat", "text": "**One clear row above every box.** 订单需求, 版定义, 裁剪配比, 铺布层数 and 排版结果 each get exactly one blank row above them, so the blocks read as separate tables rather than one run-on grid. Blocks that already had a gap are left alone, and merged headings move with the inserted row."},
        ],
    },
    {
        "version": "2.116.0",
        "date": "2026-07-28",
        "entries": [
            {"type": "feat", "text": "**The PDF can be built for one fabric too.** The fabric picker now appears on the PDF of the original file, alongside the cleanup tick-box — so the sheet the cutting room gets for the shell doesn’t carry the lining’s markers. The fabrics are read from the workbook itself: each one’s 版定义 / 裁剪配比 / 铺布层数 / 排版结果 blocks are removed together, with merged headings carried along."},
            {"type": "fix", "text": "**The plan total matches what’s on the page.** Exporting one fabric used to leave the plan-wide 总台数 counting every fabric — a sheet showing four tables printed six. It is re-added from the blocks actually left on the sheet. The order-demands block and the header are never touched, and a selection that matches no fabric on the plan leaves it whole rather than producing an empty sheet."},
        ],
    },
    {
        "version": "2.115.0",
        "date": "2026-07-28",
        "entries": [
            {"type": "feat", "text": "**Export one fabric of a cut plan, or all of them.** A plan covering shell and lining now offers a fabric picker before the build, on both the saved-plan screen and the standard output. Shell and lining are cut at different widths on different tables, so the sheet often only needs one of them. Everything is selected by default and clearing the selection means all of them — it never produces an empty sheet. Each chosen fabric keeps its own marker, spreading and solution blocks. A plan with a single fabric shows no picker, because there is nothing to choose."},
        ],
    },
    {
        "version": "2.114.1",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**No empty column or rows left behind on the cleaned cut plan.** Emptying the dropped column and the duplicate style rows left gaps where they used to be. Those now close up — 面料长度, 利用率 and 版长 sit next to each other, and the header block runs straight down from 日期 to 客户. Merged headings are carried along with the shift, which is what went wrong the first time this was tried; a blank line that is part of a merged heading is left in place, because it is holding the layout rather than being a gap."},
        ],
    },
    {
        "version": "2.114.0",
        "date": "2026-07-28",
        "entries": [
            {"type": "feat", "text": "**裁剪长度 and 材料成本 are gone from the cleaned cut plan too.** Both columns are now emptied on the PDF of the original file as well as on the standard sheet — heading and every figure under it, in each marker block. The cells are cleared, not the columns removed, so 面料长度, 利用率 and 版长 stay exactly where they were."},
            {"type": "fix", "text": "**The plan’s identifying rows are back.** Date, Order name, Style file 1 and 2, Cut plan operator and Client are kept on the cleaned sheet — they are how the cutting room tells one plan from another. Only the duplicate \"Style name\" rows (the file rows above already carry the style) and the output folder path are removed."},
        ],
    },
    {
        "version": "2.113.2",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**The cleaned cut plan’s layout no longer shifts.** Trimming the header was removing whole rows, which pulled everything underneath it up the sheet — the marker blocks ended up sitting under the wrong headings. Those cells are emptied in place now, so the unwanted labels disappear and every other cell stays exactly where the marker software put it. The cleaned sheet is the same size as the original, row for row and column for column."},
        ],
    },
    {
        "version": "2.113.1",
        "date": "2026-07-28",
        "entries": [
            {"type": "perf", "text": "**Signing in is no longer held up by an offline CPRS server.** The sidebar checks whether CPRS is reachable, and an unreachable server costs the full connection timeout — which was being paid on the first screen after sign-in and again every twenty seconds for as long as CPRS stayed down. A server that is switched off does not come back between one click and the next, so a failed check is now trusted for five minutes instead of twenty seconds. **Refresh** still forces an immediate re-check the moment it comes back. When CPRS is up nothing changes."},
        ],
    },
    {
        "version": "2.113.0",
        "date": "2026-07-28",
        "entries": [
            {"type": "feat", "text": "**Generated files can go straight to a folder.** Both **Build PDF** and **Build standard cut plan** now take an optional folder path; leave it blank and nothing changes, fill it in and a copy is written there as well as offered for download — so the cutting room’s shared drive doesn’t need a manual copy step. The path is confirmed on screen after each build, and a folder that doesn’t exist or can’t be written says so instead of failing quietly."},
            {"type": "fix", "text": "**One \"Clean for the cutting room\" tick-box, not two.** The standard cut plan had its own copy of the option sitting next to the PDF’s. The standard sheet is always built for the cutting room, so its tick-box is gone; the PDF keeps one, because that renders the original workbook and is the copy people sometimes want raw."},
        ],
    },
    {
        "version": "2.112.1",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**Every total was blank on the cleaned cut plan.** Marker sheets carry around seventy `=SUM()` cells. The cleanup was opening the workbook with its formulas rather than its values, and saving drops the stored results — so the PDF, which prints values, found nothing behind any of them. Ticking \"Clean for the cutting room\" therefore lost every sum while leaving it unticked kept them. The cleanup now reads values, baking each formula down to its number before anything else happens."},
            {"type": "feat", "text": "**The whole sheet is in Chinese now, not just some of it.** The remaining fixed headings are translated — 面料 / 排版结果 / 铺布层数 / 合计 / 尺码 / 数量 / 客户 / 日期 / 总利用率 / 总成本 / 总台数 / 平均版长 and the rest. Only unit suffixes (cm, m, %) stay as they are."},
        ],
    },
    {
        "version": "2.112.0",
        "date": "2026-07-28",
        "entries": [
            {"type": "feat", "text": "**The cut plan handed to the cutting room is trimmed to what it uses.** Two marker columns are gone — *Cut Length,m* and *Material Cost,CNY* (the cost column was repeating the fabric length rather than a cost). The header block now shows only the style files, the cut plan operator and the client; Date, Time, Order name, the \"Style name\" echo of each file and the output folder path are dropped. The PO / PC / PO-style rows stay, since they are what ties the sheet to its order."},
            {"type": "fix", "text": "**Linked orders now open with the full size and colour breakdown.** Expanding a linked order on a cut plan shows one row per style and colour with a column per size and the line total, instead of a flat list. Sky East orders read their size columns directly; GIII orders are pivoted from their per-size rows."},
            {"type": "refactor", "text": "**Header trimming happens on the delivered copy, not the stored one.** The saved sheet keeps every row because the app re-parses its own export and reads the order name back out of it — removing those rows outright broke that round-trip, which the existing tests caught. The trim now runs in the same cleanup pass as the Chinese headings, so the file you hand over is short and the file the app reads stays complete."},
        ],
    },
    {
        "version": "2.111.0",
        "date": "2026-07-28",
        "entries": [
            {"type": "perf", "text": "**Every screen now builds only the panel you are looking at.** The remaining tab bars have been converted: GIII and Sky East (four panels each), Summary, Email, Reference Data, the GIII Generate/Export pair, the tracking planner and the Translations admin. Before this, opening any of them ran every panel behind it — all the list queries, tables and export builders — to display one. The heaviest were GIII and Sky East, which each rebuilt uploads, generate/export, contract history and missing-fields on every interaction."},
            {"type": "refactor", "text": "**One helper does it, so it cannot drift back.** `lazy_sections()` in `ui/shared.py` replaces nine hand-written tab blocks and carries the reasoning with it: a tab bar that shows one panel should not build the others, the choice must survive the reruns buttons cause, and a stored choice has to be dropped when the language toggle changes the labels. The app now has no `st.tabs` left in it."},
        ],
    },
    {
        "version": "2.110.5",
        "date": "2026-07-28",
        "entries": [
            {"type": "perf", "text": "**Opening Cutting Plan is quick again.** The tab was building all three of its sections every time it opened — the upload screen with its PO pickers, the saved-plan list with each plan's detail, and the standard-output demand matrices — to show one of them. Only the section you pick is built now. This is the same tab-bar behaviour fixed in the main navigation in v2.110.0 and in the plan detail in v2.110.2; the remaining tab bars (GIII, Sky East, Email, Reference Data and the sub-tabs inside them) still work this way and are worth the same change."},
        ],
    },
    {
        "version": "2.110.4",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**Two different order numbers no longer share a column heading.** Our own PO number and the client's PO were both displayed as \"PO No.\" — in the Summary tab they appeared under identical headings in two tables, meaning different things. Each now has one heading of its own, used everywhere: **PO Number** for our PO, **Zalando PO** for the client's, **PC No.** for the Sky East contract number. The Sky East items table was the clearest case — the client's PO was being labelled from our own PO's column-mapping entry, so renaming that field in Admin would have relabelled the wrong column."},
            {"type": "fix", "text": "**The cut plan's linked-order column was mislabelled.** It reads \"Zalando PO\" now, which is what the value actually is — confirmed against the stored data, where it matches the client PO on the Sky East items and no GIII PO. The UPC Check tables, which showed a bare \"PO\", now say \"PO Number\" like everywhere else. Workbook headings are untouched: the \"PO No.\" columns in the buy plan and the other exports are the layout the factory reads."},
        ],
    },
    {
        "version": "2.110.3",
        "date": "2026-07-28",
        "entries": [
            {"type": "refactor", "text": "**One name for a PO number in the code.** The same value was being called `po_number` in most of the codebase, `po_num` in the production-plan and fax extractors, and `po_no` in the requirements resolver — 57 places now all say `po_number`. Nothing users see changed: the \"PO No.\" column headings on the buy plan and the other workbooks are the layout the factory reads and were deliberately left alone, as were the database column names."},
            {"type": "docs", "text": "**Written down which identifier is which.** PO number, Sky East PC No. and the client's own PO look interchangeable and are not — a lookup using the wrong one silently returns nothing rather than failing, which is exactly how a recent bug behaved. The project notes now record all three, where each is keyed, and why two database columns keep their older spelling: an outside service reads this database directly, so renaming a column would quietly break it."},
        ],
    },
    {
        "version": "2.110.2",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**\"Build PDF\" and \"Build standard cut plan\" appeared to do nothing.** Both buttons worked — the file was being produced — but they sat inside a tab group, and the rerun a button triggers resets that group back to its first tab. The download the button had just created was placed on a panel that was no longer on screen. The plan's Linked POs / Quantities / Materials / Files selector now keeps the panel you were on, so the result appears where you are looking."},
            {"type": "feat", "text": "**The cutting-room cleanup is now an option on the PDF of the original file.** That workbook is the one the cutting room reads, so the tick-box lives there: ticked, the PDF is rendered from a cleaned copy (Chinese headings, marker names only, PO colour names) and the filename gets a `_clean` suffix; unticked, the full workbook is rendered exactly as it is. The cleanup runs on a throwaway copy in memory — the stored file you can download is never modified, and if the cleanup fails the PDF is still produced from the untouched original."},
            {"type": "feat", "text": "**Linked orders open from the plan itself.** Each linked order on a cut plan can be expanded in place to show its lines, without going to another tab to find it. The lookup runs only for the order you actually open, and each pipeline is queried by the identifier it really uses — GIII by PO number, Sky East by PC No. — so both resolve. An order deleted since the plan was linked says so rather than showing an empty table."},
        ],
    },
    {
        "version": "2.110.1",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**Double outline on the sign-in fields.** The username and password boxes were drawing two borders, one inside the other — most obvious on the focused field, where both turned pink. The field styling was being applied to the input element itself, which sits inside a wrapper that already draws its own border. The box is now drawn once, on the wrapper. As a side effect the password reveal button sits inside the field instead of floating beside it, so both fields match."},
        ],
    },
    {
        "version": "2.110.0",
        "date": "2026-07-28",
        "entries": [
            {"type": "perf", "text": "**Pages open far faster — only the section you're looking at is built.** The tab bar rendered *every* tab's contents on every page load, not just the visible one: all twelve sections plus all twelve admin panels, so one load ran every list query, table and download-builder in the app, and threw almost all of it away. (Wrapping tabs in fragments didn't prevent this — a fragment only narrows *later* reruns, it still runs in full on a page load; this was confirmed by test, not assumed.) Navigation is now a single-select bar and one page load does one section's work. Everything is where it was and nothing else changed — the heaviest panels, the translations editor with 1,500+ rows and the 6,000-row fabric table, are simply no longer built when you aren't looking at them."},
            {"type": "feat", "text": "**The cut plan comes out ready for the cutting room.** The cleanup that used to be a hand-run Excel macro now happens in the app: English headings become the Chinese the cutting room reads (订单数 / 颜色 / 层数 / 裁剪配比 / 版长 / 面料长度 / 裁剪长度 / 材料成本), and marker cells that arrive as full Windows paths are reduced to just the marker name. There's a tick-box on both Build buttons, on by default; untick it for the raw English layout, which is the copy that can be re-uploaded and re-parsed."},
            {"type": "feat", "text": "**Colours on the cut plan are named the way the PO names them.** A colour still in English is rendered in Chinese using your PO colour translations, and a colour that is already Chinese is left alone. If the plan's own Chinese name disagrees with the PO's — the plan says 深蓝 where the PO says 藏青 — the difference is listed for you and **nothing is changed**; a button applies the PO's names to the downloadable file only if you ask, and never touches the stored plan."},
            {"type": "perf", "text": "**Tracking records are no longer dragged around whole.** The tracking table is ~175 columns wide, and building the row dictionaries — not the query — was the cost. Screens that need only a PO and style now ask for only those: the CMPT contract prefill went from 19.7 ms to 1.7 ms per rerun."},
        ],
    },
    {
        "version": "2.109.2",
        "date": "2026-07-28",
        "entries": [
            {"type": "fix", "text": "**MemoryError when opening Missing Fields (and other photo tables).** Style photos were being inlined into table cells at full resolution: source images here run to 15 MB each, base64 adds a third on top, and every photo was held twice — raw bytes in the session cache and again as an encoded string. A single table came to roughly 190 MB held on the server and shipped to the browser, for cells rendered a few dozen pixels wide. Photos are now downscaled to a 160 px thumbnail before encoding: the same 139 images went from 187.6 MB to 2.9 MB, 65× smaller. Excel exports are untouched and still embed the full-resolution originals."},
            {"type": "fix", "text": "**One unreadable photo can no longer take down the tab.** The image loader caught only `OSError`, so a `MemoryError` escaped and killed the whole page. Failures now skip that image alone and the skipped IDs are reported. A memory ceiling stops a very large batch from exhausting the machine mid-render, and it never returns nothing — a single image over the ceiling is still loaded, because an empty table is worse."},
            {"type": "fix", "text": "**BLAS thread pools capped at startup.** numpy's OpenBLAS reserves per-thread buffers for every core at import time — 28 on this machine — which on a box near its memory limit is itself the failing allocation, aborting the process with \"Memory allocation still failed after 10 retries\". The cap is set inside the app before numpy loads, so it applies however the app is launched; an explicit value in the environment still wins. This app does dataframe work, not linear algebra, so there is no performance cost."},
        ],
    },
    {
        "version": "2.109.1",
        "date": "2026-07-27",
        "entries": [
            {"type": "refactor", "text": "**Dropped the m/piece column.** Fabric consumption is now shown per garment (**m/unit**) only — the per-piece figure was a second way of saying the same thing and isn't what fabric is ordered against."},
        ],
    },
    {
        "version": "2.109.0",
        "date": "2026-07-27",
        "entries": [
            {"type": "feat", "text": "**Fabric consumption per garment (单耗).** Every fabric row now carries **m/unit** — metres of that fabric per garment, the figure fabric purchasing orders against — and **m/piece**, metres per cut piece. They differ whenever one fabric yields several pieces of a garment: on a co-ord set the shell supplies both the trousers and the top, so per garment is double per piece. Shown on the saved-plans list, on the plan detail, and in the upload preview before saving. Cross-checks against the plan's own *Average Length* line, which is the per-piece figure."},
            {"type": "feat", "text": "**Total per fabric across the listed plans.** A collapsible panel under the table totals each fabric's requirement across every plan on screen — how many metres of each fabric to buy. Grouped strictly by fabric; different fabrics are never added together."},
            {"type": "fix", "text": "A fabric with no recorded length shows a blank consumption rather than 0, which would read as \"this fabric costs nothing\"."},
        ],
    },
    {
        "version": "2.108.0",
        "date": "2026-07-27",
        "entries": [
            {"type": "feat", "text": "**Cut vs PO % on every cut plan.** A new column shows how far the plan's cut quantity sits from what the linked PO ordered — positive means overcut — and the plan detail's *Cut qty* tile carries the same figure. It's blank when no PO is linked, since there's no baseline to measure against. Plans that don't match are still called out under the table, now with the percentage."},
            {"type": "fix", "text": "**\"Cut qty\" split into two clearly different numbers.** A fabric's figure counts every *piece* cut from it while the PO counts *units*, and for a co-ord set those differ by design — the shell yields both the trousers and the top, so its piece count is double the units. Comparing the two would have read as +111 % when the plan is only 5.7 % over. The per-fabric column is now labelled **Pieces**, **Cut qty** is the unit count, and the percentage is calculated from the unit count alone."},
        ],
    },
    {
        "version": "2.107.0",
        "date": "2026-07-27",
        "entries": [
            {"type": "feat", "text": "**Saved plans list shows one row per fabric.** Shell and lining are different fabrics at different cuttable widths, so combining them into a single metre count and an averaged efficiency produced a number nobody could act on — 2,020 m of 157 cm shell plus 64 m of 173 cm lining is not \"2,085 m\". Each fabric now gets its own line with its own width, markers, tables, plies, cut quantity, metres, efficiency and cost; plan-level details repeat alongside. The same per-fabric breakdown replaces the combined figures on the plan detail screen and in the upload preview."},
            {"type": "feat", "text": "**PO quantity shown next to the plan's own quantity.** **PO qty** is what the linked PO(s) and styles actually ordered, read from the Sky East contract; **Plan qty** is what the cut plan was built for. They should agree — a gap usually means the plan was built against a superseded quantity or linked to the wrong styles — so any plan where they differ is flagged under the table. Items are counted once even when a plan holds both a whole-PO link and a per-style link."},
            {"type": "fix", "text": "Plans uploaded before this release are backfilled automatically: the per-fabric figures were always in the stored parse, so they're unpacked into the new table on first open rather than the plan disappearing from the per-fabric list. A plan whose materials couldn't be read still appears, with the fabric columns empty."},
        ],
    },
    {
        "version": "2.106.0",
        "date": "2026-07-27",
        "entries": [
            {"type": "feat", "text": "**Cut plans link to the styles inside a PO, not just the PO.** A Sky East contract carries several styles and a cut plan usually cuts only some of them, so linking now has a third level: PC No. → PO No. → style. Leave the style picker empty and every style in the selection is linked, as before. This is also where the naming gap gets bridged: the plan names its styles after the CAD files (`S24DTR003`) while the PO uses the client's style codes (`TP5016`), and nothing in either file connects the two — the link is the mapping."},
            {"type": "feat", "text": "**Two plans can now cover one PO without colliding.** Look a plan up by PC No., PO No. *or* style, and the standard output for a plan shows only the styles that plan actually cuts — a PO's other styles belong to someone else's cut plan. The saved-plans list gained a **Linked styles** column, the linked-PO count is now distinct POs rather than link rows, and the search box matches on style too."},
            {"type": "fix", "text": "Existing links are migrated automatically: the links table is rebuilt with the wider uniqueness key and old rows become \"the whole PO\", which still matches any style they're queried for, so nothing that was linked before stops being found."},
        ],
    },
    {
        "version": "2.105.0",
        "date": "2026-07-27",
        "entries": [
            {"type": "feat", "text": "**Cutting plans export to PDF, every column on one page.** Both the standard version and the original uploaded file now have a **PDF version** panel next to the Excel download. Columns are never split across sheets of paper: column widths, row heights and the font are scaled by a single factor, exactly as Excel's *fit all columns on one page* does, and long sheets continue onto further pages. Page margins are minimal (2 mm) so the widest plan still gets a readable font. Page size (A4 / A3 / Letter) and orientation are selectable — a plan covering many styles is much easier to read on A3."},
            {"type": "feat", "text": "**Nothing is clipped on the printout.** Columns are sized to the text they actually hold rather than to the width stored in the file — the Optitex export ships 12-character columns holding 50-character marker paths, which Excel hides by spilling text over neighbouring cells but a printout would simply cut off. Text still spills over genuinely empty cells the way Excel does, a single very long value can't starve the rest of the sheet, and Chinese colour and material names render correctly alongside Latin text instead of being stretched to double width."},
            {"type": "refactor", "text": "Conversion runs on PyMuPDF, already a dependency, rather than driving Excel over COM — so it works on a server with no Office installed and can't hang a worker thread. `PDF_MIME` joins the other MIME types in `po_extractor/config.py`."},
        ],
    },
    {
        "version": "2.104.0",
        "date": "2026-07-27",
        "entries": [
            {"type": "feat", "text": "**New ✂️ Cutting Plan tab — upload a cut plan, link it to the PO(s) it covers.** Cut plans are produced outside the app by the marker software (Optitex Cut Plan export): the file carries the marker ratios, ply counts, marker length, efficiency, fabric consumption and material cost, and none of it is recalculated here. Upload the .xlsx and the app reads every block — order demands, marker definition per material, marker ratios, spreading plies, and the solution — then records which POs it covers. One plan can cover many POs, and a PO can be re-cut under a later plan, so the link is many-to-many and a plan can be looked up by either PC No. or PO No. Re-uploading the identical file is flagged before it's saved twice, and the original file is kept so it can always be handed back unchanged."},
            {"type": "feat", "text": "**Standard output — one layout for every PO's cutting plan.** Different POs' plans arrive in different shapes. Pick the PO(s) and the app emits the plan in one house layout, with the *Order demands* block rebuilt from the PO itself, so the sheet always states what was actually ordered. Marker sections are filled from the cut plan(s) linked to those POs; when nothing is linked yet you get the same standard layout with those sections blank for the cutting room to complete. Plans that overcut (a marker ratio rarely divides an order exactly) are read correctly — the *Order* / *Real* split is preserved, and the per-size ordered-vs-cut difference is shown."},
            {"type": "feat", "text": "**Separate permission — Buy Plan users do not get it.** Cutting Plan is its own module in **Admin → Users**, granted explicitly and never implied by either Sky East module: cut plans expose marker efficiency, fabric consumption and material cost, which the Sky East Buy Plan role must not see. A user with *Sky East — Buy Plan only* keeps that tab and does not gain this one."},
        ],
    },
    {
        "version": "2.103.1",
        "date": "2026-07-27",
        "entries": [
            {"type": "security", "text": "**Stored XSS in the processing log — closed across every pipeline.** The \"Processing log\" panel renders its lines as HTML so it can colour them, which makes every value written into a line an injection point — and those values include uploaded filenames and cell contents from supplier workbooks. A file named `<img src=x onerror=…>.xlsx` could run script in the operator's browser. v2.75.6 fixed this for the GIII Excel pipeline only; the Sky East pipeline, the GIII PDF/smart pipeline, and the Sky East validators were left raw, and even the \"fixed\" file still had unescaped values. All 87 interpolation points across all four log producers are now HTML-escaped, plus the Sky East change-diff panel."},
            {"type": "security", "text": "**The escaping rule is now machine-enforced, so it can't silently regress again.** A new test parses each log-producing module and fails if any value reaches the log without `html.escape()` — the check that would have caught both the original gap and the incomplete v2.75.6 fix. It's paired with a test proving a hostile filename comes out inert, and a self-check proving the detector actually fails on unescaped input."},
            {"type": "security", "text": "**Hardened XML parsing for uploaded workbooks.** Sheet XML from an uploaded `.xlsx` is now parsed with `defusedxml` when available, so a crafted entity-expansion file can't be used to exhaust memory. The refusal is caught alongside the existing parse errors, so a hostile file is skipped exactly like an unreadable one instead of surfacing as a crash. Falls back to the standard parser when `defusedxml` isn't installed."},
        ],
    },
    {
        "version": "2.103.0",
        "date": "2026-07-24",
        "entries": [
            {"type": "fix", "text": "**Correctness fixes from a full-codebase review.** The GIII PO-summary Excel's *Extended Cost* now multiplies units by the per-unit FOB (it previously used a field that was sometimes a whole-PO total, inflating the number). The GIII buy plan no longer aborts when a size cell is blank or holds a decimal like `12.0` — those become 0 / 12 instead of crashing the whole plan. Fabric HHN codes stop at the code itself: `大身：HHN-JA-01715，300克/平方米` reads as `HHN-JA-01715`, not the code plus its description. A blank new row in **Admin → Size Order** is dropped instead of being saved as a phantom size `NONE`, and a non-numeric weight/width cell (`300g`, `TBC`) no longer breaks the fabric lookup. The factory progress form keeps a real order quantity of 0 rather than blanking it."},
            {"type": "fix", "text": "**Reference files can't take the app down.** If a lookup workbook (fabric 洗标, EAN export) is missing, corrupt, or password-protected, that lookup now stays empty and logs a warning instead of crashing every buy plan that reads it. Sky East processing shows a clean error message (and never a stale previous batch) if a post-parse step fails, rather than dumping a raw traceback."},
            {"type": "security", "text": "**Concurrency & input hardening.** Several first-write-wins races between simultaneous users (settings migration, colour-translation import, inbound-email and contract inserts) are now idempotent. Uploaded filenames are normalized before being used in paths, the image-cache prune can only ever delete inside its own folder, and production-tracking writes validate column names against the live schema so a typo'd field surfaces as a clear error instead of malformed SQL."},
        ],
    },
    {
        "version": "2.102.1",
        "date": "2026-07-24",
        "entries": [
            {"type": "refactor", "text": "**Cross-cutting constants centralized in `po_extractor/config.py`.** The OOXML spreadsheet MIME type (previously re-typed in ~20 places — one transposed character silently breaks a download), the ZIP/HTML/CSV types, the CPRS request timeouts (the inline 120 s / 300 s export waits), and the sign-in lockout policy now live in one place and are imported everywhere. Behaviour is identical (every value unchanged; full suite green) — this only removes duplication so these knobs are tuned once. The design-asset colours in the login screen were deliberately left inline."},
        ],
    },
    {
        "version": "2.102.0",
        "date": "2026-07-24",
        "entries": [
            {"type": "feat", "text": "**Sign-in audit log (admin only).** Every login attempt is now recorded — who, when, and how it went — and a new **Admin → 🔐 Login Log** tab shows it: successful logins plus wrong-password and lockout events, newest first, with a summary row (successful logins · distinct users · failed · locked), filters by outcome and username, CSV export, and maintenance controls to purge old rows or clear the log. The forwarded client IP is captured when the app runs behind a reverse proxy. Regular users never see it; recording is fully guarded so a logging hiccup can never block a real sign-in."},
        ],
    },
    {
        "version": "2.101.0",
        "date": "2026-07-23",
        "entries": [
            {"type": "feat", "text": "**The DSP upload now reads PDFs — the format buyers actually send.** The same uploader accepts PDF (or Excel): tables are extracted page by page with the same bilingual header matching, a multi-page table whose continuation pages repeat or omit the header row is stitched back together, repeated in-table header lines are skipped, and when the style lives in the page banner (\"STYLE: DU5105\") rather than a column, that stated style applies to the page's rows — extraction of a stated fact, never invention. A scanned-image PDF (no text layer) is refused with a clear message rather than returning nothing."},
        ],
    },
    {
        "version": "2.100.0",
        "date": "2026-07-23",
        "entries": [
            {"type": "feat", "text": "**Upload the buyer's DSP file — the trim list becomes DSP-first.** The 🧭 API documents section gained an optional DSP upload (CPRS ≥1.6.16). The app extracts per-trim rows — 款号, 辅料名称, 料号, supplier, placement, 单件用量, colour, and an optional explicit PO list — and sends them as `dspTrims[]`. In the generated pack, DSP rows form the trim list's A section with order-quantity formulas; CPRS rule rows follow, marked 以 DSP 为准 wherever they disagree; and the pack carries a verbatim per-style DSP appendix sheet. Verified live: a DSP row fed in came back inside the generated Trim_List.xlsx."},
            {"type": "feat", "text": "The parser copes with real buyer files: the header row is found anywhere in the first rows of any sheet (English or Chinese headings, banner rows above tolerated), a blank 用量 is sent as 0 so the API renders 按TP rather than a made-up number, junk cells become listed warnings instead of failures, and when several order contexts are selected each trim is routed to the context its style or explicit PO list belongs to. As always, CPRS never reads the mailbox or the file itself — extracting and structuring the DSP is the app's job, and everything extracted is passed through verbatim."},
        ],
    },
    {
        "version": "2.99.0",
        "date": "2026-07-23",
        "entries": [
            {"type": "feat", "text": "**One click now fetches the whole CPRS document pack.** The 🧭 section (upload panel and Generate / Export alike) gained a mode choice: **📦 Full doc suite** calls CPRS's new `/export/doc-suite` (≥1.6.15) and returns one ZIP per order context containing the factory requirements (no commercial info — safe to forward), bilingual packing cards with per-carton panels (18 kg cap, 1-SKU-solid and similar rules pre-applied), the rules-driven 辅料 trim list (.xlsx, with order-quantity formulas and tracking dropdowns), the internal priced variant, and a manifest. The single-HTML requirements doc remains available as the second mode."},
            {"type": "feat", "text": "Same pass-through contract as before: the decoded /evaluate context plus your PO register and confirmed notes go to CPRS verbatim, and the returned pack is saved untouched — the suite already includes both variants, so no variant choice (and no app-side filtering) applies in suite mode."},
        ],
    },
    {
        "version": "2.98.0",
        "date": "2026-07-23",
        "entries": [
            {"type": "feat", "text": "**The API requirements document is now on Generate / Export too.** The 🧭 API requirements document (HTML) section — variant, image embedding, confirmed notes, Generate — appears under the action buttons on GIII → Generate / Export → Generate Outputs, built from the **stored** PO data for whatever POs you've selected (no re-upload needed). Selected POs group into one document per order context (e.g. all 32 Calvin Klein · ROSS POs in one file), and POs whose brand can't be decoded are listed rather than silently dropped. Same section, same behavior as the upload panel — one request builder feeds both, so the two entry points can never disagree."},
        ],
    },
    {
        "version": "2.97.1",
        "date": "2026-07-23",
        "entries": [
            {"type": "fix", "text": "**API requirements doc: matched the endpoint's actual contract.** `/export/requirements-doc` takes the *decoded* `/evaluate` context (clientId + channel), not the raw PO. Generation now runs the stored raw PO through CPRS's own `/evaluate/po` first (cached since upload, so no extra wait) and passes the decoded context through verbatim — the app still resolves nothing itself. Verified live against CPRS 1.6.14: a factory-variant document generated end-to-end (27 cards)."},
        ],
    },
    {
        "version": "2.97.0",
        "date": "2026-07-23",
        "entries": [
            {"type": "feat", "text": "**GIII: generate the requirements document through the CPRS API.** Next to the existing 要求文档 (.xlsx), the results panel now has an **API requirements document (HTML)** section using CPRS's new `/export/requirements-doc` endpoint (CPRS ≥1.6.14). Pick 工厂 factory (prices stripped — safe to send out) or internal (full), optionally embed the manual artwork, add confirmed notes (one per line), and Generate — you get a self-contained bilingual HTML pack per order context, with the API's card/image counts shown. Several contexts download as one zip."},
            {"type": "feat", "text": "True to the CPRS design principle, the app invents nothing: the same raw-PO context that `/evaluate/po` gets is sent along with a PO register (SO, style, colours, size breakdown, qty, ETD, CPO, MSRP, FOB/amount) taken verbatim from the parsed POs — a missing CPO stays missing and CPRS itself renders 待定. The variant is the only policy and it's the API's: business fields are always sent, and the factory variant strips them server-side. Request bodies are prepared at upload time (no CPRS traffic until you click Generate)."},
        ],
    },
    {
        "version": "2.96.0",
        "date": "2026-07-23",
        "entries": [
            {"type": "feat", "text": "**Sign-in v2 — the designed split-screen login is live.** Implemented from the claude.ai/design project (\"Threadline Login.dc.html\"): the left panel carries the wordmark, the headline, a four-step journey strip (客户订单 Client PO → 采购计划 Buy Plan → 生产 Production → 交付 Delivery) and a line-art atelier scene — spool, garment rack, dress form, sewing machine, parcel — crossed by a slowly moving stitched thread. The right panel holds the sign-in form with rounded fields and the gradient button."},
            {"type": "feat", "text": "**Choose your language before signing in.** A 🌐 pill in the form panel switches English ↔ 中文 on the spot — factory logins land in their own language without touching the sidebar. All new copy is seeded bilingually, with the Chinese taken from the design file itself. Typography upgraded to Bricolage Grotesque + Schibsted Grotesk (+ Noto Sans SC for Chinese); dark mode and reduced-motion are both respected, the hero hides on narrow phone screens, and the styling stays scoped to the login page only."},
        ],
    },
    {
        "version": "2.95.0",
        "date": "2026-07-22",
        "entries": [
            {"type": "feat", "text": "**The app is now called Threadline** 🧵 — the thread that runs from a client PO through buy plans to the factory floor. \"PO Extractor\" no longer described what it grew into. The name is set in one place (`APP_NAME`) and flows to the login screen, the sidebar, the browser tab, and outbound emails."},
            {"type": "feat", "text": "**A bold, friendly new sign-in screen.** A warm gradient backdrop, a big rounded logo badge, a large welcome headline, pill-shaped inputs with a focus glow, and a full-width pill Sign In button — a modern, approachable first impression. It adapts to light and dark, and the styling is scoped to the login page only, so the rest of the app is untouched and the page stays fast to load."},
        ],
    },
    {
        "version": "2.94.0",
        "date": "2026-07-22",
        "entries": [
            {"type": "feat", "text": "**Factory dictionary — one factory, many names.** Different clients write the same factory differently (\"01423 - CHANGZHOU JINTAN XINZHUAN\" vs \"…XINZHUANGYUAN GARMENT CO.,LTD.\" vs a bare code), so the same factory looked like several. A new **Admin → 🏭 Factories** tab holds a canonical factory and every alias that maps to it."},
            {"type": "feat", "text": "**Unknown names are caught and queued for review.** When a loaded PO carries a factory name that isn't in the dictionary, it shows up under *Needs review* (the tab title carries a count badge). For each, the admin either links it as an alias of an existing factory — a fuzzy suggestion, matched on the shared code like \"01423\", is pre-selected — or approves it as a new factory. Regular users keep loading POs uninterrupted; nothing is auto-added without an admin's say-so."},
            {"type": "feat", "text": "**Factory logins now follow the canonical factory.** A factory-scoped user (v2.93.0) is assigned a canonical factory, and Tracking matches every one of its aliases — so a single assignment covers all the client-specific spellings, and the near-duplicate-name problem is gone. Assignments made before the dictionary existed still match by exact name."},
        ],
    },
    {
        "version": "2.93.0",
        "date": "2026-07-22",
        "entries": [
            {"type": "feat", "text": "**Factory logins for Tracking.** A user can now be scoped to one or more factories (Admin → Users → *Factory scope*). A factory user sees **only their own factory's rows** in 🏭 Tracking and may record **progress only** — actual/completion dates, quantity reports, and status notes. They cannot set planned dates, cannot add or remove tracking rows, and never see other factories or the Advanced 22-stage editor. The grid is pinned to 实际 Actual for them, and the Add / Remove tab is hidden. Perfect for giving a factory contact a login to report their own progress."},
            {"type": "security", "text": "**Client and factory scope is now enforced on every write, not just the view.** Previously a scoped user's Excel or factory-form upload could apply to any PO in the file — including clients they can't see. Now every apply path (grid save, grid Excel import, factory progress-form import, returned buy-plan import) checks each row against the user's access and refuses out-of-scope rows, reporting how many were blocked. A factory user's planned-date edits are stripped on import. Scoping is real now, not cosmetic."},
            {"type": "feat", "text": "Client-scoped users (e.g. a Sky East-only account) are unchanged in spirit but now genuinely can't reach another client's tracking rows through a crafted upload. Admins are unrestricted as before."},
        ],
    },
    {
        "version": "2.92.0",
        "date": "2026-07-22",
        "entries": [
            {"type": "feat", "text": "**Edit the whole Tracking Grid in Excel.** A new **📊 Excel export / import** panel under the grid lets you download the rows you're looking at as a spreadsheet, edit the milestone dates in Excel, and upload it back to apply — much faster than typing into the on-screen table for a whole season. The export carries both the **计划 Planned** and **实际 Actual** date of all nine milestones (colour-coded blue/green), so nothing is lost in the round-trip. On import you get a preview of how many dates each PO/style will receive before anything is written."},
            {"type": "feat", "text": "The import is deliberately safe: columns are matched by their header text (so reordering columns in Excel doesn't scramble anything), a **blank cell never erases** a stored date (clear a date in the on-screen grid instead), a filled Actual date marks that milestone done — exactly like the grid — and a mistyped date is reported and skipped rather than poisoning the whole file. Rows whose PO/style is no longer tracked are flagged and skipped, never silently dropped."},
        ],
    },
    {
        "version": "2.91.2",
        "date": "2026-07-22",
        "entries": [
            {"type": "fix", "text": "**Newly-loaded orders now show up on the Tracking Grid.** Loading contracts — Sky East orders especially — never made them appear in the grid, because tracking rows are only created when you add them, and the only place to do that was buried in the **➕ Add / Remove** tab. The grid now shows a banner at the top — *“N loaded PO/style(s) are not tracked yet”*, broken down by client — with a **Track all N new** button right there. One click creates empty tracking rows for every untracked order (their milestones then fill in from the buy plan and factory reports as usual). Nothing is auto-added — the grid stays opt-in — but the orders you just loaded are now one click from the grid instead of hidden. The banner also shows even when nothing is tracked yet, so a fresh install can populate the grid immediately."},
        ],
    },
    {
        "version": "2.91.1",
        "date": "2026-07-22",
        "entries": [
            {"type": "perf", "text": "**The app starts and the login page appears far faster.** Two things were loading the entire program before you could even see the sign-in box. First, the view layer (every tab — Sky East, Fabric DB, GIII, the exporters and their pandas/Excel machinery) was imported up-front the moment anything from the `ui` package was touched, so the login screen paid for tabs a logged-out user never sees. It now loads each tab only when you open it. Second, the login module ran a full password-hash at import purely as a timing safeguard, and pulled in the (slow-to-load) crypto library on every start; both now happen only on the first actual sign-in. Cold start of the app module dropped from ~1.6 s to ~0.6 s, and nothing heavy (pandas, Excel, image, PDF or crypto libraries) loads until a signed-in user opens a tab that needs it."},
        ],
    },
    {
        "version": "2.91.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**📧 Email — the system can now receive as well as send.** A new tab reads a mailbox you point it at, lists what arrived, and recognises the four spreadsheets it already understands **by their contents, not their filename** (factories rename files constantly): the 进度回报表 progress form, a returned buy plan's Index tab, the 大货进度表, and a 面料统计表. Each attachment shows what importing it would change — how many quantity reports, how many milestone dates, which PO/styles — and an **Apply** button writes it in. Nothing is ever applied automatically."},
            {"type": "security", "text": "**Only senders you list are trusted.** Mail from an address that isn't on the allow-list is still shown — so you can see someone wrote in — but its attachments are locked and cannot be applied until you add that address. An empty list trusts nobody, so forgetting to configure it can never be the thing that lets data in. Add the sender later and their waiting files unlock without re-fetching the mailbox. Fabric lists are the one file type email will never apply: those keep going through the 🧵 Fabric DB approval queue, which is the stronger gate."},
            {"type": "feat", "text": "**Notifications for five events** — missing fabric information, a buy plan generated, milestones overdue, factory data received, and a fabric list waiting for approval. Each has its own recipient list on the Notifications tab; leave a row empty and that notification is simply off. A notification that fails to send never disturbs the work that triggered it — a buy plan that generated correctly stays generated even if the mail server is down."},
            {"type": "feat", "text": "**Compose** sends ad-hoc mail with attachments using the SMTP settings already in Admin → Email, and the mailbox itself is configured in an admin-only **⚙️ Mailbox** panel with a Test-connection button that reports what actually went wrong."},
            {"type": "feat", "text": "Mail is checked when you press the button and once when the tab first opens in a session — there is no background poller, so an unreachable mail server can never stall the rest of the app. Reading the mailbox never deletes or moves anything: messages stay where they are, and a mis-read file can always be applied again from the original."},
        ],
    },
    {
        "version": "2.90.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**Type one date, get nine — auto-plan for the milestone grid.** Rather than filling nine milestones per style by hand, the grid drafts them from a single date: **倒推** counts back from each style's 离厂时间 (already on the client PO — read from Sky East orders and GIII factory-ship dates alike), or **正推** counts forward from a production start date you enter. You pick the direction per selection. Both read one shared lead-time table, so the two directions can never disagree. By default only empty milestones are filled, so hand-tuned dates survive; a preview shows exactly what each row will get before you commit."},
            {"type": "feat", "text": "**Lead times are yours to set.** A Lead times tab holds the days-before-离厂时间 for each milestone (fabric 45 days, cutting 20, 后道 5, and so on as sensible starting points). Tune them once per client or factory and every future draft plan follows."},
            {"type": "feat", "text": "**Bulk shortcuts in the grid**: fill one milestone date down every selected row, copy a whole plan from one style onto others, and shift a style's remaining plan by N days when it slips (blank milestones stay blank — shifting never invents a schedule)."},
            {"type": "feat", "text": "**The status strip now shows urgency, not just progress** — 🔴 overdue (planned date passed with nothing recorded), 🟠 due within a week, ✅ done, 📅 scheduled, ⬜ not scheduled — so the grid tells you where to look."},
            {"type": "refactor", "text": "**The Advanced 22-stage panel is open to everyone now** (still collapsed by default) rather than admin-only, so the stage-level detail is there for anyone who grows into it."},
        ],
    },
    {
        "version": "2.89.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**🏭 Tracking rebuilt around one page — the milestone grid.** The tab now opens on a single editable table: one row per PO/style, one column per milestone (面料到厂 · 辅料到厂 · 样衣确认 · 大货版 · 全码版 · 裁剪 · 车位 · 后道 · 工厂交期) — exactly the block the buy plan's Index tab prints. Type dates straight into the grid and hit Save. A toggle switches all nine columns between **计划 Planned** and **实际 Actual**; filling an actual date marks that milestone complete (clearing it reopens the milestone). Above the grid a ✅/📅/⬜ strip shows completion at a glance, and Company / Factory / search filters narrow the rows."},
            {"type": "refactor", "text": "**Six sub-tabs became three** — 📅 Tracking Grid · ➕ Add / Remove · 📨 Factory Updates. The Dashboard cards, the Overview table and the never-finished Plan placeholder are gone (along with its unused schedule calculator), and the per-record Milestones editor is replaced by the grid. Metrics are now the three that match the grid: Tracked · Milestones done · Overdue. Adding gained a **Track all shown** bulk button, and removing records moved here from the edit form."},
            {"type": "refactor", "text": "**The 22-stage detail form is still there, just out of the way** — it now lives in a collapsed admin-only **🛠 Advanced** panel at the bottom of the grid, with every stage, dependency, readiness gate, optional sample, expected-days field and QC inspection intact. Nothing was deleted from the database and no migration ran, so any of it can come back to the daily view as the process grows into it. The goal is a gentle starting point: the nine milestones that already appear on the buy plan come first, and the deeper stage detail is one click away when it's needed."},
        ],
    },
    {
        "version": "2.88.1",
        "date": "2026-07-21",
        "entries": [
            {"type": "fix", "text": "**Switching stage sections in Edit Record no longer throws the view around.** The A/B/C/D/QC selector sat below the read-only fields and notes, so you had to scroll down to reach it — and because the groups differ hugely in height (Pre-Production has 8 stages, Samples has one), switching shrank the page and the browser dumped your scroll position somewhere else. The selector now sits directly under the record picker, near the top, where there is nothing to jump away from."},
        ],
    },
    {
        "version": "2.88.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**The buy plan itself is now the tracking round-trip form.** Import a returned buy plan (🏭 Tracking → 📨 Factory Updates → 📥 Import a returned form) and the system reads the tracking columns the merchandiser or factory filled into the Index tab — 生产工厂 plus every （计划） expected date — matches each row to its PO by 客人PC NO + 款号, and applies them to tracking. The next buy plan then prints those dates. The importer auto-detects which file you dropped (progress form or buy plan), previews every change with a per-row status, and flags rows whose PO can't be resolved or that aren't tracked — blanks never erase existing plans. Completion marking stays online or on the progress form's 里程碑 sheet, so an expected-date sweep can't accidentally close milestones."},
        ],
    },
    {
        "version": "2.87.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**Milestone tracking module — the buy plan Index tab's tracking fields are now fully manageable.** New 📋 Milestones editor in 🏭 Tracking → 📨 Factory Updates: for each PO/style, all nine buy-plan milestones (面料到厂, 辅料到厂, 样衣确认, 大货版, 全码版, 裁剪, 车位, 后道, 工厂交期) in one table with an **expected completion date**, a **status note**, and a **completed/arrived date** — filling the completed date marks the stage Done (clearing it downgrades to In Progress). Values flow straight into the buy plan's Index columns on the next generation."},
            {"type": "feat", "text": "**Factories can now see and update the milestones too.** The factory request form gains a second 里程碑 Milestones sheet, pre-filled with the current plan — the factory updates expected dates, adds status notes, and fills the completed date when something arrives/finishes; importing the returned file shows a preview and applies everything to the tracking record (untracked PO/styles are flagged, never silently created)."},
        ],
    },
    {
        "version": "2.86.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**New 🖼 Photo issues log on the Generate screen.** One reviewable table showing every picture problem from the most recent generation: styles with **no photo anywhere** (image folder, extracted-images backup, or the upload’s embedded pictures) and source files that **failed to read** (e.g. a corrupt file on the network share), with the exact file path to fix. The log is refreshed on every generation — fix a photo and its row disappears on the next run automatically. Session-cached photo runs keep their error entries truthful too."},
        ],
    },
    {
        "version": "2.85.1",
        "date": "2026-07-21",
        "entries": [
            {"type": "fix", "text": "**Found the real photo-step stall: one corrupt file.** Per-file timing revealed a single broken PNG on the network share (TP3274_front.png) that hung for the mount’s full 60-second timeout and then failed — on every single generation, since a failed read never entered any cache. Broken source photos now get a local “bad file” marker: they are skipped instantly on later runs (retried automatically after 6 hours in case the file gets fixed), and the generate screen lists exactly which files to fix or delete on the share. Measured on the real folder: photo step 60.6s → 0.01s from the second run on."},
        ],
    },
    {
        "version": "2.85.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "perf", "text": "**Style photos on a network folder no longer dominate generation.** With the image folder on a Mountain Duck / SMB mount, reading ~20 MB of style photos one file at a time was by far the slowest part of Generate Buy Plan + 核料. Three changes: photo reads now run **concurrently** (12 at a time) instead of serially; folder scanning gets names, sizes and timestamps in a **single** enumeration; and bytes read from an external folder are **mirrored into a local cache** so later generations read from the local disk and never touch the network again. The cache key includes each file’s size and timestamp, so an updated photo is picked up automatically and stale bytes can never be served. Net effect: the first generation is several times faster, and every one after it skips the network entirely."},
        ],
    },
    {
        "version": "2.84.4",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**No more frozen-looking wait after clicking Generate.** The first ~160 lines of work (order data, colour lookups, brand check, fabric parts, and the style-photo read) ran BEFORE the \"Generating...\" box opened, so the app looked stuck for that whole stretch with no indication anything was happening. Each of those steps now announces itself live (\"⏳ Reading style photos from …\", naming the folder), so progress is visible from the instant you click."},
        ],
    },
    {
        "version": "2.84.3",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**Generation now shows a time-per-step table.** Every phase of Generate Buy Plan + 核料 is timed — load order data, build colour lookups, register new brands, fabric parts + auto-fill, style photos, buy plan export, save to output folder, 核料 export, save 核料, cross-comparison — and a summary table with a TOTAL row appears at the end of the progress box. Any slow run now shows exactly which step is responsible instead of feeling uniformly slow."},
        ],
    },
    {
        "version": "2.84.2",
        "date": "2026-07-21",
        "entries": [
            {"type": "docs", "text": "**Output-folder saves now show size and duration** (e.g. \"5.2 MB in 18.3s — network folder speed, not generation\") so a slow save to a Mountain Duck / network folder is clearly attributed to the folder's upload speed rather than the generation itself. Tip: a local output folder saves instantly; the download buttons are always instant either way."},
        ],
    },
    {
        "version": "2.84.1",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**Choose where the buy plan and 核料 save.** New \"Output folder (optional)\" field on the Generate screen: when set, the generated buy plan and every 核料 workbook are also written directly to that folder (local or network path) with their timestamped names — no more downloading and moving files by hand. The download buttons keep working either way, an unreachable folder just warns without failing the generation, and the last-used folder is remembered across sessions."},
        ],
    },
    {
        "version": "2.84.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "perf", "text": "**AI colour resolution redesigned: unresolvable colours are now asked once, ever.** The AI layer only cached successful answers — but a colour with no 大货进度表 coverage produces a genuine \"no answer\", which was re-purchased from the API on every single generation (serially in the 核料 pass). With ~176 such colours that was the dominant recurring cost. Genuine negative answers (\"no colour identified\", \"no candidate matches\") are now cached in memory AND permanently in the database, exactly like positive ones; only transport errors stay uncached so transient network problems still retry. The AI pre-warm pool also grew 6 → 16 workers, so even a first-ever encounter with many new colours resolves in a few parallel waves."},
            {"type": "perf", "text": "**Style photos are reused within a session.** Regenerating with the same folder and styles no longer re-reads ~20 MB of photos (painful on a network/Mountain Duck folder) — the map is kept for the session and invalidated automatically by a new upload run, a folder change, or a different style selection."},
            {"type": "feat", "text": "**Generation now reports per-phase timings** in the progress box (photo load, buy plan, 核料) — any future slowness names its own culprit."},
        ],
    },
    {
        "version": "2.83.5",
        "date": "2026-07-21",
        "entries": [
            {"type": "perf", "text": "**Buy plan generation no longer hangs on network image folders.** Style photos were located with up to 240 individual file checks (60 styles × front/back × 2 folders) — on a network / Mountain Duck mounted image folder every check is a network round-trip, which dominated the entire generation (minutes). Photos are now found with ONE directory listing per folder; an unreachable folder costs a single fast failure instead of hanging per file, with the local extracted-images fallback still working. The generate screen also now shows how many photos loaded and how long that took (with the folder path called out when it's slow), so any future slowness identifies itself."},
        ],
    },
    {
        "version": "2.83.4",
        "date": "2026-07-21",
        "entries": [
            {"type": "perf", "text": "**Buy Plan + 核料 generation is dramatically faster.** Profiled with real data (13 PCs · 60 styles · 40 photos): the buy plan itself takes ~4s, but the 核料 export was spending 12.5s of its 12.6s making one **blocking AI colour call per unresolved colour, one at a time** — with many unresolved colours that meant minutes. Two fixes: (1) 核料 now pre-warms all AI colour lookups in parallel before writing sheets, the same optimization the main buy plan already had; (2) AI colour answers are now **saved permanently in the database** — previously they were forgotten on every server restart and re-purchased from the API on the next generation. Measured result: 核料 export 12.6s → 0.2s once colours are known; brand-new colour names pay the API once, ever."},
        ],
    },
    {
        "version": "2.83.3",
        "date": "2026-07-21",
        "entries": [
            {"type": "perf", "text": "**Faster login page on a fresh server start.** app.py imported the heavy data stack (pandas/numpy/openpyxl/PIL) at module level just to define a post-login schema helper — the login form paid that cost (multi-second on cold starts with antivirus scanning) before it could render. The import is now deferred until after login. Also, the sidebar's CPRS health probe timeout dropped 3s → 1.5s, halving the worst-case render stall while the CPRS server is unreachable."},
        ],
    },
    {
        "version": "2.83.2",
        "date": "2026-07-21",
        "entries": [
            {"type": "fix", "text": "**AI colour matching no longer fails at random on deepseek-v4-flash.** The typo-bridging candidate match (e.g. client \"dark blue\" vs 大货进度表 \"Daek Blue\") intermittently returned nothing: v4-flash spends hidden reasoning tokens inside the same max_tokens budget, and the call's 64-token cap sometimes truncated the response before the answer was written. The v4-pro reasoning-headroom floor now applies to the whole deepseek-v4 line — verified live: the same match now succeeds consistently."},
        ],
    },
    {
        "version": "2.83.1",
        "date": "2026-07-21",
        "entries": [
            {"type": "feat", "text": "**Return Label conflicts: one-click \"Apply all new\".** The review panel gains a button that accepts the file's new value for every conflicting item at once — no more ticking each Replace checkbox when the client's newest PO is simply right. \"Apply\" is renamed \"Apply selected\" for clarity; \"Keep all as recorded\" unchanged."},
        ],
    },
    {
        "version": "2.83.0",
        "date": "2026-07-21",
        "entries": [
            {"type": "perf", "text": "**Whole-app efficiency release — every layer reviewed and the confirmed waste removed.** Summary and GIII tabs now load their order data once per interaction instead of 2-4×, and their Excel exports build on demand instead of on every click. The admin Master PO photo table and the Colors tab's export no longer rebuild per interaction. Photo-heavy Sky East buy plans generate dramatically faster (the same style photo was being re-encoded once per Overview row — now once per photo) and produce smaller files. Sky East uploads are protected against WPS files with thousands of phantom empty rows (parse now stops after 20 consecutive blanks). Large 大货进度表/EAN/fabric reference files load seconds faster. Plus: schema checks now run once per process instead of on every store construction, ~18 more in-tab actions refresh only their own tab, the Releases tab renders as a handful of elements instead of ~925, and a dead quadratic parser module was deleted."},
            {"type": "feat", "text": "**HHN Contract Progress import review, refined:** the differences table now shows the 中文颜色 (Color CN) alongside the English colour on every row, and no longer flags routine churn (离厂日期, Qty, 测试, 色汇总, Launch Date, 备注) for review — those fields still update on import, they just don't need eyes on them. The uploaded file is also parsed once instead of on every widget interaction."},
        ],
    },
    {
        "version": "2.82.3",
        "date": "2026-07-21",
        "entries": [
            {"type": "perf", "text": "**Save/import/delete actions no longer reload the whole app.** Every button action inside the Tracking, CMPT, and Fabric DB tabs used to trigger a full-app rerun — re-executing all 11 tab bodies plus the sidebar and re-mounting the entire page in the browser. These 26 action sites now refresh only their own tab (fragment-scoped rerun, with automatic fallback to a full rerun outside a fragment). GIII/Sky East upload flows deliberately keep the full refresh — their results feed the Summary and Tracking tabs' displays, which would otherwise show stale data."},
        ],
    },
    {
        "version": "2.82.2",
        "date": "2026-07-19",
        "entries": [
            {"type": "perf", "text": "**Tracking → Edit Record is much faster to interact with.** The form used to mount all ~120 widgets (4 stage groups + QC: 44 date pickers, ~30 dropdowns…) on every single click, making each selection feel seconds-slow. Stage groups are now shown one at a time via an A/B/C/D/QC selector, cutting the widget count ~4-5×. Saving is unchanged and still safe — fields in sections not currently shown keep their saved values (the same mechanism the Optional Samples toggle always used). Note: save before switching sections; unsaved edits in a hidden section are discarded."},
        ],
    },
    {
        "version": "2.82.1",
        "date": "2026-07-19",
        "entries": [
            {"type": "feat", "text": "**CMPT contract numbers auto-generate.** The New Contract form pre-fills the next number in the `CMPT-YYYY-NNN` series (sequence per year, derived from the highest existing number; gaps are not refilled). The field stays editable for your own numbering, and uniqueness is still enforced on create. After each created contract the form re-seeds with the next number."},
        ],
    },
    {
        "version": "2.82.0",
        "date": "2026-07-19",
        "entries": [
            {"type": "feat", "text": "**New 📄 CMPT Contracts tab — 加工合同 with factories + price ledger.** Create contracts (contract no., factory, date) with PO/style price lines — optionally prefilled from tracked PO/styles with ordered quantities — and generate the signed-ready document from **your own Excel template**: upload it once (admin section, with a placeholder guide), put `{{tokens}}` like `{{contract_no}}`, `{{factory}}`, `{{total_amount_cn}}` (自动大写金额) where the data goes, and one prototype line row that duplicates per contract line. Price tracking: agreed value = Σ(qty × unit price), a dated payment log (amount/method/note, refunds as negatives), and computed outstanding balance per contract and in total — all derived, never stored, so they can't drift. Tab access is controlled by the new \"📄 CMPT Contracts\" module in user management."},
        ],
    },
    {
        "version": "2.81.0",
        "date": "2026-07-19",
        "entries": [
            {"type": "feat", "text": "**🏭 Tracking → 📨 Factory Updates: factories report units cut / sewn / packed.** New sub-tab with the full round-trip: generate a pre-filled Excel request form for one factory (their PO/styles, ordered qty, and already-reported totals listed; only the yellow \"new since last report\" columns to fill), import the returned file with a validated preview (non-numeric/negative/missing-date rows flagged, untracked PO warnings), or key in reports manually. Every report is a dated log entry — full history kept, totals derived by summing — with an over-report warning when cumulative quantities exceed the ordered qty, a per-PO/style progress table (ordered vs cut/sewn/packed, packed-% bar, last report date), and admin-only correction deletes."},
            {"type": "feat", "text": "**Sky East buy plan: 裁剪数 now fills from factory cutting reports.** The Index sheet's cut-quantity column (previously always manual) populates with the summed cutting reports for that PO + style. 出货数 stays manual — \"packed\" is not \"shipped\"."},
        ],
    },
    {
        "version": "2.80.0",
        "date": "2026-07-18",
        "entries": [
            {"type": "feat", "text": "**🏭 Tracking tab: Dashboard cards + Overview table — track a PO's progress by style.** The Dashboard now shows one card per tracked PO/style with overall progress (N/22 stages), a per-group breakdown (A/B/C/D), status badges (🔴 Delayed / ⏳ Blocked / 🔔 QC due / ✅ On Track), the next stage due, and an Edit shortcut. The Overview tab shows the same records as a sortable table (progress %, current stage, status, last updated) for a flat at-a-glance view. Both share Company/Factory/\"Only at-risk\" filters."},
            {"type": "feat", "text": "**Sky East buy plan: Index sheet's schedule columns are now filled in.** 生产工厂, 工厂交期, and the planned dates for fabric/trim arrival, sample confirmation, pattern completion, cutting, and sewing were template headers that stayed blank forever — they're now populated (best-effort) from the matching 🏭 Tracking record for that PO + style, when one exists. Untracked styles simply show blank, same as before. 裁剪数/出货数 (quantities) and 裁剪计划完成时间 have no matching Tracking field and remain manual-entry."},
        ],
    },
    {
        "version": "2.79.0",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Fabric list uploads now go through peer review.** An upload no longer changes the fabric database directly — it is parsed, quality-checked (composition sums, unknown fibers, out-of-range weights/widths), diffed against the current version, and held as a **pending proposal**. A review panel at the top of the Fabric DB tab shows who proposed it, the full field-level diff, and any data-quality warnings; an **admin** approves (applying it and minting the new version, with the approver + comment recorded in Version History) or rejects with a mandatory reason. Two-person rule: approving your own upload requires a justification comment. Bulk changes (>10 removals or >20% of the table) are flagged high-risk and need an explicit acknowledgment. Buy plans keep using the current approved version until a proposal is approved. Single-record deletes stay immediate (they're already fully versioned)."},
            {"type": "feat", "text": "**Restore a previous fabric-list version** — each version in Version History (within the browsable window) gains a \"Restore this version\" button. The rollback goes through the same review gate as any upload: staged as a full-replacement proposal, applied only on admin approval."},
        ],
    },
    {
        "version": "2.78.1",
        "date": "2026-07-16",
        "entries": [
            {"type": "refactor", "text": "**Fabric-list version stamp slimmed down for outside-facing buy plans.** The separate \"Fabric Version\" tab (added in v2.78.0) is replaced by a single discreet footer cell on the Index sheet — `面料表版本 Fabric list version: v5 (2026-07-16)`, plus a \"pinned\" marker when an older version was deliberately selected. Buy plans are sent to clients and factories, so internal housekeeping (who uploaded the fabric list, the internal filename, change counts) now stays out of the workbook entirely; the version number is enough for our own team to look up the full record in Fabric DB → Version History."},
        ],
    },
    {
        "version": "2.78.0",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Sky East buy plan: new \"Fabric Version\" tab** — records exactly which fabric-list version enriched this workbook (version number, Latest vs. pinned-to-historical, upload date/user/source file, row count, that version's change summary, and the generation timestamp), right after the Overview tab. No more guessing which fabric list a months-old buy plan was built against."},
            {"type": "fix", "text": "**Manually deleting fabric records now creates a version** (source shown as \"manual delete\") with the removed rows in its diff. Previously a manual delete bypassed version history entirely: it was invisible in the log, the live table silently drifted from the latest snapshot, and re-uploading a file containing the deleted rows was reported \"unchanged\" while actually restoring them."},
            {"type": "fix", "text": "**\"Delete All & Reimport\" is now a single transaction** — the wipe and the re-import commit (and version) together, so a bad file rolls the wipe back instead of leaving the fabric table empty. This also closes the old first-import gap: a Clear & Reimport on a never-versioned database now records the legacy rows it replaced as \"removed\" in version 1's diff, instead of losing that baseline."},
            {"type": "fix", "text": "**Fabric DB import/delete result messages no longer vanish instantly.** The success/\"no new version created\" banners and the detected-column-layout panel were wiped by the automatic screen refresh right after they rendered; they now survive the refresh and display normally."},
        ],
    },
    {
        "version": "2.77.3",
        "date": "2026-07-16",
        "entries": [
            {"type": "fix", "text": "**Fabric list versioning: numeric values compare at 2 decimal places.** Fabric-table numbers (weight, widths, MOQ/MCQ, prices, shrinkage/short rates) are only meaningful to 2 dp — precision noise beyond that (Excel float artifacts, a source file carrying 66.666667 where 66.67 is already on file, 200 vs 200.0) no longer registers as a \"changed\" field, so it can't mint a spurious new version by itself. Real changes at 2 dp still bump normally, and the version-history diff now records the rounded values for numeric fields."},
        ],
    },
    {
        "version": "2.77.2",
        "date": "2026-07-16",
        "entries": [
            {"type": "fix", "text": "**Fabric list versioning: re-uploading an identical file no longer creates a new version.** Every import used to mint a version unconditionally — a byte-identical re-upload produced a duplicate snapshot, an empty diff entry, and (worst) pushed a genuinely different older snapshot out of the current+3 retention window to make room for the no-op copy. The import now diffs against the latest version first and only bumps when the fabric data actually changed (filename/upload-timestamp differences don't count); an unchanged upload shows \"matches the latest fabric list — no new version created\" instead. The very first import still always creates version 1 as the baseline."},
        ],
    },
    {
        "version": "2.77.1",
        "date": "2026-07-16",
        "entries": [
            {"type": "fix", "text": "**setup_users.py password reset no longer overwrites an account's role or tab scope.** Re-running the script always forced the slot's default role/modules onto whatever username was entered — so resetting a password could silently demote an admin (if their username was typed into a user slot) or wipe a custom tab scope back to the default. Existing accounts now get a true password-only reset, exactly as the script's own instructions promised; only brand-new accounts receive the slot's role/scope."},
            {"type": "fix", "text": "**New-brand shipping sample prompt: added a \"Remind me later\" button** — previously the only way to close the box was Save, which registered every listed brand (even a junk name from a malformed file). Remind-me-later dismisses without writing anything; the same brands are prompted again next upload."},
            {"type": "fix", "text": "**Upload flow hardening:** the new-brand detection lookup is now best-effort (a database error there can no longer crash the upload after the PO data was already saved), and the auto-added \"Return Label\" template header now anchors to the template's actual detected header row instead of assuming data starts directly below it (which an admin config override can change)."},
        ],
    },
    {
        "version": "2.77.0",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Sky East upload now prompts for a shipping sample requirement (船样要求) on any brand never seen before.** Previously, a brand with no requirement on file was just silently left blank in the buy plan until someone noticed at generation time (which only shows a static \"go fill it in\" warning). Now, right after uploading, any brand not already registered gets a review box with one row per new brand — enter the requirement (or leave blank if none applies) and Save. Existing brands are completely unaffected."},
        ],
    },
    {
        "version": "2.76.7",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Return Label now also shows in the Sky East buy plan's Index sheet** — the other summary tab in the Excel workbook, alongside the Overview sheet fixed earlier. Since Index has one row per style-sheet (which can span several colours/POs), it shows that sheet's first item's Return Label as the representative value, same convention already used there for Brand and Ex-Fty; the per-style and Overview sheets remain the exact per-item source of truth."},
        ],
    },
    {
        "version": "2.76.6",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Return Label now also shows in the two in-app Sky East summary tables**, not just the Excel output: the Contract History tab's item browser, and the 📊 Order Summary tab's \"Sky East — full item list\" (and its Excel download)."},
        ],
    },
    {
        "version": "2.76.5",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Sky East buy plan's Overview (summary) sheet now includes a Return Label column**, alongside the existing per-style sheet column — \"Yes\" / \"No\" / \"NA\" per item, so the flat cross-check table matches what's on each style tab without needing to open it."},
        ],
    },
    {
        "version": "2.76.4",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Sky East upload now checks the Return Label field on re-upload, and asks before replacing.** Previously, re-uploading an existing PO only compared sizes/qty/FOB — if those matched but the client's PO had a different Return Label than what was already on file, the item was treated as a plain duplicate and the new value was silently discarded. Now: a Return Label change (alone, or alongside other changes) is held back — never applied automatically — and shown in a review table (PC No./Style/Color/PO, current vs. new value) with a per-item Replace/Keep choice and an Apply button. Everything else in the upload (new items, and updates where the Return Label is unchanged) still saves immediately, same as before."},
        ],
    },
    {
        "version": "2.76.3",
        "date": "2026-07-16",
        "entries": [
            {"type": "fix", "text": "**Sky East upload could crash after successfully saving PO data**, if the configured image folder was a network path (e.g. from an office share) that the current machine/login couldn't reach or authenticate to (Windows error 1326, \"unknown user name or bad password\"). The PO/contract data was already safely in the database by that point, but the crash still stopped photo-saving and the run-to-completion cleanup step. Saving images is now best-effort: an unreachable/misconfigured folder shows a warning instead of crashing, and the local extracted-images fallback (which most buy-plan photo lookups already use) still runs normally."},
        ],
    },
    {
        "version": "2.76.2",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**New dev tool: build a self-contained install pack for a different PC.** `installer/Build-DistPackage.bat` exports the git-tracked source tree, flattens `installer/`'s scripts up to the pack's root (`Install.ps1`/`Update.ps1`/`Uninstall.ps1` all assume they're direct siblings of `app.py`/`requirements.lock`, not one folder down), and zips the result into `dist/` — clean by construction, since anything never committed (`.venv`, databases, `auth/users.json`, `auth/license.key`, `__pycache__`, scratch files) was never seen by `git archive` in the first place. Copy the resulting zip to a different Windows PC, extract it anywhere, and run `Install.bat` there — same install flow as today, just packaged into one file instead of a raw git checkout."},
        ],
    },
    {
        "version": "2.76.1",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Installer now provisions 4 standard, role-scoped accounts.** `setup_users.py` (run by `installer/Install.ps1` on a fresh machine) previously created up to 3 arbitrary accounts with only the very first one auto-promoted to admin. It now walks through exactly 4 fixed slots — **admin** (full access), **skyeast** (Sky East tab only), **giii** (GIII tab only), and **fabric** (Fabric DB tab only) — each with a suggested default username you can override, and a password you can leave blank to skip that account. Re-running the script resets a password without touching that account's role/module scope. The existing update mechanism (`installer/Update.ps1`) already excludes `auth/users.json` from every update, so these accounts persist across updates unchanged."},
        ],
    },
    {
        "version": "2.76.0",
        "date": "2026-07-16",
        "entries": [
            {"type": "feat", "text": "**Sky East buy plan: new Return Label column.** Reads the client PO's Return Label column (the parser already recognised the header — \"需要挂 Return Label\", \"Return Label\", etc. — but never extracted the value) and writes \"Yes\" / \"No\" per line item (same per-row granularity as size quantities), defaulting to \"NA\" when the source PO has no recognisable value. Written to a new column past the template's existing last column; older buy-plan templates that don't already have a matching header get one added automatically (\"Return Label\") so the column isn't left unlabeled."},
        ],
    },
    {
        "version": "2.75.6",
        "date": "2026-07-16",
        "entries": [
            {"type": "security", "text": "**Stored XSS via uploaded Excel content.** The Excel-pipeline processing log rendered raw cell values and filenames (e.g. a color name, a skipped filename) as unescaped HTML (`unsafe_allow_html=True`) — a malicious cell like `<img src=x onerror=...>` would execute as live HTML in the admin's browser. Every interpolated value is now HTML-escaped before being added to the log."},
            {"type": "security", "text": "**Arbitrary file read via the legacy Photo1/Photo2 Excel column.** The GIII/HHP buy-plan exporter's photo-resolution fallback treated a Photo1/Photo2 cell value — read directly from an uploaded PO Excel file — as a server-side file path with no restriction, so any file path the server process could read (if known/guessed) would get embedded into the output workbook. That fallback is now sandboxed to only accept paths that resolve inside the configured images folder."},
            {"type": "fix", "text": "**\"Replace all\" fabric-style mapping could permanently lose data on a mid-import failure.** The delete and the re-save ran as two separate transactions; if the save half failed, the source's fabric mapping was already gone with nothing to restore. Both steps now run inside a single transaction, so a failure rolls back the delete too."},
            {"type": "fix", "text": "**Colors tab \"Replace all data\" import has never actually worked** — it called a method (`store._connect()`) that doesn't exist on the store, so every attempt raised an error before anything was touched. Fixed to use the store's real connection method; also fixed two leaked temp files left behind after every color-list import."},
            {"type": "fix", "text": "**Sky East contract uploads with a duplicate (style, color, PO) pair in the same file could silently lose the first item's data** — the in-memory \"does this already exist\" lookup was built once before the loop and never refreshed, so a second matching item compared against stale pre-upload state instead of what the loop had just written."},
            {"type": "fix", "text": "**Colors tab bulk-import \"update existing\" option had no effect** — turning off \"skip existing\" still just counted existing rows as skipped instead of updating them."},
            {"type": "fix", "text": "**GIII requirement-matrix export silently dropped requirements** when two PO contexts shared the same destination (account+region) — only the first context's requirements survived; the rest were discarded instead of merged."},
            {"type": "fix", "text": "**Fabric config file corruption/malformation now degrades gracefully instead of crashing** the fabric-DB-path lookup/save (previously an `AttributeError` on a malformed `fabric_config.json`, e.g. from a manual edit, was uncaught)."},
            {"type": "fix", "text": "**A first-time database migration on a fresh/legacy DB could crash under concurrent access** — a `PRAGMA journal_mode=WAL` pragma failing under lock contention, and a raw `ALTER TABLE ADD COLUMN` racing between two sessions, were both unguarded. Both now fail gracefully / reuse the existing safe-migration helper instead of crashing the second session."},
            {"type": "fix", "text": "**4 temp-directory leaks in GIII PDF/Excel processing and fabric mapping import** (Smart Upload, PDF extraction, Excel extraction, mapping-file import) — each left its working temp folder behind on any error partway through; all now clean up unconditionally via try/finally."},
            {"type": "fix", "text": "**Fabric DB upload left a temp file behind on every failed import** (bad file, malformed headers) — now cleaned up unconditionally."},
            {"type": "fix", "text": "**HHP buy-plan export could silently merge different colors/POs into one row** when the uploaded Excel was missing an optional Config SKU or Color Description column — the grouping key silently narrowed instead of keeping rows separate. Also fixed: pre-filled template sample rows beyond the last real group used to leak through into the output, and blank fabric-detail cells kept stale values from the copied template instead of clearing."},
            {"type": "fix", "text": "**Color-plan export missed the Chinese color name for numeric color values** — the lookup always converted the key to a string but the lookup map's keys kept pandas' inferred numeric type, so they never matched."},
            {"type": "fix", "text": "**Cross-check export could false-flag a MISMATCH** for a client template whose \"Total\" header row sits past row 10 (widened the search range) — the same class of bug this check had already been bumped once for."},
            {"type": "fix", "text": "**GIII production-plan export could exceed Excel's 31-character sheet-name limit** in the rare case of 100+ styles collapsing to the same cleaned sheet name."},
            {"type": "fix", "text": "**Fabric DB browse view showed \"—\" instead of \"0\"** for a fabric with a genuinely-zero weight/width value (truthiness check treated 0 the same as missing)."},
            {"type": "fix", "text": "**Admin Pipeline Layout / boat-sample delete / DeepSeek model list** — clearing a data-editor cell could write the literal string \"nan\" into saved config instead of blank; deleting a boat-sample entry could silently fail (or pick the wrong row) if a company name contained \" / \"; \"auto\" extraction mode didn't show the live DeepSeek model list even though it can call the API."},
            {"type": "fix", "text": "**Sky East buy-plan generation and the missing-fields tab could crash** on a progress-lookup DB error or a malformed contract-number lookup — both now degrade gracefully instead of propagating the exception (the missing-fields one was crashing on every render, not just until its cache expired)."},
            {"type": "docs", "text": "Ran a DeepSeek-pro-assisted review across the whole codebase (~50K lines) and independently verified every high/medium finding against actual source before fixing anything — roughly 40% of the raw findings were false positives (missed guard clauses, misread docstring-documented contracts, unreachable dead code); this release fixes the ~31 that were confirmed real."},
        ],
    },
    {
        "version": "2.75.5",
        "date": "2026-07-16",
        "entries": [
            {"type": "fix", "text": "**AI colour-enhance and price-masking would silently stop working if an admin ever selected the \"deepseek-v4-pro\" model.** Ran a DeepSeek-pro-assisted review of the codebase and, in the course of it, hit the same bug live: deepseek-v4-pro is a hidden-reasoning model whose reasoning trace can run into the thousands of tokens, but this app's reasoning-model detection only recognised the older \"deepseek-reasoner\" name, so v4-pro's small max_tokens budgets (64–128, sized for a short colour/price answer) were silently consumed entirely by invisible reasoning, returning empty responses with no error. It's tracked separately from the temperature-rejection check (v4-pro accepts temperature fine, unlike deepseek-reasoner) with its own larger token floor."},
            {"type": "fix", "text": "**Infor Nexus row-major size-grid parser could over-capture past the intended stop label.** The row-major fallback (used when a PDF linearises the size table row-first) looked for the next section via a regex ending in `\\b` right after stop words like \"Qty:\" — but `\\b` can never match immediately after a colon, so the lookahead silently failed and the non-greedy match ran to the end of the block instead of stopping cleanly. In the current data shape (Qty is always the last section) this happened to be masked by the existing length-based row alignment, but the regex itself was wrong and would misbehave for any other section ordering."},
            {"type": "fix", "text": "**Sky East buy-plan generation could crash on a blank size cell.** `int(value or 0)` doesn't treat NaN as falsy (NaN is truthy in Python), so a missing/empty cell in a size column raised `ValueError: cannot convert float NaN to integer` instead of being treated as zero."},
            {"type": "fix", "text": "**A corrupted users.json or companies.json now fails with a clear error instead of a bare crash or silent lockout.** Both files were read via plain `json.load()` with no error handling — a corrupted file (e.g. from an interrupted write) previously raised an unguarded `JSONDecodeError`; now it raises a clear message naming the file so it's obvious what to restore from backup, rather than every login looking like \"wrong password\" with no explanation."},
        ],
    },
    {
        "version": "2.75.4",
        "date": "2026-07-16",
        "entries": [
            {"type": "fix", "text": "**Fabric DB validation tables now translate to Chinese.** The composition and field-check issue tables (Fabric DB tab) showed messages like \"Unknown fiber 'spandex'\" or \"Cuttable width (153.0 cm) exceeds full width (148.0 cm)\" in English even with the UI switched to Chinese — these are backend-generated diagnostic strings that were never wired into the translation layer. Every validator message is now built from a translatable template plus its raw values (e.g. field name, percentage, quality_no) instead of a pre-baked English sentence, and the column headers (Detail, Field, Value, Issue, Total %, Suggested Fix) are translated too. Downloaded .csv/.xlsx issue exports now match the active UI language as well."},
        ],
    },
    {
        "version": "2.75.3",
        "date": "2026-07-15",
        "entries": [
            {"type": "fix", "text": "**AI colour recognition no longer runs for rows that aren't real items.** Found the cause of a remaining ~1.7s serial AI call: a row whose every field is literally the source file's own column-header text (e.g. style=\"Style No.\", colour=\"Color name\") had leaked into the items table — a parsing artifact with zero quantity in every size, not an actual order. AI colour lookup is now skipped for any row confirmed to have zero quantity across every size column (both in the new parallel prefetch and the real per-row resolution path), so it's never asked to guess a colour for something that was never a real PO/style combination in the first place. A row that simply doesn't carry size-column data at all (several existing call sites) is treated as \"unknown,\" not \"confirmed empty\" — AI still runs there as before."},
        ],
    },
    {
        "version": "2.75.2",
        "date": "2026-07-15",
        "entries": [
            {"type": "perf", "text": "**Found the real cause of \"Generate Buy Plan\" taking 19+ seconds: \"Local + AI Enhance\" colour recognition was making blocking DeepSeek API calls one at a time, inline, inside the sheet-writing loop** (~1-3s per unresolved colour, serially). A new parallel pre-fetch pass resolves every colour the export will need to ask AI about — all at once, concurrently — before the (fast) serial sheet-writing begins, so those calls overlap instead of stacking up. Measured on a real 55-style / 9-contract run: **19.4s → 7.5s (2.6x faster)**, with zero change to the resolved colours themselves (same cache, same logic, same results — only when the network calls happen changed)."},
            {"type": "feat", "text": "**Real progress bar for \"Generate Buy Plan.\"** The static \"Generating...\" status is now a percentage bar that tracks AI colour resolution (\"Resolving colours via AI (4/11)…\") and then each style sheet as it's written (\"Writing DR5124 (23/55)…\") — so a run that takes several seconds no longer looks frozen."},
        ],
    },
    {
        "version": "2.75.1",
        "date": "2026-07-15",
        "entries": [
            {"type": "perf", "text": "**Sky East → Generate/Export was recomputing expensive data on every unrelated click.** Streamlit re-renders every sub-tab's content on every rerun (regardless of which one is visually active), so the \"Missing Fields N\" badge count — a full item scan + per-row contract lookup + colour enrichment — was recomputed from scratch on *any* widget interaction anywhere in the Sky East tab, including the new fabric-version selector, the colour-source radio, or the PC multiselect. Same for the \"N style(s) have no fabric code\" pre-flight check on Generate/Export. Both are now cached (keyed by the actual selection where relevant) and explicitly invalidated at every real write point (contract upload, missing-field save/auto-fill, contract delete) — so results stay accurate immediately after your own edits, but an unrelated click no longer redoes the work. Measured ~100x faster on repeat renders (20ms → 0.1ms and 10ms → 0.1ms) with no behavior change."},
        ],
    },
    {
        "version": "2.75.0",
        "date": "2026-07-14",
        "entries": [
            {"type": "feat", "text": "**Fabric list versioning.** Every fabric-table upload (面料统计表.xlsx) now creates a version: the current list plus the 3 most recent previous uploads stay fully browsable, older snapshot data is pruned automatically, and a permanent incremental-diff log records exactly which fabrics were added, removed, or changed (and which field) between each consecutive version, with who uploaded it. New **📜 Version History** section in the Fabric DB tab shows this log. The Sky East and GIII (Excel/HHP) buy-plan screens each get a **Fabric list version** selector — defaults to Latest, but any of the retained previous versions can be picked to enrich that run's buy plan instead."},
            {"type": "docs", "text": "A user restricted to only the Fabric DB tab (Admin → Users → Allowed tabs → only \"Fabric DB\" checked) can now be handed fabric-list maintenance exclusively — no other tab is visible to them. No new code was needed for this; the existing module-gating system already supports it."},
        ],
    },
    {
        "version": "2.74.2",
        "date": "2026-07-14",
        "entries": [
            {"type": "docs", "text": "**Corrected \"boat sample\" → \"shipping sample\" in user-facing text.** 船样 means a pre-shipment sample, not a literal boat — fixed in the Admin → 船样要求 panel (captions, help text, placeholder), the auto-registration warning shown after Sky East uploads, and the Production Tracking stage label (Group D). Also accepts \"shipping sample\" / \"shipping sample req\" as column headers in uploaded templates (old \"boat sample\" wording still works). No behavior change — Python identifiers, the SQL table, and the production-tracking stage key are left as-is (shared with an external read-only consumer / would need a data migration)."},
        ],
    },
    {
        "version": "2.74.1",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**船样要求 (boat-sample requirement) now looks up by the ORDER FILE's brand again, not 大货进度表's.** v2.74.0's 大货进度表-first brand switch was applied too broadly — it also fed into the 船样要求 lookup and the colour/主标颜色 DB fallback, both of which are keyed by the order file's brand (GIII data) in their backing stores. A 大货进度表 BRAND value that doesn't exactly match those keys would have silently turned a real match into a miss. The printed 品牌 cell (and the Overview/Index brand columns) still show 大货进度表's brand as requested; every internal lookup key reverts to the order-file brand."},
        ],
    },
    {
        "version": "2.74.0",
        "date": "2026-07-14",
        "entries": [
            {"type": "feat", "text": "**Sky East buy plan sources 品牌 from 大货进度表.** The brand column now comes from the 大货进度表's own BRAND column (matched by PC No. · style, with a style-only fallback) whenever the progress file is loaded, instead of the order file's brand — applied to both the style sheets and the Index. Falls back to the order-file brand for any style the progress table doesn't cover."},
        ],
    },
    {
        "version": "2.73.9",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**MSRP now stays visible even when the parser didn't capture it.** DKNY-variant POs (e.g. DUKHSP) print `MSRP: $54.00` but the parser only extracts MSRP on KL POs, so the keep-set was empty and the `$54.00` got masked. The masker now reads the retail price straight from each PDF's own `MSRP:` / `SRP` / `RRP` label and keeps it — parser-independent — so the MSRP is preserved while unit cost / extended cost / tariff % / discount % are masked."},
        ],
    },
    {
        "version": "2.73.8",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "PDF masking now also redacts the **discount % and tariff %** (e.g. `0.75%`, `000.00`) alongside the unit/extended cost — the price pattern matches a trailing `%` and the leading-dot form (`.75%`), so the discount is hidden both in the data field and in the standard G-III terms paragraph. MSRP, quantities, UPCs, and dates stay visible. Net: masking now covers unit cost + extended cost + tariff % + discount %, nothing else."},
        ],
    },
    {
        "version": "2.73.7",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**MSRP (retail price) is never masked in PDFs.** Retail prices are public, so price-masking now leaves them visible: the AI detector is instructed to mask only confidential costs (FOB/cost/wholesale/unit cost/line total) and explicitly keep MSRP/SRP/RRP/retail, and any parsed MSRP value is added to a keep-set the redactor never covers (numeric compare, so \"$59\" protects the \"59.00\" token). Excel masking already excluded retail columns; this brings the PDF path in line."},
        ],
    },
    {
        "version": "2.73.6",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**Warehouse + account now resolve from the PO.** Two field-mapping fixes to CPRS: (1) the parsed destination code carries a `WRH` prefix (`WRHUC`) that CPRS can't resolve — it's now stripped to the bare DC code (`UC`), so the warehouse resolves and RFID/MSRP come from the actual DC. (2) The account is now taken from the PO's **Customer** (the retail account: AM Retail→AMRG, Ross→ROSS, MODIVO→MODIVO), not the buyer field (which is the G-III vendor entity and never matched). A PO with no customer sends no account and uses brand defaults silently instead of a false \"account not matched\" warning. Net effect: the wall of yellow account/warehouse warnings clears; the documents already generated, but now with warehouse- and account-specific requirements applied."},
        ],
    },
    {
        "version": "2.73.5",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**Fixed \"CPRS returned no evaluation\" for every DKNY/CK/KL PO.** The parser stores a raw division code (e.g. \"DW\") or abbreviation (\"DKNY W/SPRTSWR\") in the division field, and the resolver was sending that to CPRS as the brand — which CPRS rejects with 400 (\"Provide a recognizable brand name\"), so every PO was skipped. Brand derivation now maps the PO prefix to the canonical name CPRS accepts (\"DW…\" → \"DKNY Sportswear\", \"CS…\" → \"Calvin Klein\", \"LS…\" → \"Karl Lagerfeld\") before falling back to the division text. Verified live: the same POs now resolve with full requirement sets."},
        ],
    },
    {
        "version": "2.73.4",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**Resilient to CPRS restarts mid-run.** CPRS often restarts between POs; a single transient miss used to drop that PO (\"CPRS returned no evaluation\") even though the server was back moments later. Each PO evaluation now retries a few times with a short backoff before giving up — free in the happy path (retries fire only on a miss). Successful evaluations are still cached per-PO, so a manual re-generate only re-hits CPRS for the ones that truly failed."},
        ],
    },
    {
        "version": "2.73.3",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "Renamed the admin CPRS field **“CPRS base URL” → “CPRS server address”** (with help text “The CPRS API base URL, e.g. http://localhost:3100”) so the input for the CPRS address is easy to find in Admin → Settings → CPRS Knowledge Base. Same field, clearer label — no data change."},
        ],
    },
    {
        "version": "2.73.2",
        "date": "2026-07-14",
        "entries": [
            {"type": "feat", "text": "Admin option **Show server address in the sidebar status** (Admin → Settings → CPRS Knowledge Base). Off by default — the sidebar shows only Online/Offline + version; turn it on to reveal the host:port (and the full offline reason). Saved with the CPRS settings."},
        ],
    },
    {
        "version": "2.73.1",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "The CPRS sidebar status no longer shows the server address (host:port). The Online line drops the host (keeps db state + version); the Offline line shows an address-free reason — a raw connection error (which can embed host:port) is collapsed to a clean \"Unreachable\", while HTTP-status reasons show as-is."},
        ],
    },
    {
        "version": "2.73.0",
        "date": "2026-07-14",
        "entries": [
            {"type": "feat", "text": "**CPRS server status in the sidebar.** A live indicator near the top of the sidebar shows 🟢 Online (with the CPRS version) or 🔴 Offline (with the reason — connection refused, HTTP status, …), plus the host and DB state. The health probe is cached (~20 s TTL, short timeout) so it never slows the UI, and a 🔄 Refresh button re-checks on demand — so a CPRS outage is visible at a glance instead of only surfacing when a document comes back with blank requirement columns."},
        ],
    },
    {
        "version": "2.72.3",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**Clearer CPRS-outage diagnostics.** When CPRS is unreachable, the buy plan / requirements document now show **one** actionable line — \"CPRS is not reachable (<reason>) — start CPRS, then re-generate\" — instead of a misleading \"unreachable or empty rule set\" repeated once per PO. A single `health()` pre-check runs before the per-PO loop and reports *why* (connection refused, HTTP status, …); if it says down, no PO is evaluated. The per-PO fallback message no longer conflates an outage with an empty rule set."},
        ],
    },
    {
        "version": "2.72.2",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**预包比例 (pack ratio) now also reads straight from CPRS** — removed the last app-side prepack gate. With this, *every* GIII requirement value comes from CPRS's `/evaluate/po` verbatim, with no local applicability gate on top; CPRS's own status decides what applies (a non-prepack order simply gets no ratio back)."},
            {"type": "docs", "text": "Recorded the non-negotiable design principle **\"CPRS is the single source of truth — never build a local gate on it\"** in `docs/GIII_CPRS_Integration_API.md` and `CLAUDE.md`. The doc now describes the `/evaluate/po` architecture (decode + evaluate in CPRS) and lists the forbidden patterns (applicability gates, local derivation, local business rules) so they can't creep back in."},
        ],
    },
    {
        "version": "2.72.1",
        "date": "2026-07-14",
        "entries": [
            {"type": "fix", "text": "**每箱件数 (pieces per carton) is read straight from CPRS for every order**, not just prepack ones — removed the app-side prepack gate. (预包比例 stays prepack-only, since a pack-ratio only exists inside a prepack.)"},
        ],
    },
    {
        "version": "2.72.0",
        "date": "2026-07-14",
        "entries": [
            {"type": "refactor", "text": "**Requirements now come straight from CPRS.** Both the buy plan and the requirements document resolve via CPRS's `/evaluate/po` (one-call PO intake): CPRS decodes the raw PO (brand→client, ship-to→warehouse, buyer→account, channel, COO) and evaluates it, and the app reads the values verbatim from `decoded` + `results`. The app no longer fuzzy-resolves the client/warehouse/account, derives the channel, or reads separate warehouse flags — that's all CPRS's job now"},
            {"type": "fix", "text": "Consequences of the switch: the **红色箱贴纸** is whatever CPRS confirms (no more app-forced \"无需\" on non-prepack POs); **主箱唛** correctly falls through to a confirmed warehouse_diamond; **MSRP/RFID** come from CPRS's decoded warehouse defaults; and **COO** is always sent, so the buy plan and requirements document can no longer disagree on the same PO. 每箱件数/预包比例 still follow the PO's own prepack flag"},
        ],
    },
    {
        "version": "2.71.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "Buy plan requirement columns now **explain their blanks**: every empty 包装方式/衣架/是否预包/每箱件数/箱重限制/MSRP/RFID/红色箱贴纸/主箱唛 cell gets an Excel comment (hover the red triangle) saying WHY — no brand on PO, CPRS not resolved, warehouse unmatched, not on the PO, etc."},
            {"type": "feat", "text": "**MSRP** shows the actual price when the PO carries one; when MSRP is *required* (Y) but no price is found, the cell keeps `Y` and a comment explains the price is missing. **是否预包** now falls back to the CPRS prepack ratio when the PO has no packing text (so a prepack order isn't left blank)"},
        ],
    },
    {
        "version": "2.71.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**PO requirements document rebuilt in the KL illustrated format** — five new sheets modelled on `KL_FALL26_Requirements_Illustrated.xlsx`: **PO Index** (PO · style · article · units · account · whs · destination · packing · MSRP · source file + total), **Requirements + Pictures** (per-domain spec · CPRS source · embedded manual pictures), **Requirement Matrix** (domain/subtype × destination-account grid of ✓ / ✓* / ⚡ / — / ctx), **Pre-pack** (per-PO prepack ratio + pcs/box), and **Actions & Confirm** (auto-listed conflicts / missing-context / warnings). The existing Summary 汇总, 款号对比 By Style and per-PO sheets are kept. Structure + pictures + matrix are auto-filled from CPRS; the sample's hand-written bilingual prose is not reproduced"},
        ],
    },
    {
        "version": "2.70.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "New **UPC 明细** tab in the buy plan (4th sheet, after UPC 汇总) — a flat per-size list with the identifying header columns (款号/品牌/合同号/PO号/颜色) attached to each row, then 尺码 / UPC / 数量, one row per size, plus a TTL. Complements the wide UPC 汇总 pivot"},
        ],
    },
    {
        "version": "2.70.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**The \"Buy Plan\" download is now the enriched 生产计划单** everywhere — the upload results, and Reports → Generate All Outputs — matching what the **Create Buy Plan (生产计划单)** button already produced (one sheet per style, 面料/artwork, Summary 汇总 · 简明汇总 · UPC 汇总 · 款号对比 By Style, CPRS requirement columns). The old \"Style × PO × Color\" grid is no longer a download; it's retained only as the Cross-Check totals source"},
            {"type": "refactor", "text": "**One buy-plan code path** — both the upload auto-download and the Reports button now build through a single shared helper (`ui/giii/_buyplan.build_giii_production_plan`) that resolves CPRS requirements + 大货进度表 maps and calls the production-plan exporter. No more two divergent buy-plan implementations"},
        ],
    },
    {
        "version": "2.69.3",
        "date": "2026-07-13",
        "entries": [
            {"type": "perf", "text": "AI price-masking is now **parallelised** — it was the slow phase on multi-file uploads because each PDF made its DeepSeek price-detection call one at a time. The AI calls now run concurrently (up to 6 at once, while the PyMuPDF redaction stays serial for thread-safety), and the progress bar shows live per-file masking progress (`⚙ Masking prices… 5/19`). Roughly N-files → ~ceil(N/6) call-rounds"},
        ],
    },
    {
        "version": "2.69.2",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "Processing progress now covers the **whole** pipeline, not just parsing. Clean files parse in <1s, but the bar then sat full with a spinning wheel through save → buy plan → summaries → price masking → CPRS requirements document — looking stuck. The bar now advances through each of those phases with a labelled % (e.g. `⚙ Resolving requirements (CPRS)… (80%)`), so you see what it's doing and which step is slow, and the final line shows total elapsed"},
        ],
    },
    {
        "version": "2.69.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "perf", "text": "Added an index on `po_size_rows(upc)` — every PDA scan (UPC lookup / verify / stocktake) previously full-scanned the size-rows table; now it's an indexed lookup"},
            {"type": "fix", "text": "SQLite `busy_timeout=5000` — concurrent stocktake writes from multiple PDAs now wait briefly instead of failing with \"database is locked\""},
            {"type": "security", "text": "Web scanner login is now throttled per IP (8 failures / 15 min → HTTP 429) so the shared password can't be brute-forced on the LAN"},
            {"type": "fix", "text": "Web scanner now shows a red error state when a scan fails (server/network error) instead of silently resetting — an operator always knows if a scan was recorded"},
            {"type": "fix", "text": "Verify mode: size rows with no UPC no longer inflate the \"matched X/Y\" total or linger in \"not yet scanned\"; stocktake context now reads style/colour/size from one consistent PO row (no per-column mixing)"},
        ],
    },
    {
        "version": "2.69.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "The **PO requirements document** now embeds **every linked picture** (all CPRS artwork per requirement, not just the first) in an 图示 Image column on each PO sheet, and gains a new **款号对比 By Style** summary tab: requirements identical across all styles collapse to one row (\"全部 All\"), while requirements that differ are broken out per style and highlighted — so divergences jump out at a glance"},
        ],
    },
    {
        "version": "2.68.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "New **full CPRS API client** (`po_extractor/cprs`) generated from the CPRS OpenAPI spec (v1.6.8) — all 98 endpoints grouped by tag (`api.evaluation.evaluate(...)`, `api.clients.get_warehouses(id)`, …) with a typed dataclass for every schema, api-key/Bearer auth, binary downloads, and explicit `CprsError` on failure. Regenerate via `scripts/gen_cprs_client.py`. The buy-plan's best-effort `CprsClient` is unchanged. See docs/CPRS_API_CLIENT.md"},
        ],
    },
    {
        "version": "2.67.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "New **web scanner** (`python -m web_scan`) — a lightweight browser scan page for warehouse PDAs, served on its own port (default 8502) by Starlette+uvicorn over the same database, separate from the Streamlit app so it's instant on a handheld (no reruns). Keyboard-wedge input with a focus trap; three modes (🔍 Lookup / ✓ Verify against PO / 🧮 Stocktake 盘点) mirroring the UPC Check tab; shared-password gate. See docs/WEB_SCANNER.md"},
        ],
    },
    {
        "version": "2.66.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**UPC 汇总** now prints **two lines per PO/colour** — a 数量 line with each size's units and a UPC line with that size's barcode directly beneath it — so units and UPC line up under the same size column. A 项目 label marks each line; leading columns (款号/PO号/颜色…) and 总数量 merge across the pair"},
        ],
    },
    {
        "version": "2.66.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "The **📷 UPC Check** tab now shows the app's **PDA web address** (a 🌐 panel near the top): the server's LAN URL(s) — e.g. `http://192.168.0.153:8501` — so an operator can point the PDA scanner's browser straight at the app. The address is detected from the server's network interfaces and port; the PDA must be on the same LAN / Wi-Fi"},
        ],
    },
    {
        "version": "2.65.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**UPC 汇总** sheet reshaped to one row per PO/colour with each **size as its own column** and that size's **UPC printed under it** — a compact size→UPC card instead of one row per size. Trailing 总数量 per row and a TTL remain; empty size cells mean the PO carried no UPC there (never fabricated)"},
        ],
    },
    {
        "version": "2.65.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "New **UPC 汇总** sheet in the GIII buy plan (third tab, after Summary 汇总 and 简明汇总): the size-level UPC list the buy plan otherwise aggregates away — one row per PO / colour / size with 款号 / 品牌 / 合同号 / PO号 / 颜色 / 尺码 / **UPC** / 数量, plus a TTL. UPCs are kept as text so 12-digit barcodes never turn into scientific-notation numbers; a size with no UPC on the PO stays blank (never fabricated)"},
        ],
    },
    {
        "version": "2.64.2",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "The **MSRP** column in the GIII buy plan (both the style sheets and the Summary 汇总) now shows the actual retail price printed on the PO (e.g. `$59.00`) whenever the PO carries one — previously it only showed CPRS's `Y`/`N` \"MSRP required\" warehouse flag. POs without a price still fall back to that flag; no value is ever guessed"},
        ],
    },
    {
        "version": "2.64.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "Processing status was confusing on fast runs — in **Auto** mode clean PDFs parse in a fraction of a second, so the bar filled instantly and showed `elapsed 0:00`, reading as if nothing happened. Elapsed time is now sub-second aware (`0.2s`) and the completion line shows the parser/AI split (e.g. `✅ 19 files (19 ✅ by parser) — elapsed 0.2s`), so a fast run clearly reads as done-and-fast. The bar still visibly advances on the slow AI path"},
        ],
    },
    {
        "version": "2.64.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**New 📷 UPC Check tab — a PDA barcode-scanner module** with three modes. **🔍 Lookup**: scan a UPC → shows its PO, style, colour, size, client, destination warehouse and units (all matching POs). **✓ Verify against PO**: pick a PO, scan each UPC → instant match / not-in-PO check with a matched-count and a list of sizes still unscanned. **🧮 Stocktake (盘点)**: scan to +1 / −1 a running physical count per UPC (persisted), with per-UPC context, running totals, Excel download and clear. Scans use the standard PDA flow (the scanner types the UPC + Enter; the box auto-clears for the next scan). Company-scoped like the rest of the app"},
        ],
    },
    {
        "version": "2.63.2",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "**Crash when processing files** (`NameError: name 't' is not defined`) — the new progress bar used the translation helper `t()` but `extraction.py` didn't import it, so processing errored the moment the progress line rendered. Fixed the import; a new guard test fails if any module calls `t()` without importing it (same protection now covers both `SK` and `t`)"},
        ],
    },
    {
        "version": "2.63.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "**Server crash (\"Connection error\") when processing many files** — PDFium (the PDF text engine) is not thread-safe, and the parallel-extraction feature (v2.57) read PDFs across a thread pool, which could segfault the whole Streamlit process (a native crash, no Python traceback → the browser's \"Is Streamlit still running?\" popup). All PDFium reads now run under one process-wide lock; extraction is sub-millisecond so this costs nothing, and the slow per-file AI calls still run concurrently. Stress-tested with hundreds of concurrent reads"},
        ],
    },
    {
        "version": "2.63.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "**Infor Nexus size grids that linearise row-first now keep their UPCs and quantities.** The parser only understood the column-major layout (Size/UOM/UPC/Qty headers, then each size's four values); PDFs whose table extracts row-major (Size: then all sizes, UPC: then all UPCs, Qty: then all qtys) had the entire grid — UPCs and quantities — dropped. A row-major fallback now parses those by matching each size to its UPC and qty by position; the column-major path is unchanged"},
        ],
    },
    {
        "version": "2.62.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "**Price masking no longer redacts MSRP** (or SRP/RRP/retail) — those are public retail prices printed on the hangtag, not the confidential FOB/cost that masking protects. Retail columns are now an explicit exclusion that wins even when the header also contains a generic price word (e.g. 'Suggested Retail Price'); FOB, unit cost, wholesale, line total, and currency-symbol columns still mask as before"},
        ],
    },
    {
        "version": "2.62.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**Live progress during file processing** — a progress bar plus a running line showing **completed/total files**, the **last file done**, **elapsed time**, and **ETA** (e.g. `⏳ 4/19 files — DW843124UC.pdf · elapsed 0:38 · ETA 2:41`). The parallel AI batch now reports each file as it finishes (via as_completed) while still returning results in the original order"},
        ],
    },
    {
        "version": "2.61.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**Searchable consumption panel** in Reference Data → 🧵 Fabric Consumption / Marker — search stored 单耗/排版 data by 款号 (substring, case-insensitive), see a filtered/total count, download the shown rows, and clear all data. Replaces the old collapsed expander"},
        ],
    },
    {
        "version": "2.61.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**单耗/排版 moved to the Summary 汇总 sheet** — the six fabric-consumption columns (单耗 kg/cm, 排版利用率, 排版件数, 排版有效门幅, 排版面料克重) now appear once per style on the summary (where there's exactly one row per style) instead of merged down every style sheet. Cleaner style sheets; same data, same kg↔cm reconciliation on the gross width"},
        ],
    },
    {
        "version": "2.60.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "单耗 kg is now computed on the **gross width** — `毛门幅 = 排版有效门幅 + 5cm`, and `kg = cm × 毛门幅 × gsm ÷ 1e7` (weight is billed on the full roll width incl. selvage, not the usable marker width). e.g. cm 165 · 有效门幅 150 · 200g/m² → 毛门幅 155 → **0.5115 kg** (was 0.495). The kg↔cm consistency check uses the same gross width"},
        ],
    },
    {
        "version": "2.60.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**Fabric consumption / marker (单耗 · 排版) on the buy plan.** Six new columns at the end of each 生产计划单 style sheet: 单耗(kg), 单耗(cm), 排版利用率, 排版件数, 排版有效门幅(cm), 排版面料克重(g/m²). They come from a **new per-style consumption table** you populate via an Excel template — download a blank (or the current data) in **Reference Data → 🧵 Fabric Consumption / Marker**, fill it in, and upload. **单耗 kg and cm are interconvertible**: give either one plus the effective width and fabric weight and the other is calculated (`kg = cm × width × gsm ÷ 1e7`); give both and they're consistency-checked on import (a >5% mismatch is flagged, values kept). A one-time DB table is created automatically; the buy plan reads it per style"},
        ],
    },
    {
        "version": "2.59.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "The processing status now shows the **detected format** per group — e.g. `GIII: 19 file(s) — Infor Nexus PDF ×17 · Vendor Fax ×2` — in both the group summary and each 'Processing …' line, so you can see which parser each batch is using at a glance"},
        ],
    },
    {
        "version": "2.59.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**New ⚡ Auto extraction mode** (Admin → AI Extraction, third option) — runs the instant built-in regex parser first and only falls back to the (slower) AI for files that come back **low-confidence, unparsed, or that the parser can't read**. Best of both: clean PDFs stay near-instant, messy/novel layouts still get AI. The AI fallbacks in a batch run concurrently (like the DeepSeek-every-file mode), and each file is tagged 🤖/✅ in the log by whether AI was actually used. Needs the API key; without one it transparently behaves as regex"},
        ],
    },
    {
        "version": "2.58.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**Admin → AI Extraction model list is now live** — pulled from the DeepSeek `/models` API (cached 30 min) instead of a hardcoded pair, so newly released models appear automatically. The new **deepseek-v4-pro** and **deepseek-v4-flash** now show up (verified live); the currently-saved model and a static fallback are always included, and the dropdown no longer breaks if the saved model isn't `chat`/`reasoner`. The v4 models are correctly treated as chat-style (they accept the sampling params, verified against the API)"},
        ],
    },
    {
        "version": "2.57.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "perf", "text": "**Multi-file AI extraction now runs in parallel.** The combined GIII uploader parsed each PDF's DeepSeek call one after another — with the reasoner model at ~30–60s per file, a 7-file batch took several minutes. The independent per-file AI calls now run concurrently (up to 6 at once), collapsing the batch to roughly a single call's wall-time (~3.5× faster on a 7-file batch, more with the slower reasoner). PDF reading itself was never the bottleneck — text extraction is ~0.05s for 7 files; content de-dup, ordering, and per-file error handling are unchanged"},
        ],
    },
    {
        "version": "2.56.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "**Crash on the GIII combined uploader** (`NameError: name 'SK' is not defined`) — `giii_view.py` referenced the session-key constants without importing `SK`, a latent bug since the upload-detection cache was added that only fired on that specific path. Added the import; a new structural test now fails if any UI module uses `SK.*` without importing it, so this class of missing-import can't recur"},
        ],
    },
    {
        "version": "2.56.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "**Split-delivery lines are no longer collapsed** — the same style+colour+size shipped in two windows (different ex-factory dates) used to overwrite each other in storage, so only the last line's units survived and the PO total came up short. Size rows now carry the ex-factory date and it's part of the unique key, so both shipments are kept and the totals are correct. Same SKU with the *same* date is still treated as one row (a genuine duplicate). A one-time DB migration adds the column and preserves all existing rows"},
            {"type": "fix", "text": "CPRS requirement lookups are unaffected by the split — resolution is per-PO order-context (which never included the ship date), so a split-delivery PO still makes a single CPRS evaluation and the buy plan sums the windows into the correct per-size total"},
        ],
    },
    {
        "version": "2.55.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "security", "text": "**GIII → Missing Fields tab was unscoped** — it listed (and let a non-admin edit) every company's POs, unlike every sibling tab. Now scoped to the user's assigned companies; an unassigned non-admin sees nothing"},
            {"type": "security", "text": "Sign-out now also clears the Reports-tab result/download keys and fax smart-extract results (raw-string session keys the old sweep missed), so the next user on a shared browser can't see the previous user's generated buy plans / summaries"},
            {"type": "security", "text": "Price-masking now redacts **formula** cells in price columns — a `=Dn*En` formula previously survived masking and Excel recalculated the price on open, leaking it from a file believed redacted"},
            {"type": "fix", "text": "**CPRS client no longer poisons its cache on a transient failure** — a network blip or server restart during a Generate used to cache an empty client/warehouse/account/evaluate result for the whole process lifetime, so every later generation reported 'CPRS unreachable' until restart. Failed fetches now retry; only genuine results are cached"},
            {"type": "fix", "text": "Legacy-GIII fallback size capture is word-bounded and longest-match-first — a bare `S`/`M`/`L` can no longer match a substring inside other text (the `L` in `/LT`) and `P2XL` wins over `P2X`"},
            {"type": "fix", "text": "Sky East number cells formatted as text (`1,225`, `$3.45`) now coerce instead of silently becoming 0 (which dropped the whole line as zero-qty); DeepSeek quantities returned as strings coerce too"},
            {"type": "fix", "text": "DeepSeek fallback parser: prompt cap raised 12k→60k with a warning when a long PO is still truncated, and output token limit raised — long multi-item POs no longer silently lose their tail size rows"},
            {"type": "fix", "text": "Stale-value guards added to the GIII delete-POs and Sky East wash-label multiselects (deletes / mapping re-imports no longer crash or silently wipe the selection); HHP/Zalando Chinese-colour enrichment now warns instead of silently shipping blank 中文颜色 when the colour DB is unavailable"},
        ],
    },
    {
        "version": "2.54.2",
        "date": "2026-07-13",
        "entries": [
            {"type": "fix", "text": "Code-review fixes on the buy-plan rework: 目的地 keeps a ship-to segment that carries more than the buyer name (`ROSS STORES DC#4` no longer discarded); 目的地国家 no longer reads English words as US states (`…IN TRANSIT` ≠ Indiana — word-like codes match only after a comma); 每箱件数 surfaces every distinct figure when a requirement states different pack-outs per garment category (`36/12`) instead of silently picking the first; carton-weight values that already carry a unit aren't double-suffixed; Summary hyperlinks escape apostrophes in sheet names; removed dead O(n²) po_end loop and an unused import"},
        ],
    },
    {
        "version": "2.54.1",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "箱重限制 always shows the equivalent in the other unit — lbs values get kg and vice versa (`上限 40 lbs (18.1 kg)`, `下限 5 lbs (2.3 kg)`, TJX Australia `上限 22.68 kg (50 lbs)`). The KB's stated figure renders verbatim; only the converted figure is rounded"},
        ],
    },
    {
        "version": "2.54.0",
        "date": "2026-07-13",
        "entries": [
            {"type": "feat", "text": "**箱重限制 now states its bounds explicitly** — the KB carries BOTH bounds for some brands (CK/DKNY packing: `weight_lbs 5-40` → `下限 5 lbs / 上限 40 lbs`) and upper-only rules for others (KL/corporate → `上限 40 lbs`). Ranges render both bounds; upper-only rules render 上限 alone without claiming a lower bound the KB doesn't state; a brand range combines with the corporate max (missing bound filled). pallet_spec weights (2200 lb!) and board-strength values (ECT/burst) are explicitly excluded"},
        ],
    },
    {
        "version": "2.53.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**箱重限制 column** (carton weight limit, per client) on the style sheets and Summary 汇总, next to 每箱件数 — read from the brand's CPRS carton_spec requirement (G-III corporate: `40 lbs / 18 kg per carton`; KL's own account spec: `40 lbs`). Marking fields like net/gross weight are not mistaken for limits; no stated limit → blank"},
        ],
    },
    {
        "version": "2.52.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**Full-size 图示 blocks on every style sheet** — below the footer, each sheet now shows the readable 红色箱贴纸图示 and 主箱唛图示 artwork (up to ~240px tall) with a label listing the POs it applies to; identical artwork shared by several POs appears once. The small in-cell thumbnails stay as reminders"},
            {"type": "fix", "text": "CK's red-sticker artwork now resolves — it is linked under the sibling `red_carton_sticker_sizes` subtype; the resolver falls back across `red_carton_sticker*` subtypes when the main result carries no image"},
        ],
    },
    {
        "version": "2.51.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "fix", "text": "**每箱件数 was blank** — two causes: (1) CPRS v1.6.5 search results went slim, dropping `structured_output` (where the per-account prepack ratios/pieces live) — it is now requested explicitly via `include=structured_output`; (2) brands like CK state the pack-out inside the requirement wording ('6 pre-packs per box, **36 pcs/carton**') rather than a structured ratio table — the resolver now reads explicit pcs/carton figures from the winning packaging/hangtag/carton requirements. Priority: manual input > per-account spec > requirement wording; still blank (never guessed) when no source states it"},
        ],
    },
    {
        "version": "2.50.1",
        "date": "2026-07-12",
        "entries": [
            {"type": "fix", "text": "**A dead CPRS server no longer masquerades as 'brand not found'** — when CPRS is unreachable the warning now says exactly that (one message, not one per brand). 'Not found in CPRS' only appears when the server answered and genuinely has no such client"},
            {"type": "fix", "text": "Brand matching understands vowel-dropped division names — `DKNY W/SPRTSWR` now deterministically resolves to DKNY Sportswear (two-token abbreviation match beats DKNY Suits' single token, regardless of API list order)"},
        ],
    },
    {
        "version": "2.50.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**目的地国家 column** (US/EU/UK/CA/AU) on the style sheets and Summary 汇总, next to 目的地 — from the CPRS warehouse's region when requirements are resolved, else parsed from unambiguous markers in the ship-to address (US state+ZIP, country names, safe country codes); no marker → blank, never guessed"},
        ],
    },
    {
        "version": "2.49.1",
        "date": "2026-07-12",
        "entries": [
            {"type": "fix", "text": "目的地 no longer repeats the buyer — ship-to text leads with the consignee name (`ROSS STORES / 3404 INDIAN AVE / …`), which duplicated the 买家 column; when the first segment matches the buyer it is stripped, leaving just the address"},
        ],
    },
    {
        "version": "2.49.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**品牌 column on the style sheets** (after 款号, alongside 目的地) — the brand read off the PO; brand-less POs show the red ⚠ 无品牌 flag there (moved out of 备注)"},
            {"type": "fix", "text": "**Prepack detection understands pack ratios** — a ratio printed in the PO's packing/hanger text (e.g. `FLAT PACK + HANGER (1-2-2-1)`) means the order IS prepack even without a PPK marker: 是否预包 now shows `Y 1-2-2-1` (PO ratio wins over CPRS's per-account ratio), 衣架 shows just `HANGER` with the ratio stripped, and the CPRS red-sticker check receives the correct prepack flag"},
        ],
    },
    {
        "version": "2.48.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**Adopt the CPRS v1.6.5 contract** — every evaluate result now carries linked manual artwork as `images[]`; the buy plan reads that (falling back to the old `resultJson.image_id`), so 红色箱贴纸/主箱唛 pictures embed whenever the knowledge base has artwork for the winning requirement. The stricter-400 / auth-header / health behaviours of 1.6.5 were verified compatible with our client"},
        ],
    },
    {
        "version": "2.47.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**Brand decoded from the PO number's division prefix** — GIII PO numbers start with the division code, which is on the PO itself (not a guess). Documented prefixes from the CPRS knowledge base are mapped: **CS** → Calvin Klein (the CSKHHN HOL26 Ross faxes), **LS** → Karl Lagerfeld (LSKHHN Perris POE series), **DW** → DKNY Sportswear. Used by the buy plan (品牌 column + CPRS resolution) and the upload-time requirements document when the PO has no division field. Undocumented prefixes (e.g. DU…) still flag ⚠ 无品牌 rather than guessing"},
        ],
    },
    {
        "version": "2.46.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "fix", "text": "**No brand guessing.** A PO without a brand (division) on it is now flagged **⚠ 无品牌** in the buy plan — red marker in the style sheet's 备注 and in the Summary's new 品牌 column — and every brand-dependent cell (红色箱贴纸, 主箱唛, 是否预包 ratio, 每箱件数, MSRP, RFID, CPRS warehouse fill) stays **empty**. The v2.44 evidence-based client matching and the brand picker are removed; the old 红色箱贴纸 default of 无 is gone too — an unresolved requirement renders blank, never as a claim"},
        ],
    },
    {
        "version": "2.45.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**No. column + 颜色(中文) in both summary sheets** — Summary 汇总 rows and 简明汇总 style blocks are numbered, and the Chinese colour name (进度表 first, colour DB fallback) appears next to the English colour"},
            {"type": "feat", "text": "**包装方式 broken into individual columns** on the style sheets AND Summary 汇总: 包装方式 (packing only), 衣架 (hanger), 是否预包 (Y + prepack ratio when known / N), 每箱件数 (pcs per carton from CPRS or the manual input), MSRP and RFID (warehouse defaults from CPRS). 备注 stays empty for manual notes"},
        ],
    },
    {
        "version": "2.44.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "fix", "text": "**仓库代码 was blank on most POs — now resolved three ways**: (1) the PO's own destination code when present; (2) the DKNY PO-number suffix (DW843120**DN** → DN), validated against the client's real CPRS warehouse catalog so non-codes like a fax PO's '…5R' are never trusted; (3) the ship-to address via CPRS ZIP matching (Ross Perris DC → **DW**, US POE)"},
            {"type": "feat", "text": "**Brand detection for vendor-fax POs** — faxes carry no division, so the brand string used to fall back to an HTS code and CPRS was silently skipped. Requirements resolution now matches the CPRS client from order evidence (buyer account hit, PO-suffix warehouse hit, ship-to resolution). When the evidence is ambiguous (DKNY and KL both sell to Ross Perris) it names the tied candidates instead of guessing, and a new **brand picker** in the requirement inputs lets the operator decide"},
        ],
    },
    {
        "version": "2.43.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**Style sheets gain 目的地 and 包装方式 columns** — the ship-to destination (after 仓库代码) and the packing method (packing + hanger, moved out of 备注 into its own column; 备注 stays for manual notes). Both merge per PO like the other PO-level cells"},
            {"type": "fix", "text": "**离厂时间 is now ETD − 10 days** — the PO's ship date is the vessel ETD; the goods must leave the factory ~10 days earlier. Applies to the style sheets and both summary sheets; unparseable dates (e.g. 'TBD') pass through unchanged"},
        ],
    },
    {
        "version": "2.42.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**Summary 汇总 now shows the size breakdown with quantities** (尺码明细, e.g. `S 1400 / M 2800 / L 2800 / XL 1400`), plus **包装方式** (packing + hanger from the PO) and **目的地** (ship-to destination) columns"},
            {"type": "feat", "text": "**简明汇总 sheet** — a second, simplified summary: one row per (款号, 颜色) with the 面料 line from the 款式面料表格, dynamic per-size quantity columns, 总数量, and a per-size TTL row. Style and fabric cells merge across each style's colour rows"},
        ],
    },
    {
        "version": "2.41.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**Summary 汇总 sheet in the buy plan** — the 生产计划单 workbook now opens with a summary table: one row per style's buy plan (款号 links to its sheet) with 品名, 合同号, PO count + numbers, colours, sizes, 总数量, 离厂时间, 仓库代码, 买家 and the CPRS 红色箱贴纸/主箱唛 values, plus a grand-total TTL row"},
        ],
    },
    {
        "version": "2.40.0",
        "date": "2026-07-12",
        "entries": [
            {"type": "feat", "text": "**GIII buy plan is now the 生产计划单 format, enriched** — the production-plan layout the factory actually uses (one sheet per style, only ordered colours, per-style size columns) now carries 面料 rows from the 款式面料表格 (main part + 面料_其他1/2/3), 合同号 and 中文颜色 from the 大货进度表, and 红色箱贴纸/主箱唛 text **and artwork** resolved live from CPRS (per PO, with warehouse fill-in when the PO has no destination code). The separate A–W 'Buy Plan + Requirements' button is retired — 📋 Create Buy Plan does it all; 🔍 Check requirements still previews without generating"},
            {"type": "fix", "text": "**Buy-plan outputs showed many empty rows and lost plus sizes** — two causes fixed: (1) the upload-time by-style workbook fell back to the *Zalando* template (`default.xlsx`), whose fixed XS–XXL columns silently dropped 1X/2X/3X quantities and left Brand/中文颜色 blank — the template is removed, GIII reverts to the clean built-in layout; (2) unordered colourways (all-zero rows from the PO's full SKU matrix) are now filtered out, matching the 'filtered' in the file name"},
            {"type": "fix", "text": "生产计划单: NaN metadata no longer renders as literal 'nan' in CPO#/仓库代码/备注 cells"},
        ],
    },
    {
        "version": "2.39.1",
        "date": "2026-07-11",
        "entries": [
            {"type": "fix", "text": "**CPRS evaluate calls were silently returning nothing through the client** — the API answers POST with HTTP 201 (NestJS default) and the client only accepted 200, so every `/evaluate` came back empty (blank carton/requirement fields in earlier live runs). The client now accepts any 2xx. Verified live: a real DKNY PO now pulls **51 requirements** into the requirements document (35 confirmed / 8 pending / 8 N/A)"},
            {"type": "fix", "text": "Brand resolution now also matches the CPRS client's **division code** — real GIII PDFs carry the division (e.g. `DW`) rather than the brand name, which previously failed to resolve and skipped the PO from the requirements document"},
        ],
    },
    {
        "version": "2.39.0",
        "date": "2026-07-11",
        "entries": [
            {"type": "feat", "text": "**Uploading GIII POs now also pulls each PO's client requirements into an Excel requirements document.** When CPRS is configured, the upload pipeline resolves the full requirement set per PO (brand from the PO's division, warehouse from its destination code or ship-to, account from the buyer) and produces **PO_Requirements.xlsx**: a Summary sheet with per-status counts per PO, plus one sheet per PO listing every requirement — labels, hangtags, packaging, carton marking, testing — with bilingual status markers (必须/待定/冲突/不适用), the requirement wording, and its manual source. POs sharing an order context are evaluated once. A 🧭 download button appears with the other outputs; unresolvable brands/warehouses are warned about, and any CPRS failure skips the document without failing the upload"},
        ],
    },
    {
        "version": "2.38.0",
        "date": "2026-07-10",
        "entries": [
            {"type": "feat", "text": "**Carton artwork now embeds into the buy plan.** The red-sticker and 主箱唛 images CPRS provides render inside their cells (sized to fit, row height adjusted) like the reference workbook's DISPIMG images — with the text value kept underneath, and unreadable image bytes skipped rather than failing the export"},
            {"type": "feat", "text": "**Per-PO DIM codes.** The requirement-inputs expander now has an editable PO → DIM table, so one generation can carry different pre-pack codes per PO; the single DIM field acts as the default for unlisted POs"},
            {"type": "feat", "text": "**🔍 Check requirements only** — resolve and preview the CPRS requirements for the selected POs without generating a workbook (assembly, resolution, and export are now separate steps)"},
            {"type": "docs", "text": "Buy-plan validation via CPRS `/production-submission/compare` is documented as **blocked by API-key scope** — verified live that the current key is read/evaluate-only and upload requires an admin/editor role. Ask the CPRS admin for a broader key to unlock it"},
        ],
    },
    {
        "version": "2.37.0",
        "date": "2026-07-10",
        "entries": [
            {"type": "refactor", "text": "**CPRS integration redesigned into a proper service layer** (`po_extractor/ui_helpers/giii_requirements.py`, design in `docs/GIII_CPRS_Integration_API.md`). Requirement resolution moved out of the exporter into one typed call returning per-row requirements **plus warnings** — unmatched buyers, unresolved ship-tos, and missing prepack ratios now surface in the UI instead of silently blanking cells. Rows sharing an order context (warehouse + buyer + prepack) resolve once, not once per row"},
            {"type": "fix", "text": "**Three integration bugs found in review:** (1) the evaluate cache ignored `contextFields`, so a supplied DIM code could return the stale no-context result; (2) the evaluate **channel was hardcoded WHOLESALE** — it now derives from the CPRS account type (Macy's.com → ECOMM, Ross → OFF_PRICE, …), which changes which requirements match; (3) brand matching could arbitrarily pick \"DKNY Suits\" vs \"DKNY Sportswear\" for a bare \"DKNY\" — candidates are now ranked. Also: ship-to warehouse lookups are cached, and the CPRS client itself is session-cached (`ui/stores.py`) instead of rebuilt on every click"},
            {"type": "feat", "text": "**Resolution preview before sending:** after generating a Buy Plan + Requirements, an expander shows exactly what CPRS resolved per PO (warehouse, account, channel, red sticker, ratio, PCs/box, MSRP, RFID) with any warnings above it — so the operator verifies against the factory's expectations before downloading"},
        ],
    },
    {
        "version": "2.36.1",
        "date": "2026-07-09",
        "entries": [
            {"type": "feat", "text": "**Prepack orders now show the real ratio and PCs-per-box.** The prepack ratio and pieces-per-bag turned out to live per-account inside the CPRS `pre_pack_ratio` requirement (which is why `/evaluate` reported a conflict — two tier-1 rules with no account filter). The buy plan now reads them directly by the row's account: e.g. ROSS → ratio `4-14 1-1`, 6 pcs/box; MARMAXX → `S-XL 1-2-2-1`, 6. Both columns fill only for prepack orders (checked first, like the red sticker), and a manually-entered PCs/box still overrides. Verified live against CPRS"},
        ],
    },
    {
        "version": "2.36.0",
        "date": "2026-07-09",
        "entries": [
            {"type": "feat", "text": "**GIII buy plan: red sticker now checks prepack first, plus manual runtime inputs and Chinese translation.** Verified live against CPRS: the red carton sticker is required only for **prepack** orders and must show the pre-pack **DIM code**. So the buy plan now writes 无需 for non-prepack rows, and for prepack rows shows the DIM code (a new generate-time input) — supplying it also resolves the CPRS requirement from pending to confirmed. Added generate-time inputs for the **DIM code** and **PCs-per-box** (which CPRS leaves to the factory at runtime), plus an optional **translate CPRS requirement text to Chinese** toggle (DeepSeek), since the knowledge base returns wording in English. All under a new expander in GIII → 📦 Generate / Export"},
        ],
    },
    {
        "version": "2.35.1",
        "date": "2026-07-09",
        "entries": [
            {"type": "fix", "text": "**GIII buy plan reconciled against the live CPRS API.** Corrected the client's field names to the real ones (`account_code`, `warehouse_code`, `rfid_default`, `msrp_required_default`) and made the requirement parsing status-aware for the real response shapes — not_applicable→无需, pending_input→a 待定:&lt;field&gt; marker (e.g. the red sticker waits on a runtime `dim_code`), conflict→冲突. Verified end-to-end live: MSRP/RFID resolve correctly from the warehouse code"},
            {"type": "fix", "text": "**中文颜色 now comes from the 大货进度表** (progress records' EN→CN colour), not the general colour-translation store; **面料信息 now comes from the 款式面料表格** (style-fabric mapping) for the buy plan's primary style, matching the intended sources"},
        ],
    },
    {
        "version": "2.35.0",
        "date": "2026-07-09",
        "entries": [
            {"type": "feat", "text": "**GIII buy-plan build, step 2c — wired end-to-end.** GIII → 📦 Generate / Export has a new **🧭 Buy Plan + Requirements (CPRS)** button: it assembles buy-plan rows from the selected POs' stored size rows + metadata, resolves contract numbers from the 大货进度表 and Chinese colours from the translation store, pulls the client requirements (red sticker, carton mark, prepack ratio, PCs/box, MSRP, RFID) live from CPRS when configured, and downloads the finished A–W GIII buy plan. Works with or without CPRS (requirement columns blank when it's not set up). Completes the GIII buy-plan build (steps 2a–2c)"},
        ],
    },
    {
        "version": "2.34.0",
        "date": "2026-07-09",
        "entries": [
            {"type": "feat", "text": "**GIII buy-plan build, step 2b: the GIII buy-plan exporter.** Added `po_extractor/exporters/giii_buyplan_export.py` — generates the real GIII 生产计划单 (buy plan) A–W bilingual layout: manufacturer banner, supplier/fabric/description header block, two-row EN+中文 column headers, one data row per PO × color with a dynamic size block, a grand TTL, and per-color subtotals. The requirement-driven columns (red sticker, carton mark, prepack ratio, PCs/box, MSRP, RFID) and the warehouse code resolve live from CPRS when a client is configured, and are left blank (buy plan still generates) when it isn't. Built as a from-scratch workbook generator rather than a fill-in template — more testable and robust to size-count changes. 5 exporter tests (with and without a mock CPRS). Pipeline/UI wiring is step 2c"},
        ],
    },
    {
        "version": "2.33.0",
        "date": "2026-07-09",
        "entries": [
            {"type": "feat", "text": "**GIII buy-plan build, step 2a: CPRS knowledge-base client.** Added `po_extractor/utils/cprs_client.py` — a read-only, cached, gracefully-degrading REST client that resolves brand→clientId, ship-to→warehouse, buyer→account, the carton requirements, and warehouse RFID/MSRP flags from the CPRS API (the data behind the buy plan's red-sticker / carton-mark / MSRP / RFID columns). Configure it under **Admin → Settings → 🧭 CPRS Knowledge Base** (base URL, API key, Test-connection button); leave blank to disable, in which case buy plans still generate with those fields blank. This is the dependency root for the GIII buy-plan exporter (steps 2b/2c to follow)"},
        ],
    },
    {
        "version": "2.32.2",
        "date": "2026-07-09",
        "entries": [
            {"type": "docs", "text": "GIII buy-plan spec: added **MSRP (V)** and **RFID (W)** as two separate columns, both **CPRS-sourced and warehouse-driven** (resolved from the warehouse code in col E — the CPRS API states RFID/MSRP-required never come from the PO). Noted that the MSRP price *value*, if needed, is available on KL POs (`msrp`)"},
        ],
    },
    {
        "version": "2.32.1",
        "date": "2026-07-09",
        "entries": [
            {"type": "docs", "text": "GIII buy-plan spec: resolved the packing-column sources — **是否预包 (Prepack Y/N) is PO-sourced** (the PPK marker on the order, which triggers the rest), while **预包比例 (Prepack Ratio)** and **每箱件数 (PCs per Box)** are **CPRS-sourced** (`packaging` domain, client-mandated). Added Prepack Ratio as its own column (S/T/U = Prepack · Ratio · PCs-per-Box)"},
        ],
    },
    {
        "version": "2.32.0",
        "date": "2026-07-09",
        "entries": [
            {"type": "feat", "text": "**Optional AI-assisted price masking (DeepSeek).** A new **Admin → Settings** toggle (“Use AI to detect prices when masking”, off by default) lets the masker ask DeepSeek to identify prices from context — catching ones the built-in rules can't, like a whole-dollar FOB or an oddly-formatted amount, and price columns whose header has no recognized keyword. AI findings are **unioned** with the pattern/keyword detection, never replace it, so the built-in rules stay the floor even if AI is off or the call fails. Applies to every masking path (GIII PDF, GIII/Zalando Excel, Sky East). Uses the existing DeepSeek key; graceful fallback when unset or unreachable"},
        ],
    },
    {
        "version": "2.31.4",
        "date": "2026-07-09",
        "entries": [
            {"type": "docs", "text": "GIII buy-plan field-mapping spec: renamed the R column 备注 → **包装方式 (Packing Method)**, and added two new columns — **S 每箱件数 (PCs per Box)** and **T 是否预包 (Prepack Y/N)** — both provisionally sourced from CPRS's `packaging` domain (which carries the per-brand/account prepack + packs-per-carton rules), flagged for source confirmation"},
        ],
    },
    {
        "version": "2.31.3",
        "date": "2026-07-09",
        "entries": [
            {"type": "fix", "text": "**Price masking now catches prices it used to miss.** PDF masking previously only matched plain `123.45` amounts — it now also masks prices with thousands separators (`1,234.00`, `12,345.67`) and currency prefixes (`$4.17`, `€1,000.00`, `£`, `¥`), while still leaving bare integers (quantities, UPCs, PO numbers) untouched. Excel masking gained more price-header keywords (**MSRP, SRP/RRP, retail, wholesale, extended, line total**, and currency-symbol headers like `Line Total ($)`) — a real gap, since MSRP and line-total columns weren't being masked before — and now also masks currency-formatted string values (`$69.00`) inside detected price columns. Text cells in those columns (e.g. a `Retail Partner` name) are still left intact"},
        ],
    },
    {
        "version": "2.31.2",
        "date": "2026-07-09",
        "entries": [
            {"type": "docs", "text": "GIII buy-plan field-mapping spec: resolved the open question on the 备注 (Remarks) column — it is **PO-sourced** (`packaging`/`hanger`, e.g. 平装+衣架), not a CPRS lookup"},
        ],
    },
    {
        "version": "2.31.1",
        "date": "2026-07-09",
        "entries": [
            {"type": "docs", "text": "Added `docs/GIII_BuyPlan_Field_Mapping.md` — the field-mapping spec for the real GIII buy-plan format (the one all GIII POs use, DKNY being one brand). Maps every cell to its source (PO record · HHN 大货进度表 · color-translation) and defines how the two carton-image columns (红色箱贴纸 / 主箱唛) and warehouse/account resolution come live from the CPRS knowledge base API. This is the pre-build spec for a Sky-East-class GIII exporter; no code behavior changes yet"},
        ],
    },
    {
        "version": "2.31.0",
        "date": "2026-07-09",
        "entries": [
            {"type": "feat", "text": "**Other PO types combined into one uploader with automatic type detection.** Instead of picking the right section (MSG fax / KL / InforNexus / TK EU), drop any mix of .msg emails and PDFs into one drop zone — each file's type is determined from its **content** (InforNexus portal keywords; Kostroma/TJX UK markers; the KL MSRP block; AS400 fax-doubled text) and routed to the right extractor, which opens below with its files pre-loaded. Extension plays no role, since the same fax documents arrive both inside .msg emails and as bare PDFs. Unrecognized files are listed explicitly rather than silently dropped, and classification is cached per file set (and reads only each document's first pages), so it doesn't re-run on every page interaction"},
            {"type": "feat", "text": "The KL extractor now also accepts .msg-wrapped KL POs (the router can hand it fax emails); the InforNexus section keeps its manual side-by-side KL-comparison uploader"},
        ],
    },
    {
        "version": "2.30.10",
        "date": "2026-07-08",
        "entries": [
            {"type": "fix", "text": "**Masked-price download: when masking produces no files, the results now say so explicitly** (with the failure reasons) instead of the 🔒 download button silently not appearing. The per-file failure warnings previously scrolled away with the processing status, leaving no visible trace of why there was nothing to download"},
        ],
    },
    {
        "version": "2.30.9",
        "date": "2026-07-08",
        "entries": [
            {"type": "perf", "text": "**GIII upload auto-detection is much faster.** Two fixes: (1) detection results are now cached per uploaded file set — previously EVERY interaction on the page (a checkbox, opening an expander) re-read and re-classified the entire PDF batch on the Streamlit rerun; (2) classification now reads only the first 3 pages of each PDF instead of the whole document, since the format keywords are header-level (parsing still reads the full document, and the parser re-detects on full text, so routing is unaffected)"},
        ],
    },
    {
        "version": "2.30.8",
        "date": "2026-07-08",
        "entries": [
            {"type": "refactor", "text": "**The Excel cell-styling helpers nested inside the MSG, KL, and TK EU workbook builders are combined into one shared style kit** (`make_excel_style_kit` in `ui/giii/_shared.py`) — Arial 10, thin borders, white-on-navy wrapped headers, bounded autofit — with TK EU keeping its teal header via a parameter. Golden style tests were added first and pass unchanged after the swap, proving the generated workbooks are styled identically. InforNexus's builder keeps its own helpers for now (different palette/width variants)"},
        ],
    },
    {
        "version": "2.30.7",
        "date": "2026-07-08",
        "entries": [
            {"type": "refactor", "text": "**GIII extraction modules de-duplicated into shared helpers** (`ui/giii/_shared.py`): the .msg→PDF unwrap loop (previously copy-pasted between the MSG and TK EU sections), the stale-results guard (three copies), the fax size-column order, and the workbook colour palette (four copies each) now live in one place. No behavior change — locked by regression tests that pin the historical size order and palette values, since both are part of the generated workbooks' layout"},
        ],
    },
    {
        "version": "2.30.6",
        "date": "2026-07-08",
        "entries": [
            {"type": "feat", "text": "**MSG/Vendor Fax and TK EU sections now accept the fax PDFs directly**, not only Outlook .msg emails. Files ending in .pdf skip the email-unpacking step and go straight to the same parser; .msg files work exactly as before (including the PO-number-from-subject fallback, which only applies to emails). The extract-msg library is now only required when the batch actually contains .msg files"},
        ],
    },
    {
        "version": "2.30.5",
        "date": "2026-07-08",
        "entries": [
            {"type": "refactor", "text": "**AI extraction is now an admin-only choice.** The 🤖 AI Extraction expander (per-run toggle + session API-key override) on GIII → New Contracts is gone — the extraction method, DeepSeek key, and model are configured solely in **Admin → Settings**, which already had the full section. The upload page now just shows a one-line note when AI mode is active (or a warning if it's enabled without a key, in which case files fall back to the built-in parser)"},
        ],
    },
    {
        "version": "2.30.4",
        "date": "2026-07-08",
        "entries": [
            {"type": "refactor", "text": "**GIII → New Contracts redesigned: the specialized PO extractors (MSG/Vendor Fax, KL PDFs, InforNexus, TK EU) are now collapsed expanders under an \"Other PO types\" section** beneath the main PO uploader, instead of four fully-rendered sections stacked down the page. Same page, same functionality — open only the type you're working with. Expander labels are translated for the Chinese UI"},
        ],
    },
    {
        "version": "2.30.3",
        "date": "2026-07-08",
        "entries": [
            {"type": "refactor", "text": "**Removed the duplicate fabric-mapping upload from GIII → New Contracts.** Style-Fabric mapping (and HHN contract progress) are managed centrally in the 📐 Reference Data tab — per company and saved persistently — so the ad-hoc upload expander on the GIII upload screen was a second, competing way to do the same thing. The upload tab now shows a one-line pointer to Reference Data instead"},
        ],
    },
    {
        "version": "2.30.2",
        "date": "2026-07-08",
        "entries": [
            {"type": "refactor", "text": "**GIII tab bar now uses the same menu names as Sky East**: \"Upload\" → \"New Contracts\" and \"PO History\" → \"Contract History\", so both client tabs read identically (New Contracts → 📦 Generate / Export → Contract History → Missing Fields). GIII orders carry HHN contract numbers via the 大货进度表, so the contract terminology fits this pipeline too. Chinese translations already covered both names"},
        ],
    },
    {
        "version": "2.30.1",
        "date": "2026-07-08",
        "entries": [
            {"type": "refactor", "text": "**GIII tab bar now matches Sky East's layout**: same order (Upload → 📦 Generate / Export → PO History → Missing Fields) and same label style — plain text with 📦 only on the output tab, and the Missing Fields count shown as a plain number like Sky East's. The 🔴 pending-exception alert on PO History is GIII-specific and stays"},
        ],
    },
    {
        "version": "2.30.0",
        "date": "2026-07-07",
        "entries": [
            {"type": "feat", "text": "**Pipeline convergence phase 5: one shared read-side shape for cross-client order data.** A single backend call (`load_standard_orders()`) now returns every pipeline's orders as one standardized DataFrame — GIII contract numbers resolved from the 大货进度表 automatically, Sky East order dates from contract headers, with per-pipeline include toggles for permission gating. A companion adapter (`sky_east_items_to_size_rows()`) explodes Sky East items to the same PO/style/color/size/units grain as GIII's size rows, so size-level consumers can treat both pipelines identically"},
            {"type": "refactor", "text": "Summary → Overview's per-company aggregate table is now computed from the standard shape with a single groupby instead of separate GIII and Sky East code branches; the All Orders tab loads through the same backend call. On-screen result is unchanged — the same numbers now come from one code path instead of three"},
        ],
    },
    {
        "version": "2.29.2",
        "date": "2026-07-07",
        "entries": [
            {"type": "refactor", "text": "**Pipeline convergence phase 4: Sky East's Buy Plan and 核料 exporters are registered in the output-format registry** alongside GIII's four formats, so there is now one catalogue of every output the system can produce instead of Sky East's exporters being invisible to format discovery. No behavior change to the exports themselves"},
        ],
    },
    {
        "version": "2.29.1",
        "date": "2026-07-07",
        "entries": [
            {"type": "fix", "text": "**Pipeline convergence phase 3: Sky East parse failures now land in the persistent Exception Queue** (the same one GIII parse failures use, tagged with company \"Sky East\") instead of existing only as a red line in the upload log that vanished with the browser session. They show up in the Exception Queue panel for admins and Sky East-permitted users, with the file name and failure reason"},
        ],
    },
    {
        "version": "2.29.0",
        "date": "2026-07-07",
        "entries": [
            {"type": "feat", "text": "**Pipeline convergence phase 2: Sky East contracts now grade their own quality the way GIII POs do.** The parser computes a real confidence score (100 minus 10 per missing contract-header field, replacing the old crude 100-or-50) and a `validation_status` of valid/warning/exception on the same scale as GIII's, so both pipelines' quality grades mean the same thing downstream. The item-level import checks (blank style/color, negative quantities, non-standard HHN, unparseable dates, Config SKU coverage) moved from the upload screen into the backend (`po_extractor/parsers/sky_east_validation.py`) — the UI still shows identical warnings, but the checks are now reusable and testable outside Streamlit"},
        ],
    },
    {
        "version": "2.28.2",
        "date": "2026-07-07",
        "entries": [
            {"type": "refactor", "text": "**Pipeline convergence phase 1: Sky East now goes through the same front door as GIII.** The universal file detector recognizes Sky East purchase contracts by content (same keyword signature the parser locks onto), a canonical `parse_sky_east_order()` lives in the parsers facade alongside `parse_pdf()` (the Sky East upload flow now calls it instead of importing parser internals), and the superseded hardcoded-layout Sky East parser is no longer exported. Sky East is also registered as an Excel format on its company entry, so format→company resolution works for it like it does for the PDF formats"},
        ],
    },
    {
        "version": "2.28.1",
        "date": "2026-07-07",
        "entries": [
            {"type": "fix", "text": "**All Orders: GIII's Contract No. now comes from the HHN 大货进度表 progress records** instead of just mirroring the PO number. Matched by the progress sheet's PO# column first (normalized, so casing/whitespace differences don't matter), falling back to a style match when PO# is blank — and left empty when the progress data has no row for the order, rather than showing a misleading value. Upload the 大货进度表 per company via the HHN Contract Progress tab to populate it"},
        ],
    },
    {
        "version": "2.28.0",
        "date": "2026-07-07",
        "entries": [
            {"type": "feat", "text": "**Summary → new 🧾 All Orders sub-tab: every client's orders in one combined table with standardized columns.** GIII POs and Sky East contract items previously lived in separate lists with different headers; they now map into one standard column set (Company, PO Number, Contract No., Style, Color, Brand/Customer, Factory, COO, Order Date, Ex-Fty Date, Units, Unit Price, Total Cost, Season, Source) with client filter, PO/contract/style/color search, a column picker, and a single-sheet Excel download. Fields one client can't provide stay blank rather than shifting the header, so the layout is identical no matter which clients contribute rows. Company-permission gating matches the rest of the Summary tab"},
            {"type": "refactor", "text": "The standard column mapping lives in a new backend module (`po_extractor/ui_helpers/combined_summary.py`) with adapters per pipeline, so future views and exporters can reuse the same standardized shape instead of hand-mapping each client's schema — first step of the GIII/Sky East structural-convergence plan's shared read-side model"},
        ],
    },
    {
        "version": "2.27.8",
        "date": "2026-07-06",
        "entries": [
            {"type": "fix", "text": "**Update.bat would have overwritten user-customized settings with factory defaults.** The updater's protect-list only covered databases and account/license files — but companies, size order, output schema, custom fibers, and the buy-plan template workbooks are all edited at runtime through the app's admin screens AND ship in the pack, so an update would have silently reset them. The `data\\` directories and `auth\\companies.json` are now excluded from the copy wholesale, so a future runtime-editable file can't reintroduce the bug by being forgotten. Verified with an adversarial test where the pack deliberately carried factory versions of every such file"},
            {"type": "fix", "text": "**Update/Uninstall couldn't tell the app was running.** Their check matched the process command line, but `Start_PO_Extractor.bat` launches Python via a relative path, so the command line never contains the install folder — the scripts always said \"Not running\" and Uninstall could then die mid-removal on the locked `.venv\\python.exe`. Detection now matches the process's executable path, which is always absolute"},
            {"type": "fix", "text": "Install/Update now verify each native step actually succeeded (venv creation, pip install, license registration) instead of printing \"complete!\" even after e.g. a network failure — PowerShell's error handling doesn't cover native commands' exit codes"},
            {"type": "security", "text": "Uninstall's full-wipe (`DELETE`) path now also removes `auth\\smtp_settings.json` (which can hold an SMTP password), `auth\\companies.json`, and `po_extractor\\data\\custom_fibers.json` — a \"remove everything\" run no longer leaves a credential file behind"},
            {"type": "fix", "text": "Install's Python detection no longer trips over the `*` default-interpreter marker in `py -0p` output when 3.13 is the system default (the captured path started with `*` and failed validation, falling back to guessed install locations)"},
        ],
    },
    {
        "version": "2.27.7",
        "date": "2026-07-06",
        "entries": [
            {"type": "feat", "text": "**Added an updater to the install pack** (`Update.bat` / `Update.ps1`). Run it from a newly-extracted pack folder, point it at an existing install, and it copies in the new app code and refreshes dependencies — `data\\`, `auth\\users.json`, `auth\\license.key`, `auth\\smtp_settings.json`, and `.venv\\` are explicitly excluded from the copy and never touched, even if a future pack happened to contain files by those names. Verified with a smoke test where the source pack deliberately included conflicting files under those exact names, to confirm the exclusion is defensive rather than incidental"},
        ],
    },
    {
        "version": "2.27.6",
        "date": "2026-07-06",
        "entries": [
            {"type": "fix", "text": "**Resetting an existing user's password via `setup_users.py` silently demoted admins back to a regular user.** `create_user()` always wrote whatever `role` it was given, defaulting to `user` — unlike `companies`/`modules`/`email`, it never fell back to the account's existing role when the caller didn't specify one. Since `setup_users.py` never passed a role except for the very first bootstrap account, re-running it against an existing admin (e.g. to change their password) quietly took away their admin access with no warning. `create_user()` now preserves the existing role when none is given, same as its other fields; explicitly passing a role (the admin User Management screen, and the first-run bootstrap) still overrides it as before"},
        ],
    },
    {
        "version": "2.27.5",
        "date": "2026-07-06",
        "entries": [
            {"type": "security", "text": "**This machine's `auth/license.key` had been committed to git** — `.gitignore` excluded `auth/license_key.txt`, but the file the app actually writes is `auth/license.key`, so the typo never matched and every clone/archive carried this dev machine's hardware-fingerprint key. Fixed the filename in `.gitignore` and untracked the file (kept on disk locally — the running app is unaffected). Not a live exposure risk in practice since `Install.ps1`/`docs/DEPLOYMENT.md` both regenerate a fresh key unconditionally on setup, but it had no business being in git history going forward"},
        ],
    },
    {
        "version": "2.27.4",
        "date": "2026-07-06",
        "entries": [
            {"type": "feat", "text": "**Added an uninstaller to the install pack** (`Uninstall.bat` / `Uninstall.ps1`). Always removes the Python environment (`.venv`) and this computer's license, since both rebuild automatically on the next install. Your PO history, fabric database, and login accounts are kept by default — typing `DELETE` at the prompt is required to also erase those. Deleting the install folder itself and uninstalling Python 3.13 are left as manual steps, since the script can't safely remove files it's running from and Python may be shared with other software on the machine"},
            {"type": "chore", "text": "The install pack's helper scripts (`Install.ps1`, `Install.bat`, `Start_PO_Extractor.bat`, the new uninstaller, `INSTALL_README.md`) are now tracked under `installer/` in this repo instead of only existing in an ad-hoc build folder, so rebuilding the distributable pack no longer depends on that folder still being around"},
        ],
    },
    {
        "version": "2.27.3",
        "date": "2026-07-06",
        "entries": [
            {"type": "fix", "text": "**`setup_users.py` had no way to create the first admin account.** It always created accounts as role `user` (the default on `create_user()`), so a brand-new install — including from the installer pack — had no login that could reach the User Management screen without hand-editing `auth/users.json`. On a fresh install (no accounts yet), the very first account created is now automatically made admin; every account after that still defaults to a regular user as before"},
        ],
    },
    {
        "version": "2.27.2",
        "date": "2026-07-04",
        "entries": [
            {"type": "docs", "text": "**Sky East User Guide: added a \"Buy Plan Only Accounts\" section** (all three versions — bilingual, English, Chinese) covering the restricted role's actual screen: one \"Sky East\" tab, only New Contracts + 📦 Generate / Export sub-tabs, and Generate / Export going straight to Buy Plan + 核料 with no mode picker. A callout near the top now points readers to the right section for their account type"},
            {"type": "fix", "text": "**Sky East User Guide's own Step 4 was out of date** — it claimed the New Contracts \"Process\" button generates the Buy Plan/核料 workbooks directly. That moved to a separate 📦 Generate / Export sub-tab a few releases ago; the button is now named **Process Sky East Files** and only saves the contract. Corrected the button name and the description in all three guide versions and pointed readers to Generate / Export for the actual output step"},
        ],
    },
    {
        "version": "2.27.1",
        "date": "2026-07-04",
        "entries": [
            {"type": "docs", "text": "Added `docs/DEPLOYMENT.md` — a runbook for installing the app as a persistent Windows Service (NSSM: auto-start on boot, auto-restart on crash, rotated logs) instead of running it manually in a terminal. Covers getting the code onto a server, the Python/venv setup, first-run licensing and user setup, the firewall rule, a post-deploy verification checklist, and the update/rollback procedure"},
        ],
    },
    {
        "version": "2.27.0",
        "date": "2026-07-04",
        "entries": [
            {"type": "feat", "text": "**Tracking → Add New can now track Sky East orders, not just GIII.** The untracked-PO picker only ever queried the GIII pipeline's tables, so a Sky East order could never be offered no matter which company you had access to. It now also pulls from Sky East's item table, and a new **Client** filter appears whenever more than one client has untracked orders, so a mixed list doesn't get unwieldy"},
            {"type": "fix", "text": "The 🏭 Tracking sub-tab labels (Dashboard/Overview/Edit Record/Add New/Plan) didn't translate under the Chinese UI — they're rendered via a radio's `format_func`, which the i18n coverage audit couldn't see since the string isn't a literal argument to `t()`. Added their translations explicitly"},
        ],
    },
    {
        "version": "2.26.5",
        "date": "2026-07-03",
        "entries": [
            {"type": "feat", "text": "**Every menu, tab, and admin screen now has full Chinese coverage.** Reference Data, GIII, Sky East, Summary, Tracking, Colors, Fabric DB, and every Admin sub-tab (Users, Companies, Templates, Pipeline Layouts, Size Order, Email, Translations, Settings) — plus the top navigation bar, sidebar, and login form — are wrapped for translation; **793 new Chinese translations** were added so switching to 中文 (🌐) actually shows Chinese everywhere instead of leaving most of the app in English. File names stay English as before"},
            {"type": "fix", "text": "**Tracking → Add New crashed with `UnboundLocalError: cannot access local variable 't'`.** A `for t in targets:` loop inside `_render_add_tab` shadowed the module's `t()` translator for the whole function — Python treats a name assigned anywhere in a function as local throughout, so the `t(\"Overall Notes\")` call earlier in the same function broke every time the tab was opened. Renamed the loop variable and swept the entire codebase for the same hazard (none remain)"},
        ],
    },
    {
        "version": "2.26.4",
        "date": "2026-07-03",
        "entries": [
            {"type": "refactor", "text": "**Chinese-UI coverage sweep.** Tab-bar menus and section headers across the GIII, Sky East, Order Summary, GIII Generate/Export, and admin Translations views are now t()-wrapped, so their tab labels, subheaders, captions, buttons, and status messages translate under the Chinese UI. Radio/selectbox option values compared or stored in code stay English; only their labels are wrapped"},
        ],
    },
    {
        "version": "2.26.3",
        "date": "2026-07-03",
        "entries": [
            {"type": "fix", "text": "**Parser accuracy batch.** Whole-number discounts are no longer 10× smaller (\"1.5%\" became \"0.1.5%\"); multi-word countries/ports survive (\"Sri Lanka\", \"Ho Chi Minh\" were truncated to their first word); 13-digit EAN barcodes and quantities with thousands separators no longer silently drop their size rows; the AI (DeepSeek) parser asks for and stores the real per-row colour instead of filling every row with the division code; the EAN lookup warns loudly when it falls back to fixed column positions"},
            {"type": "fix", "text": "**Price masking is trustworthy again.** Masked `.xlsm` files keep their macros (previously re-packaged as plain xlsx under the .xlsm name — Excel refused to open them), legacy `.xls` fails with a clear message instead of vanishing, and every masking failure now shows in the processing log / on screen instead of a console print nobody sees — a file can no longer silently go missing from the masked zip"},
            {"type": "fix", "text": "**Colors tab: deleting the right rows, keeping manual shades.** The 🗑 delete checkbox now pairs each row with its database id (removing a row inline used to shift every row down and delete the wrong record), and re-importing a 大货进度表 no longer blanks a manually set light/dark shade the keyword classifier can't derive"},
            {"type": "fix", "text": "**Extraction tabs can't serve stale results.** All four fax/portal sections (MSG · KL · TK EU · InforNexus) now tie their results to the uploaded file set — swapping files without re-extracting drops the old table and its download instead of silently offering the previous batch. FOB values that aren't clean numbers degrade gracefully in the summary sheets instead of crashing the export, and non-price FOBs no longer display as \"$NOT CONFIRMED\"/\"$?\""},
            {"type": "fix", "text": "Concurrent-use hardening: simultaneous saves of the same PO serialize (no more lost archive rows / duplicate history), first-run schema migrations tolerate two sessions racing (`duplicate column` crash), buy-plan sheets whose styles collide at 31 chars no longer swap photos, cross-check totals find the Total header on any row (configurable templates read 0 before), production-plan styles containing `/` export instead of crashing, and blank-colour size rows are counted instead of dropped"},
            {"type": "security", "text": "The admin Email panel no longer round-trips the stored SMTP password into the browser on every render (leave blank to keep it), sign-in timing no longer reveals whether a username exists, and the sole remaining admin can no longer demote themselves into a lockout"},
            {"type": "perf", "text": "The styled PO-Tracker workbook is cached instead of being rebuilt on every filter click (Summary tab and GIII Generate/Export)"},
            {"type": "refactor", "text": "**Convention sweep:** GIII extraction sections + Tracking/Summary views now use SK session-key constants (state resets properly on sign-out), user-facing text is t()/_th()-wrapped for the Chinese UI, and every DB-driven multiselect uses the seed-once + stale-value-guard idiom (`guard_multiselect_state` in ui/shared.py) instead of the banned key=+default= pattern"},
        ],
    },
    {
        "version": "2.26.2",
        "date": "2026-07-03",
        "entries": [
            {"type": "fix", "text": "**Fabric DB auto-migration actually runs now.** A fresh deployment silently got an *empty* fabric master (blank 综合key/composition in every buy plan): the store's own schema migrations stamped the same `user_version` values the factory used as its \"legacy copy done\" marker, so the copy from `po_history.db` was unreachable. The marker now uses a dedicated bit; locked by a new regression test"},
            {"type": "fix", "text": "**Photo injection can no longer delete a finished buy plan.** When no sheet matched the photo map (e.g. every photo style contained `&` — sheet titles were compared XML-escaped), the injector removed the export before discovering there was nothing to move. Titles are now unescaped and the workbook is only replaced when the patched copy exists"},
            {"type": "fix", "text": "**核料 colour column no longer misdetected.** An always-true guard (string-vs-int comparison) overrode a correctly detected 颜色/Color header with the leftmost other column whenever the size-header row contained any extra label (e.g. 合计)"},
            {"type": "fix", "text": "**Sky East contracts missing an optional header row (e.g. Trade Term) no longer fail entirely** with a cryptic `'trade_term'` error — absent fields default to blank and the file's items import normally (parse confidence drops as before)"},
            {"type": "fix", "text": "**Sky East style photos are read from the actual contract sheet.** Image positions were always taken from sheet 1 even when the contract was found on a later sheet, attaching wrong or missing photos"},
            {"type": "fix", "text": "**KL/MSG extraction: HTS codes with repeated digits are no longer corrupted** (6110.20.2079 became 610.20.2079). De-doubling is now applied only when the match is genuinely fax-doubled (doubled dots)"},
        ],
    },
    {
        "version": "2.26.1",
        "date": "2026-07-03",
        "entries": [
            {"type": "security", "text": "**A non-admin with no assigned companies now sees nothing instead of everything.** The Summary tab, GIII PO History, GIII Generate/Export, and the GIII exception badge passed an empty company list through to an *unfiltered* query (the stores treat an empty list as \"no filter\"), so a freshly created user saw every company's POs including unit/extended costs. All four now show the same \"No companies assigned\" notice the Tracking tab already used"},
            {"type": "security", "text": "**Failed sign-ins are now rate-limited.** 5 wrong passwords for a username lock it out for 60 s with exponential backoff (cap 15 min), plus a global brake against username spraying — previously unlimited guesses were possible against the network-reachable login"},
            {"type": "fix", "text": "**Tracking → Edit Record: Delete no longer throws a StreamlitAPIException.** Confirm Delete assigned to the record selectbox's own session key after the widget was rendered (forbidden by Streamlit) — the record *was* deleted, but the error screen replaced the success message. The selection now reconciles automatically and a proper \"Record deleted.\" confirmation shows after the rerun"},
        ],
    },
    {
        "version": "2.26.0",
        "date": "2026-07-03",
        "entries": [
            {"type": "feat", "text": "**Tracking: lab-dip gates for bulk purchasing.** Trim Layout must now be confirmed before Trim Purchase, and Fabric Color (LD) before Fabric Purchase — both gates are ON by default (new *and* existing records) and editable per record in the dependency matrix. Trim Purchase and Fabric Purchase show a readiness badge in the Edit form (✅ Ready / ⏳ Waiting on …), and Group A stages are re-ordered so each confirmation stage sits directly above the purchase it gates"},
            {"type": "perf", "text": "**Faster tab renders on SQLite-heavy screens.** `PRAGMA journal_mode=WAL` (a persisted DB property) now runs once per database file per process instead of on every connection (≈5× a bare connect); the Production Tracking store's schema check is likewise memoized per process, and the store instance is cached via `functools.cache` in `ui/stores.py` — reads still open fresh connections, so data freshness is unchanged"},
            {"type": "refactor", "text": "The AS400 fax-copy parser helpers (`_undouble`, size-code regexes, line-item patterns) previously copy-pasted in the MSG, KL, and TK EU extractors now live once in `ui/giii/_shared.py`; header-field parsing runs each `grep` once instead of twice per field"},
            {"type": "fix", "text": "**MSG extraction: FOB price is now read only from the FOB line** — previously the first doubled `$$` amount anywhere in the PO could be picked up (e.g. an MSRP), and the UNCONFIRMED check now takes priority. InforNexus PO-number fallback no longer uses a redundant `O` in its letter-to-zero substitution"},
            {"type": "security", "text": "`auth/users.json` and `data/fabric_master.db` are no longer tracked by git (local files kept; both added to `.gitignore` along with the fabric DB's WAL/journal side-files and `data/extracted_images/`)"},
        ],
    },
    {
        "version": "2.25.0",
        "date": "2026-07-03",
        "entries": [
            {"type": "feat", "text": "**Per-user tab restrictions.** Admin → Users now has an **Allowed tabs** picker (leave empty = all tabs, same convention as Allowed companies). A new **\"Sky East — Buy Plan only\"** option narrows a user's entire app down to Upload + Generate/Export, pinned to Buy Plan + 核料 mode — Contract History, Missing Fields, Item Data, Wash Labels, and every other top-level tab (GIII, Fabric DB, Reference Data, Colors, Summary, Tracking) stay hidden for that user"},
        ],
    },
    {
        "version": "2.24.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Memory management** to keep RAM and disk bounded (`ui/memory.py`). Automatic: the persistent `extracted_images` folder is pruned to a file-count + total-size cap (oldest first) after each processing run, and the in-memory style-photo cache is trimmed to a cap after processing / buy-plan generation (safe — misses reload from disk). Manual: a new sidebar **🧹 Memory (~N MB)** control shows the approximate size of held blobs (cached downloads + photo cache) and a **Free memory now** button that drops them and clears the AI colour caches without signing out"},
        ],
    },
    {
        "version": "2.23.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Style photos now survive restarts.** Images extracted from Sky East source spreadsheets are saved to a persistent `data/extracted_images` folder (as well as your configured image folder), and the buy-plan generator falls back to it when a photo isn't in the primary folder. Previously extracted images lived only in memory + the configured folder, so a server restart (or a changed/emptied folder) left the buy plan with no pictures until you re-processed"},
            {"type": "feat", "text": "**The buy plan now warns exactly which styles have no photo** — e.g. \"🖼 3 style(s) have no photo in the buy plan: DR5124, DR4578, …\" — instead of silently shipping an image-less workbook, with a hint to re-run Process or drop a `<style>_front.png` into the image folder"},
        ],
    },
    {
        "version": "2.22.2",
        "date": "2026-07-02",
        "entries": [
            {"type": "fix", "text": "**The colour-resolution issues log no longer shows the same miss over and over.** The log is append-only (a fresh row per generation run), so re-running the buy plan stacked identical rows — e.g. DR5124 \"(dark blue)\"→Navy appeared once per run. The table now shows one row per distinct miss (same PC · contract · style · PO · colour · source), keeping the most recent timestamp; the \"N unresolved colour(s)\" counts reflect the de-duplicated total. The underlying log stays a full audit trail, and 🗑️ Clear still wipes it"},
        ],
    },
    {
        "version": "2.22.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Tracking → Edit Record is no longer a ~40-row wall.** Stage groups A (Pre-Production), C (Production), and D (Post-Production) are now collapsible panels whose labels carry a live done-count (e.g. \"🧵 Group A — Pre-Production · 5/8 ✅\"); fully-completed groups collapse automatically so the form stays focused on stages that still need work (values in collapsed groups are still saved). Group B keeps its heading (it hosts the Optional Samples panel, which can't nest) but shows the same done-count. A one-line legend above the groups explains what A/B/C/D mean"},
        ],
    },
    {
        "version": "2.22.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Sky East Generate / Export is now one flat screen.** The three sub-tabs (Buy Plan + 核料 · Item Data · Wash Labels) are replaced by a single \"What do you want to generate?\" selector, and ONE shared PC-No. selector serves every output type — switching between buy plan, item downloads, and wash labels no longer loses your PC selection or requires re-picking it three times. Wash Labels keeps its own \"Select by\" modes (PC No. / Style / Upload); when a non-PC mode is chosen a caption clarifies the shared PC selection isn't used. A selection made under the old sub-tabs is migrated automatically"},
        ],
    },
    {
        "version": "2.21.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Processing logs can no longer hide failures.** The GIII and Sky East \"Processing log\" expanders now auto-open with an issue count in the label (e.g. \"Processing log (2 ⚠️)\") whenever any log line carries an error/warning marker — a run with problems no longer looks identical to a clean one. Shared helper `show_processing_log()` in `ui/shared.py`"},
            {"type": "feat", "text": "**GIII's \"📊 Reports\" sub-tab is renamed \"📦 Generate / Export\"** to match Sky East (both regenerate downloadable files from stored data), and the 📦 emoji now consistently means output while 📤 stays reserved for uploads. GIII/Sky East sub-tab labels are wrapped in `t()` so the 🌐 Chinese toggle can translate the navigation"},
            {"type": "fix", "text": "**Chinese-mode i18n gaps closed** in the Sky East results screen (Processing Results, New/Amended item headings, style-photo captions), the buy-plan panel's newer strings (hand-off, pre-flight fabric-code note, colour source/recognition mode line, cross-comparison hints, 大货进度表 status), and the Tracking QC labels — all now wrapped in `t()` with English fallback"},
            {"type": "fix", "text": "**Consistent thousands separators** on Tracking dashboard and Colors tab metrics; Tracking's Edit Record selector now shows how many records it holds"},
            {"type": "fix", "text": "**Large import changesets are no longer invisible**: the Reference Data diff panels keep auto-collapsing above 30 changes, but the label now carries the full field-change count plus a visible \"open to review all N changes\" caption. The Colors audit-log clear now uses a persistent two-step confirm — the button changes to \"Confirm clear (N entries)\" with a Cancel option, instead of a transient warning that silently stayed armed"},
            {"type": "feat", "text": "**\"What lives where\" captions** on the three reference-data tabs (🧵 Fabric DB · 📐 Reference Data · 🎨 Colors) so it's clear which tab holds fabric properties vs style→fabric assignments vs colour translations"},
        ],
    },
    {
        "version": "2.20.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**The \"Generating…\" box now states which colour source and recognition mode the run is using** — e.g. \"🎨 Colour source: **大货进度表** · Recognition: **Local + AI Enhance**\" (or \"Local only\", or a warning if AI Enhance is on but no API key is configured) — so it's clear at a glance whether the AI fallback is active"},
            {"type": "feat", "text": "**Renamed the Sky East \"📊 Reports\" tab to \"📤 Generate / Export\" and moved it to second position** (right after New Contracts), so the primary output step reads as an action and follows the natural Upload → Generate flow instead of being buried after Contract History"},
        ],
    },
    {
        "version": "2.20.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**Sky East ease-of-use pass.** After processing new contracts, a clear \"✅ Saved N PC No.(s) — next step: 📊 Reports → Buy Plan + 核料\" hand-off now points users to the generation step (previously it wasn't obvious that generation lived in a different tab)"},
            {"type": "feat", "text": "**Exporter diagnostics now surface in the UI, not just the server log.** Missing fabric-master HHN codes and the 主标颜色 mismatch/missing warnings are captured during generation and shown as ⚠️ warnings under the buy plan. The buy-plan download caption now reads \"⚠️ N unresolved colour(s)\" when colours failed to resolve, so a green download button can't hide misses"},
            {"type": "feat", "text": "**Pre-flight fabric-code check.** Before you generate, the Buy Plan panel now flags styles with no fabric code (accounting for saved fabric mappings) — \"N style(s) have no fabric code — 核料 will skip them\" — so 核料 gaps are caught up-front instead of being discovered as a silent omission"},
            {"type": "feat", "text": "**Cross-comparison mismatches are now actionable** — when buy-plan and 核料 totals disagree, the UI names the styles that produced no 核料 output (the usual \"no fabric code\" cause) and points at where to fix them"},
            {"type": "fix", "text": "**Clarified the misleading \"Total Styles\" metric.** It counted style·colour combinations, not distinct styles. The Buy Plan panel now shows both **Styles** (distinct style numbers) and **Style·Colours** (combos) with tooltips, and the Contract History summary column is renamed to **Style·Colours**"},
            {"type": "fix", "text": "**Buy-plan / 核料 filenames now carry a date-time stamp** (e.g. `SkyEast_..._BuyPlan_20260702-1530.xlsx`) so regenerating doesn't silently overwrite the previous download. Also clarified that the New Contracts colour-source radio only sets the Buy Plan default, and that the 大货进度表 uploaded there is one-off (save it in 📐 Reference Data to reuse)"},
        ],
    },
    {
        "version": "2.19.2",
        "date": "2026-07-02",
        "entries": [
            {"type": "refactor", "text": "Removed the redundant 大货进度表 file-uploader from the Sky East Buy Plan panel. The 大货进度表 is managed centrally in **📐 Reference Data → HHN Contract Progress**, so the buy-plan panel now only reports which saved data the run will use (colour resolution already fell back to the saved data automatically — this just removes a duplicate, confusing second upload point)"},
        ],
    },
    {
        "version": "2.19.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**主标颜色 is now left genuinely blank when no label colour is on file, instead of being auto-derived.** Following on from the cross-check in v2.19.0: the light/dark heuristic is no longer used to *fill* the value at all — only to cross-check an on-file value. When neither 大货进度表 nor the internal DB has a 主标颜色 for an item, the cell stays empty (not a guessed 白色/黑色), gets a \"missing — enter manually\" comment, and the export raises an end-of-run warning listing the affected items. A guessed label can no longer be mistaken for a confirmed one"},
        ],
    },
    {
        "version": "2.19.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**主标颜色 (main label colour) is now cross-checked against the light/dark heuristic and flags disagreements.** 大货进度表's 主标颜色 is used verbatim (it was already authoritative), but the derived light/dark value is no longer just a silent fallback — it now cross-checks 大货进度表's value. When they disagree (e.g. 大货进度表 records 白色 for a \"Navy\" body colour, which the heuristic reads as 黑色), 大货进度表's value is kept but the cell gets a diagnostic comment and the export raises an end-of-run warning listing every mismatch, so a data-entry slip in 大货进度表 surfaces for review instead of shipping unnoticed. The heuristic is still used only as a last-resort fill when neither 大货进度表 nor the internal DB has a label colour"},
        ],
    },
    {
        "version": "2.18.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "feat", "text": "**核料 (Template_P) size columns now follow the order's actual size range instead of the template's fixed header.** The shipped Template_P header only defines S/M/L/XL, so any XS or XXL/2XL quantities were silently dropped from the 核料 workbooks. The size columns are now laid out from the sizes that actually appear in the order (canonical XS→XXL order, anchored at the template's first size column): a size the order uses always gets a column, and a size it never uses isn't shown as an empty column (and leaves no orphaned L/XL header). An explicit `size_column_map` in `Sky_East_P_config.json` still wins for admins who pin columns"},
        ],
    },
    {
        "version": "2.17.1",
        "date": "2026-07-02",
        "entries": [
            {"type": "refactor", "text": "Decomposed the 631-line `export_sky_east_buyplan` (down to 365 lines) into focused, unit-testable module-level helpers: `_prefetch_boat_sample_cache`, `_prefetch_fabric_master_cache` + a `_FabricMasterCache` class (the old nested `_display_key_for` closure is now a method), `_fill_fabric_header`, and `_fill_one_style_row` (the per-row writer, threaded via a `_RowContext`). Behaviour is unchanged — the produced workbooks are identical. Replaced the `from _sky_east_helpers import *` wildcard (a documented `NameError` footgun) with an explicit 23-name import. 13 new fast unit tests exercise the extracted helpers directly, without generating a whole workbook"},
        ],
    },
    {
        "version": "2.17.0",
        "date": "2026-07-02",
        "entries": [
            {"type": "fix", "text": "**核料 (Template_P) workbooks now flag unresolved colours the same way the buy plan does.** Previously a colour that failed to resolve was written into the 核料 label as e.g. `Black(未找到)`, with no entry in the colour-resolution log — so a mismatch that was loud in the buy plan was silent (and messy) in 核料. Now the cell shows the English colour alone, carries a diagnostic comment (client's PO colour + 大货进度表's own colour on file), and is recorded in the colour-miss log, mirroring the main buy plan"},
            {"type": "fix", "text": "**核料 workbooks are no longer produced with a malformed stylesheet.** The per-fabric copy used `copy.deepcopy()`, which yielded a workbook whose saved stylesheet referenced a non-existent font — openpyxl (and Excel's repair check) rejected it on reload. It now re-opens the template from an in-memory buffer instead: clean, reloadable output, still no disk re-read, ~1 ms/fabric slower"},
            {"type": "refactor", "text": "De-duplicated the ~19-line \"Local + AI Enhance\" settings auto-fetch that was copy-pasted across both Sky East exporters into one `_resolve_ai_enhance_settings()` helper; de-magic'd the hardcoded 船样要求 column (now resolved from the detected template layout, falling back to column P). Fixed the `export_sky_east_buyplan` docstring, which claimed it returns a path when it returns a `(path, style_totals)` tuple"},
        ],
    },
    {
        "version": "2.16.5",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Local + AI Enhance colour matching returned no match for genuinely correctable cases (e.g. \"dark brown\" vs 大货进度表's \"Dk Brown\") when the `deepseek-reasoner` model was selected.** `deepseek-reasoner` spends part of its `max_tokens` budget on a hidden reasoning trace before writing the visible answer — the 64/128-token budget sized for a short chat-model answer was being fully consumed by reasoning, truncating the response (`finish_reason: \"length\"`, empty content) before any JSON answer was written. Confirmed live: a 64-token budget produced empty content with all 64 tokens spent on reasoning, while 1024 completed normally with the correct answer. New `max_tokens_for()` in `po_extractor/utils/deepseek_client.py` raises the floor to 1024 for reasoning models at both `color_ai_enhance.py` call sites"},
        ],
    },
    {
        "version": "2.16.4",
        "date": "2026-07-01",
        "entries": [
            {"type": "security", "text": "**Local + AI Enhance was silently matching genuinely different colours as if they were the same** — the AI prompt explicitly told the model to \"treat synonyms as the same (e.g. 'Navy' = 'Dark Blue')\", so a client's \"Dark Blue\" order line got assigned 大货进度表's \"Navy\" colour code, a wrong result presented as a confident match. Rewrote the prompt to allow ONLY spelling/formatting variants of the identical name — typos (\"Daek Blue\" → \"Dark Blue\"), abbreviations of the same name (\"DK Brown\" → \"Dark Brown\"), and formatting differences (case, spacing, a numeric code prefix) — while explicitly forbidding matches across different colour names (Navy/Dark Blue, Cream/White, etc.) even when related or visually similar. An honest 未找到 is safer than a wrong colour code silently assigned to an order"},
            {"type": "docs", "text": "Renamed/reworked the misleading `test_match_color_to_candidates_picks_synonym` test to test the actually-intended typo-correction case, and added a regression guard directly on the prompt text so the old \"treat synonyms as the same\" instruction can't silently come back"},
        ],
    },
    {
        "version": "2.16.3",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**AI Extraction / Local + AI Enhance failed silently whenever the DeepSeek `deepseek-reasoner` model was selected.** Every DeepSeek call (PO PDF extraction, the admin \"Test API key\" button, and colour recognition/matching) unconditionally sent `temperature=0`, but `deepseek-reasoner` rejects that parameter — the call errors out, and the error was swallowed and treated as a plain \"no result\". New shared `po_extractor/utils/deepseek_client.py` (`chat_kwargs()`) omits `temperature` for reasoning models across all three call sites"},
            {"type": "fix", "text": "**A failed AI-enhance colour lookup was being cached forever.** `recognize_colors()`/`match_color_to_candidates()` cached *every* outcome, including API errors and \"no match\" answers — so a colour that failed once (e.g. due to the reasoner-model bug above, or a missing key at the time) stayed stuck at 未找到 for the rest of the server's uptime even after the underlying problem was fixed, since it was never retried. Only genuine successes are cached now; a failure is retried on the next generation"},
            {"type": "docs", "text": "8 new tests: the shared `chat_kwargs()`/`is_reasoning_model()` helpers, that `recognize_colors()`/`match_color_to_candidates()`/`_call_deepseek()` all omit `temperature` for `deepseek-reasoner`, and that a transient failure in either colour-AI function doesn't block a subsequent retry"},
        ],
    },
    {
        "version": "2.16.2",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**DeepSeek AI Extraction / Local + AI Enhance were both broken** — the `openai` package (the OpenAI-compatible client both features use to call DeepSeek) was never added to `requirements.txt`/`requirements.lock` and wasn't installed, so \"Test API key\" failed with `No module named 'openai'` regardless of a valid key. Installed the package and pinned it (and its transitive dependencies: httpx, pydantic, distro, jiter, etc.) in both requirement files so a fresh environment install includes it"},
        ],
    },
    {
        "version": "2.16.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Colour resolution issues log now also shows 大货进度表's own colour(s)**, alongside the client's PO colour — the same comparison already shown in the Excel cell comment, now visible in the reviewable table too without opening the buy plan"},
            {"type": "docs", "text": "New `progress_colors` column on `sky_east_color_misses`, with an ALTER TABLE migration for existing databases (older rows show blank, never crash or drop data). 6 new tests: storing/joining/blanking progress_colors, the migration path against a pre-existing DB, and an end-to-end naming-mismatch check"},
        ],
    },
    {
        "version": "2.16.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**\"Local + AI Enhance\" now bridges colour-name mismatches between the order file and 大货进度表.** When an exact (客人PC NO · 款式 · 英文颜色) match misses but that PC No. + style *does* have colour(s) on file, the API is asked to pick which of those **actual recorded colours** the client's colour refers to — resolving the common cases where the two files simply spell the same colour differently: synonyms (order says \"Dark Blue\", 大货进度表 says \"Navy\"), abbreviations (\"Dark Brown\" vs \"DK Brown\"), and outright typos (\"Daek Blue\"). The API only ever picks among colours already on file (its answer is validated against the candidate list), so the Chinese name/code still come from the trusted 大货进度表 — a wrong pick can at worst surface the wrong existing row, never fabricate data. Only runs when Local + AI Enhance is enabled and only on a genuine miss; cached per (colour, candidate-set) so a repeated question costs one API call. **Local-only mode is unchanged — these still show 未找到** with the diagnostic comment listing 大货进度表's own colour(s)"},
            {"type": "docs", "text": "New `match_color_to_candidates()` in `color_ai_enhance.py`, tried before the existing open-ended `recognize_colors()` fallback inside `_ai_retry_component`. 10 new tests: the matcher itself (synonym pick, hallucination rejected, empty/no-candidate/error paths, caching) and end-to-end resolution of a \"(dark blue)\"→\"Navy\" mismatch through the Overview sheet"},
        ],
    },
    {
        "version": "2.15.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "Reverted the brief v2.15.0 \"客户PO + style\" lookup tier — it matched on the wrong 大货进度表 column (a separate \"PO#\" field) instead of 客人PC NO. Confirmed the correct, already-existing join key is **客人PC NO + 款式 + 英文颜色 — an exact match with no fallback tier**, which is exactly how `build_pc_style_color_lookups()` already worked before v2.15.0. No behaviour change from v2.14.1"},
        ],
    },
    {
        "version": "2.14.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**未找到 cell comments now also show 大货进度表's own colour(s) for that PC No./Style**, alongside the client's PO colour already shown — so a naming mismatch (e.g. client says \"Dark Brown\", 大货进度表 says \"Chocolate\") is visible at a glance instead of requiring the source file to be reopened. When 大货进度表 has no colour recorded at all for that PC/Style, the comment says so explicitly. When the internal DB (not 大货进度表) is the selected source, the extra line is omitted — that source was never consulted, so there's nothing to compare"},
            {"type": "docs", "text": "New shared `_color_miss_comment_text()` / `_available_progress_colors()` helpers (single source of truth for the per-style-sheet and Overview-sheet comments). 8 new tests covering both helpers directly plus end-to-end naming-mismatch and internal-DB-source cases"},
        ],
    },
    {
        "version": "2.14.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Index sheet now includes 客人PC NO**, right after 款号 (and 图片, if photos are enabled) — mirrors the same column already added to the Overview sheet, so the PC No. used for every 大货进度表 lookup is visible without switching tabs"},
            {"type": "docs", "text": "1 new test locking in the column's presence, position, and value on the Index sheet"},
        ],
    },
    {
        "version": "2.13.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Style hyperlinks in the buy plan (Index and Overview sheets) didn't work in WPS Office.** They were written as `cell.hyperlink = \"#'Sheet'!A1\"` — a plain string, which openpyxl always saves as an *external* relationship (`TargetMode=\"External\"`) whose literal target is that `\"#...\"` text. Excel has an undocumented leniency that follows a `\"#\"`-prefixed external target as an internal jump anyway, but that's Excel-specific, not part of the OOXML spec — WPS (and other readers) take the target literally, so the link silently did nothing. Fixed by writing the link's `location` attribute directly instead (`Hyperlink(location=\"'Sheet'!A1\", target=None)`), the spec-correct way to express a same-workbook link with no relationship at all — works the same in Excel and is now portable to WPS/LibreOffice/etc. Affects the Sky East buy plan (Index + Overview) and the HHP/Zalando buy plan Index sheet — all three shared the same pattern"},
            {"type": "docs", "text": "New shared `set_internal_hyperlink()` helper in `_excel_helpers.py` (single source of truth for all 3 call sites, was previously duplicated). 6 new tests: unit tests for the helper (location vs target, round-trips through a real save/load with zero relationships written, custom anchor, doesn't clobber an existing cell value) plus updated Index/Overview hyperlink-shape assertions"},
        ],
    },
    {
        "version": "2.13.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**找不到的颜色 (未找到) now carry a diagnostic comment showing the client's PO colour.** Every 未找到 cell in the Overview sheet and per-style sheets gets an Excel cell comment with the raw colour text exactly as the client's order file had it — before bracket-stripping or multi-colour splitting — so a reviewer can see what was actually searched for without reopening the source order file"},
            {"type": "feat", "text": "**New Sky East colour-resolution error log.** Every colour miss during buy plan generation is now recorded (PC No., Contract No., Style, PO No., client's PO colour, source) in a dedicated log — separate from the GIII PDF-parsing Exception Queue, since it's a different kind of failure. A new **Colour resolution issues** panel appears under Sky East → Contract History after generating a buy plan whenever any misses were logged, with a table and a clear-log button"},
            {"type": "docs", "text": "11 new tests: SkyEastStore.log_color_miss()/list_color_misses()/clear_color_misses() unit tests, plus end-to-end checks that a 未找到 cell gets the comment (and a resolved one doesn't), that a miss is logged with the correct raw client colour, and that passing sky_east_store=None disables logging without affecting the export itself"},
        ],
    },
    {
        "version": "2.12.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Two-tone order-file colours now show BOTH Chinese names/codes, not just one.** A colour like \"Dark Blue / White\" used to display only whichever component happened to resolve first (e.g. \"藏青\" alone) — it now combines every component that resolves into one string, e.g. \"藏青 / 白色\" and \"52# / 3#\", matching the already-combined \"Dark Blue / White\" shown in Color (EN). A component that still can't be matched (even after AI Enhance) is silently omitted from the combination rather than blanking the whole result. \"Local + AI Enhance\" retries are now attempted per component, not just once against the full combined string, so a two-tone item with one missing colour can recover just that one"},
            {"type": "feat", "text": "**Overview sheet gains 客人PC NO and 主标颜色 columns.** 客人PC NO sits right next to Contract No. (the PC No. used for all 大货进度表 lookups, previously visible only via the underlying data, never in the sheet itself); 主标颜色 sits next to Color Code, mirroring the column that was already present on every per-style sheet but missing from the flat cross-check table"},
            {"type": "docs", "text": "6 new tests: combined-both-components resolution, label-colour passthrough when combining, AI-enhance recovering just the missing half of a two-tone pair, and end-to-end Overview checks for the combined Chinese names and the two new columns"},
        ],
    },
    {
        "version": "2.11.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**New optional \"Local + AI Enhance\" colour recognition mode.** When a Sky East order-file colour still fails to resolve locally (against the selected 大货进度表/internal-DB source) even after the multi-colour split, the DeepSeek API can now be asked to recognize the colour name(s) so a second local-lookup attempt can succeed — the API never supplies the Chinese translation or code itself, so a bad AI guess can only fail to help, never inject wrong data. The API is called **only** on a genuine colour-lookup miss, is never used for anything else (dates, quantities, other fields), and results are cached per raw colour string for the session so a repeated colour across many rows only costs one API call. Reuses the existing DeepSeek API key/model already configured for AI PO extraction — no new credential to manage"},
            {"type": "feat", "text": "New **Admin Settings → 🎨 Colour Recognition — Local + AI Enhance** toggle: **Local only** (default, no network calls) vs **Local + AI Enhance**"},
            {"type": "docs", "text": "10 new tests: `recognize_colors()` unit tests (success, cache hit, API error, malformed JSON, missing key/input) and `_resolve_pc_color_multi` AI-enhance wiring tests (disabled mode never calls the API, a local hit never calls the API, a local miss calls the API exactly once with the raw combined string, an API miss still falls back to the not-found result)"},
        ],
    },
    {
        "version": "2.10.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Order-file multi-colour cells now use the same detect-and-separate logic as 大货进度表.** A two-tone item like `\"(dark blue)(white)\"` used to become one combined `\"Dark Blue / White\"` lookup key that could never exact-match either 大货进度表 or the internal colour DB (both store single-colour keys), silently showing 未找到/blank even when one of the two colours was mapped. The buy plan and 核料 exporters now try each colour component individually and use the first one that resolves — the combined display string is unchanged, only the lookup behaviour is smarter"},
            {"type": "docs", "text": "6 new tests covering the multi-colour resolver directly (single-colour passthrough, first-component match, second-component fallback, neither-matches) plus an end-to-end Overview-sheet check for a `\"(dark blue)(white)\"` order-file cell"},
        ],
    },
    {
        "version": "2.9.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**大货进度表 multi-colour rows are now split and independently look-up-able.** A two-tone style's colour code cell (e.g. `52#/白色 3#` for a Dark Blue/White style) used to leave the second colour's code unreachable — an order-file item coloured \"White\" could never match it. Each colour in a two-tone row now becomes its own record (same PC No./Style/contract, distinct colour), so both `get_contract_no()`/`get_color_code()`/etc. and the persisted 大货进度表 store resolve either colour correctly. When the second colour has no isolable English name (an accent/trim colour rather than a second body colour, e.g. \"BLACK WITH WHITE STRAP...\"), its Chinese name and code are still captured, just not matchable by English name alone"},
            {"type": "fix", "text": "The 色汇总 (colour summary) column was never being detected — its real header wraps onto two lines (`颜色汇总\\n英文 中文 色号 色卡本`), which didn't match any alias exactly. Header matching now collapses embedded newlines/whitespace before comparing, and the exact real-world header text was added as an alias"},
            {"type": "docs", "text": "5 new tests covering the multi-colour split (both a clean two-tone case and a headerless-accent-colour case), a normal single-colour row staying untouched, and end-to-end resolution through both `ProgressLookup` and the persisted DB store"},
        ],
    },
    {
        "version": "2.8.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Top navigation tab renamed **📐 Fabric Mapping** → **📐 Reference Data**, since it now holds two distinct sub-sections (Style-Fabric Mapping and HHN Contract Progress) that \"Fabric Mapping\" alone no longer described. All in-app hints pointing to this tab updated to match"},
            {"type": "feat", "text": "**HHN Contract Progress** preview table now shows the Chinese colour name (中文颜色), colour code (中文颜色代码), label colour (主标颜色), ex-factory date, and quantity for every record — not just PC No. / Style / English colour / Contract No. — so a mismatch is visible directly in the preview instead of requiring a full import first"},
        ],
    },
    {
        "version": "2.8.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**Wash Label export was crashing** — `po_extractor/ui_helpers/wash_label.py` referenced `pd.NA` without ever importing pandas, so `write_wash_label_excel()` raised `NameError` any time it ran against real style data. Added the missing import; wash label generation now works"},
            {"type": "fix", "text": "Test suite cleanup: fixed 2 long-stale `test_store_factories.py` tests that assumed `fabric_master` shares `po_history.db` — it's intentionally a separate database file (`FABRIC_DB_PATH`) per the documented data/ layout, so the canonical-path test and the `fabric_in_db` fixture were both pointed at the wrong file, silently making the fixture's test data invisible to the real code path"},
            {"type": "fix", "text": "Updated 4 stale `test_excel_reports.py` PO-summary tests written against a since-replaced simple version of `generate_po_summary_excel` (a single header row + dynamic per-input-column labels). The current exporter emits a fixed title + 12-row metadata block + fixed detail-table structure; tests now assert against that actual shape. Also surfaced that the `label_for` custom-label parameter is accepted but no longer called anywhere in the current implementation — documented as a no-op rather than silently tested as if it still worked"},
            {"type": "docs", "text": "Full test suite is green for the first time this cycle: 281 passed, 0 failed (previously 13 persistent failures across three files, unrelated to any single feature change)"},
        ],
    },
    {
        "version": "2.7.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan sheet tab names simplified to **\"<running index>_<style>\"** (e.g. `1_DR5124`, `2_DR4578`), matching the Index sheet's own \"No.\" column — the fabric/HHN code is no longer part of the tab name. A style with multiple fabric combos still gets one sheet per combo, disambiguated purely by the index (e.g. `1_DR5009`, `2_DR5009`)"},
        ],
    },
    {
        "version": "2.7.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**大货进度表 (HHN Contract Progress)** can now be uploaded once and saved permanently, the same way **📐 Fabric Mapping** already works — no more re-uploading the same progress file for every Sky East run or buy plan. New **📋 HHN Contract Progress** sub-tab lives right next to Fabric Mapping, with the same Upsert / Add new only / Replace all import modes, a New/Will Update/Already Up to Date/Skipped preview, and a field-level diff for anything that changed (合同号, colors, codes, dates, qty, and more — every column except IMAGE). Row identity is (PC No. · Style · Color), normalised so re-uploading with different casing/whitespace still matches the same saved row instead of duplicating it"},
            {"type": "feat", "text": "Sky East order processing, the Missing Fields checker, and Buy Plan generation now automatically use the saved 大货进度表 data when no file is uploaded for that specific run — an ad-hoc upload still overrides it for a one-off test, but it's no longer required every time"},
            {"type": "refactor", "text": "Extracted `parse_progress_rows()` — the 大货进度表 column-detection and row-parsing logic — out of `ProgressLookup._load()` so both the session-upload path and the new persistent-store importer share one parser; added `ProgressLookup.from_records()` to build a lookup directly from saved DB rows with no file I/O. Behavior-preserving: all 26 existing tests pass unchanged. 20 new tests across the store, parser, and diff logic"},
        ],
    },
    {
        "version": "2.6.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan Chinese-colour resolution now respects the **Chinese color mapping source** radio exclusively — when 大货进度表 is selected and a style/colour isn't in it, the internal Colors DB is no longer silently tried as a fallback (even if it happens to have a matching entry). A genuine miss now shows an explicit **未找到** (\"not found\") marker in both Color (CN) and Color Code, on the per-style sheets and the Overview sheet, so a missing translation is visible rather than looking like it quietly came from a different, unselected source. A row matched in the selected source whose code field is simply blank still shows the existing `NA` placeholder — that's a different, legitimate case from a full miss. 3 new tests"},
        ],
    },
    {
        "version": "2.5.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: some order files store the colour fully wrapped in parentheses (e.g. `(dark blue)`, or two-tone as `(black)(white)`) — this showed as `(Dark Blue)` with ugly brackets in the buy plan, and worse, silently broke every colour-name lookup against 大货进度表 / the internal colour DB (which store plain names like `Dark Blue`), so the Chinese colour name and colour code came back empty even when the DB had a matching entry. Brackets are now stripped before display and lookup — `(dark blue)` → `Dark Blue`, `(black)(white)` → `Black / White` — across both the per-style sheets and the Overview sheet. Note: if Color (CN) / Color Code are still blank after this fix, the colour genuinely has no entry (or a blank one) in the selected colour source — check the 🎨 Colors tab or the loaded 大货进度表"},
        ],
    },
    {
        "version": "2.5.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan: new **Overview** sheet, inserted right after Index — one flat row per style/PO/colour item across the *entire* workbook, for easy cross-checking without hopping between per-style tabs. Mirrors the Contract History item-browser preview (Style with a hyperlink to its sheet, Photo, Brand, PO No., Config SKU, Article Name, sizes, Ex-Fty, Fabric N / 综合标识 Key N) plus **both English and Chinese colour names side by side and the plain colour code** as separate columns. Only created when the buy plan has at least one item. Covered by 7 new tests"},
        ],
    },
    {
        "version": "2.4.2",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**HHN Contract No. (大货进度表) lookup**: a broken formula in the source file (e.g. a 中文颜色代码 VLOOKUP with no numeric code to extract, such as \"BLACK 黑色\" with nothing after it) is cached by Excel/openpyxl as the literal text `#N/A` — not blank. This was read as a real value and leaked straight into match keys and the buy plan's 中文颜色代码 cell as garbage `#N/A` text. Excel error strings (`#N/A`, `#REF!`, `#VALUE!`, `#DIV/0!`, `#NAME?`, `#NULL!`, `#NUM!`, `#SPILL!`, `#CALC!`) are now treated as blank everywhere a progress-file cell is read, so the colour name still resolves correctly and the missing code falls back to the existing `NA` placeholder instead of the raw error"},
        ],
    },
    {
        "version": "2.4.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**HHN Contract No. (大货进度表) lookup**: `ProgressLookup` required every row to have a numeric **序号** (row sequence number) as an \"is this real data\" signal — but some 大货进度表 exports never populate that column at all. Enforcing the check unconditionally silently discarded **every row in the file**, losing 合同号 (contract no.), colours, and ex-fty dates for the whole sheet with no visible error. The gate now only applies when the file actually uses 序号 as a marker (≥1 row has a numeric value); otherwise a present style number alone is enough. Covered by 2 new tests, one confirming the original protection still holds for files that do use 序号"},
        ],
    },
    {
        "version": "2.4.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**Sky East order parsing**: a row with 0 total units (a cancelled/blanked-out order line — strikethrough style, PO and price wiped, but the row left in the sheet) is now **ignored** instead of being imported as a phantom item. Each ignored row is reported in the **Processing log** with its row number, style, and PO No., so it's visible rather than silently dropped. Covered by 3 new parser tests"},
        ],
    },
    {
        "version": "2.3.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**📐 Fabric Mapping** import preview: **♻️ Will update** was flagged for any style already in the database, even when its content matched the file exactly (e.g. after a duplicate combo had already been cleaned up) — misleading, since nothing would actually change. Existing styles are now diffed up front and split into **♻️ Will update** (real content difference) vs. a new **✓ Already up to date** count; the style list and the differences expander reflect the same split"},
        ],
    },
    {
        "version": "2.3.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**📐 Fabric Mapping** tab: new **🩺 Check for duplicate fabric mapping data** section — scans all companies for a style whose fabric combo is stored identically twice under different combo numbers, and a one-click **🧹 Remove all duplicate combos** button to clean them up (only the extra copy is removed; the kept combo is untouched). Backed by two new store methods, `find_duplicate_fabric_combos()` and `delete_fabric_combo()`, covered by 7 new tests"},
            {"type": "fix", "text": "Cleaned up 2 real duplicate-combo styles found in the live database (**BL3069**, **ZLD060/S24DTR003**) — each was stored twice with byte-for-byte identical fabric data, which would have produced an extra duplicate sheet per style in the next Sky East Buy Plan export"},
        ],
    },
    {
        "version": "2.2.1",
        "date": "2026-07-01",
        "entries": [
            {"type": "fix", "text": "**📐 Fabric Mapping** diff (added in 2.2.0): a stored fabric slot missing from the uploaded file was always labeled **(slot removed)** — but `save_fabric_parts_batch()` only upserts, it never deletes, so under **Upsert** / **Add new only** that slot actually stays in the database untouched. The label now depends on the selected import mode: **(slot removed)** only under **Replace all** (which does wipe first); otherwise **(not in file — kept, not deleted)** with a note explaining Replace all is needed to actually remove it. Styles under **Add new only** now show a plain skip notice instead of a diff, since existing styles aren't touched at all in that mode"},
        ],
    },
    {
        "version": "2.2.0",
        "date": "2026-07-01",
        "entries": [
            {"type": "feat", "text": "**📐 Fabric Mapping** import preview: styles flagged **♻️ Will update** now have a field-level diff against the currently stored data — shows Stored vs. In File for each changed Body Part / HHN No. / Composition / Weight / Width, plus added or removed fabric slots. Styles whose file content is identical to what's stored are called out separately, so a 'Will update' count no longer means a guaranteed change"},
            {"type": "fix", "text": "Sky East upload page: the fabric-mapping hint pointed at a stale location (**Contract History → 🧵 Fabric Mapping**) that no longer matches the app's tab layout — corrected to the actual top-level **📐 Fabric Mapping** tab"},
        ],
    },
    {
        "version": "2.1.2",
        "date": "2026-07-01",
        "entries": [
            {"type": "docs", "text": "Added `docs/HOW_TO_START.md` — a run guide covering how to start the server (foreground / background / fully-detached), the correct Python 3.13 interpreter, health check, how to stop by PID, when a restart is needed after module changes, and troubleshooting for the app not staying up"},
        ],
    },
    {
        "version": "2.1.1",
        "date": "2026-06-19",
        "entries": [
            {"type": "perf", "text": "Sky East Buy Plan: the per-row style normalisation introduced in 2.1.0 is now memoised per distinct style within a sheet — collapsing what was one `_norm_key()` call per data row back down to one call per style (a sheet has at most a base style and its `A` variant)"},
        ],
    },
    {
        "version": "2.1.0",
        "date": "2026-06-19",
        "entries": [
            {"type": "feat", "text": "Sky East Buy Plan: a style ending in **A** (e.g. `DR5302A`) is now placed in the **same sheet** as its base style (`DR5302`) instead of getting its own tab — but only when the base style is also present in the data. Each data row keeps its own style name, so `DR5302` and `DR5302A` stay distinct in column B; the sheet's per-tab total combines both. A standalone `…A` style with no matching base is unaffected. The Buy Plan ↔ 核料 cross-comparison folds the variant onto the base style too, so the Match column stays correct"},
        ],
    },
    {
        "version": "2.0.6",
        "date": "2026-06-18",
        "entries": [
            {"type": "perf", "text": "All 8 main tabs are now wrapped in `st.fragment` — a widget interaction (typing, selecting, clicking) reruns **only its own tab** instead of all 8. Previously `st.tabs` re-executed every tab's data loads and table renders on every interaction anywhere in the app (~8× the necessary work per click)"},
            {"type": "perf", "text": "`BaseSQLiteStore._conn()` now sets `PRAGMA journal_mode=WAL` **once per database per process** instead of on every connection — WAL is a persisted DB property, so re-applying it on each query (≈5× the cost of a bare connect, ~11× per items-table build) was pure overhead"},
            {"type": "refactor", "text": "Dependencies upgraded to latest (Streamlit 1.58.0, pyarrow 24, cryptography 49, and ~24 others); `beautifulsoup4` / `ebcdic` held at the newest versions `extract-msg` (the `.msg` PO parser) supports — environment verified consistent via `pip check`"},
        ],
    },
    {
        "version": "2.0.5",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East processing: `_run_sky_east_processing` now wraps its temp directory in `try/finally` — the temp dir leaked on the early *no contracts parsed* return and on any exception during a run"},
            {"type": "fix", "text": "Sky East **Missing Fields** editor: the Save action now drops the locale-aware Photo column (`_th(\"Photo\")`) rather than the literal `\"Photo\"`, so the image column is correctly removed before saving under the Chinese UI"},
        ],
    },
    {
        "version": "2.0.4",
        "date": "2026-06-17",
        "entries": [
            {"type": "refactor", "text": "Sky East Buy Plan PC No. multiselect simplified to the same single-key pattern used by the Download / Wash Label multiselects — removed the shadow-key + pre-render-snapshot workaround. Structurally eliminates both the deselect-all bug and the stale-delete crash rather than patching them"},
        ],
    },
    {
        "version": "2.0.3",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: deleting a contract that was selected here no longer crashes the tab — a stale-value guard now cleans the multiselect's widget key before render, matching every other multiselect in the module (`reports_tab` guard fixed to clean the actual widget key, not just the logical mirror)"},
            {"type": "fix", "text": "Sky East Buy Plan: the PC No. selection can now be **fully cleared** — removed a fallback that silently re-added the last deselected PC, which made deselect-all impossible"},
            {"type": "fix", "text": "Buy Plan temp directory is now removed via `try/finally` even if brand registration or image-map building throws mid-generation"},
            {"type": "refactor", "text": "Cross-comparison mismatch count made robust to the emoji label changing in `build_cross_comparison`; removed an unused pandas import; unified download filename thresholds"},
        ],
    },
    {
        "version": "2.0.2",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: fixed a broken indentation in the **Generate Buy Plan + 核料** handler and a stale `sel` reference — the full buy-plan + 核料 generation block now runs correctly and the output filename uses the effective selection"},
        ],
    },
    {
        "version": "2.0.1",
        "date": "2026-06-17",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: initial fixes for the **Generate Buy Plan + 核料** button staying disabled after uploading 大货进度表 — handling for the multiselect session-state desync that left the selection empty"},
        ],
    },
    {
        "version": "2.0.0",
        "date": "2026-05-26",
        "entries": [
            {"type": "feat", "text": "**Production Stage Tracking** reaches its 2.0 baseline — the new 🏭 Tracking module is now a first-class part of PO Extractor (22 stages across 4 groups, dependency-driven readiness, forward-scheduling planner, and QC inspection tracking)"},
            {"type": "fix", "text": "Tracking: `list_untracked_pos` is now scoped by company (P1) so the Add New picker only offers POs the user is permitted to see"},
            {"type": "fix", "text": "Tracking: inapplicable optional sample stages are excluded from the dashboard Delayed / Blocked metrics (P2) so N/A stages don't inflate at-risk counts"},
        ],
    },
    {
        "version": "1.15.0",
        "date": "2026-05-26",
        "entries": [
            {"type": "feat", "text": "Added the **Production Stage Tracking** module — Stages 0–4: wide-table schema (22 stages, dependency matrix, QC inspections), store layer with `compute_readiness` / `compute_schedule` / `compute_inspection_reminders`, and the 🏭 Tracking tab (Dashboard, Overview, Edit, Add New, Plan)"},
        ],
    },
    {
        "version": "1.14.8",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan multiselect + multiple bug fixes (merged from the production-delivery-tracking branch)"},
        ],
    },
    {
        "version": "1.14.6",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East → Reports → Download Items: **CSV download crashed** with `NameError: name 'CSV_MIME' is not defined` — `CSV_MIME` was used but never imported from `ui.shared`"},
            {"type": "fix", "text": "Sky East → Reports → Wash Labels: selecting styles in **Style (Fabric Mapping)** mode and then deleting a contract in the History tab wiped all selected styles — the stale-state guard was incorrectly filtering style names against the PC No. set; `se_wl_styles` is now excluded from that guard"},
            {"type": "fix", "text": "Sign-out now resets all generated file bytes (buy plan, 核料 zip, item download, wash label), progress lookup, fabric lookup, and masked zip — previously these persisted across logout, leaking one user's generated data to the next user on the same browser session"},
            {"type": "fix", "text": "Sign-out now clears `_se_bp_prog_fp` (大货进度表 fingerprint key) — previously a second user uploading the same file as the first user would silently skip processing"},
            {"type": "fix", "text": "Session-state defaults in `app.py` now initialize `SE_PROGRESS_LKUP`, `SE_FABRIC_LOOKUP`, `SE_MASKED_ZIP`, and `SE_IMAGES_DIR` — previously missing from the defaults block"},
            {"type": "fix", "text": "Admin → Email: Brevo sender warning now shows a clear message when both Sender and Username are empty (`empty — neither Username nor Sender is set`) instead of rendering an empty backtick pair"},
        ],
    },
    {
        "version": "1.14.5",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East → Reports → Buy Plan: **Generate Buy Plan button now stays enabled** after uploading 大货进度表 — removed the explicit `st.rerun()` after processing the file; the file-upload event already triggers a script rerun, so the extra rerun was causing `se_bp_sel` to remain `[]` when the file was uploaded before PC Nos were selected, keeping the button permanently disabled"},
            {"type": "fix", "text": "Buy Plan: 大货进度表 loaded status message now appears immediately in the same run as the upload (moved caption to read session state after processing rather than before)"},
        ],
    },
    {
        "version": "1.14.4",
        "date": "2026-05-25",
        "entries": [
            {"type": "fix", "text": "Sky East → Reports → Buy Plan: fingerprint guard added to prevent infinite-rerun loop from 大货进度表 file uploader in Streamlit 1.57.0"},
            {"type": "fix", "text": "Sky East → New Contracts → Reference files expander now **defaults to open** — drag-and-drop into file uploaders inside a collapsed expander was unreliable in some browser configurations"},
        ],
    },
    {
        "version": "1.14.3",
        "date": "2026-05-23",
        "entries": [
            {"type": "fix", "text": "Email via Brevo: the SMTP connection was succeeding but emails were **silently dropped** because the From address was the `@smtp-brevo.com` login username rather than a verified sender — Brevo accepts the handshake but never delivers in this case"},
            {"type": "fix", "text": "Admin → Email now shows a clear warning when using Brevo with an unverified sender address, linking to the Brevo senders page to resolve it"},
            {"type": "fix", "text": "Sky East → Reports: email section now shows an inline warning (before the Send button) when the Brevo sender is misconfigured, so the issue is visible without navigating to Admin"},
        ],
    },
    {
        "version": "1.14.2",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East history: **Browse Items** and **Delete Selected** now work reliably — stale session-state values that pointed to deleted PC Nos. were causing a `StreamlitAPIException` on the next render, silently breaking both widgets"},
            {"type": "fix", "text": "`_se_hist_item_browser` strips any pc_nos from `se_hist_pc` session state that are no longer in `pc_options` before the multiselect renders — prevents crash after deletion"},
            {"type": "fix", "text": "`_se_hist_delete_section` clears both `se_del_pcs` and `se_hist_pc` from session state before `st.rerun()` and uses `st.toast` so confirmation persists across the rerun"},
            {"type": "fix", "text": "History section auto-cleans orphaned `pc_no = ''` contracts on every load — these were left by files parsed before the dynamic header fix and appeared as invisible blank options in every multiselect"},
        ],
    },
    {
        "version": "1.14.1",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Sky East parser v1.3: `_find_header_row` now scores every candidate row by counting recognised alias matches — picks the row with the most hits instead of the first row containing any single signal (eliminates false positives when header rows appear late in the sheet)"},
            {"type": "feat", "text": "Header-row signal set is now auto-derived from `_COL_ALIASES` at detection time — adding new aliases to the alias table automatically improves header detection with no separate maintenance"},
            {"type": "feat", "text": "`_map_columns` gains a **Pass 3** partial/substring matcher — if an exact alias fails, any alias ≥ 5 chars that is a substring of the header cell (or vice versa) claims the column; covers near-miss names like 'supplier article number' matching 'article number'"},
            {"type": "feat", "text": "`_COL_ALIASES` substantially expanded: `style_no` (12 variants), `po_number` (13 variants), `color_name` / `color_code` (10+ variants each), `total_qty`, `ex_fty`, `fob_usd`, `article_name`, `fabric_no`, `launch_date` — all with broader synonym coverage"},
            {"type": "feat", "text": "`_HEADER_LABEL_ALIASES` (contract header fields) expanded: `pc_no`, `party_a`, `party_b`, `payment_terms`, `trade_term`, `pc_date` all have more label variants including Chinese, abbreviated, and punctuation-variant forms"},
        ],
    },
    {
        "version": "1.14.0",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Sky East store: `_sizes_to_db_cols()` helper collapses any dynamic size dict (including \"1X\", \"2X\", \"XXXL\", \"SM\", etc.) into the 6 fixed DB columns (xs/s/m/l/xl/xxl) using the `SIZE_TO_DB` mapping from the parser"},
            {"type": "feat", "text": "`_normalize_sizes()` added to store schema — normalises raw parser size keys to the 6 canonical keys before duplicate/change detection, so files with \"1X\"/\"2X\" styles compare correctly against existing DB rows"},
            {"type": "fix", "text": "`_sizes_equal()` updated to normalise both sides before comparison — prevents false \"updated\" records when the same quantities are expressed with different size key names across file versions"},
            {"type": "refactor", "text": "`_insert_item` and `_update_item` now call `_sizes_to_db_cols()` instead of hardcoded `sizes.get(\"XS\", 0)` etc. — any size layout supported without code changes"},
        ],
    },
    {
        "version": "1.13.9",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East parser: contract header reader now scans from the label column rightward instead of assuming the value is always in column E — fixes HHPPC046-style files where the value sits in column D (one column left of the standard layout)"},
            {"type": "fix", "text": "Fallback row positions (pc_no, pc_date, party_b, etc.) now try column D before column E, covering both old and new Sky East file layouts"},
        ],
    },
    {
        "version": "1.13.8",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "GIII Reports → Generate Outputs: added **📋 Create Buy Plan (生产计划单)** button — generates a factory production plan in standard GIII format (one sheet per style, two-row merged header, PO/color rows with size breakdown, Chinese colour lookup, merged cells, footer totals)"},
            {"type": "feat", "text": "New exporter `giii_production_plan.py`: dynamic size columns, standard size ordering, automatic NaN/null handling for fabric/description fields"},
        ],
    },
    {
        "version": "1.13.7",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Completed comprehensive temp-file leak audit — all `mkdtemp()` / `mkstemp()` directories are now cleaned up after every processing run"},
            {"type": "fix", "text": "GIII Smart Upload (`giii_view.py`): detection temp dir now wrapped in try/finally so it is deleted after every page render"},
            {"type": "fix", "text": "GIII Excel pipeline (`excel_extraction.py`): `mask_out_dir`, `tmpdir`, and `out_dir` all cleaned up after run"},
        ],
    },
    {
        "version": "1.13.6",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East processing: `mask_out_dir` and `tmpdir` cleaned up after every order file run"},
            {"type": "fix", "text": "GIII extraction: `tmpdir` and `out_dir` cleaned up in `_run_extraction`, `_run_from_history`, and `_create_buyplan_bytes`"},
            {"type": "fix", "text": "`ProgressLookup` now accepts `data=bytes` — large progress files (144 MB+) are never written to disk, eliminating the primary source of temp-file disk exhaustion"},
        ],
    },
    {
        "version": "1.13.5",
        "date": "2026-05-22",
        "entries": [
            {"type": "perf", "text": "Buy plan generation: `load_workbook()` hoisted outside the 核料 loop — template is parsed once and deep-copied per workbook instead of re-read from disk N times"},
            {"type": "perf", "text": "Image cache: loaded bytes are written back to `st.session_state` so repeated Generate presses re-use in-memory data without disk re-reads"},
            {"type": "perf", "text": "Wash label export: replaced three `iterrows` sweeps with vectorised pandas `drop_duplicates + set_index + to_dict` ops"},
            {"type": "perf", "text": "KL format export: pre-grouped size rows by PO number (O(1) lookup vs O(n) scan per style)"},
            {"type": "perf", "text": "Buy plan font allocation: shared `Font` object cache eliminates per-cell `Font()` construction overhead"},
        ],
    },
    {
        "version": "1.13.4",
        "date": "2026-05-22",
        "entries": [
            {"type": "fix", "text": "Sky East Buy Plan: added **Select All** button next to PC No. multiselect so all contracts can be included in one click"},
            {"type": "fix", "text": "Sky East Buy Plan / Download Items / Wash Labels: info message shown when nothing is selected, explaining what to do"},
            {"type": "fix", "text": "Wash Labels: improved guidance message when no fabric mapping is available for style-based generation"},
        ],
    },
    {
        "version": "1.13.3",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Sky East history: Buy Plan buy `out_dir` cleaned up after all file bytes are captured into session state"},
            {"type": "fix",  "text": "Dual-header photo lookup: vectorised style→picture_id dict construction replaces slow `iterrows`"},
        ],
    },
    {
        "version": "1.13.2",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Intermediate release — internal feature work and stability improvements"},
        ],
    },
    {
        "version": "1.9.1",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "Added production tracking schema stub for future order-progress integration"},
        ],
    },
    {
        "version": "1.9.0",
        "date": "2026-05-22",
        "entries": [
            {"type": "feat", "text": "KL format export for Sky East orders"},
            {"type": "feat", "text": "Vendor fax number parsing from order files"},
            {"type": "feat", "text": "Multi-source combined order summary view"},
            {"type": "refactor", "text": "Major UI refactor across Sky East and GIII tabs"},
        ],
    },
    {
        "version": "1.8.5",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Six bugs found in code review — item enrichment, contract save, and display fixes"},
        ],
    },
    {
        "version": "1.8.4",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Progress lookup correctness: legacy column defaults + colour code key normalisation"},
        ],
    },
    {
        "version": "1.8.3",
        "date": "2026-05-08",
        "entries": [
            {"type": "refactor", "text": "Centralised constants + `BuyplanColorLookups` NamedTuple for cleaner lookup passing"},
        ],
    },
    {
        "version": "1.8.2",
        "date": "2026-05-08",
        "entries": [
            {"type": "refactor", "text": "Addressed code review findings across parsers and exporters"},
        ],
    },
    {
        "version": "1.8.1",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "One-time migration sets `default_color_source` to `progress` for existing installs"},
        ],
    },
    {
        "version": "1.8.0",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "Progress lookup now uses primary key `PC No · style · color` — more precise contract matching"},
        ],
    },
    {
        "version": "1.7.9",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "Color source radio button in Buy Plan section lets users choose between Progress file and Color DB"},
            {"type": "feat", "text": "大货进度表 uploader added directly to Buy Plan section for quick colour lookup"},
        ],
    },
    {
        "version": "1.7.8",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Corrected buy plan left/right page margins to 0.64 cm (0.25 in)"},
        ],
    },
    {
        "version": "1.7.7",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "Configurable print margins added to buy plan export"},
            {"type": "feat", "text": "Index 综合key included in fabric description column"},
        ],
    },
    {
        "version": "1.7.6",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Print settings not being applied — fixed by using `pageSetUpPr.fitToPage` flag"},
        ],
    },
    {
        "version": "1.7.5",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Disabled brand-agnostic fallback in colour code lookup to prevent incorrect cross-brand matches"},
        ],
    },
    {
        "version": "1.7.4",
        "date": "2026-05-08",
        "entries": [
            {"type": "fix", "text": "Doubled colour code appearing in BODY COLOR-CN column"},
            {"type": "fix", "text": "Empty 综合key no longer written to fabric index"},
        ],
    },
    {
        "version": "1.7.3",
        "date": "2026-05-08",
        "entries": [
            {"type": "feat", "text": "A4 landscape fit-all-columns print settings applied to all buy plan sheets"},
        ],
    },
    {
        "version": "1.7.2",
        "date": "2026-05-07",
        "entries": [
            {"type": "feat", "text": "Centralised fabric master database — fabric parts stored and queried from a shared DB table across all companies"},
        ],
    },
    {
        "version": "1.7.1",
        "date": "2026-05-07",
        "entries": [
            {"type": "feat", "text": "Admin-configurable default Chinese colour mapping source (Progress file vs Colour DB)"},
        ],
    },
    {
        "version": "1.7.0",
        "date": "2026-05-07",
        "entries": [
            {"type": "feat", "text": "PC No.-keyed colour lookups for precise Sky East colour resolution"},
            {"type": "feat", "text": "Bilingual UI (English / 中文) with language toggle in sidebar"},
            {"type": "feat", "text": "Email delivery — generated buy plan and 核料 files can be sent directly from the app"},
            {"type": "feat", "text": "Combined Chinese colour pipeline: Progress file → Colour DB → buyer PO fallback"},
        ],
    },
    {
        "version": "1.63.4",
        "date": "2026-05-06",
        "entries": [
            {"type": "fix", "text": "COLLATE NOCASE matching in progress-xlsx importer; merges case-duplicate colour rows correctly"},
        ],
    },
    {
        "version": "1.63.3",
        "date": "2026-05-06",
        "entries": [
            {"type": "fix", "text": "Sky East: buyer PO colour_code no longer copied into 中文颜色代码 (separate fields)"},
        ],
    },
    {
        "version": "1.63.2",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Progress-xlsx importer extended to read `英文颜色` / `中文颜色代码` headers and write back colour codes"},
        ],
    },
    {
        "version": "1.63.1",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "中文颜色 formatted as `#code|name` in HHP buy plan column I for richer colour display"},
        ],
    },
    {
        "version": "1.63.0",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "中文颜色代码 added to colour lookup pipeline and HHP buy plan output"},
        ],
    },
    {
        "version": "1.62.4",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Added Brevo and Resend email provider presets"},
            {"type": "feat", "text": "SSL port 465 support for SMTP email delivery"},
        ],
    },
    {
        "version": "1.62.2",
        "date": "2026-05-06",
        "entries": [
            {"type": "fix", "text": "Outlook SMTP 535 auth error — added App Password guidance in Admin → Email"},
        ],
    },
    {
        "version": "1.62.1",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Email provider quick-setup presets (Gmail, Outlook, QQ Mail, etc.) in Admin → Email"},
        ],
    },
    {
        "version": "1.62.0",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "SMTP settings now fully configurable from Admin → Email tab (no config file editing required)"},
        ],
    },
    {
        "version": "1.61.0",
        "date": "2026-05-06",
        "entries": [
            {"type": "feat", "text": "Email delivery feature — generated buy plan / 核料 files can be emailed to recipients"},
        ],
    },
    {
        "version": "1.60.0",
        "date": "2026-05-05",
        "entries": [
            {"type": "feat", "text": "Initial release of PO Extractor — PDF and Excel purchase order parsing for GIII and Sky East"},
            {"type": "feat", "text": "Buy plan generation, Template_P export, 核料 workbooks"},
            {"type": "feat", "text": "Fabric mapping, colour translation, and wash label generation"},
            {"type": "feat", "text": "Admin panel: users, companies, column mapping, size order, templates"},
        ],
    },
]

# ---------------------------------------------------------------------------
# Type display config
# ---------------------------------------------------------------------------
_TYPE_CONFIG = {
    "feat":     ("🌟", "#0d6efd", "Feature"),
    "fix":      ("🐛", "#dc3545", "Fix"),
    "perf":     ("⚡", "#fd7e14", "Performance"),
    "refactor": ("♻️",  "#6c757d", "Refactor"),
    "security": ("🔒", "#198754", "Security"),
    "docs":     ("📄", "#6610f2", "Docs"),
}


# How many of the newest versions render outside the "Older versions"
# expander.  Everything is still just markdown -- but concatenated into ONE
# st.markdown call per group instead of ~4 elements per version, which at
# 200+ versions was ~900 DOM-mounted Streamlit elements on every rerun.
_RECENT_VERSION_COUNT = 20

_VERSION_SEPARATOR = (
    "<hr style='margin:0.9rem 0; border:none; "
    "border-top:1px solid rgba(128,128,128,0.35);'>"
)


def _version_card_html(entry: dict) -> str:
    """Build one version's card (header + typed entry lines) as an HTML string."""
    parts = [
        f"<div style='display:flex; align-items:baseline; gap:0.75rem;'>"
        f"<span style='font-size:1.15rem; font-weight:700;'>v{entry['version']}</span>"
        f"<span style='color:#888; font-size:0.85rem;'>{entry['date']}</span>"
        f"</div>"
    ]
    for item in entry["entries"]:
        ttype = item.get("type", "feat")
        icon, color, label = _TYPE_CONFIG.get(ttype, ("•", "#333", ttype))
        parts.append(
            f"<div style='margin: 0.15rem 0 0.15rem 1rem; font-size:0.92rem;'>"
            f"<span style='color:{color}; font-weight:600; margin-right:0.4rem'>{icon}</span>"
            f"{item['text']}"
            f"</div>"
        )
    return "".join(parts)


def show_changelog_tab() -> None:
    """Render the Releases / Changelog tab."""
    st.markdown("## 🔖 Release History")
    st.caption("All versions of PO Extractor, newest first.")

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_cols = st.columns(len(_TYPE_CONFIG))
    for col, (ttype, (icon, color, label)) in zip(legend_cols, _TYPE_CONFIG.items()):
        col.markdown(
            f"<span style='color:{color}; font-weight:600'>{icon} {label}</span>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Version cards ─────────────────────────────────────────────────────────
    recent = _CHANGELOG[:_RECENT_VERSION_COUNT]
    older  = _CHANGELOG[_RECENT_VERSION_COUNT:]

    st.markdown(
        _VERSION_SEPARATOR.join(_version_card_html(e) for e in recent),
        unsafe_allow_html=True,
    )

    if older:
        st.divider()
        with st.expander(
            f"📦 Older versions (v{older[-1]['version']} – v{older[0]['version']} · "
            f"{len(older)} releases)",
            expanded=False,
        ):
            st.markdown(
                _VERSION_SEPARATOR.join(_version_card_html(e) for e in older),
                unsafe_allow_html=True,
            )
