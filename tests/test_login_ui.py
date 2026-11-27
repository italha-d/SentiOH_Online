from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_app_requires_login_before_dashboard():
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "require_login" in text
    assert "st.stop()" in text
    assert "render(st, current_user=user)" in text


def test_login_page_uses_username_dropdown_and_password_field():
    text = (ROOT / "ui" / "login.py").read_text(encoding="utf-8")
    assert 'st.selectbox(' in text
    assert '"Username"' in text
    assert 'type="password"' in text
    assert "Authorised user sign-in" in text
    assert 'st.text_input("Username"' not in text


def test_login_error_is_password_specific():
    text = (ROOT / "ui" / "login.py").read_text(encoding="utf-8")
    assert "Incorrect password for the selected username." in text
