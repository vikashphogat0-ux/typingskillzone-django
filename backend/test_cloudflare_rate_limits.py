from cloudflare_rate_limits import build_rate_limit_plan, counter_key

CLIENT_IP = "203.0.113.9"


def test_counter_key_matches_legacy_key_format():
    import hashlib
    raw = "student-login:203.0.113.9:user@example.test"
    expected = "auth-throttle:student-login:" + hashlib.sha256(raw.encode()).hexdigest()
    assert counter_key("student-login", CLIENT_IP, " USER@example.test ") == expected


def test_student_registration_preserves_existing_limit():
    plan = build_rate_limit_plan("/accounts/student/register/", "POST", {}, CLIENT_IP)
    check = plan["checks"][0]
    assert (check["scope"], check["limit"], check["window"]) == ("student-register", 5, 3600)
    assert plan["blocked_status"] == 429


def test_resend_checks_email_first_and_ip_limit_only_suppresses_delivery():
    plan = build_rate_limit_plan("/accounts/student/verify/resend/", "POST", {"email": "Person@Example.test"}, CLIENT_IP)
    checks = plan["checks"]
    assert [item["scope"] for item in checks] == ["student-resend", "student-resend-ip"]
    assert checks[0]["identity"] == "person@example.test"
    assert checks[1]["suppress_only"] is True
    assert plan["stop_on_limit"] is True


def test_password_reset_only_counts_valid_email_and_checks_both_counters():
    assert build_rate_limit_plan("/accounts/password-reset/", "POST", {"email": "bad"}, CLIENT_IP) is None
    plan = build_rate_limit_plan("/accounts/password-reset/", "POST", {"email": "Person@Example.test"}, CLIENT_IP, valid_password_reset_email=True)
    assert [item["scope"] for item in plan["checks"]] == ["password-reset-email", "password-reset-ip"]
    assert plan["stop_on_limit"] is False


def test_login_scopes_match_existing_portals():
    for path, scope in [
        ("/institutes/owner/login/", "owner-login"),
        ("/institutes/student/login/", "student-login"),
        ("/institutes/staff/login/", "staff-login"),
    ]:
        plan = build_rate_limit_plan(path, "POST", {"username": "U@example.test"}, CLIENT_IP)
        assert plan["checks"][0]["scope"] == scope
        assert plan["checks"][0]["identity"] == "u@example.test"
        assert (plan["checks"][0]["limit"], plan["checks"][0]["window"]) == (8, 900)


def test_get_requests_are_never_counted():
    assert build_rate_limit_plan("/accounts/student/verify/token/", "GET", {}, CLIENT_IP) is None
