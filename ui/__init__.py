"""Streamlit view modules — extracted from app.py for separation of concerns.

Each module exports `show_*` functions that render one tab/admin section.
View functions take their app-specific dependencies (paths, cache-clear
callbacks) as parameters to avoid circular imports back into app.py.
"""
from ui.admin_buyplan_template import show_buyplan_template_admin  # back-compat
from ui.admin_companies import show_company_admin
from ui.admin_pipeline_layout import show_pipeline_layout_admin
from ui.admin_schema import show_schema_editor
from ui.admin_size_order import show_size_order_admin
from ui.admin_templates import show_templates_admin
from ui.admin_users import show_user_admin
from ui.sky_east_view import show_sky_east_tab
from ui.fabric_db_view import show_fabric_db_tab
from ui.color_translation_view import show_color_translation_tab
from ui.giii_view import show_smart_upload_tab
from ui.summary_view import show_summary_tab

__all__ = [
    "show_buyplan_template_admin",
    "show_company_admin",
    "show_pipeline_layout_admin",
    "show_schema_editor",
    "show_size_order_admin",
    "show_templates_admin",
    "show_user_admin",
    "show_sky_east_tab",
    "show_fabric_db_tab",
    "show_color_translation_tab",
    "show_smart_upload_tab",
    "show_summary_tab",
]
