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

    # ── Bulk i18n coverage sweep (v2.26.x) — auto-generated, covers every t()/_th() key used across the app's tabs, admin panels, and section headers ─────────────────────────────────────────────────
    ('GIII', 'GIII', 'label', 'admin'),
    ('Sky East', '天东', 'label', 'admin'),
    ('Reference Data', '参考数据', 'label', 'admin'),
    ('Tracking', '生产跟踪', 'label', 'admin'),
    ('Releases', '更新日志', 'label', 'admin'),
    ('Users', '用户', 'label', 'admin'),
    ('船样要求', '船样要求', 'label', 'admin'),
    ('Settings', '设置', 'label', 'admin'),
    ('Too many failed attempts. Try again in', '登录尝试次数过多，请稍后重试：', 'label', 'admin'),
    ('Current password is incorrect.', '当前密码不正确。', 'label', 'admin'),
    ('Stage', '阶段', 'label', 'admin'),
    ('Planned', '计划', 'label', 'admin'),
    ('Actual', '实际', 'label', 'admin'),
    ('Exp.Days', '预计天数', 'label', 'admin'),
    ('Ready', '就绪', 'label', 'admin'),
    ('Waiting on:', '等待：', 'label', 'admin'),
    ('No prerequisites set', '未设置前置条件', 'label', 'admin'),
    ('Group A — Pre-Production (Parallel)', 'A组 — 生产前准备（并行）', 'label', 'admin'),
    ('Group B — Samples', 'B组 — 样品', 'label', 'admin'),
    ('Group C — Production (Sequential)', 'C组 — 生产（顺序）', 'label', 'admin'),
    ('Group D — Post-Production', 'D组 — 生产后', 'label', 'admin'),
    ('Optional Samples', '可选样品', 'label', 'admin'),
    ('Overall Notes', '总体备注', 'label', 'admin'),
    ('Booking Deadline', '预约截止日期', 'label', 'admin'),
    ('Reminder Days', '提醒天数', 'label', 'admin'),
    ('Booked', '已预约', 'label', 'admin'),
    ('Booking Date', '预约日期', 'label', 'admin'),
    ('Inspection Date', '验货日期', 'label', 'admin'),
    ('Result', '结果', 'label', 'admin'),
    ('Total Tracked', '跟踪总数', 'label', 'admin'),
    ('Delayed Stages', '延误阶段', 'label', 'admin'),
    ('Blocked', '受阻', 'label', 'admin'),
    ('Completed Today', '今日完成', 'label', 'admin'),
    ('QC Bookings Due', '待预约验货', 'label', 'admin'),
    ('No companies assigned to your account. Contact an administrator to be granted access.', '您的账户未分配任何公司。请联系管理员授予权限。', 'label', 'admin'),
    ('No tracked records yet.', '暂无跟踪记录。', 'label', 'admin'),
    ('No tracked records yet. Use **➕ Add New** first.', '暂无跟踪记录。请先使用 **➕ 新增**。', 'label', 'admin'),
    ('No tracked records yet. Use **➕ Add New** to start tracking a PO/style.', '暂无跟踪记录。使用 **➕ 新增** 开始跟踪某个订单/款式。', 'label', 'admin'),
    ('No tracked records yet — nothing to plan.', '暂无跟踪记录 — 无可排程内容。', 'label', 'admin'),
    ('All POs are already being tracked.', '所有订单均已在跟踪中。', 'label', 'admin'),
    ('Select PO / Style', '选择订单/款式', 'label', 'admin'),
    ('record(s) tracked', '条记录已跟踪', 'label', 'admin'),
    ('Confirm Delete', '确认删除', 'label', 'admin'),
    ('This cannot be undone.', '此操作无法撤销。', 'label', 'admin'),
    ('Record deleted.', '记录已删除。', 'label', 'admin'),
    ('Style:', '款式：', 'label', 'admin'),
    ('no style', '无款式', 'label', 'admin'),
    ('Dashboard placeholder', '仪表盘占位', 'label', 'admin'),
    ('Overview placeholder', '概览占位', 'label', 'admin'),
    ('Plan placeholder', '排程占位', 'label', 'admin'),
    ('record(s) loaded. Card grid lands in Stage 7.', '条记录已加载。卡片视图将在第7阶段推出。', 'label', 'admin'),
    ('record(s) loaded. Full table lands in Stage 7.', '条记录已加载。完整表格将在第7阶段推出。', 'label', 'admin'),
    ('record(s) available. Schedule calculator lands in Stage 8.', '条记录可用。排程计算器将在第8阶段推出。', 'label', 'admin'),
    ('Stage groups: 🧵 **A** pre-production prep (parallel) · 🧪 **B** samples · 🏭 **C** production (sequential) · 📦 **D** post-production/shipping. Fully-completed groups are collapsed — open them to review.', '阶段分组：🧵 **A** 生产前准备（并行）· 🧪 **B** 样品 · 🏭 **C** 生产（顺序）· 📦 **D** 生产后/发运。已全部完成的分组会折叠 — 展开可查看。', 'label', 'admin'),
    ('PO Tracker', '订单跟踪', 'label', 'admin'),
    ('One row per PO — all commercial fields for comparison and tracking.', '每个订单一行 — 包含所有商务字段，便于对比和跟踪。', 'label', 'admin'),
    ('No POs stored yet. Upload PDFs via the GIII tab to populate.', '暂无订单数据。请通过 GIII 选项卡上传 PDF 以填充。', 'label', 'admin'),
    ('Aggregated view of all orders across clients, filtered to your permitted companies.', '所有客户订单的汇总视图，已按您的权限公司筛选。', 'label', 'admin'),
    ('Columns to display', '显示的列', 'label', 'admin'),
    ("You don't have permission to view any company's orders. Contact an admin.", '您没有查看任何公司订单的权限。请联系管理员。', 'label', 'admin'),
    ('PO History', '订单历史', 'label', 'admin'),
    ('Generate / Export', '生成/导出', 'label', 'admin'),
    ('Generate Outputs', '生成输出', 'label', 'admin'),
    ('Generate Excel outputs from stored PO data', '根据已存订单数据生成 Excel 输出', 'label', 'admin'),
    ('Season', '季节', 'label', 'admin'),
    ('Columns', '列', 'label', 'admin'),
    ('Select POs', '选择订单', 'label', 'admin'),
    ('No POs match the current filters.', '没有订单符合当前筛选条件。', 'label', 'admin'),
    ('PO Number', '采购单号', 'label', 'admin'),
    ('PO Date', '下单日期', 'label', 'admin'),
    ('Ship Date', '发货日期', 'label', 'admin'),
    ('Customer Name', '客户名称', 'label', 'admin'),
    ('Ship To', '收货方', 'label', 'admin'),
    ('Vendor', '供应商', 'label', 'admin'),
    ('Description', '描述', 'label', 'admin'),
    ('Hanger Info', '衣架信息', 'label', 'admin'),
    ('Pack Ratio', '装箱比例', 'label', 'admin'),
    ('FOB Price', 'FOB价格', 'label', 'admin'),
    ('PO Metadata', '订单元数据', 'label', 'admin'),
    ('ETD', '预计出运日', 'label', 'admin'),
    ('HTS#', '海关编码', 'label', 'admin'),
    ('MSRP', '建议零售价', 'label', 'admin'),
    ('CPO', '客户订单号', 'label', 'admin'),
    ('Pack', '装箱', 'label', 'admin'),
    ('Total', '合计', 'label', 'admin'),
    ('size(s)', '个尺码', 'label', 'admin'),
    ('file(s)', '个文件', 'label', 'admin'),
    ('file(s) selected', '个文件已选择', 'label', 'admin'),
    ('total units', '总数量', 'label', 'admin'),
    ('PO(s)', '个订单', 'label', 'admin'),
    ('Building Excel…', '正在生成 Excel…', 'label', 'admin'),
    ('Parsing InforNexus PDFs…', '正在解析 InforNexus PDF…', 'label', 'admin'),
    ('Parsing KL PO PDFs…', '正在解析 KL 订单 PDF…', 'label', 'admin'),
    ('Parsing KL fax PDFs…', '正在解析 KL 传真 PDF…', 'label', 'admin'),
    ('Extracting PDFs and parsing POs…', '正在提取 PDF 并解析订单…', 'label', 'admin'),
    ('Extract & Compare', '提取并对比', 'label', 'admin'),
    ('Extract TK EU POs', '提取 TK EU 订单', 'label', 'admin'),
    ('▶  Extract KL POs', '▶  提取 KL 订单', 'label', 'admin'),
    ('▶  Extract MSG POs', '▶  提取 MSG 订单', 'label', 'admin'),
    ('Download Excel', '下载 Excel', 'label', 'admin'),
    ('⬇ Download Excel', '⬇ 下载 Excel', 'label', 'admin'),
    ('Download Comparison Excel', '下载对比 Excel', 'label', 'admin'),
    ('Download InforNexus Excel', '下载 InforNexus Excel', 'label', 'admin'),
    ('No POs could be parsed from the uploaded files.', '无法从上传的文件中解析出任何订单。', 'label', 'admin'),
    ('No POs could be parsed.', '无法解析任何订单。', 'label', 'admin'),
    ('Upload InforNexus PDFs to get started.', '上传 InforNexus PDF 以开始。', 'label', 'admin'),
    ('Upload InforNexus-format PO PDFs. Optionally also upload the matching KL fax PDFs to generate a side-by-side comparison.', '上传 InforNexus 格式的订单 PDF。可选：同时上传对应的 KL 传真 PDF 以生成并排对比。', 'label', 'admin'),
    ('Upload KL-format purchase order PDFs directly. The system parses PO fields, MSRP details, HTS codes and produces a formatted Excel workbook ready for download.', '直接上传 KL 格式的采购订单 PDF。系统会解析订单字段、建议零售价、海关编码，并生成可下载的格式化 Excel 工作簿。', 'label', 'admin'),
    ('Upload Outlook **.msg** emails (vendor fax copies from AS400). The system extracts the embedded PDF, parses PO fields, and produces a formatted Excel workbook ready for download.', '上传 Outlook **.msg** 邮件（来自 AS400 的供应商传真件）。系统会提取内嵌的 PDF，解析订单字段，并生成可下载的格式化 Excel 工作簿。', 'label', 'admin'),
    ('Upload Outlook **.msg** vendor fax emails for TK EU / Kostroma purchase orders (TJX UK). The system extracts the embedded PDF, parses PO fields, and produces a formatted Excel.', '上传 TK EU / Kostroma 采购订单（TJX UK）的 Outlook **.msg** 供应商传真邮件。系统会提取内嵌的 PDF，解析订单字段，并生成格式化的 Excel。', 'label', 'admin'),
    ('Upload one or more .msg vendor fax emails to get started.', '上传一个或多个 .msg 供应商传真邮件以开始。', 'label', 'admin'),
    ('Upload one or more KL PO PDF files to get started.', '上传一个或多个 KL 订单 PDF 文件以开始。', 'label', 'admin'),
    ('Upload one or more TK EU .msg vendor fax emails to get started.', '上传一个或多个 TK EU .msg 供应商传真邮件以开始。', 'label', 'admin'),
    ('Parse error in', '解析出错：', 'label', 'admin'),
    ('KL parse error', 'KL 解析错误', 'label', 'admin'),
    ('Could not open', '无法打开', 'label', 'admin'),
    ('No PDF attachment in', '未找到 PDF 附件：', 'label', 'admin'),
    ('skipped.', '已跳过。', 'label', 'admin'),
    ('**extract-msg** library not installed. Run `pip install extract-msg` and restart the app.', '未安装 **extract-msg** 库。请运行 `pip install extract-msg` 并重启应用。', 'label', 'admin'),
    ('**extract-msg** library not installed. Run `pip install extract-msg`.', '未安装 **extract-msg** 库。请运行 `pip install extract-msg`。', 'label', 'admin'),
    ('Memory', '内存', 'label', 'admin'),
    ('Free memory now', '立即释放内存', 'label', 'admin'),
    ('Freed', '已释放', 'label', 'admin'),
    ('Frees cached downloads and style-photo memory held for this session. Generated files must be re-created afterwards; style photos reload from disk automatically.', '释放本会话缓存的下载内容和款式照片内存。之后需要重新生成文件；款式照片会自动从磁盘重新加载。', 'label', 'admin'),
    ('Processing Results', '处理结果', 'label', 'admin'),
    ('New', '新增', 'label', 'admin'),
    ('Amended', '已修改', 'label', 'admin'),
    ('Duplicate(s)', '重复项', 'label', 'admin'),
    ('New Item(s)', '新增明细', 'label', 'admin'),
    ('Amended Item(s)', '已修改明细', 'label', 'admin'),
    ('item(s) total', '条明细合计', 'label', 'admin'),
    ('item(s) were identical to stored records and were skipped.', '条明细与已存记录相同，已跳过。', 'label', 'admin'),
    ('Style Photos', '款式照片', 'label', 'admin'),
    ('style(s)', '个款式', 'label', 'admin'),
    ('Front', '正面', 'label', 'admin'),
    ('Back', '背面', 'label', 'admin'),
    ('Saved', '已保存', 'label', 'admin'),
    ('What do you want to generate?', '您想生成什么？', 'label', 'admin'),
    ('No Sky East contracts saved yet. Upload files via the New Contracts tab.', '暂无天东合同记录。请通过“新合同”选项卡上传文件。', 'label', 'admin'),
    ('Colour source', '颜色来源', 'label', 'admin'),
    ('Colour resolution issues', '颜色匹配问题', 'label', 'admin'),
    ('Cross-comparison detail', '交叉对比明细', 'label', 'admin'),
    ('Recognition', '识别', 'label', 'admin'),
    ('records', '条记录', 'label', 'admin'),
    ('大货进度表 loaded for this run', '本次运行已加载大货进度表', 'label', 'admin'),
    ('Using saved 大货进度表 data', '使用已保存的大货进度表数据', 'label', 'admin'),
    ('Select one or more PC Nos. above, then click Generate.', '请在上方选择一个或多个合同号，然后点击“生成”。', 'label', 'admin'),
    ('Please select at least one PC No. above before generating.', '生成前请至少选择一个合同号。', 'label', 'admin'),
    ('Generates the main buy plan (Template) and fabric 核料 workbooks (Template_P) from the selected contracts, matching the VBA output format.', '根据所选合同生成主采购计划（Template）和面料核料工作簿（Template_P），与 VBA 输出格式一致。', 'label', 'admin'),
    ('Main buy plan -- one sheet per style + Index', '主采购计划 — 每款一个工作表 + 索引', 'label', 'admin'),
    ('Main buy plan — one sheet per style + Index', '主采购计划 — 每款一个工作表 + 索引', 'label', 'admin'),
    ('One workbook per fabric -- Color x Size per style', '每种面料一个工作簿 — 每款按颜色×尺码', 'label', 'admin'),
    ('One workbook per fabric — Color x Size per style', '每种面料一个工作簿 — 每款按颜色×尺码', 'label', 'admin'),
    ('Style · Photo · Seq · Body Part · Fabric Code · Composition — up to 4 rows per style', '款式 · 图片 · 序号 · 部位 · 面料编号 · 成分 — 每款最多 4 行', 'label', 'admin'),
    ('Upload a fabric mapping file to generate wash labels for all styles in that file. This file is used only for this download and is **not** saved to the database.', '上传面料映射文件，为文件中的所有款式生成洗水唛。该文件仅用于本次下载，**不会**保存到数据库。', 'label', 'admin'),
    ('All style totals match between buy plan and 核料 workbooks.', '采购计划与核料工作簿的所有款式合计一致。', 'label', 'admin'),
    ('Add the 面料编号 (HHN No.) via the **Missing Fields** tab or **📐 Reference Data**, then regenerate.', '请通过 **缺失字段** 选项卡或 **📐 参考数据** 添加面料编号（HHN No.），然后重新生成。', 'label', 'admin'),
    ('of these produced **no 核料 output** — most likely no fabric code on file', '其中部分**未生成核料输出** — 很可能是缺少面料编号', 'label', 'admin'),
    ('style(s) have **no fabric code** on file', '个款式**缺少面料编号**', 'label', 'admin'),
    ('style(s) have no photo in the buy plan', '个款式在采购计划中没有照片', 'label', 'admin'),
    ('style(s) have unit-total mismatches between buy plan and 核料 data.', '个款式的采购计划与核料数据的数量合计不一致。', 'label', 'admin'),
    ('核料 will skip them. Add the 面料编号 (HHN No.) via the **Missing Fields** tab or **📐 Reference Data** first.', '核料将跳过这些款式。请先通过 **缺失字段** 选项卡或 **📐 参考数据** 添加面料编号（HHN No.）。', 'label', 'admin'),
    ('Re-run **Process** on New Contracts to (re)extract images, or drop `<style>_front.png` into the image folder.', '在“新合同”上重新运行 **处理** 以（重新）提取图片，或将 `<style>_front.png` 放入图片文件夹。', 'label', 'admin'),
    ('unresolved colour(s) — see the log below', '个未匹配颜色 — 见下方日志', 'label', 'admin'),
    ("distinct colour(s) could not be resolved across recent buy plan runs -- see the cell comments on the Overview sheet's 未找到 cells, or the detail below.", '个不同颜色在近期采购计划运行中无法匹配 — 请查看总览表“未找到”单元格的批注，或下方明细。', 'label', 'admin'),
    ("distinct colour(s) could not be resolved across recent buy plan runs — see the cell comments on the Overview sheet's 未找到 cells, or the detail below.", '个不同颜色在近期采购计划运行中无法匹配 — 请查看总览表“未找到”单元格的批注，或下方明细。', 'label', 'admin'),
    ('Distinct style numbers (a style offered in several colours counts once).', '不同款号数（同一款式的多种颜色只计一次）。', 'label', 'admin'),
    ('Distinct style·colour combinations — a style in 3 colours counts as 3.', '不同“款式·颜色”组合数 — 一款 3 种颜色计为 3。', 'label', 'admin'),
    ('Style·Colours', '款式·颜色', 'label', 'admin'),
    ('uploaded via **📐 Reference Data → HHN Contract Progress**.', '通过 **📐 参考数据 → HHN 合同进度** 上传。', 'label', 'admin'),
    ('ℹ️ No saved 大货进度表 data for Sky East yet — upload it via **📐 Reference Data → HHN Contract Progress**.', 'ℹ️ 天东尚无已保存的大货进度表数据 — 请通过 **📐 参考数据 → HHN 合同进度** 上传。', 'label', 'admin'),
    ('ℹ️ The PC selection above is not used in this mode — pick styles below.', 'ℹ️ 此模式下不使用上方的合同号选择 — 请在下方选择款式。', 'label', 'admin'),
    ('ℹ️ The PC selection above is not used in this mode — the uploaded file decides the styles.', 'ℹ️ 此模式下不使用上方的合同号选择 — 由上传的文件决定款式。', 'label', 'admin'),
    ('🗂 Chinese colors sourced from 大货进度表 (PC No. · style · color match only).', '🗂 中文颜色来源于大货进度表（仅按合同号 · 款式 · 颜色匹配）。', 'label', 'admin'),
    ('**Next step →** open the **📦 Generate / Export** tab → **Buy Plan + 核料** to generate outputs (or **Contract History** to review saved data).', '**下一步 →** 打开 **📦 生成/导出** 选项卡 → **采购计划 + 核料** 生成输出（或打开 **合同历史** 查看已保存数据）。', 'label', 'admin'),
    ("↑ Sets the default colour source used when you **generate the Buy Plan** (📦 Generate / Export tab). It doesn't change this Process step.", '↑ 设置**生成采购计划**时使用的默认颜色来源（📦 生成/导出 选项卡）。不影响当前处理步骤。', 'label', 'admin'),
    ('💡 One-off for this run. To reuse the 大货进度表 across runs, save it in the **📐 Reference Data → HHN Contract Progress** tab.', '💡 仅本次运行有效。若要跨运行复用大货进度表，请在 **📐 参考数据 → HHN 合同进度** 选项卡中保存。', 'label', 'admin'),
    ('💡 This tab holds **style→fabric assignments** and the **大货进度表** (HHN contract progress). Fabric properties (composition · gsm · width) live in **🧵 Fabric DB**; colour translations live in **🎨 Colors**.', '💡 此选项卡保存**款式→面料对应关系**和**大货进度表**（HHN合同进度）。面料属性（成分·克重·门幅）在 **🧵 面料数据库** 中管理；颜色翻译在 **🎨 颜色** 中管理。', 'label', 'admin'),
    ('Style-Fabric Mapping', '款式-面料映射', 'label', 'admin'),
    ('HHN Contract Progress (大货进度表)', 'HHN合同进度（大货进度表）', 'label', 'admin'),
    ('Save style-to-fabric data independently of order processing. The stored mapping is used by wash labels and buy plans.', '独立于订单处理保存款式到面料的数据。已保存的映射用于洗水唛和采购计划。', 'label', 'admin'),
    ('Download Template', '下载模板', 'label', 'admin'),
    ('Company / Client', '公司/客户', 'label', 'admin'),
    ('Fabric mappings are stored per company. Select the client this mapping belongs to.', '面料映射按公司存储。请选择此映射所属的客户。', 'label', 'admin'),
    ('currently has fabric data for', '当前存有面料数据，涉及', 'label', 'admin'),
    ('style(s) stored in the database.', '个款式已存入数据库。', 'label', 'admin'),
    ('View stored styles', '查看已存款式', 'label', 'admin'),
    ('No fabric mapping stored yet for', '尚无面料映射数据：', 'label', 'admin'),
    ('Check for duplicate fabric mapping data', '检查重复的面料映射数据', 'label', 'admin'),
    ('Scans **all companies** for styles whose fabric combo is stored identically twice under different combo numbers — a leftover from an import that saw the same style row more than once. Left alone, each duplicate combo produces an extra, identical sheet in exports that iterate one sheet per combo (e.g. the Sky East Buy Plan).', '扫描**所有公司**，查找面料组合以不同组合编号重复存储两次的款式 — 这是导入时同一款式行被处理多次留下的遗留问题。若不清理，每个重复组合都会在按组合逐表导出（如天东采购计划）时产生一张多余的重复工作表。', 'label', 'admin'),
    ('Scan for duplicates', '扫描重复项', 'label', 'admin'),
    ('No duplicate fabric combos found.', '未发现重复的面料组合。', 'label', 'admin'),
    ('Found', '发现', 'label', 'admin'),
    ('duplicate combo group(s)', '组重复组合', 'label', 'admin'),
    ('across', '涉及', 'label', 'admin'),
    ('style(s).', '个款式。', 'label', 'admin'),
    ('Keep Combo', '保留组合', 'label', 'admin'),
    ('Remove Combo(s)', '移除组合', 'label', 'admin'),
    ('Fabric', '面料', 'label', 'admin'),
    ('Remove all duplicate combos shown above', '移除以上所有重复组合', 'label', 'admin'),
    ('Removed', '已移除', 'label', 'admin'),
    ('duplicate fabric part row(s).', '条重复面料明细。', 'label', 'admin'),
    ('Import mode', '导入模式', 'label', 'admin'),
    ('**Upsert**: each style in the file overwrites whatever is stored for that style.  \n**Add new only**: styles already in the DB are left unchanged.  \n**Replace all**: ALL existing fabric data for this company is deleted before import.', '**更新插入**：文件中每个款式都会覆盖该款式已存的数据。 \n**仅新增**：数据库中已存在的款式保持不变。 \n**全部替换**：导入前删除该公司所有已存的面料数据。', 'label', 'admin'),
    ('Style-Fabric mapping file', '款式-面料映射文件', 'label', 'admin'),
    ('Could not parse file:', '无法解析文件：', 'label', 'admin'),
    ('No valid style rows found in the file. Check that the header row matches the template format.', '文件中未找到有效的款式行。请检查表头是否与模板格式一致。', 'label', 'admin'),
    ('Fabric Codes', '面料编号数', 'label', 'admin'),
    ('No fabric codes', '无面料编号', 'label', 'admin'),
    ('Will update', '将更新', 'label', 'admin'),
    ('Up to date', '已是最新', 'label', 'admin'),
    ('Preview —', '预览 —', 'label', 'admin'),
    ('New styles', '新款式', 'label', 'admin'),
    ('Already up to date', '已是最新', 'label', 'admin'),
    ('Skipped (no codes)', '已跳过（无编号）', 'label', 'admin'),
    ('Show full style list', '显示完整款式列表', 'label', 'admin'),
    ('existing style(s) — will be skipped', '个已存在的款式 — 将被跳过', 'label', 'admin'),
    ('Import mode is **Add new only**: styles already in the database are left completely unchanged. None of these will be touched by this import.', '导入模式为 **仅新增**：数据库中已存在的款式将完全保持不变，本次导入不会影响它们。', 'label', 'admin'),
    ('Large changeset — open the panel below to review all', '变更较多 — 请展开下方面板查看全部', 'label', 'admin'),
    ('field-level changes before importing.', '个字段级变更后再导入。', 'label', 'admin'),
    ('Show differences for updating styles', '查看待更新款式的差异', 'label', 'admin'),
    ('of', '共', 'label', 'admin'),
    ('actually changed —', '个实际发生变化 —', 'label', 'admin'),
    ('field change(s))', '个字段变更）', 'label', 'admin'),
    ('💡 **(not in file — kept, not deleted)** rows stay in the database as-is under Upsert. Use **Replace all** if you need stale fabric slots actually removed.', '💡 标记为**（文件中不存在 — 保留未删除）**的行在“更新插入”模式下会原样保留在数据库中。如需真正移除过期的面料槽位，请使用**全部替换**。', 'label', 'admin'),
    ('No field-level differences — the stored data already matches the file.', '没有字段级差异 — 已存数据与文件一致。', 'label', 'admin'),
    ('**Replace all** will permanently delete ALL existing fabric data for', '**全部替换**将永久删除以下公司的所有已存面料数据：', 'label', 'admin'),
    ('I understand — delete existing data and replace with this file', '我已了解 — 删除已存数据并用此文件替换', 'label', 'admin'),
    ('Import Fabric Mapping', '导入面料映射', 'label', 'admin'),
    ('Saving fabric mapping...', '正在保存面料映射...', 'label', 'admin'),
    ('Deleted', '已删除', 'label', 'admin'),
    ('existing fabric part(s) for', '条已存面料明细，公司为', 'label', 'admin'),
    ('Skipped', '已跳过', 'label', 'admin'),
    ('existing style(s).', '个已存款式。', 'label', 'admin'),
    ('Nothing to import after applying the selected mode.', '按所选模式处理后没有可导入的内容。', 'label', 'admin'),
    ('fabric part(s) across', '条面料明细，涉及', 'label', 'admin'),
    ('style(s) for', '个款式，公司为', 'label', 'admin'),
    ('Import failed:', '导入失败：', 'label', 'admin'),
    ('Field', '字段', 'label', 'admin'),
    ('(new fabric slot)', '（新增面料槽位）', 'label', 'admin'),
    ('Stored', '已存', 'label', 'admin'),
    ('In File', '文件中', 'label', 'admin'),
    ('(slot removed)', '（槽位已移除）', 'label', 'admin'),
    ('(not in file — kept, not deleted)', '（文件中不存在 — 保留未删除）', 'label', 'admin'),
    ('(unchanged)', '（未变化）', 'label', 'admin'),
    ('HHN No.', 'HHN编号', 'label', 'admin'),
    ('Save 大货进度表 (HHN Contract Progress) data independently of order processing. Upload once here — every Sky East run and buy plan afterward automatically uses the saved data, no need to re-upload the same file every time. Pictures are not stored (text data only).', '独立于订单处理保存大货进度表（HHN合同进度）数据。在此上传一次后，之后每次天东处理和采购计划都会自动使用已保存的数据，无需每次重复上传。图片不会被存储（仅文本数据）。', 'label', 'admin'),
    ('Progress data is stored per company. Select the client this file belongs to.', '进度数据按公司存储。请选择此文件所属的客户。', 'label', 'admin'),
    ('currently has', '当前存有', 'label', 'admin'),
    ('progress', '进度', 'label', 'admin'),
    ('record(s) stored in the database.', '条记录已存入数据库。', 'label', 'admin'),
    ('View stored records', '查看已存记录', 'label', 'admin'),
    ('Contract No.', '合同号', 'label', 'admin'),
    ('Color (EN)', '颜色（英文）', 'label', 'admin'),
    ('Color (CN)', '颜色（中文）', 'label', 'admin'),
    ('PO#', '订单号', 'label', 'admin'),
    ('No progress data stored yet for', '尚无进度数据：', 'label', 'admin'),
    ('**Upsert**: each row in the file overwrites whatever is stored for that (PC No. · Style · Color) combination.  \n**Add new only**: combinations already in the DB are left unchanged.  \n**Replace all**: ALL existing progress data for this company is deleted before import.', '**更新插入**：文件中每一行都会覆盖该（合同号·款式·颜色）组合已存的数据。 \n**仅新增**：数据库中已存在的组合保持不变。 \n**全部替换**：导入前删除该公司所有已存的进度数据。', 'label', 'admin'),
    ('HHN Contract Progress file (大货进度表)', 'HHN合同进度文件（大货进度表）', 'label', 'admin'),
    ('No valid rows found in the file. Check that the header row matches the expected 大货进度表 format.', '文件中未找到有效行。请检查表头是否与预期的大货进度表格式一致。', 'label', 'admin'),
    ('No style', '无款式', 'label', 'admin'),
    ('New records', '新记录', 'label', 'admin'),
    ('Show full record list', '显示完整记录列表', 'label', 'admin'),
    ('existing record(s) — will be skipped', '条已存记录 — 将被跳过', 'label', 'admin'),
    ('Import mode is **Add new only**: records already in the database are left completely unchanged. None of these will be touched by this import.', '导入模式为 **仅新增**：数据库中已存在的记录将完全保持不变，本次导入不会影响它们。', 'label', 'admin'),
    ('Show differences for updating records', '查看待更新记录的差异', 'label', 'admin'),
    ('**Replace all** will permanently delete ALL existing progress data for', '**全部替换**将永久删除以下公司的所有已存进度数据：', 'label', 'admin'),
    ('record(s)) before importing.', '条记录）后再导入。', 'label', 'admin'),
    ('Import Progress Data', '导入进度数据', 'label', 'admin'),
    ('Saving progress data...', '正在保存进度数据...', 'label', 'admin'),
    ('existing record(s) for', '条已存记录，公司为', 'label', 'admin'),
    ('existing record(s).', '条已存记录。', 'label', 'admin'),
    ('progress record(s) for', '条进度记录，公司为', 'label', 'admin'),
    ('Fabric Detail', '面料明细', 'label', 'admin'),
    ('测试', '测试', 'label', 'admin'),
    ('色汇总', '色汇总', 'label', 'admin'),
    ('备注', '备注', 'label', 'admin'),
    ('Upsert — update existing + add new', '更新插入 — 更新已有并新增', 'label', 'admin'),
    ('Add new only — skip styles already in DB', '仅新增 — 跳过数据库中已有的款式', 'label', 'admin'),
    ('Add new only — skip records already in DB', '仅新增 — 跳过数据库中已有的记录', 'label', 'admin'),
    ('Replace all — clear existing first, then import', '全部替换 — 先清除已有数据，再导入', 'label', 'admin'),
    ('Zalando Buy Plan', 'Zalando采购计划', 'label', 'admin'),
    ('Upload one or more client Excel files (each with a **1.1.PO_Client** sheet). The system merges them, detects repeat orders, and generates the buy plan + Template_P files.', '上传一个或多个客户 Excel 文件（每个文件需包含 **1.1.PO_Client** 工作表）。系统会合并这些文件，检测重复订单，并生成采购计划 + Template_P 文件。', 'label', 'admin'),
    ('Upload client Excel file(s)', '上传客户 Excel 文件', 'label', 'admin'),
    ('Options', '选项', 'label', 'admin'),
    ('Source sheet name', '源工作表名称', 'label', 'admin'),
    ('Client profile', '客户配置', 'label', 'admin'),
    ('💡 Need a blank mapping template? Get it from **Admin → 📄 Templates → Client PO Mapping Template (1.1.PO_Client)**.', '💡 需要空白映射模板？请前往 **管理 → 📄 模板 → 客户订单映射模板 (1.1.PO_Client)** 获取。', 'label', 'admin'),
    ('大货进度表 (contract number lookup)', '大货进度表（合同号查询）', 'label', 'admin'),
    ('Upload the production-progress Excel (大货进度表) to auto-fill **合同号** in the buy plan.  Leave blank to skip.', '上传生产进度 Excel（大货进度表）以自动填充采购计划中的**合同号**。留空则跳过。', 'label', 'admin'),
    ('Upload one or more client Excel files to get started.', '上传一个或多个客户 Excel 文件以开始。', 'label', 'admin'),
    ('Mask prices in output files', '在输出文件中隐藏价格', 'label', 'admin'),
    ('Process Excel Files', '处理 Excel 文件', 'label', 'admin'),
    ('PO Files', '订单文件', 'label', 'admin'),
    ('Upload PO files', '上传订单文件', 'label', 'admin'),
    ('Reference files (Fabric Mapping)', '参考文件（面料映射）', 'label', 'admin'),
    ('AI Extraction (DeepSeek)', 'AI 提取（DeepSeek）', 'label', 'admin'),
    ('Use the DeepSeek API to extract PO fields instead of the built-in regex parser.  Useful for non-standard layouts or when you want AI-assisted field recognition.', '使用 DeepSeek API 提取订单字段，替代内置的正则解析器。适用于非标准版式或需要 AI 辅助识别字段的场景。', 'label', 'admin'),
    ('Use DeepSeek AI extraction', '使用 DeepSeek AI 提取', 'label', 'admin'),
    ('API Key (leave blank to use admin-configured key)', 'API 密钥（留空则使用管理员配置的密钥）', 'label', 'admin'),
    ('No DeepSeek API key configured. Set one in Admin → Settings or enter above.', '未配置 DeepSeek API 密钥。请在 管理 → 设置 中配置，或在上方输入。', 'label', 'admin'),
    ('Model', '模型', 'label', 'admin'),
    ('key ending', '密钥末尾', 'label', 'admin'),
    ('Upload one or more PO files (PDF or Excel) to begin.', '上传一个或多个订单文件（PDF 或 Excel）以开始。', 'label', 'admin'),
    ('GIII PO Processing', 'GIII 订单处理', 'label', 'admin'),
    ('Upload PDF or Excel PO files — client and format are auto-detected per file. PDFs produce Buy Plan · Color Plan · PO Summary · Cross-Check. Excel files produce HHP Buy Plan · Template_P workbooks.', '上传 PDF 或 Excel 订单文件 — 系统会自动识别每个文件的客户和格式。PDF 会生成采购计划·配色计划·订单汇总·交叉核对；Excel 会生成 HHP 采购计划·Template_P 工作簿。', 'label', 'admin'),
    ('Overview', '概览', 'label', 'admin'),
    ('Download PO Tracker (.xlsx)', '下载订单跟踪表 (.xlsx)', 'label', 'admin'),
    ('GIII — full PO list', 'GIII — 完整订单列表', 'label', 'admin'),
    ('Sky East — full item list', '天东 — 完整明细列表', 'label', 'admin'),
    ('Download Full Summary', '下载完整汇总', 'label', 'admin'),
    ('Filter and select POs below, then click **Generate All Outputs** to rebuild Buy Plan · Color Plan · PO Summary · Cross-Check from the stored data — no re-upload required.', '在下方筛选并选择订单，然后点击 **生成所有输出**，即可从已存数据重新生成采购计划·配色计划·订单汇总·交叉核对 — 无需重新上传。', 'label', 'admin'),
    ('No POs stored yet. Upload PDFs via the **Upload** tab to get started.', '暂无订单数据。请通过 **上传** 选项卡上传 PDF 以开始。', 'label', 'admin'),
    ('available after filters', '个符合筛选条件', 'label', 'admin'),
    ('Select one or more PO numbers…', '选择一个或多个订单号…', 'label', 'admin'),
    ('PO(s) selected', '个订单已选', 'label', 'admin'),
    ('Generate All Outputs', '生成所有输出', 'label', 'admin'),
    ('Color Plan Only', '仅配色计划', 'label', 'admin'),
    ('Building color plan…', '正在生成配色计划…', 'label', 'admin'),
    ('No size data found for selected POs.', '所选订单未找到尺码数据。', 'label', 'admin'),
    ('PO Summary Only', '仅订单汇总', 'label', 'admin'),
    ('Building PO summary…', '正在生成订单汇总…', 'label', 'admin'),
    ('KL Format Summary', 'KL 格式汇总', 'label', 'admin'),
    ('Building KL-format summary…', '正在生成 KL 格式汇总…', 'label', 'admin'),
    ('**KL summary consistency check failed** — the file may have missing rows:', '**KL 汇总一致性检查失败** — 文件可能缺少行：', 'label', 'admin'),
    ('Create Buy Plan (生产计划单)', '创建采购计划（生产计划单）', 'label', 'admin'),
    ('Building production plan…', '正在生成生产计划…', 'label', 'admin'),
    ('No size data found for the selected POs.', '所选订单未找到尺码数据。', 'label', 'admin'),
    ('Production plan generation failed:', '生产计划生成失败：', 'label', 'admin'),
    ('Download Color Plan (.xlsx)', '下载配色计划 (.xlsx)', 'label', 'admin'),
    ('Download PO Summary (.xlsx)', '下载订单汇总 (.xlsx)', 'label', 'admin'),
    ('Download KL Format Summary (.xlsx)', '下载 KL 格式汇总 (.xlsx)', 'label', 'admin'),
    ('Download Buy Plan — 生产计划单 (.xlsx)', '下载采购计划 — 生产计划单 (.xlsx)', 'label', 'admin'),
    ('PO Tracker — commercial detail view', '订单跟踪 — 商务明细视图', 'label', 'admin'),
    ('One row per PO with all extracted commercial fields. Filter, pick columns, and download.', '每个订单一行，包含所有提取的商务字段。可筛选、选列并下载。', 'label', 'admin'),
    ('No POs stored yet. Upload PDFs via the **Upload** tab.', '暂无订单数据。请通过 **上传** 选项卡上传 PDF。', 'label', 'admin'),
    ('UI Translation Management', '界面翻译管理', 'label', 'admin'),
    ('keys', '个键', 'label', 'admin'),
    ('missing Chinese translations', '缺少中文翻译', 'label', 'admin'),
    ('Changes take effect immediately after saving.', '保存后立即生效。', 'label', 'admin'),
    ('Browse & Edit', '浏览与编辑', 'label', 'admin'),
    ('Browse &amp; Edit', '浏览与编辑', 'label', 'admin'),
    ('Add Key', '新增键', 'label', 'admin'),
    ('Import / Export', '导入/导出', 'label', 'admin'),
    ('Seed Defaults', '初始化默认值', 'label', 'admin'),
    ('Module', '模块', 'label', 'admin'),
    ('Category', '分类', 'label', 'admin'),
    ('Search (key / Chinese text)', '搜索（键/中文文本）', 'label', 'admin'),
    ('type to filter...', '输入以筛选...', 'label', 'admin'),
    ('No translations match the current filter.', '没有符合当前筛选条件的翻译。', 'label', 'admin'),
    ('row(s) shown', '行已显示', 'label', 'admin'),
    ('Save changes', '保存更改', 'label', 'admin'),
    ('translation(s). Cache cleared.', '条翻译。缓存已清除。', 'label', 'admin'),
    ('Delete selected keys', '删除选中的键', 'label', 'admin'),
    ('Keys to delete', '待删除的键', 'label', 'admin'),
    ('key(s). Cache cleared.', '个键。缓存已清除。', 'label', 'admin'),
    ('Add a new translation key', '新增翻译键', 'label', 'admin'),
    ('Key (English text, used in UI)', '键（界面中使用的英文文本）', 'label', 'admin'),
    ('Chinese translation (中文)', '中文翻译', 'label', 'admin'),
    ('Key cannot be empty.', '键不能为空。', 'label', 'admin'),
    ('Added key', '已新增键', 'label', 'admin'),
    ('Cache cleared.', '缓存已清除。', 'label', 'admin'),
    ('Download all translations as a CSV file.', '将所有翻译下载为 CSV 文件。', 'label', 'admin'),
    ('Generate CSV', '生成 CSV', 'label', 'admin'),
    ('Download translations.csv', '下载 translations.csv', 'label', 'admin'),
    ('Upload a CSV with columns: `key`, `en_text`, `zh_text`, `category`, `module`.  Existing keys are **updated** unless the *Skip existing* option is checked.', '上传包含以下列的 CSV 文件：`key`、`en_text`、`zh_text`、`category`、`module`。除非勾选*跳过已存在*选项，否则已存在的键将被**更新**。', 'label', 'admin'),
    ('CSV file', 'CSV 文件', 'label', 'admin'),
    ('Skip existing keys', '跳过已存在的键', 'label', 'admin'),
    ('Import complete', '导入完成', 'label', 'admin'),
    ('inserted', '已插入', 'label', 'admin'),
    ('updated', '已更新', 'label', 'admin'),
    ('skipped', '已跳过', 'label', 'admin'),
    ('Seed built-in default translations', '初始化内置默认翻译', 'label', 'admin'),
    ('The system ships with', '系统内置了', 'label', 'admin'),
    ('built-in translation strings.  Run this to populate any that are missing from the database — already-present keys are never overwritten.', '条翻译字符串。运行此操作可填充数据库中缺失的部分 — 已存在的键永远不会被覆盖。', 'label', 'admin'),
    ('Total keys in DB', '数据库中的键总数', 'label', 'admin'),
    ('Missing Chinese (zh)', '缺少中文', 'label', 'admin'),
    ('Seed missing defaults', '初始化缺失的默认值', 'label', 'admin'),
    ('new key(s)', '个新键', 'label', 'admin'),
    ('already existed.', '已存在。', 'label', 'admin'),
    ('Force re-seed (overwrite existing)', '强制重新初始化（覆盖已有）', 'label', 'admin'),
    ('Resets ALL built-in strings to their default Chinese translations, overwriting any manual edits to those keys.', '将所有内置字符串重置为默认中文翻译，覆盖对这些键的任何手动编辑。', 'label', 'admin'),
    ('Force re-seed (destructive)', '强制重新初始化（破坏性操作）', 'label', 'admin'),
    ('Force re-seed all defaults', '强制重新初始化所有默认值', 'label', 'admin'),
    ('Force-seeded', '已强制初始化', 'label', 'admin'),
    ('Clear translation cache', '清除翻译缓存', 'label', 'admin'),
    ('Forces the next page load to re-read all translations from the DB.', '强制下次页面加载时从数据库重新读取所有翻译。', 'label', 'admin'),
    ('Clear cache', '清除缓存', 'label', 'admin'),
    ('Translation cache cleared.', '翻译缓存已清除。', 'label', 'admin'),
    ('Upload Sky East order file(s)', '上传天东订单文件', 'label', 'admin'),
    ('Config SKU file (Zalando PO report xlsx)', 'Config SKU 文件（Zalando 订单报表 xlsx）', 'label', 'admin'),
    ('HHN contract No. file', 'HHN 合同号文件', 'label', 'admin'),
    ('Upload fabric mapping independently in the **📐 Reference Data** tab.', '请在 **📐 参考数据** 选项卡中单独上传面料映射。', 'label', 'admin'),
    ('Download Masked Files (.zip)', '下载已隐藏价格的文件 (.zip)', 'label', 'admin'),
    ('all tabs', '全部选项卡', 'label', 'admin'),
    ('companies:', '公司：', 'label', 'admin'),
    ('all (admin)', '全部（管理员）', 'label', 'admin'),
    ('tabs:', '选项卡：', 'label', 'admin'),
    ('admin', '管理员', 'label', 'admin'),
    ('user', '用户', 'label', 'admin'),
    ('Set role', '设置角色', 'label', 'admin'),
    ('Cannot demote the last admin account.', '无法降级最后一个管理员账户。', 'label', 'admin'),
    ('Role updated.', '角色已更新。', 'label', 'admin'),
    ('Allowed companies (leave empty = all for admin)', '允许的公司（留空 = 管理员可访问全部）', 'label', 'admin'),
    ('Set companies', '设置公司', 'label', 'admin'),
    ('Companies updated.', '公司已更新。', 'label', 'admin'),
    ('Delete user', '删除用户', 'label', 'admin'),
    ('Allowed tabs (leave empty = all tabs)', '允许的选项卡（留空 = 全部选项卡）', 'label', 'admin'),
    ('Set allowed tabs', '设置允许的选项卡', 'label', 'admin'),
    ('Allowed tabs updated.', '允许的选项卡已更新。', 'label', 'admin'),
    ('Email (used for sending generated files)', '邮箱（用于发送生成的文件）', 'label', 'admin'),
    ('Set email', '设置邮箱', 'label', 'admin'),
    ('Email updated.', '邮箱已更新。', 'label', 'admin'),
    ('Email (optional)', '邮箱（可选）', 'label', 'admin'),
    ('Create user', '创建用户', 'label', 'admin'),
    ('created.', '已创建。', 'label', 'admin'),
    ('Username and password are required.', '用户名和密码为必填项。', 'label', 'admin'),
    ('| Placeholder | Description |', '| 占位符 | 说明 |', 'label', 'admin'),
    ('|---|---|', '|---|---|', 'label', 'admin'),
    ('| `{{factory}}` | Factory name + code |', '| `{{factory}}` | 工厂名称 + 代码 |', 'label', 'admin'),
    ('| `{{style}}` | Style number |', '| `{{style}}` | 款号 |', 'label', 'admin'),
    ('| `{{xfactory_date}}` | X-Factory Date (X-Port minus 10 days) |', '| `{{xfactory_date}}` | 出厂日期（离厂日期减10天）|', 'label', 'admin'),
    ('| `{{xport_date}}` | Orig X-Port Date |', '| `{{xport_date}}` | 原始离厂日期 |', 'label', 'admin'),
    ('| `{{coo}}` | Country of Origin |', '| `{{coo}}` | 原产地 |', 'label', 'admin'),
    ('| `{{division}}` | Division code + name |', '| `{{division}}` | 分部代码 + 名称 |', 'label', 'admin'),
    ('| `{{created_at}}` | Timestamp when the file was generated |', '| `{{created_at}}` | 文件生成时间戳 |', 'label', 'admin'),
    ('| `{{data_start}}` | **Marker only** — marks the row where the data table starts |', '| `{{data_start}}` | **仅作标记** — 标示数据表格的起始行 |', 'label', 'admin'),
    ('**Template lookup order:** client-specific → `default` → built-in format', '**模板查找顺序：** 客户专属 → `default`（默认）→ 内置格式', 'label', 'admin'),
    ('**Tips:**', '**提示：**', 'label', 'admin'),
    ('- Rows *above* `{{data_start}}` are your metadata / branding area.', '- `{{data_start}}` *上方*的行为元数据/品牌信息区域。', 'label', 'admin'),
    ('- `{{data_start}}` row is overwritten with column headers (PO Number, Style, Color…).', '- `{{data_start}}` 所在行会被列标题（订单号、款式、颜色……）覆盖。', 'label', 'admin'),
    ('- Data rows and the grand-total row are written immediately below.', '- 数据行和总计行紧接着写在下方。', 'label', 'admin'),
    ('**If you still want to try Outlook:**', '**如果您仍想尝试使用 Outlook：**', 'label', 'admin'),
    ('1. Enable 2FA at https://account.microsoft.com/security', '1. 在 https://account.microsoft.com/security 启用双重验证', 'label', 'admin'),
    ('2. Create App Password → Advanced security options → App passwords', '2. 创建应用密码 → 高级安全选项 → 应用密码', 'label', 'admin'),
    ('3. Enable POP/IMAP at https://outlook.live.com/mail/0/options/mail/accounts/popImap', '3. 在 https://outlook.live.com/mail/0/options/mail/accounts/popImap 启用 POP/IMAP', 'label', 'admin'),
    ('4. Use your full email as Username and the App Password below', '4. 用户名填写完整邮箱地址，密码填写下方的应用密码', 'label', 'admin'),
    ('**⚡ Resend — 100 emails/day free, 3,000/month**', '**⚡ Resend — 每天100封免费，每月3,000封**', 'label', 'admin'),
    ('1. Sign up at https://resend.com', '1. 在 https://resend.com 注册', 'label', 'admin'),
    ('2. Go to **API Keys → Create API Key**', '2. 进入 **API Keys → Create API Key**', 'label', 'admin'),
    ('3. **Username:** `resend` (literally)', '3. **用户名：** `resend`（原样填写）', 'label', 'admin'),
    ('4. **Password:** paste your API key', '4. **密码：** 粘贴您的 API 密钥', 'label', 'admin'),
    ('5. **Sender:** must use a verified domain (e.g. `you@yourdomain.com`)\n   — free accounts can also use `onboarding@resend.dev` for testing', '5. **发件人：** 必须使用已验证的域名（例如 `you@yourdomain.com`）\n   — 免费账户测试时也可使用 `onboarding@resend.dev`', 'label', 'admin'),
    ('Uses SSL on port 465 (configured automatically).', '使用 465 端口的 SSL（自动配置）。', 'label', 'admin'),
    ('**🏢 Office 365 setup**', '**🏢 Office 365 设置**', 'label', 'admin'),
    ('- Username: your full work email address', '- 用户名：您完整的工作邮箱地址', 'label', 'admin'),
    ('- Password: your Microsoft 365 password (or App Password if MFA is on)', '- 密码：您的 Microsoft 365 密码（若已开启多因素验证，则使用应用密码）', 'label', 'admin'),
    ('- Your IT admin must have **SMTP AUTH enabled** for your mailbox', '- 需要您的 IT 管理员为该邮箱**启用 SMTP AUTH**', 'label', 'admin'),
    ('**💌 Brevo — 300 emails/day free (best free tier)**', '**💌 Brevo — 每天300封免费（最佳免费额度）**', 'label', 'admin'),
    ('1. Sign up at https://brevo.com', '1. 在 https://brevo.com 注册', 'label', 'admin'),
    ('2. Go to **Settings → SMTP & API → Generate a new SMTP key**', '2. 进入 **Settings → SMTP & API → Generate a new SMTP key**', 'label', 'admin'),
    ('3. **Username:** your Brevo account email address', '3. **用户名：** 您的 Brevo 账户邮箱地址', 'label', 'admin'),
    ('4. **Password:** paste the SMTP key (not your login password)', '4. **密码：** 粘贴 SMTP 密钥（不是登录密码）', 'label', 'admin'),
    ("5. **Sender:** any address you've verified in Brevo", '5. **发件人：** 任意已在 Brevo 验证过的地址', 'label', 'admin'),
    ('300 emails/day free — 3× more than SendGrid.', '每天300封免费 — 是 SendGrid 的3倍。', 'label', 'admin'),
    ('**📨 SendGrid — 100 emails/day free**', '**📨 SendGrid — 每天100封免费**', 'label', 'admin'),
    ('2. **Settings → API Keys → Create API Key** → Full Access → Create', '2. **Settings → API Keys → Create API Key** → 选择 Full Access → Create', 'label', 'admin'),
    ('3. **Username:** `apikey` (literally)', '3. **用户名：** `apikey`（原样填写）', 'label', 'admin'),
    ('5. **Sender:** verify at https://app.sendgrid.com/settings/sender_auth', '5. **发件人：** 在 https://app.sendgrid.com/settings/sender_auth 验证', 'label', 'admin'),
    ('**🔴 Gmail setup**', '**🔴 Gmail 设置**', 'label', 'admin'),
    ('1. Enable 2-Step Verification: https://myaccount.google.com/security', '1. 启用两步验证：https://myaccount.google.com/security', 'label', 'admin'),
    ('2. Create App Password: https://myaccount.google.com/apppasswords', '2. 创建应用密码：https://myaccount.google.com/apppasswords', 'label', 'admin'),
    ('3. Username: your Gmail address', '3. 用户名：您的 Gmail 地址', 'label', 'admin'),
    ('4. Password: the 16-character App Password (not your normal password)', '4. 密码：16位应用密码（不是您平时使用的密码）', 'label', 'admin'),
    ('AI Extraction — DeepSeek', 'AI 提取 — DeepSeek', 'label', 'admin'),
    ('API key / app password', 'API 密钥/应用密码', 'label', 'admin'),
    ('Action', '操作', 'label', 'admin'),
    ('Add company', '新增公司', 'label', 'admin'),
    ('Add new company', '新增公司', 'label', 'admin'),
    ('Added', '已新增', 'label', 'admin'),
    ('After', '之后', 'label', 'admin'),
    ('All items are complete -- no missing fields.', '所有明细均完整 — 无缺失字段。', 'label', 'admin'),
    ('All items have Fabric No. and HHN Contract No.', '所有明细均已有面料编号和HHN合同号。', 'label', 'admin'),
    ('Always included in standard outputs.', '始终包含在标准输出中。', 'label', 'admin'),
    ('Application Settings', '应用设置', 'label', 'admin'),
    ('Assign rows to client', '将行分配给客户', 'label', 'admin'),
    ('Auto-detected columns', '自动检测到的列', 'label', 'admin'),
    ('Auto-fill & Save', '自动填充并保存', 'label', 'admin'),
    ('Auto-filled and saved', '已自动填充并保存', 'label', 'admin'),
    ('Before', '之前', 'label', 'admin'),
    ('Blank / Sample Templates (download only)', '空白/示例模板（仅供下载）', 'label', 'admin'),
    ('Body-part column', '部位列', 'label', 'admin'),
    ('Brands', '品牌', 'label', 'admin'),
    ('Brevo will accept the connection but **silently drop the email** without delivering it.', 'Brevo 会接受连接，但**会静默丢弃邮件**而不予投递。', 'label', 'admin'),
    ('**Fix:** Fill in the **Sender** field above with an email address you have verified in your Brevo account (e.g. `orders@yourdomain.com`), then click **Save**.', '**解决方法：** 在上方**发件人**字段中填入您已在 Brevo 账户中验证过的邮箱地址（例如 `orders@yourdomain.com`），然后点击**保存**。', 'label', 'admin'),
    ('Verify senders at: https://app.brevo.com/senders', '验证发件人：https://app.brevo.com/senders', 'label', 'admin'),
    ('Cannot connect:', '无法连接：', 'label', 'admin'),
    ('Cannot read template:', '无法读取模板：', 'label', 'admin'),
    ('Case-insensitive — "navy", "NAVY" both match.', '不区分大小写 — “navy”与“NAVY”均可匹配。', 'label', 'admin'),
    ('Change fabric master DB path', '更改面料主数据库路径', 'label', 'admin'),
    ('Change history', '变更历史', 'label', 'admin'),
    ('Changed:', '已变更：', 'label', 'admin'),
    ('Chinese Color Mapping — Default Source', '中文颜色映射 — 默认来源', 'label', 'admin'),
    ('Clear audit history', '清除审计历史', 'label', 'admin'),
    ('Cleared', '已清除', 'label', 'admin'),
    ('Click **Confirm clear** to proceed, or Cancel to keep it.', '点击**确认清除**继续，或点击取消以保留。', 'label', 'admin'),
    ('Client', '客户', 'label', 'admin'),
    ('Client PO Mapping Template (1.1.PO_Client)', '客户订单映射模板 (1.1.PO_Client)', 'label', 'admin'),
    ('Clients', '客户数', 'label', 'admin'),
    ('Color Name Translation', '颜色名称翻译', 'label', 'admin'),
    ('Colour Recognition — Local + AI Enhance', '颜色识别 — 本地 + AI 增强', 'label', 'admin'),
    ('Colour recognition mode', '颜色识别模式', 'label', 'admin'),
    ('Colour recognition mode saved:', '颜色识别模式已保存：', 'label', 'admin'),
    ('Column', '列', 'label', 'admin'),
    ('Column mapping', '列映射', 'label', 'admin'),
    ('Column name as it appears in Infor Nexus PO files.', '该字段在 Infor Nexus 订单文件中的列名。', 'label', 'admin'),
    ('Column name in legacy GIII Excel PO files.', '该字段在旧版 GIII Excel 订单文件中的列名。', 'label', 'admin'),
    ('Column-header overrides', '列标题覆盖', 'label', 'admin'),
    ('Companies are pre-seeded. Add new clients here when on-boarding them.', '公司列表已预置。新增客户接入时请在此添加。', 'label', 'admin'),
    ('Config', '配置', 'label', 'admin'),
    ('Config file:', '配置文件：', 'label', 'admin'),
    ('Configure the outgoing mail server. Settings are saved to `auth/smtp_settings.json` (excluded from git).', '配置发件邮件服务器。设置将保存到 `auth/smtp_settings.json`（已从 git 中排除）。', 'label', 'admin'),
    ('Configured:', '已配置：', 'label', 'admin'),
    ('Confirm clear', '确认清除', 'label', 'admin'),
    ('Connected —', '已连接 —', 'label', 'admin'),
    ('Connecting to', '正在连接', 'label', 'admin'),
    ('Controls how Sky East order-file colours (e.g. a two-tone cell like "(dark blue)(white)") are matched against 大货进度表 / the internal colour DB. **Local only** relies purely on regex detection and never makes a network call. **Local + AI Enhance** falls back to the DeepSeek API, but *only* when a colour has already failed to resolve locally — it is never called for anything else (dates, quantities, other fields), to avoid spending API tokens unnecessarily. Uses the same DeepSeek API key/model configured above.', '控制天东订单文件中的颜色（例如“(dark blue)(white)”这类双色单元格）如何与大货进度表/内部颜色数据库匹配。**仅本地**完全依赖正则检测，不发起网络请求。**本地 + AI 增强**在本地匹配失败*时*才会调用 DeepSeek API 兜底 — 绝不用于其他内容（日期、数量等字段），以避免不必要的 API 消耗。使用上方配置的同一个 DeepSeek API 密钥/模型。', 'label', 'admin'),
    ('Controls the column order of sizes in buy-plan, color-plan, PO-summary, and cross-check exports. Sizes not in this list are appended at the end in the order they appear in the data. Changes take effect on the next export.', '控制采购计划、配色计划、订单汇总及交叉核对导出文件中尺码列的顺序。不在此列表中的尺码将按数据中出现的顺序附加在末尾。更改将在下次导出时生效。', 'label', 'admin'),
    ('Controls the pre-selected option for the **Chinese color mapping source** radio on the Sky East tab.  New sessions start with this value; users can still change it within their session.', '控制天东选项卡上**中文颜色映射来源**单选框的预选项。新会话将以此值为起点，用户仍可在会话中自行更改。', 'label', 'admin'),
    ('Current saved config (JSON)', '当前已保存的配置（JSON）', 'label', 'admin'),
    ('Current size order', '当前尺码顺序', 'label', 'admin'),
    ('DB Field (internal)', '数据库字段（内部）', 'label', 'admin'),
    ('Data start row', '数据起始行', 'label', 'admin'),
    ('Data-table position', '数据表格位置', 'label', 'admin'),
    ('DeepSeek API Key', 'DeepSeek API 密钥', 'label', 'admin'),
    ('Default color source saved:', '默认颜色来源已保存：', 'label', 'admin'),
    ('Default extraction method', '默认提取方式', 'label', 'admin'),
    ('Default source', '默认来源', 'label', 'admin'),
    ('Delete all entries for:', '删除以下条目：', 'label', 'admin'),
    ('Delete filtered', '删除已筛选项', 'label', 'admin'),
    ('Delete the rows whose 🗑 checkbox is ticked.', '删除勾选了🗑复选框的行。', 'label', 'admin'),
    ('Delete this template', '删除此模板', 'label', 'admin'),
    ('Deleted template for', '已删除模板：', 'label', 'admin'),
    ('Download / delete an existing client template', '下载/删除已有的客户模板', 'label', 'admin'),
    ('Download current', '下载当前文件', 'label', 'admin'),
    ('Download fabric mapping template', '下载面料映射模板', 'label', 'admin'),
    ('Download mapping as Excel', '以 Excel 格式下载映射表', 'label', 'admin'),
    ('Download mapping template', '下载映射模板', 'label', 'admin'),
    ('Download sample buy-plan template', '下载采购计划示例模板', 'label', 'admin'),
    ('Download template (.xlsx)', '下载模板 (.xlsx)', 'label', 'admin'),
    ("Each client can have its own buy-plan Excel template. When exporting, the system picks the template matching the PO's company name. **default** is used as a fallback when no client-specific template exists. Without any template the built-in format is used.", '每个客户可以拥有自己的采购计划 Excel 模板。导出时，系统会根据订单的公司名称匹配对应模板。当不存在客户专属模板时，将使用 **default**（默认）模板作为后备；若连默认模板也不存在，则使用内置格式。', 'label', 'admin'),
    ('Each slot has the row number and three columns: body part, HHN code, and the 综合标识 Key (display_key) cell.', '每个槽位包含行号及三列：部位、HHN编号，以及综合标识Key（display_key）单元格。', 'label', 'admin'),
    ('Edit cells below and click **Save Changes**:', '编辑下方单元格后点击**保存更改**：', 'label', 'admin'),
    ('Email (SMTP) Settings', '邮件（SMTP）设置', 'label', 'admin'),
    ('English colour', '英文颜色', 'label', 'admin'),
    ('Enter an absolute path to the `fabric_master.db` file.  All apps sharing this file must have read access to the same location (e.g. a mapped network drive or shared folder).', '输入 `fabric_master.db` 文件的绝对路径。共享此文件的所有应用都必须能读取同一位置（例如映射的网络驱动器或共享文件夹）。', 'label', 'admin'),
    ('Every insert / update / delete on the colour-translation table is recorded here.  Filter by client / brand / English colour, then the most recent changes (newest first) are shown.  Use this to see who changed what and when.', '颜色翻译表上的每一次新增/更新/删除都会记录在此。可按客户/品牌/英文颜色筛选，最近的更改会优先显示（最新在前）。可用于查看谁在何时做了什么更改。', 'label', 'admin'),
    ('Excel column letter (A, B, …, AA …) or 1-based number.', 'Excel 列字母（A、B、……、AA……）或从1开始的数字。', 'label', 'admin'),
    ('Excel sheet name', 'Excel 工作表名称', 'label', 'admin'),
    ('Export Date', '出运日期', 'label', 'admin'),
    ('Export all (.xlsx)', '全部导出 (.xlsx)', 'label', 'admin'),
    ('FOB (USD)', 'FOB（美元）', 'label', 'admin'),
    ('Fabric Master Database', '面料主数据库', 'label', 'admin'),
    ('Fabric key field', '面料主键字段', 'label', 'admin'),
    ('Fabric lookup', '面料查询', 'label', 'admin'),
    ('Fabric master DB path', '面料主数据库路径', 'label', 'admin'),
    ('Fabric reference data from **面料统计表.xlsx**. Upload a new version of the file below to refresh all records. Use the search box to look up any fabric by code, composition, or supplier.', '面料参考数据来源于 **面料统计表.xlsx**。在下方上传新版本文件即可刷新所有记录。可使用搜索框按编号、成分或供应商查找面料。', 'label', 'admin'),
    ('Fabric slots', '面料槽位', 'label', 'admin'),
    ('Failed to save template:', '保存模板失败：', 'label', 'admin'),
    ('Failed to save:', '保存失败：', 'label', 'admin'),
    ('Failed:', '失败：', 'label', 'admin'),
    ('File types (pdf, excel)', '文件类型（pdf、excel）', 'label', 'admin'),
    ('Fill in Host, Username and Password/API Key, then click **Save** before testing.', '请先填写主机、用户名和密码/API密钥，点击**保存**后再测试。', 'label', 'admin'),
    ('Filter by PC No.', '按合同号筛选', 'label', 'admin'),
    ('Filter by brand', '按品牌筛选', 'label', 'admin'),
    ('Filter by client', '按客户筛选', 'label', 'admin'),
    ('Filter by client and/or brand. Edit cells directly, then click Save.', '按客户和/或品牌筛选。可直接编辑单元格，然后点击保存。', 'label', 'admin'),
    ('First sheet is the per-style master. Use {{data_start}} to mark where the data table starts. Placeholders: {{factory}}, {{style}}, {{xfactory_date}}, {{xport_date}}, {{coo}}, {{division}}, {{created_at}}', '第一个工作表为每款主表。使用 {{data_start}} 标记数据表格起始位置。可用占位符：{{factory}}、{{style}}、{{xfactory_date}}、{{xport_date}}、{{coo}}、{{division}}、{{created_at}}', 'label', 'admin'),
    ('Format IDs (comma-separated)', '格式ID（逗号分隔）', 'label', 'admin'),
    ('Free-text explanation for this field.', '该字段的自由文本说明。', 'label', 'admin'),
    ('GIII Buy-Plan Sample Template', 'GIII 采购计划示例模板', 'label', 'admin'),
    ('GIII Per-Client Buy-Plan Templates', 'GIII 各客户采购计划模板', 'label', 'admin'),
    ('Generate mapping template', '生成映射模板', 'label', 'admin'),
    ('HHN column', 'HHN编号列', 'label', 'admin'),
    ('Header row', '表头行', 'label', 'admin'),
    ('Header row (fallback if no {{data_start}})', '表头行（无 {{data_start}} 时的后备值）', 'label', 'admin'),
    ('How Sky East calls this field in their own files. Shown in row 1 of dual-header Excel downloads.', '天东在其自身文件中对该字段的称呼。显示在双表头 Excel 下载文件的第1行。', 'label', 'admin'),
    ('How other apps connect to this database', '其他应用如何连接此数据库', 'label', 'admin'),
    ('How the From address appears. Defaults to Username when empty.', '发件地址的显示方式。留空时默认使用用户名。', 'label', 'admin'),
    ('If you previously used this app before the centralised fabric DB was introduced, your fabric data is still in `po_history.db`.  Click below to copy it into the dedicated `fabric_master.db`.', '如果您在引入集中式面料数据库之前就已使用本应用，您的面料数据可能仍在 `po_history.db` 中。点击下方按钮将其复制到专用的 `fabric_master.db`。', 'label', 'admin'),
    ('Import from progress tracker (大货进度表)', '从进度跟踪表导入（大货进度表）', 'label', 'admin'),
    ('Import progress tracker', '导入进度跟踪表', 'label', 'admin'),
    ('Imported:', '已导入：', 'label', 'admin'),
    ('Infor Nexus (client alias)', 'Infor Nexus（客户别名）', 'label', 'admin'),
    ('Internal database / DataFrame column name. Do not rename — this must match the code.', '内部数据库/DataFrame 列名。请勿重命名 — 必须与代码保持一致。', 'label', 'admin'),
    ('Invalid config:', '配置无效：', 'label', 'admin'),
    ('It will be used on the next export for matching POs.', '下次导出匹配订单时将使用该模板。', 'label', 'admin'),
    ('Items with Missing Fields', '缺失字段的明细', 'label', 'admin'),
    ('Legacy GIII (client alias)', '旧版 GIII（客户别名）', 'label', 'admin'),
    ('Load colors from PO database', '从订单数据库加载颜色', 'label', 'admin'),
    ('Max rows', '最大行数', 'label', 'admin'),
    ('Meta columns', '元数据列', 'label', 'admin'),
    ('Migrate', '迁移', 'label', 'admin'),
    ('Migrate existing fabric data from main app DB', '从主应用数据库迁移已有面料数据', 'label', 'admin'),
    ('Migrating…', '正在迁移…', 'label', 'admin'),
    ('Migration complete.', '迁移完成。', 'label', 'admin'),
    ('Missing Composition or Cuttable Width', '缺少成分或有效门幅', 'label', 'admin'),
    ('Must be valid JSON. Saved as UTF-8.', '必须是有效的 JSON。以 UTF-8 编码保存。', 'label', 'admin'),
    ('Must have columns: client, en_color, cn_color (optional: color_code, notes)', '必须包含以下列：client、en_color、cn_color（可选：color_code、notes）', 'label', 'admin'),
    ('Name (unique key)', '名称（唯一键）', 'label', 'admin'),
    ('Named fields', '已命名字段', 'label', 'admin'),
    ('New sessions will start with this selection.', '新会话将以此选项为起点。', 'label', 'admin'),
    ('New value', '新值', 'label', 'admin'),
    ('Next export will use the new template.', '下次导出将使用新模板。', 'label', 'admin'),
    ('No audit entries match the current filter.', '没有符合当前筛选条件的审计记录。', 'label', 'admin'),
    ('No color translations yet. Use the import section above or add rows in the editor below.', '尚无颜色翻译数据。请使用上方的导入区，或在下方编辑器中添加行。', 'label', 'admin'),
    ('No fabric data yet. Upload a 面料统计表.xlsx file above to get started.', '尚无面料数据。请在上方上传 面料统计表.xlsx 文件以开始。', 'label', 'admin'),
    ('No fabric records found in `po_history.db` — nothing to migrate.', '`po_history.db` 中未找到面料记录 — 无需迁移。', 'label', 'admin'),
    ('No fabrics match your search.', '没有符合搜索条件的面料。', 'label', 'admin'),
    ('No items missing composition or cuttable width.', '没有明细缺少成分或有效门幅。', 'label', 'admin'),
    ('No new colors found — all', '未发现新颜色 — 全部', 'label', 'admin'),
    ('No per-client templates installed yet — all GIII exports use the built-in format.', '尚未安装任何客户专属模板 — 所有 GIII 导出均使用内置格式。', 'label', 'admin'),
    ('No rows updated.', '没有行被更新。', 'label', 'admin'),
    ('No template installed yet.', '尚未安装模板。', 'label', 'admin'),
    ('Notes (free-text, stored with the config)', '备注（自由文本，随配置一并保存）', 'label', 'admin'),
    ('Old value', '旧值', 'label', 'admin'),
    ('On conflict:', '冲突时：', 'label', 'admin'),
    ("Optional JSON file that lets you remap column-header text to the canonical Sky East field names without editing the template. Leave empty to delete and fall back to the template's own headers.", '可选的 JSON 文件，允许您在不修改模板的情况下将列标题文本重新映射到标准的天东字段名。留空即删除并回退到模板自身的表头。', 'label', 'admin'),
    ("Our company's standard output heading used in ALL export files.", '我方标准输出标题，用于所有导出文件。', 'label', 'admin'),
    ('Output Column Mapping', '输出列映射', 'label', 'admin'),
    ('PO size rows and', '订单尺码行以及', 'label', 'admin'),
    ('PO(s) are missing factory name or export date. These fields are extracted from the source PDF. If they remain blank after re-processing, the source file may not contain them.', '个订单缺少工厂名称或出运日期。这些字段是从源 PDF 中提取的。若重新处理后仍为空，说明源文件中可能本就没有这些信息。', 'label', 'admin'),
    ('PO(s).', '个订单。', 'label', 'admin'),
    ('POs with Missing Fields', '缺失字段的订单', 'label', 'admin'),
    ('POs,', '个订单，', 'label', 'admin'),
    ('Password / API Key / App Password', '密码/API密钥/应用密码', 'label', 'admin'),
    ("Per-client buy-plan template layouts. Edit the column mapping, data-start row, and fabric-slot rows for each pipeline — saved values override the auto-detection that runs against the .xlsx template. Leave a row blank to fall back to the template's auto-detected position.", '各客户采购计划模板布局。可为每条流水线编辑列映射、数据起始行和面料槽位行 — 已保存的值会覆盖对 .xlsx 模板运行的自动检测。行留空则回退到模板自动检测的位置。', 'label', 'admin'),
    ('Permanently delete all audit-log entries.  Does NOT touch the colour-translation rows themselves.', '永久删除所有审计日志条目。不会影响颜色翻译表本身的数据行。', 'label', 'admin'),
    ('Pick a file above first.', '请先在上方选择文件。', 'label', 'admin'),
    ("Pick the new workbook here, then click 'Save' below to overwrite the file on disk.", '在此选择新工作簿，然后点击下方“保存”以覆盖磁盘上的文件。', 'label', 'admin'),
    ('Pipeline', '流水线', 'label', 'admin'),
    ('Pipeline Buy-Plan Layouts', '流水线采购计划布局', 'label', 'admin'),
    ('Placeholder reference (GIII per-client templates)', '占位符参考（GIII 各客户模板）', 'label', 'admin'),
    ('Port', '端口', 'label', 'admin'),
    ("Pre-built blank templates to hand to clients or to use as a starting point. These are generated on demand — they aren't stored on disk.", '预先制作的空白模板，可提供给客户或作为起始模板使用。这些模板按需生成 — 不存储在磁盘上。', 'label', 'admin'),
    ('Pre-fill client headers', '预填充客户表头', 'label', 'admin'),
    ('Primary file type', '主要文件类型', 'label', 'admin'),
    ('Progress lookup', '进度查询', 'label', 'admin'),
    ('Quick setup — choose your mail provider:', '快速设置 — 选择您的邮件服务商：', 'label', 'admin'),
    ('Reading', '正在读取', 'label', 'admin'),
    ('Reads the **颜色 / 主标颜色 / 中文颜色** columns (and **BRAND** when present) from a 大货进度表 workbook and upserts every unique combination into this table.  English colour names are case-insensitive — "NAVY", "navy" and "Navy" all collapse into the same row stored as "Navy".', '从大货进度表工作簿中读取**颜色 / 主标颜色 / 中文颜色**列（若存在则一并读取 **BRAND**），并将每个唯一组合更新插入到此表中。英文颜色名不区分大小写 — “NAVY”、“navy”与“Navy”都会归并为同一行，存储为“Navy”。', 'label', 'admin'),
    ('Ready-made sample with all `{{placeholders}}` — rename and upload it to a client slot in the **GIII Per-Client Buy-Plan Templates** section above.', '包含全部 `{{占位符}}` 的现成示例 — 重命名后上传到上方 **GIII 各客户采购计划模板** 区域中的客户槽位。', 'label', 'admin'),
    ('Records in fabric_master.db', 'fabric_master.db 中的记录数', 'label', 'admin'),
    ('Records in po_history.db', 'po_history.db 中的记录数', 'label', 'admin'),
    ('Reference files in session:', '本次会话中的参考文件：', 'label', 'admin'),
    ('Reference table mapping English color names to Chinese (中文颜色) by client and brand (e.g. GIII / Karl Lagerfeld, Sky East / Anna Field). Use the editor below to add/edit entries, or bulk-import from Excel.', '按客户和品牌（例如 GIII / Karl Lagerfeld，天东 / Anna Field）将英文颜色名映射为中文颜色的参考表。可使用下方编辑器新增/编辑条目，或从 Excel 批量导入。', 'label', 'admin'),
    ('Reload from disk', '从磁盘重新加载', 'label', 'admin'),
    ('Replace template', '替换模板', 'label', 'admin'),
    ('Replace template (.xlsx)', '替换模板 (.xlsx)', 'label', 'admin'),
    ('Required', '必填', 'label', 'admin'),
    ('Reset to Defaults', '重置为默认值', 'label', 'admin'),
    ('Reset to built-in defaults.', '重置为内置默认值。', 'label', 'admin'),
    ('Reset to defaults', '重置为默认值', 'label', 'admin'),
    ("Restricts which top-level tabs this user sees. 'Sky East — Buy Plan only' hides Contract History / Missing Fields and pins Generate/Export to Buy Plan mode.", '限制该用户可见的顶层选项卡。“天东 — 仅采购计划”会隐藏合同历史/缺失字段，并将生成/导出固定为采购计划模式。', 'label', 'admin'),
    ('Row', '行', 'label', 'admin'),
    ('Row number of the column-header row (0 = leave to auto-detect).', '列标题所在行号（0 = 交由自动检测）。', 'label', 'admin'),
    ('Row number of the first data row (0 = header_row + 1, or auto-detected).', '首个数据行的行号（0 = 表头行+1，或自动检测）。', 'label', 'admin'),
    ('Row where column headers (PO Number, Style, Color…) will be written.', '列标题（订单号、款式、颜色……）将写入的行号。', 'label', 'admin'),
    ('Run import', '执行导入', 'label', 'admin'),
    ('SMTP Host', 'SMTP 主机', 'label', 'admin'),
    ('Save AI settings', '保存 AI 设置', 'label', 'admin'),
    ('Save Changes', '保存更改', 'label', 'admin'),
    ('Save colour recognition mode', '保存颜色识别模式', 'label', 'admin'),
    ('Save config', '保存配置', 'label', 'admin'),
    ('Save failed:', '保存失败：', 'label', 'admin'),
    ('Save layout', '保存布局', 'label', 'admin'),
    ('Save path', '保存路径', 'label', 'admin'),
    ('Save replacement', '保存替换文件', 'label', 'admin'),
    ('Save size order', '保存尺码顺序', 'label', 'admin'),
    ('Save template', '保存模板', 'label', 'admin'),
    ('Saved to', '已保存到', 'label', 'admin'),
    ('Saved →', '已保存 →', 'label', 'admin'),
    ('Saved.', '已保存。', 'label', 'admin'),
    ('Saved. All exports will use the updated labels.', '已保存。所有导出将使用更新后的标签。', 'label', 'admin'),
    ('Scanned', '已扫描', 'label', 'admin'),
    ('Scanning PO database for color names…', '正在扫描订单数据库中的颜色名称…', 'label', 'admin'),
    ('Scans all', '扫描全部', 'label', 'admin'),
    ('Search by Quality No., composition, supplier, or fabric structure', '按品质编号、成分、供应商或面料结构搜索', 'label', 'admin'),
    ('Seeded', '已初始化', 'label', 'admin'),
    ('Select a client or brand to delete', '选择要删除的客户或品牌', 'label', 'admin'),
    ('Select template', '选择模板', 'label', 'admin'),
    ("Select the client this template applies to. 'default' is the shared fallback for any client without a specific template.", '选择此模板适用的客户。“default”（默认）是没有专属模板的客户所使用的共享后备模板。', 'label', 'admin'),
    ('Send test', '发送测试', 'label', 'admin'),
    ('Send test email to', '发送测试邮件至', 'label', 'admin'),
    ('Sender (From address)', '发件人（发件地址）', 'label', 'admin'),
    ('Settings here apply to all users.  Individual users can still override per-session where allowed.', '此处设置适用于所有用户。在允许的情况下，各用户仍可在自己的会话中覆盖设置。', 'label', 'admin'),
    ('Showing', '显示', 'label', 'admin'),
    ('Single place to upload, replace, download, and amend every template the app uses. Sky East templates are at the top, GIII per-client buy-plan templates in the middle, and blank/sample template downloads at the bottom.', '在此统一上传、替换、下载和修改应用中使用的所有模板。天东模板位于顶部，GIII 各客户采购计划模板位于中部，空白/示例模板下载位于底部。', 'label', 'admin'),
    ('Size code', '尺码代码', 'label', 'admin'),
    ('Size columns', '尺码列', 'label', 'admin'),
    ('Size list cannot be empty.', '尺码列表不能为空。', 'label', 'admin'),
    ('Sky East (client alias)', '天东（客户别名）', 'label', 'admin'),
    ('Sky East Templates', '天东模板', 'label', 'admin'),
    ('Sky_East_config.json contents', 'Sky_East_config.json 内容', 'label', 'admin'),
    ('Standard Label ✏️', '标准标签 ✏️', 'label', 'admin'),
    ('Style-Fabric Mapping Template (HHN codes)', '款式-面料映射模板（HHN编号）', 'label', 'admin'),
    ('Template file', '模板文件', 'label', 'admin'),
    ('Template file (.xlsx)', '模板文件 (.xlsx)', 'label', 'admin'),
    ('Template file is missing. Upload one to install it.', '缺少模板文件。请上传一个以安装。', 'label', 'admin'),
    ('Template file:', '模板文件：', 'label', 'admin'),
    ('Template replaced.', '模板已替换。', 'label', 'admin'),
    ('Template saved for', '模板已保存，客户为', 'label', 'admin'),
    ('Template saved.', '模板已保存。', 'label', 'admin'),
    ('Test API key', '测试 API 密钥', 'label', 'admin'),
    ('Test connection', '测试连接', 'label', 'admin'),
    ('Test email delivered to', '测试邮件已投递至', 'label', 'admin'),
    ('Testing…', '测试中…', 'label', 'admin'),
    ("The fabric master lives in its **own dedicated SQLite file** so that other applications can share the same data.  Point any app's `FabricMasterStore` (or copy `fabric_master_client.py`) at the path below to get read access.", '面料主数据保存在**专用的独立 SQLite 文件**中，以便其他应用共享同一份数据。将任意应用的 `FabricMasterStore`（或复制 `fabric_master_client.py`）指向下方路径即可获得读取权限。', 'label', 'admin'),
    ('These items have a Fabric No. but the **Fabric DB** does not have their composition or cuttable width. Import the 面料统计表 in the **Fabric DB** tab to resolve them.', '这些明细已有面料编号，但**面料数据库**中缺少其成分或有效门幅数据。请在**面料数据库**选项卡中导入面料统计表以补全。', 'label', 'admin'),
    ('These mappings are detected automatically each time the template is used. No config file needed — just ensure the header row labels match standard names.', '每次使用模板时都会自动检测这些映射。无需配置文件 — 只需确保表头标签与标准名称一致即可。', 'label', 'admin'),
    ('These two workbooks drive the Sky East buy-plan and 核料 exporters. They live on disk at `data/buyplan_templates/` and are loaded directly by the Sky East exporter — replace them here whenever the layout changes.', '这两个工作簿驱动天东采购计划和核料导出器。它们保存在磁盘 `data/buyplan_templates/` 目录下，并由天东导出器直接加载 — 每当布局变化时请在此处替换。', 'label', 'admin'),
    ('This table controls every column heading in all export files (Excel downloads, reports). Edit the **Standard Label** to rename a column across all outputs instantly. Client alias columns show what that client calls the same field in their input files — useful for the dual-header row in Sky East Excel downloads. Add rows for new fields; delete rows to hide them from outputs.', '此表控制所有导出文件（Excel 下载、报表）中的每个列标题。编辑**标准标签**即可立即在所有输出中重命名该列。客户别名列展示该客户在其输入文件中对同一字段的称呼 — 对天东 Excel 下载的双表头行很有用。新增行以添加新字段；删除行以在输出中隐藏该字段。', 'label', 'admin'),
    ('This will erase the entire change history', '此操作将清除全部变更历史', 'label', 'admin'),
    ('Total entries', '总条目数', 'label', 'admin'),
    ("Two-row header workbook used by the GIII Excel pipeline to import a client's PO data. Pre-fill the row-1 client headers for a known client below.", 'GIII Excel 流水线用于导入客户订单数据的双行表头工作簿。可在下方为已知客户预填第1行的客户表头。', 'label', 'admin'),
    ('Updated', '已更新', 'label', 'admin'),
    ('Upload / replace a client template', '上传/替换客户模板', 'label', 'admin'),
    ('Upload Excel (.xlsx)', '上传 Excel (.xlsx)', 'label', 'admin'),
    ('Upload template (.xlsx)', '上传模板 (.xlsx)', 'label', 'admin'),
    ('Upload 大货进度表 workbook (.xlsx)', '上传大货进度表工作簿 (.xlsx)', 'label', 'admin'),
    ('Use STARTTLS (recommended)', '使用 STARTTLS（推荐）', 'label', 'admin'),
    ('Used by both the GIII Reference panel and the Sky East tab to map each style to up to 4 HHN fabric codes. Same template for both pipelines.', 'GIII 参考面板和天东选项卡均使用此模板，将每个款式映射到最多4个HHN面料编号。两条流水线共用同一模板。', 'label', 'admin'),
    ('User', '用户', 'label', 'admin'),
    ('Users can also switch per-session on the GIII upload tab.', '用户也可以在 GIII 上传选项卡中按会话切换。', 'label', 'admin'),
    ('When (UTC)', '时间（UTC）', 'label', 'admin'),
    ('When enabled, PO PDFs are sent to the **DeepSeek API** for field extraction instead of (or alongside) the built-in regex parser.  Requires a DeepSeek API key from [platform.deepseek.com](https://platform.deepseek.com).', '启用后，订单 PDF 将发送至 **DeepSeek API** 进行字段提取，替代（或配合）内置的正则解析器。需要从 [platform.deepseek.com](https://platform.deepseek.com) 获取的 DeepSeek API 密钥。', 'label', 'admin'),
    ('Which company should the imported rows be filed under?', '导入的行应归入哪个公司？', 'label', 'admin'),
    ('Which fabric_master field to write into the fabric-key column.', '要写入面料主键列的 fabric_master 字段。', 'label', 'admin'),
    ('Who', '操作人', 'label', 'admin'),
    ('Your current From address is', '您当前的发件地址为', 'label', 'admin'),
    ('added.', '已新增。', 'label', 'admin'),
    ('already existed (preserved).', '已存在（已保留）。', 'label', 'admin'),
    ('as', '作为', 'label', 'admin'),
    ('at row', '位于第', 'label', 'admin'),
    ('audit entries.', '条审计记录。', 'label', 'admin'),
    ('color(s) were already in the table.', '个颜色已在表中。', 'label', 'admin'),
    ('data table will start there.', '数据表格将从此处开始。', 'label', 'admin'),
    ('deleted (defaults restored)', '已删除（已恢复默认）', 'label', 'admin'),
    ('e.g. Style, PO Number, Color, 合同号', '例如：Style、PO Number、Color、合同号', 'label', 'admin'),
    ('edit, reorder rows, or add new sizes below:', '在下方编辑、调整行顺序或新增尺码：', 'label', 'admin'),
    ('empty — neither Username nor Sender is set', '为空 — 用户名和发件人均未设置', 'label', 'admin'),
    ('entries', '条记录', 'label', 'admin'),
    ('entries for', '条记录，对象为', 'label', 'admin'),
    ('entries.', '条记录。', 'label', 'admin'),
    ('extra fields → Excel column letter', '附加字段 → Excel 列字母', 'label', 'admin'),
    ('fabric_master.db now has', 'fabric_master.db 现有', 'label', 'admin'),
    ('found — expand to verify', '已找到 — 展开以核实', 'label', 'admin'),
    ('from', '来自', 'label', 'admin'),
    ('item(s) can be auto-filled.', '条明细可自动填充。', 'label', 'admin'),
    ('item(s).', '条明细。', 'label', 'admin'),
    ('items for distinct color names and adds any not already in this table. Existing Chinese translations are preserved.', '个条目，提取不重复的颜色名称并添加表中尚不存在的部分。已有的中文翻译将被保留。', 'label', 'admin'),
    ('logical field → Excel column letter', '逻辑字段 → Excel 列字母', 'label', 'admin'),
    ('match(es) shown (search limit: 300)', '个匹配结果（搜索上限：300）', 'label', 'admin'),
    ('new', '个新增', 'label', 'admin'),
    ('new color(s) —', '个新颜色 —', 'label', 'admin'),
    ('one row per fabric header in the template', '模板中每个面料表头对应一行', 'label', 'admin'),
    ('records → fabric_master.db', '条记录 → fabric_master.db', 'label', 'admin'),
    ('records.', '条记录。', 'label', 'admin'),
    ('row(s).', '行。', 'label', 'admin'),
    ('saved to', '已保存到', 'label', 'admin'),
    ('selected row(s).', '行已选中。', 'label', 'admin'),
    ('sheet(s):', '个工作表：', 'label', 'admin'),
    ('size label → Excel column letter', '尺码标签 → Excel 列字母', 'label', 'admin'),
    ('sizes.', '个尺码。', 'label', 'admin'),
    ('skipped (blank colour)', '已跳过（颜色为空）', 'label', 'admin'),
    ('style(s)) before importing.', '个款式）后再导入。', 'label', 'admin'),
    ('takes effect on next export.', '将在下次导出时生效。', 'label', 'admin'),
    ('this is the SMTP login username, NOT a verified sender', '这是 SMTP 登录用户名，并非已验证的发件人', 'label', 'admin'),
    ('•••••• (saved — leave blank to keep)', '•••••• （已保存 — 留空即保持不变）', 'label', 'admin'),
    ('ℹ️ Drag rows to reorder. The row index shown is the column position (0-based). Delete a row to remove a size from the known order (it will still appear in exports, just after all known sizes).', 'ℹ️ 拖动行即可调整顺序。显示的行索引即列位置（从0开始）。删除某行即可将该尺码移出已知顺序（导出时仍会出现，只是排在所有已知尺码之后）。', 'label', 'admin'),
    ('ℹ️ No standard column headers detected — will use sequential write.', 'ℹ️ 未检测到标准列标题 — 将按顺序写入。', 'label', 'admin'),
    ('ℹ️ Path is overridden by the `FABRIC_DB_PATH` environment variable.  Clear the env var to use the path configured below.', 'ℹ️ 该路径已被环境变量 `FABRIC_DB_PATH` 覆盖。请清除该环境变量以使用下方配置的路径。', 'label', 'admin'),
    ('⚠️ **Brevo: Sender address is not set correctly.**', '⚠️ **Brevo：发件人地址设置不正确。**', 'label', 'admin'),
    ('⚠️ **Microsoft has disabled basic SMTP auth for most personal Outlook/Hotmail accounts** — even App Passwords are blocked in many regions.', '⚠️ **Microsoft 已对大多数个人 Outlook/Hotmail 账户禁用基础 SMTP 身份验证** — 在许多地区，即使使用应用密码也会被拦截。', 'label', 'admin'),
    ('If you keep getting error 535, switch to **📨 SendGrid** (free) or **🔴 Gmail** instead.', '如果持续收到 535 错误，请改用 **📨 SendGrid**（免费）或 **🔴 Gmail**。', 'label', 'admin'),
    ('⚠️ No DeepSeek API key configured above — AI Enhance will have no effect until one is saved.', '⚠️ 上方尚未配置 DeepSeek API 密钥 — 在保存密钥之前，AI 增强不会生效。', 'label', 'admin'),
    ('⚠️ No `{{data_start}}` found. If this is a Sky East template, upload it via the **Sky East Templates** section above instead. Otherwise, set the header row manually below.', '⚠️ 未找到 `{{data_start}}`。如果这是天东模板，请改用上方的**天东模板**区域上传。否则，请在下方手动设置表头行。', 'label', 'admin'),
    ('⚠️ This will delete ALL existing color translations before importing.', '⚠️ 此操作将在导入前删除所有已存在的颜色翻译。', 'label', 'admin'),
    ('✅ AI extraction settings saved.', '✅ AI 提取设置已保存。', 'label', 'admin'),
    ('✅ All stored POs are complete — no missing fields.', '✅ 所有已存订单信息均完整 — 无缺失字段。', 'label', 'admin'),
    ('✅ Path saved to `fabric_config.json`.  Reload the page to apply.', '✅ 路径已保存到 `fabric_config.json`。请重新加载页面以生效。', 'label', 'admin'),
    ('综合标识 Key column', '综合标识 Key 列', 'label', 'admin'),
    ('💡 This tab holds **colour translations** only. Fabric properties live in **🧵 Fabric DB**; style→fabric assignments and the 大货进度表 live in **📐 Reference Data**.', '💡 此选项卡仅保存**颜色翻译**数据。面料属性在 **🧵 面料数据库** 中管理；款式→面料对应关系及大货进度表在 **📐 参考数据** 中管理。', 'label', 'admin'),
    ('💡 This tab holds **fabric properties** (composition · gsm · width per HHN code). Style→fabric assignments and the 大货进度表 live in **📐 Reference Data**; colour translations live in **🎨 Colors**.', '💡 此选项卡保存**面料属性**（每个HHN编号的成分·克重·门幅）。款式→面料对应关系及大货进度表在 **📐 参考数据** 中管理；颜色翻译在 **🎨 颜色** 中管理。', 'label', 'admin'),
    ('\n| Placeholder | Description |\n|---|---|\n| `{{factory}}` | Factory name + code |\n| `{{style}}` | Style number |\n| `{{xfactory_date}}` | X-Factory Date (X-Port minus 10 days) |\n| `{{xport_date}}` | Orig X-Port Date |\n| `{{coo}}` | Country of Origin |\n| `{{division}}` | Division code + name |\n| `{{created_at}}` | Timestamp when the file was generated |\n| `{{data_start}}` | **Marker only** — marks the row where the data table starts |\n\n**Template lookup order:** client-specific → `default` → built-in format\n\n**Tips:**\n- Rows *above* `{{data_start}}` are your metadata / branding area.\n- `{{data_start}}` row is overwritten with column headers (PO Number, Style, Color…).\n- Data rows and the grand-total row are written immediately below.\n        ', '\n| 占位符 | 说明 |\n|---|---|\n| `{{factory}}` | 工厂名称 + 代码 |\n| `{{style}}` | 款号 |\n| `{{xfactory_date}}` | 出厂日期（离厂日期减10天）|\n| `{{xport_date}}` | 原始离厂日期 |\n| `{{coo}}` | 原产地 |\n| `{{division}}` | 分部代码 + 名称 |\n| `{{created_at}}` | 文件生成时间戳 |\n| `{{data_start}}` | **仅作标记** — 标示数据表格的起始行 |\n\n**模板查找顺序：** 客户专属 → `default`（默认）→ 内置格式\n\n**提示：**\n- `{{data_start}}` *上方*的行为元数据/品牌信息区域。\n- `{{data_start}}` 所在行会被列标题（订单号、款式、颜色……）覆盖。\n- 数据行和总计行紧接着写在下方。\n        ', 'label', 'admin'),
    ('⚠️ **Microsoft has disabled basic SMTP auth for most personal Outlook/Hotmail accounts** — even App Passwords are blocked in many regions.\n\nIf you keep getting error 535, switch to **📨 SendGrid** (free) or **🔴 Gmail** instead.', '⚠️ **Microsoft 已对大多数个人 Outlook/Hotmail 账户禁用基础 SMTP 身份验证** — 在许多地区，即使使用应用密码也会被拦截。\n\n如果持续收到 535 错误，请改用 **📨 SendGrid**（免费）或 **🔴 Gmail**。', 'label', 'admin'),
    ('**If you still want to try Outlook:**\n\n1. Enable 2FA at https://account.microsoft.com/security\n2. Create App Password → Advanced security options → App passwords\n3. Enable POP/IMAP at https://outlook.live.com/mail/0/options/mail/accounts/popImap\n4. Use your full email as Username and the App Password below', '**如果您仍想尝试使用 Outlook：**\n\n1. 在 https://account.microsoft.com/security 启用双重验证\n2. 创建应用密码 → 高级安全选项 → 应用密码\n3. 在 https://outlook.live.com/mail/0/options/mail/accounts/popImap 启用 POP/IMAP\n4. 用户名填写完整邮箱地址，密码填写下方的应用密码', 'label', 'admin'),
    ('**🏢 Office 365 setup**\n\n- Username: your full work email address\n- Password: your Microsoft 365 password (or App Password if MFA is on)\n- Your IT admin must have **SMTP AUTH enabled** for your mailbox', '**🏢 Office 365 设置**\n\n- 用户名：您完整的工作邮箱地址\n- 密码：您的 Microsoft 365 密码（若已开启多因素验证，则使用应用密码）\n- 需要您的 IT 管理员为该邮箱**启用 SMTP AUTH**', 'label', 'admin'),
    ('**🔴 Gmail setup**\n\n1. Enable 2-Step Verification: https://myaccount.google.com/security\n2. Create App Password: https://myaccount.google.com/apppasswords\n3. Username: your Gmail address\n4. Password: the 16-character App Password (not your normal password)', '**🔴 Gmail 设置**\n\n1. 启用两步验证：https://myaccount.google.com/security\n2. 创建应用密码：https://myaccount.google.com/apppasswords\n3. 用户名：您的 Gmail 地址\n4. 密码：16位应用密码（不是您平时使用的密码）', 'label', 'admin'),
    ('**📨 SendGrid — 100 emails/day free**\n\n1. Sign up at https://sendgrid.com\n2. **Settings → API Keys → Create API Key** → Full Access → Create\n3. **Username:** `apikey` (literally)\n4. **Password:** paste your API key\n5. **Sender:** verify at https://app.sendgrid.com/settings/sender_auth', '**📨 SendGrid — 每天100封免费**\n\n1. 在 https://sendgrid.com 注册\n2. **Settings → API Keys → Create API Key** → 选择 Full Access → Create\n3. **用户名：** `apikey`（原样填写）\n4. **密码：** 粘贴您的 API 密钥\n5. **发件人：** 在 https://app.sendgrid.com/settings/sender_auth 验证', 'label', 'admin'),
    ("**💌 Brevo — 300 emails/day free (best free tier)**\n\n1. Sign up at https://brevo.com\n2. Go to **Settings → SMTP & API → Generate a new SMTP key**\n3. **Username:** your Brevo account email address\n4. **Password:** paste the SMTP key (not your login password)\n5. **Sender:** any address you've verified in Brevo\n\n300 emails/day free — 3× more than SendGrid.", '**💌 Brevo — 每天300封免费（最佳免费额度）**\n\n1. 在 https://brevo.com 注册\n2. 进入 **Settings → SMTP & API → Generate a new SMTP key**\n3. **用户名：** 您的 Brevo 账户邮箱地址\n4. **密码：** 粘贴 SMTP 密钥（不是登录密码）\n5. **发件人：** 任意已在 Brevo 验证过的地址\n\n每天300封免费 — 是 SendGrid 的3倍。', 'label', 'admin'),
    ('**⚡ Resend — 100 emails/day free, 3,000/month**\n\n1. Sign up at https://resend.com\n2. Go to **API Keys → Create API Key**\n3. **Username:** `resend` (literally)\n4. **Password:** paste your API key\n5. **Sender:** must use a verified domain (e.g. `you@yourdomain.com`)\n   — free accounts can also use `onboarding@resend.dev` for testing\n\nUses SSL on port 465 (configured automatically).', '**⚡ Resend — 每天100封免费，每月3,000封**\n\n1. 在 https://resend.com 注册\n2. 进入 **API Keys → Create API Key**\n3. **用户名：** `resend`（原样填写）\n4. **密码：** 粘贴您的 API 密钥\n5. **发件人：** 必须使用已验证的域名（例如 `you@yourdomain.com`）\n   — 免费账户测试时也可使用 `onboarding@resend.dev`\n\n使用 465 端口的 SSL（自动配置）。', 'label', 'admin'),
    ('Brevo will accept the connection but **silently drop the email** without delivering it.\n\n**Fix:** Fill in the **Sender** field above with an email address you have verified in your Brevo account (e.g. `orders@yourdomain.com`), then click **Save**.\n\nVerify senders at: https://app.brevo.com/senders', 'Brevo 会接受连接，但**会静默丢弃邮件**而不予投递。\n\n**解决方法：** 在上方**发件人**字段中填入您已在 Brevo 账户中验证过的邮箱地址（例如 `orders@yourdomain.com`），然后点击**保存**。\n\n验证发件人：https://app.brevo.com/senders', 'label', 'admin'),

    # Tracking sub-tab radio labels — passed through format_func=t as WHOLE
    # strings (emoji included), so the static t()-literal-argument audit
    # can't see them as "used" keys; add explicitly.
    ('📊 Dashboard', '📊 仪表盘', 'header', 'tracking'),
    ('📋 Overview', '📋 概览', 'header', 'tracking'),
    ('✏️ Edit Record', '✏️ 编辑记录', 'header', 'tracking'),
    ('➕ Add New', '➕ 新增跟踪', 'header', 'tracking'),
    ('📅 Plan', '📅 计划', 'header', 'tracking'),

    # Tracking → Add New: client filter (v2.26.6 — Sky East orders are now
    # offered here too, so a mixed candidate list needs a way to narrow down).
    # 'Client' is already seeded above (admin/label) with the same value.
    ('All clients', '全部客户', 'label', 'tracking'),
    ('Select PO / Style to start tracking', '选择要开始跟踪的订单/款式', 'label', 'tracking'),

    # Summary → All Orders (v2.28.0 — combined cross-client PO table with
    # standardized headers).
    ('All Orders', '全部订单', 'header', 'summary'),
    ("Every client's orders in one table with standardized columns — GIII POs and Sky East contract items side by side.",
     '所有客户的订单汇总在一张表中，列名统一标准化 — GIII 订单与天东合同项目并列显示。', 'label', 'summary'),
    ('Search (PO / Contract / Style / Color)', '搜索（订单号 / 合同号 / 款式 / 颜色）', 'label', 'summary'),
    ('row(s)', '行', 'label', 'summary'),
    ('units', '件', 'label', 'summary'),
    ('Download All Orders (.xlsx)', '下载全部订单 (.xlsx)', 'button', 'summary'),
    ('Brand / Customer', '品牌/客户', 'header', 'summary'),
    ('Order Date', '下单日期', 'header', 'summary'),
    ('Unit Price', '单价', 'header', 'summary'),

    # GIII → New Contracts: fabric-mapping upload moved out (v2.30.3) — the
    # tab now just points at the Reference Data tab.
    ('Style-Fabric mapping and HHN contract progress are managed in the 📐 Reference Data tab — upload them once there, every run uses the saved data.',
     '款式-面料映射和HHN大货进度在 📐 参考数据 标签页中管理 — 在那里上传一次，之后每次处理都会自动使用已保存的数据。', 'label', 'giii'),

    # GIII → New Contracts redesign (v2.30.4): specialized PO extractors
    # collapsed into expanders under the main uploader.
    ('Other PO types', '其他订单类型', 'header', 'giii'),
    ('Specialized extractors for POs that arrive as fax emails or portal PDFs. Open the type you need — each produces its own formatted Excel.',
     '针对以传真邮件或门户PDF形式到达的订单的专用提取器。打开所需的类型 — 每种类型都会生成各自的格式化Excel。', 'label', 'giii'),
    ('MSG / Vendor Fax POs', 'MSG / 供应商传真订单', 'header', 'giii'),
    ('KL PO PDFs', 'KL 订单 PDF', 'header', 'giii'),
    ('InforNexus POs', 'InforNexus 订单', 'header', 'giii'),
    ('TK EU POs (Kostroma / TJX UK)', 'TK EU 订单（Kostroma / TJX UK）', 'header', 'giii'),
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
