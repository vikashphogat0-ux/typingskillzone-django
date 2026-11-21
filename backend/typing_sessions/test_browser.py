"""End-to-end browser smoke tests for core TypingSkillZone workflows.

These tests drive a real Chromium browser against Django's LiveServerTestCase
so the student, institute staff/owner and platform-admin navigation, the
simulator/passage access, and the typing start->result flow are exercised
through the same URLs and CSRF-protected forms used in production.

Playwright runs in a dedicated worker thread so that Django's synchronous ORM
access (setUp / post-browser assertions) stays on the main test thread and
never sees Playwright's asyncio event loop. Only test accounts and the Django
test database are used. No live payments, no production data.
"""
import threading

from django.test import LiveServerTestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from playwright.sync_api import sync_playwright, expect

from exams.models import ExamConfiguration
from passages.models import PassageSource, SimulatorPassage
from institutes.models import (
    Institute,
    InstituteMembership,
    InstituteSubscription,
    SubscriptionPlan,
)
from typing_sessions.models import TypingSession

User = get_user_model()

STUDENT_EMAIL = "browser-student@example.test"
STAFF_EMAIL = "browser-staff@example.test"
OWNER_EMAIL = "browser-owner@example.test"
SUPERADMIN_EMAIL = "browser-superadmin@example.test"
PASSWORD = "Browser-Test-Password-2026!"


class BrowserCoreWorkflowTests(LiveServerTestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            email=STUDENT_EMAIL,
            password=PASSWORD,
            role=User.Roles.STUDENT,
            is_active=True,
            is_email_verified=True,
        )
        self.staff = User.objects.create_user(
            email=STAFF_EMAIL,
            password=PASSWORD,
            role=User.Roles.INSTITUTE_STAFF,
            is_active=True,
            is_email_verified=True,
        )
        self.owner = User.objects.create_user(
            email=OWNER_EMAIL,
            password=PASSWORD,
            role=User.Roles.INSTITUTE_OWNER,
            is_active=True,
            is_email_verified=True,
        )
        self.superadmin = User.objects.create_superuser(
            email=SUPERADMIN_EMAIL, password=PASSWORD
        )
        self.superadmin.role = User.Roles.SUPER_ADMIN
        self.superadmin.save()

        self.institute = Institute.objects.create(
            name="Browser Academy",
            owner=self.owner,
            email="academy@example.test",
            phone="9000000000",
            status=Institute.Status.APPROVED,
        )
        self.plan = SubscriptionPlan.objects.create(
            name="Browser Trial",
            code="browser-trial",
            duration_days=7,
            price=0,
            max_students=25,
            max_staff=2,
        )
        now = timezone.now()
        InstituteSubscription.objects.create(
            institute=self.institute,
            plan=self.plan,
            status=InstituteSubscription.Status.ACTIVE,
            starts_at=now,
            ends_at=now + timezone.timedelta(days=7),
            amount_paid=0,
        )
        InstituteMembership.objects.create(
            institute=self.institute,
            user=self.student,
            role=InstituteMembership.Role.STUDENT,
            is_active=True,
        )
        InstituteMembership.objects.create(
            institute=self.institute,
            user=self.staff,
            role=InstituteMembership.Role.STAFF,
            is_active=True,
        )

        self.exam = ExamConfiguration.objects.create(
            code="browser-exam",
            name="Browser Exam",
            language="ENGLISH",
            script="LATIN",
            duration_seconds=600,
            is_active=True,
        )
        self.source = PassageSource.objects.create(
            title="Browser passage",
            content="The quick brown fox jumps over the lazy dog.",
            language="ENGLISH",
            script="LATIN",
            status=PassageSource.Status.PUBLISHED,
        )
        self.publication = SimulatorPassage.objects.create(
            exam=self.exam,
            source=self.source,
            serial_number=1,
            status=SimulatorPassage.Status.PUBLISHED,
        )

    # ---------- Playwright helper (runs on a worker thread) ----------
    def _run_playwright(self, callback):
        """Run ``callback(page)`` in a thread with its own Chromium instance.

        Keeps Playwright's asyncio loop off the main Django test thread so
        synchronous ORM access before/after is never rejected.
        """
        outcome = {}

        def worker():
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    context = browser.new_context()
                    page = context.new_page()
                    try:
                        callback(page)
                    finally:
                        context.close()
                        browser.close()
            except BaseException as exc:  # noqa: BLE001
                outcome["error"] = exc

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        if "error" in outcome:
            raise outcome["error"]

    def _login(self, page, login_path, email):
        page.goto(self.live_server_url + login_path)
        page.fill('input[name="username"]', email)
        page.fill('input[name="password"]', PASSWORD)
        # Works for both institute pages (<button type="submit">) and the
        # Django admin login (<input type="submit">).
        page.click('[type="submit"]')

    def _assert_dashboard(self, page, expected_path_fragment):
        page.wait_for_load_state("networkidle", timeout=10000)
        assert expected_path_fragment in page.url, (
            f"expected {expected_path_fragment} in {page.url}"
        )

    # ---------- role-based login / dashboard ----------
    def test_student_login_reaches_student_dashboard(self):
        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            self._assert_dashboard(page, "/institutes/student/dashboard/")
            expect(page.locator("text=Browser Academy")).to_be_visible(timeout=10000)

        self._run_playwright(flow)

    def test_staff_login_reaches_staff_dashboard(self):
        def flow(page):
            self._login(page, "/institutes/staff/login/", STAFF_EMAIL)
            self._assert_dashboard(page, "/institutes/staff/dashboard/")
            expect(page.locator("text=Browser Academy")).to_be_visible(timeout=10000)

        self._run_playwright(flow)

    def test_owner_login_reaches_owner_dashboard(self):
        def flow(page):
            self._login(page, "/institutes/owner/login/", OWNER_EMAIL)
            self._assert_dashboard(page, "/institutes/owner/dashboard/")
            expect(page.locator("text=Browser Academy")).to_be_visible(timeout=10000)

        self._run_playwright(flow)

    def test_superadmin_login_reaches_super_admin_dashboard(self):
        def flow(page):
            # Platform super admins authenticate through the Django admin login.
            self._login(page, "/admin/login/", SUPERADMIN_EMAIL)
            page.goto(self.live_server_url + "/institutes/dashboard/super-admin/")
            self._assert_dashboard(page, "/institutes/dashboard/super-admin/")
            expect(page.locator("text=Browser Academy")).to_be_visible(timeout=10000)

        self._run_playwright(flow)

    def test_student_cannot_access_staff_portal(self):
        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            # Staff dashboard rejects a student role with HTTP 403.
            response = page.goto(self.live_server_url + "/institutes/staff/dashboard/")
            assert response.status == 403

        self._run_playwright(flow)

    # ---------- simulator / passage access ----------
    def test_passage_list_requires_login_and_shows_passage(self):
        def flow(page):
            # Anonymous access is redirected to the login page.
            page.goto(
                self.live_server_url + f"/simulators/{self.exam.code}/passages/"
            )
            page.wait_for_load_state("networkidle", timeout=10000)
            # Students are sent to the student login, not the Django admin login (ROUTE-01).
            assert "/accounts/student/login/" in page.url
            expect(page.locator("text=Browser passage")).not_to_be_visible()

            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            page.goto(
                self.live_server_url + f"/simulators/{self.exam.code}/passages/"
            )
            page.wait_for_load_state("networkidle", timeout=10000)
            assert f"/exams/{self.exam.code}/" in page.url
            expect(page.locator("text=Browser passage")).to_be_visible(timeout=10000)

        self._run_playwright(flow)

    # ---------- typing start -> result ----------
    def test_typing_start_to_result_flow(self):
        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            # Legacy passage URLs resolve into the selected exam workspace.
            detail_url = (
                f"/simulators/{self.exam.code}/passages/"
                f"{self.publication.passage_id}/"
            )
            page.goto(self.live_server_url + detail_url)
            expect(page.locator("text=Browser passage")).to_be_visible(timeout=10000)
            # Start the selected passage with the chosen fixed display mode.
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=10000)
            assert "/typing/" in page.url
            expect(page.locator("#typing-form")).to_be_visible(timeout=10000)

            reference = page.locator("#reference").inner_text()
            page.fill("#typed-text", reference)
            page.click("#finish-button")

            # Submitted attempt lands on the result page with metrics.
            page.wait_for_load_state("networkidle", timeout=10000)
            expect(page.locator("text=Test result")).to_be_visible(timeout=10000)

        self._run_playwright(flow)
        # Django ORM assertions on the main thread (no Playwright loop here).
        attempt = TypingSession.objects.filter(learner=self.student).latest(
            "started_at"
        )
        self.assertEqual(attempt.state, TypingSession.State.SUBMITTED)
        self.assertTrue(attempt.result_snapshot)
