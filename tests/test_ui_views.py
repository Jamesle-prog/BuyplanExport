"""Smoke tests for view-module migration.

These verify the new ui/ package imports cleanly and exposes the expected
view functions. Full Streamlit AppTest coverage of view rendering is a
later phase; this layer just guards against import-time regressions.
"""
import inspect


def test_ui_package_importable():
    import ui  # noqa: F401


def test_show_size_order_admin_exported():
    from ui import show_size_order_admin
    assert callable(show_size_order_admin)
    sig = inspect.signature(show_size_order_admin)
    assert len(sig.parameters) == 0


def test_show_schema_editor_exported():
    from ui import show_schema_editor
    assert callable(show_schema_editor)
    sig = inspect.signature(show_schema_editor)
    # Two params: schema_path (required) + on_schema_change (optional)
    params = list(sig.parameters.values())
    assert params[0].name == "schema_path"
    assert params[1].name == "on_schema_change"
    assert params[1].default is None


def test_show_user_admin_exported():
    from ui import show_user_admin
    assert callable(show_user_admin)
    assert len(inspect.signature(show_user_admin).parameters) == 0


def test_show_company_admin_exported():
    from ui import show_company_admin
    assert callable(show_company_admin)
    assert len(inspect.signature(show_company_admin).parameters) == 0


def test_show_buyplan_template_admin_exported():
    from ui import show_buyplan_template_admin
    assert callable(show_buyplan_template_admin)
    assert len(inspect.signature(show_buyplan_template_admin).parameters) == 0


def test_show_templates_admin_exported():
    """The unified Templates admin view (replaces the old buy-plan-only view)."""
    from ui import show_templates_admin
    assert callable(show_templates_admin)
    assert len(inspect.signature(show_templates_admin).parameters) == 0


def test_buyplan_admin_alias_points_at_templates_admin():
    """Back-compat: the old name must resolve to the new unified view."""
    from ui import show_buyplan_template_admin, show_templates_admin
    assert show_buyplan_template_admin is show_templates_admin


def test_show_pipeline_layout_admin_exported():
    from ui import show_pipeline_layout_admin
    assert callable(show_pipeline_layout_admin)
    assert len(inspect.signature(show_pipeline_layout_admin).parameters) == 0


def test_show_sky_east_tab_exported():
    from ui import show_sky_east_tab
    assert callable(show_sky_east_tab)
    assert len(inspect.signature(show_sky_east_tab).parameters) == 0


def test_show_fabric_db_tab_exported():
    from ui import show_fabric_db_tab
    assert callable(show_fabric_db_tab)
    assert len(inspect.signature(show_fabric_db_tab).parameters) == 0


def test_show_color_translation_tab_exported():
    from ui import show_color_translation_tab
    assert callable(show_color_translation_tab)
    assert len(inspect.signature(show_color_translation_tab).parameters) == 0


def test_show_smart_upload_tab_exported():
    from ui import show_smart_upload_tab
    assert callable(show_smart_upload_tab)
    assert len(inspect.signature(show_smart_upload_tab).parameters) == 0


def test_show_summary_tab_exported():
    from ui import show_summary_tab
    assert callable(show_summary_tab)
    sig = inspect.signature(show_summary_tab)
    params = list(sig.parameters.values())
    assert params[0].name == "user_cos"
    assert params[1].name == "admin_mode"


def test_view_modules_do_not_import_app_py():
    """Guard against circular imports back into app.py."""
    import ui.admin_schema as m1
    import ui.admin_size_order as m2
    import ui.admin_users as m3
    import ui.admin_companies as m4
    import ui.admin_buyplan_template as m5
    import ui.admin_pipeline_layout as m6
    import ui.admin_templates as m12
    import ui.sky_east_view as m7
    import ui.fabric_db_view as m8
    import ui.color_translation_view as m9
    import ui.giii_view as m10
    import ui.summary_view as m11
    for mod in (m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11, m12):
        src = inspect.getsource(mod)
        assert "from app import" not in src
        assert "import app" not in src


def test_admin_schema_import_does_not_require_streamlit_runtime():
    """Module-level import should succeed even outside `streamlit run`."""
    # If the module body executed Streamlit calls (e.g. st.subheader at top-level),
    # importing it would warn. We allow imports — module body only defines functions.
    import ui.admin_schema  # noqa
    import ui.admin_size_order  # noqa
    import ui.admin_users  # noqa
    import ui.admin_companies  # noqa
    import ui.admin_buyplan_template  # noqa
    import ui.admin_pipeline_layout  # noqa
    import ui.admin_templates  # noqa
    import ui.sky_east_view  # noqa
    import ui.fabric_db_view  # noqa
    import ui.color_translation_view  # noqa
    import ui.giii_view  # noqa
    import ui.summary_view  # noqa
