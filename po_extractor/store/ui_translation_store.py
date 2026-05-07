"""SQLite-backed store for UI translation strings.

Stores English text → per-language translations so the interface can be
displayed in any supported language without touching Python source.

Schema
------
ui_translations(
    id          INTEGER PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,   -- English text used as stable key
    en_text     TEXT NOT NULL DEFAULT '',
    zh_text     TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '', -- "label"|"button"|"header"|"message"|"caption"
    module      TEXT NOT NULL DEFAULT '', -- "shared"|"giii"|"sky_east"|"admin"|"summary"
    updated_at  TEXT,
    updated_by  TEXT
)
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from .base_store import BaseSQLiteStore

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ui_translations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key         TEXT    NOT NULL UNIQUE,
    en_text     TEXT    NOT NULL DEFAULT '',
    zh_text     TEXT    NOT NULL DEFAULT '',
    category    TEXT    NOT NULL DEFAULT '',
    module      TEXT    NOT NULL DEFAULT '',
    updated_at  TEXT,
    updated_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_uit_module   ON ui_translations(module);
CREATE INDEX IF NOT EXISTS idx_uit_category ON ui_translations(category);
"""

# Supported language codes → column name in ui_translations.
_LANG_COL: dict[str, str] = {
    "zh": "zh_text",
}

# ---------------------------------------------------------------------------
# Seed data: English key → (zh_text, category, module)
# ---------------------------------------------------------------------------

# fmt: off
_SEED: list[tuple[str, str, str, str]] = [
    # ── Shared column headers (migrated from _LABEL_ZH) ─────────────────────
    ("Company",               "公司",         "label",   "shared"),
    ("Companies",             "公司数",        "label",   "shared"),
    ("Source",                "来源",          "label",   "shared"),
    ("POs",                   "订单数",        "label",   "shared"),
    ("Total POs",             "总订单数",       "label",   "shared"),
    ("Styles",                "款式数",        "label",   "shared"),
    ("Total Styles",          "总款式数",       "label",   "shared"),
    ("Units",                 "数量",          "label",   "shared"),
    ("Total Units",           "总数量",        "label",   "shared"),
    ("Total Qty",             "总数量",        "label",   "shared"),
    ("Factory",               "工厂",          "label",   "shared"),
    ("COO",                   "原产地",        "label",   "shared"),
    ("Latest Ex-Fty",         "最新离厂日期",   "label",   "shared"),
    ("Ex-Fty",                "离厂日期",      "label",   "shared"),
    ("Ex-Fty Date",           "离厂日期",      "label",   "shared"),
    ("PC No.",                "合同编号",      "label",   "shared"),
    ("PO No.",                "采购单号",      "label",   "shared"),
    ("Style",                 "款式",          "label",   "shared"),
    ("Style No.",             "款式编号",      "label",   "shared"),
    ("Color",                 "颜色",          "label",   "shared"),
    ("Brand",                 "品牌",          "label",   "shared"),
    ("Photo",                 "图片",          "label",   "shared"),
    ("Source File",           "来源文件",      "label",   "shared"),
    ("Extracted At",          "提取时间",      "label",   "shared"),
    # Sky East item labels
    ("HHN Contract No.",      "HHN合同号",     "label",   "sky_east"),
    ("Config SKU",            "Config SKU",   "label",   "sky_east"),
    ("Article Name",          "商品名称",      "label",   "sky_east"),
    ("Color Code",            "颜色代码",      "label",   "sky_east"),
    ("Fabric No.",            "面料编号",      "label",   "sky_east"),
    ("Composition",           "成分",          "label",   "sky_east"),
    ("Cuttable Width (cm)",   "有效门幅(cm)", "label",   "sky_east"),
    ("Fabric Key",            "综合标识Key",   "label",   "sky_east"),
    ("Shrinkage Rate",        "烫缩率",        "label",   "sky_east"),
    ("Short Rate",            "短码率",        "label",   "sky_east"),
    # Sky East contract labels
    ("PC Date",               "合同日期",      "label",   "sky_east"),
    ("Buyer",                 "买方",          "label",   "sky_east"),
    ("Seller",                "卖方",          "label",   "sky_east"),
    ("Currency",              "币种",          "label",   "sky_east"),
    ("Trade Term",            "贸易条款",      "label",   "sky_east"),
    # GIII / history labels
    ("Division",              "分部",          "label",   "giii"),
    ("Issue Date",            "下单日期",      "label",   "giii"),
    ("Version",               "版本",          "label",   "giii"),
    ("File",                  "文件",          "label",   "giii"),
    # Missing fields labels
    ("Fabric No. (was)",          "面料编号(原)",    "label", "sky_east"),
    ("HHN Contract No. (was)",    "HHN合同号(原)",  "label", "sky_east"),
    ("Fabric No. → (new)",        "面料编号→(新)",  "label", "sky_east"),
    ("HHN Contract No. → (new)", "HHN合同号→(新)", "label", "sky_east"),
    # ── New: common UI labels ────────────────────────────────────────────────
    ("ID",                    "编号",          "label",   "shared"),
    ("Name",                  "名称",          "label",   "shared"),
    ("Type",                  "类型",          "label",   "shared"),
    ("Status",                "状态",          "label",   "shared"),
    ("Date",                  "日期",          "label",   "shared"),
    ("Notes",                 "备注",          "label",   "shared"),
    ("Actions",               "操作",          "label",   "shared"),
    ("Role",                  "角色",          "label",   "shared"),
    ("Active",                "启用",          "label",   "shared"),
    ("Username",              "用户名",        "label",   "shared"),
    ("Password",              "密码",          "label",   "shared"),
    ("Email",                 "邮箱",          "label",   "shared"),
    ("Size",                  "尺码",          "label",   "shared"),
    ("Qty",                   "数量",          "label",   "shared"),
    ("XS",                    "XS",           "label",   "shared"),
    ("S",                     "S",            "label",   "shared"),
    ("M",                     "M",            "label",   "shared"),
    ("L",                     "L",            "label",   "shared"),
    ("XL",                    "XL",           "label",   "shared"),
    ("2XL",                   "2XL",          "label",   "shared"),
    ("Reason",                "原因",          "label",   "shared"),
    ("Archived At",           "归档时间",      "label",   "shared"),
    ("Zalando PO",            "Zalando订单",   "label",   "shared"),
    ("Total Cost",            "总成本",        "label",   "shared"),
    ("FOB",                   "FOB",          "label",   "shared"),
    ("Launch Date",           "上市日期",      "label",   "shared"),
    # ── Buttons ──────────────────────────────────────────────────────────────
    ("Sign In",               "登录",          "button",  "shared"),
    ("Sign Out",              "退出登录",       "button",  "shared"),
    ("Save",                  "保存",          "button",  "shared"),
    ("Delete",                "删除",          "button",  "shared"),
    ("Apply",                 "应用",          "button",  "shared"),
    ("Cancel",                "取消",          "button",  "shared"),
    ("Generate",              "生成",          "button",  "shared"),
    ("Download",              "下载",          "button",  "shared"),
    ("Upload",                "上传",          "button",  "shared"),
    ("Import",                "导入",          "button",  "shared"),
    ("Export",                "导出",          "button",  "shared"),
    ("Refresh",               "刷新",          "button",  "shared"),
    ("Add",                   "添加",          "button",  "shared"),
    ("Edit",                  "编辑",          "button",  "shared"),
    ("Select all",            "全选",          "button",  "shared"),
    ("Clear",                 "清除",          "button",  "shared"),
    ("Reset",                 "重置",          "button",  "shared"),
    ("Confirm",               "确认",          "button",  "shared"),
    ("Create",                "创建",          "button",  "shared"),
    ("Update",                "更新",          "button",  "shared"),
    ("Process",               "处理",          "button",  "shared"),
    ("Process Files",         "处理文件",       "button",  "shared"),
    ("Change Password",       "修改密码",       "button",  "shared"),
    # GIII buttons
    ("Process all files",     "处理所有文件",   "button",  "giii"),
    ("Export results",        "导出结果",       "button",  "giii"),
    # Sky East buttons
    ("Process Sky East Files",   "处理天东文件",  "button", "sky_east"),
    ("Generate Buy Plan + 核料", "生成采购计划 + 核料", "button", "sky_east"),
    ("Generate Buy Plan",     "生成采购计划",    "button", "sky_east"),
    ("Generate Wash Label",   "生成洗水唛",     "button",  "sky_east"),
    ("Generate anyway (keep errors)", "直接生成（保留错误）", "button", "sky_east"),
    ("Delete selected",       "删除选中",       "button",  "sky_east"),
    ("Apply & Generate",      "应用并生成",     "button",  "sky_east"),
    # ── Tab / section headings ───────────────────────────────────────────────
    ("New Contracts",         "新合同",        "header",  "sky_east"),
    ("Contract History",      "合同历史",      "header",  "sky_east"),
    ("Missing Fields",        "缺失字段",      "header",  "sky_east"),
    ("History",               "历史",          "header",  "shared"),
    ("Summary",               "汇总",          "header",  "shared"),
    ("Admin",                 "管理",          "header",  "shared"),
    ("User Management",       "用户管理",      "header",  "admin"),
    ("Company Registry",      "公司注册",      "header",  "admin"),
    ("Column Mapping",        "列映射",        "header",  "admin"),
    ("Size Order",            "尺码顺序",      "header",  "admin"),
    ("Templates",             "模板",          "header",  "admin"),
    ("Pipeline Layouts",      "流水线布局",    "header",  "admin"),
    ("Email Settings",        "邮件设置",      "header",  "admin"),
    ("Translations",          "翻译管理",      "header",  "admin"),
    ("Order Summary",         "订单汇总",      "header",  "summary"),
    ("Fabric DB",             "面料数据库",    "header",  "shared"),
    ("Fabric Mapping",        "面料映射",      "header",  "shared"),
    ("Colors",                "颜色",          "header",  "shared"),
    ("Buy Plan",              "采购计划",      "header",  "shared"),
    ("Amendment History",     "修改历史",      "header",  "sky_east"),
    ("Processing log",        "处理日志",      "header",  "shared"),
    ("Reference files",       "参考文件",      "header",  "shared"),
    # ── Captions / messages ──────────────────────────────────────────────────
    ("No data available.",       "暂无数据。",    "message", "shared"),
    ("Done!",                    "完成！",        "message", "shared"),
    ("Error",                    "错误",          "message", "shared"),
    ("Warning",                  "警告",          "message", "shared"),
    ("Success",                  "成功",          "message", "shared"),
    ("Loading...",               "加载中...",     "message", "shared"),
    ("Processing...",            "处理中...",     "message", "shared"),
    ("Saved successfully.",      "保存成功。",    "message", "shared"),
    ("Deleted successfully.",    "删除成功。",    "message", "shared"),
    ("No records found.",        "未找到记录。",  "message", "shared"),
    ("Password changed.",        "密码已修改。",  "message", "shared"),
    ("Incorrect username or password.", "用户名或密码错误。", "message", "shared"),
    ("New password cannot be empty.",   "新密码不能为空。",   "message", "shared"),
    ("Passwords do not match.",         "两次密码不一致。",   "message", "shared"),
    # Sky East messages
    ("No valid contracts could be parsed.", "无法解析任何有效合同。", "message", "sky_east"),
    ("No data found for the selected contracts.", "所选合同无数据。", "message", "sky_east"),
    ("Generating...",            "生成中...",     "message", "sky_east"),
    ("Building file...",         "构建文件中...", "message", "sky_east"),
    ("Building wash label file...", "生成洗水唛文件中...", "message", "sky_east"),
    # Form labels / placeholders
    ("Current password",         "当前密码",     "label",   "shared"),
    ("New password",             "新密码",       "label",   "shared"),
    ("Confirm new password",     "确认新密码",   "label",   "shared"),
    ("Create new user",          "创建新用户",   "label",   "admin"),
    ("Display name",             "显示名称",     "label",   "admin"),
    ("Format IDs",               "格式ID",       "label",   "admin"),
    ("File types",               "文件类型",     "label",   "admin"),
    ("Badge colour",             "标签颜色",     "label",   "admin"),
    ("Sheet name",               "表格名称",     "label",   "admin"),
    # ── Color translation view ────────────────────────────────────────────────
    ("Chinese Color",            "中文颜色",     "label",   "shared"),
    ("English Color",            "英文颜色",     "label",   "shared"),
    ("Light/Dark",               "深浅",         "label",   "shared"),
    ("Label Color",              "主标颜色",     "label",   "shared"),
    ("Color Translation",        "颜色翻译",     "header",  "shared"),
    # ── Fabric labels ─────────────────────────────────────────────────────────
    ("HHN Code",                 "HHN编号",      "label",   "sky_east"),
    ("Weight (gsm)",             "克重(gsm)",    "label",   "sky_east"),
    ("Width (cm)",               "幅宽(cm)",     "label",   "sky_east"),
    ("Body Part",                "部位",         "label",   "sky_east"),
    ("Seq",                      "序号",         "label",   "sky_east"),
    ("Combo",                    "组合",         "label",   "sky_east"),
    ("Fabric Code",              "面料编号",     "label",   "sky_east"),
    ("Issue",                    "问题",         "label",   "sky_east"),
    ("Suggestion",               "建议",         "label",   "sky_east"),
    # ── Summary view ─────────────────────────────────────────────────────────
    ("Aggregated view of all orders across clients",
     "所有客户订单汇总视图", "caption", "summary"),
    ("No order data available for your permitted companies.",
     "您的权限公司暂无订单数据。", "message", "summary"),
    ("Show all columns",         "显示所有列",   "button",  "summary"),
    # ── Image folder ─────────────────────────────────────────────────────────
    ("Folder path",              "文件夹路径",   "label",   "shared"),
    ("Recent folders",           "最近使用",     "label",   "shared"),
    ("Folder exists",            "文件夹已存在", "message", "shared"),
    ("Image folder updated.",    "图片文件夹已更新。", "message", "shared"),
    ("Image folder (load & save style photos)",
     "图片文件夹（加载 & 保存款式照片）",        "label",   "shared"),
    ("Folder not found — it will be created when processing runs.",
     "文件夹不存在 — 处理时将自动创建。",        "message", "shared"),
    # ── Sky East view ─────────────────────────────────────────────────────────
    ("Sky East Purchase Contracts",  "天东采购合同",          "header",  "sky_east"),
    ("Upload one or more Sky East order Excel files. "
     "Files with the **same PC No.** are merged (quantities added). "
     "Changed size breakdowns are detected as amendments and logged to history.",
     "上传一个或多个天东订单Excel文件。相同**合同号**的文件将被合并（数量相加）。"
     "尺码变更将被检测为修改并记录到历史。",    "caption",  "sky_east"),
    ("Order Files",                  "订单文件",              "label",   "sky_east"),
    ("Internal Database",            "内部数据库",            "label",   "sky_east"),
    ("Chinese color mapping source", "中文颜色来源",          "label",   "sky_east"),
    ("Mask prices",                  "隐藏价格",              "label",   "sky_east"),
    ("Upload one or more Sky East Purchase Contract Excel files to begin.",
     "请上传一个或多个天东采购合同Excel文件以开始。",         "message", "sky_east"),
    ("Format",                       "格式",                  "label",   "shared"),
    # ── Sky East history ──────────────────────────────────────────────────────
    ("Saved Contracts",              "已保存合同",            "header",  "sky_east"),
    ("No Sky East contracts saved yet.", "暂无天东合同记录。","message", "sky_east"),
    ("Download items by PC No.",     "按合同号下载明细",      "header",  "sky_east"),
    ("Select PC No.(s) to download:", "选择合同号下载：",     "label",   "sky_east"),
    ("Download Wash Label Content",  "下载洗水唛内容",        "header",  "sky_east"),
    ("Select PC No.(s) for wash label:", "选择合同号（洗水唛）：", "label", "sky_east"),
    ("Select Style(s) for wash label:", "选择款式（洗水唛）：",   "label", "sky_east"),
    ("Select by",                    "选择方式",              "label",   "sky_east"),
    ("Create Buy Plan",              "创建采购计划",          "header",  "sky_east"),
    ("PC No.(s) to include:",        "选择合同号（采购计划）：", "label", "sky_east"),
    ("PCs selected",                 "已选合同数",            "label",   "sky_east"),
    ("Delete contracts from history", "从历史记录中删除合同", "header",  "sky_east"),
    ("Select PC No.(s) to delete:",  "选择要删除的合同号：",  "label",   "sky_east"),
    ("Browse items for PC No.:",     "浏览合同明细：",        "label",   "sky_east"),
    ("View amendment history for a style", "查看款式修改历史","header",  "sky_east"),
]
# fmt: on


def _current_actor() -> str:
    try:
        import streamlit as st
        from ui.session_keys import SK
        return str(st.session_state.get(SK.USERNAME) or "system").strip() or "system"
    except Exception:
        return "system"


class UITranslationStore(BaseSQLiteStore):
    """SQLite-backed store for UI translation strings.

    Keys are the English text strings used throughout the UI.  For each key
    the store holds one translation column per supported language (currently
    only ``zh_text``).  Additional language columns can be added via schema
    migrations without breaking existing code.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ── Seed ──────────────────────────────────────────────────────────────────

    def seed_defaults(self, skip_existing: bool = True) -> dict[str, int]:
        """Insert built-in translations.  Skips rows already present by default.

        Returns ``{"inserted": N, "skipped": N}``.
        """
        now = datetime.now(timezone.utc).isoformat()
        inserted = skipped = 0
        with self._conn() as conn:
            for key, zh_text, category, module in _SEED:
                exists = conn.execute(
                    "SELECT id FROM ui_translations WHERE key=?", (key,)
                ).fetchone()
                if exists:
                    if skip_existing:
                        skipped += 1
                        continue
                    conn.execute(
                        """UPDATE ui_translations
                           SET zh_text=?, category=?, module=?,
                               updated_at=?, updated_by='seed'
                           WHERE key=?""",
                        (zh_text, category, module, now, key),
                    )
                else:
                    conn.execute(
                        """INSERT INTO ui_translations
                               (key, en_text, zh_text, category, module,
                                updated_at, updated_by)
                           VALUES (?,?,?,?,?,?,?)""",
                        (key, key, zh_text, category, module, now, "seed"),
                    )
                inserted += 1
        return {"inserted": inserted, "skipped": skipped}

    # ── Upsert / write ────────────────────────────────────────────────────────

    def upsert(self, key: str, en_text: str, zh_text: str,
               category: str = "", module: str = "",
               actor: str | None = None) -> None:
        """Insert or update a single translation row."""
        now   = datetime.now(timezone.utc).isoformat()
        by    = actor or _current_actor()
        en    = en_text.strip()
        clean = key.strip()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO ui_translations
                       (key, en_text, zh_text, category, module, updated_at, updated_by)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(key) DO UPDATE SET
                       en_text=excluded.en_text,
                       zh_text=excluded.zh_text,
                       category=excluded.category,
                       module=excluded.module,
                       updated_at=excluded.updated_at,
                       updated_by=excluded.updated_by""",
                (clean, en, zh_text.strip(), category, module, now, by),
            )

    def upsert_many(self, rows: list[dict],
                    skip_existing: bool = False) -> dict[str, int]:
        """Bulk-upsert a list of dicts with keys ``key, en_text, zh_text,
        category, module``.  Returns ``{"inserted": N, "updated": N, "skipped": N}``.
        """
        now = datetime.now(timezone.utc).isoformat()
        by = _current_actor()
        inserted = updated = skipped = 0
        with self._conn() as conn:
            for row in rows:
                key = str(row.get("key", "") or "").strip()
                if not key:
                    continue
                exists = conn.execute(
                    "SELECT id FROM ui_translations WHERE key=?", (key,)
                ).fetchone()
                if exists and skip_existing:
                    skipped += 1
                    continue
                conn.execute(
                    """INSERT INTO ui_translations
                           (key, en_text, zh_text, category, module,
                            updated_at, updated_by)
                       VALUES (?,?,?,?,?,?,?)
                       ON CONFLICT(key) DO UPDATE SET
                           en_text=excluded.en_text,
                           zh_text=excluded.zh_text,
                           category=excluded.category,
                           module=excluded.module,
                           updated_at=excluded.updated_at,
                           updated_by=excluded.updated_by""",
                    (key,
                     str(row.get("en_text", key)).strip(),
                     str(row.get("zh_text", "") or "").strip(),
                     str(row.get("category", "") or ""),
                     str(row.get("module",   "") or ""),
                     now, by),
                )
                if exists:
                    updated += 1
                else:
                    inserted += 1
        return {"inserted": inserted, "updated": updated, "skipped": skipped}

    def delete_ids(self, ids: list[int]) -> int:
        """Delete rows by primary key.  Returns count deleted."""
        clean = [int(i) for i in ids if i is not None]
        if not clean:
            return 0
        ph = ",".join("?" * len(clean))
        with self._conn() as conn:
            cur = conn.execute(
                f"DELETE FROM ui_translations WHERE id IN ({ph})", clean
            )
        return cur.rowcount

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """Return all rows as list of dicts."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ui_translations "
                "ORDER BY module, category, key"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_by_module(self, module: str) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ui_translations WHERE module=? "
                "ORDER BY category, key",
                (module,),
            ).fetchall()
        return [dict(r) for r in rows]

    def build_lookup(self, lang: str) -> dict[str, str]:
        """Return ``{key: translated_text}`` for the given language.

        Falls back to English (key itself) for missing translations.
        Only returns rows where the translation column is non-empty.
        """
        col = _LANG_COL.get(lang)
        if not col:
            return {}
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT key, {col} FROM ui_translations WHERE {col} != ''"
            ).fetchall()
        return {r["key"]: r[col] for r in rows}

    def list_modules(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT module FROM ui_translations ORDER BY module"
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def list_categories(self) -> list[str]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM ui_translations ORDER BY category"
            ).fetchall()
        return [r[0] for r in rows if r[0]]

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM ui_translations"
            ).fetchone()[0]

    def count_missing(self, lang: str = "zh") -> int:
        """Count rows where the translation for *lang* is empty."""
        col = _LANG_COL.get(lang, "zh_text")
        with self._conn() as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM ui_translations WHERE {col}=''"
            ).fetchone()[0]

    # ── Import / Export ───────────────────────────────────────────────────────

    def to_csv(self) -> str:
        """Export all translations as a UTF-8 CSV string."""
        buf = io.StringIO()
        writer = csv.DictWriter(
            buf,
            fieldnames=["key", "en_text", "zh_text", "category", "module"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(self.get_all())
        return buf.getvalue()

    def import_csv(self, csv_text: str,
                   skip_existing: bool = False) -> dict[str, int]:
        """Import translations from a CSV string.  Returns upsert counts."""
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        return self.upsert_many(rows, skip_existing=skip_existing)

    def to_dataframe(self):
        """Return all rows as a pandas DataFrame (for admin data_editor)."""
        import pandas as pd
        rows = self.get_all()
        cols = ["id", "key", "en_text", "zh_text", "category", "module",
                "updated_at", "updated_by"]
        if not rows:
            return pd.DataFrame(columns=cols)
        return pd.DataFrame(rows)[
            [c for c in cols if c in rows[0]]
        ]
