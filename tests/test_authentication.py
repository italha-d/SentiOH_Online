from auth.service import authenticate


def test_demo_login_accepts_valid_role_account():
    user = authenticate("warehouse.manager", "!")
    assert user is not None
    assert user["role"] == "Warehouse Manager"
    assert user["display_name"] == "Galway Warehouse Manager"


def test_demo_login_rejects_wrong_password():
    assert authenticate("warehouse.manager", "wrong-password") is None


def test_demo_login_rejects_unknown_user():
    assert authenticate("nobody", "!") is None


from auth.service import available_accounts


def test_available_accounts_does_not_expose_password_material():
    accounts = available_accounts()
    assert accounts
    for account in accounts:
        assert set(account) == {"username", "display_name", "role"}
        assert "password_hash" not in account
        assert "password_salt" not in account


def test_all_manager_demo_accounts_use_bang_password():
    manager_usernames = [
        "warehouse.manager",
        "site.manager",
        "cork.manager",
        "logistics.manager",
        "quality.manager",
        "procurement.manager",
        "incident.manager",
        "senior.manager",
    ]
    for username in manager_usernames:
        user = authenticate(username, "!")
        assert user is not None, username
        assert "Manager" in user["role"]
