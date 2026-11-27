from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_supplied_sentioh_logo_is_packaged():
    logo = ROOT / "assets" / "sentioh_logo.png"
    assert logo.exists()
    assert logo.stat().st_size > 0


def test_login_and_dashboard_render_shared_logo():
    login = (ROOT / "ui" / "login.py").read_text(encoding="utf-8")
    dashboard = (
        ROOT / "ui" / "single_dashboard.py"
    ).read_text(encoding="utf-8")
    branding = (
        ROOT / "ui" / "branding.py"
    ).read_text(encoding="utf-8")

    assert "render_brand_header(st, width=650)" in login
    assert "render_brand_header(st, width=650)" in dashboard
    assert 'assets" / "sentioh_logo.png' in branding
    assert "st.image(" in branding
