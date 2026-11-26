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
            expect(page.locator("#passage_id")).to_be_visible(timeout=10000)
            assert page.locator("#passage_id option").count() == 1

        self._run_playwright(flow)

    # ---------- typing start -> result ----------
    def test_live_rkc_error_identification_handles_typo_and_omission_without_suffix_errors(self):
        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            detail_url = (
                f"/simulators/{self.exam.code}/passages/"
                f"{self.publication.passage_id}/"
            )
            page.goto(self.live_server_url + detail_url)
            # Highlighted mode exposes word-level status on the passage itself;
            # live numeric diagnostics remain absent in every exam mode.
            page.locator('input[name="display_mode"][value="highlighted"]').check()
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=10000)
            for counter in ("#rkc-correct", "#rkc-wrong", "#rkc-omitted", "#rkc-extra"):
                expect(page.locator(counter)).to_have_count(0)

            # One misspelt committed word is one error; later correct words
            # must realign sequentially without marking the passage suffix omitted.
            page.fill("#typed-text", "The quick brwn ")
            expect(page.locator("#reference .word.ok")).to_have_count(2)
            expect(page.locator("#reference .word.bad")).to_have_count(1)
            expect(page.locator("#reference .word.miss")).to_have_count(0)

            # Skipping "quick" and then typing "brown" is one omission.
            page.fill("#typed-text", "The brown ")
            expect(page.locator("#reference .word.ok")).to_have_count(2)
            expect(page.locator("#reference .word.bad")).to_have_count(0)
            expect(page.locator("#reference .word.miss")).to_have_count(1)

            # The final untyped passage suffix is never marked as omitted.
            page.fill("#typed-text", "The quick brown ")
            expect(page.locator("#reference .word.ok")).to_have_count(3)
            expect(page.locator("#reference .word.bad")).to_have_count(0)
            expect(page.locator("#reference .word.miss")).to_have_count(0)

        self._run_playwright(flow)

    def test_explicit_enter_new_line_overrides_continuous_passage_layout(self):
        self.exam.passage_layout = ExamConfiguration.PassageLayout.CONTINUOUS
        self.exam.enter_behavior = ExamConfiguration.EnterBehavior.NEW_LINE
        self.exam.save(update_fields=("passage_layout", "enter_behavior"))

        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            page.goto(self.live_server_url + f"/simulators/{self.exam.code}/passages/{self.publication.passage_id}/")
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=10000)
            editor = page.locator("#typed-text")
            editor.fill("alpha")
            editor.press("Enter")
            assert editor.input_value() == "alpha\n"

        self._run_playwright(flow)

    def test_explicit_tab_insert_spaces_is_not_overridden_by_preserve_tabs(self):
        self.exam.passage_layout = ExamConfiguration.PassageLayout.PARA_TAB
        self.exam.passage_preserve_tabs = True
        self.exam.passage_tab_size = 3
        self.exam.tab_behavior = ExamConfiguration.TabBehavior.INSERT_SPACES
        self.exam.save(update_fields=(
            "passage_layout", "passage_preserve_tabs", "passage_tab_size", "tab_behavior",
        ))

        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            page.goto(self.live_server_url + f"/simulators/{self.exam.code}/passages/{self.publication.passage_id}/")
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=10000)
            editor = page.locator("#typed-text")
            editor.fill("x")
            editor.press("Tab")
            assert editor.input_value() == "x   "

        self._run_playwright(flow)

    def test_disabled_keyboard_actions_are_enforced(self):
        self.exam.backspace_policy = ExamConfiguration.BackspacePolicy.DISABLED
        self.exam.allow_backspace = False
        self.exam.allow_delete = False
        self.exam.allow_arrow_navigation = False
        self.exam.enter_behavior = ExamConfiguration.EnterBehavior.DISABLED
        self.exam.space_behavior = ExamConfiguration.SpaceBehavior.DISABLED
        self.exam.tab_behavior = ExamConfiguration.TabBehavior.DISABLED
        self.exam.save(update_fields=(
            "backspace_policy", "allow_backspace", "allow_delete", "allow_arrow_navigation",
            "enter_behavior", "space_behavior", "tab_behavior",
        ))

        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            page.goto(self.live_server_url + f"/simulators/{self.exam.code}/passages/{self.publication.passage_id}/")
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=10000)
            editor = page.locator("#typed-text")
            editor.fill("abc")
            editor.press("Backspace")
            assert editor.input_value() == "abc"
            editor.evaluate("(el) => el.setSelectionRange(0, 0)")
            editor.press("Delete")
            assert editor.input_value() == "abc"
            editor.evaluate("(el) => el.setSelectionRange(3, 3)")
            editor.press("ArrowLeft")
            assert editor.evaluate("(el) => el.selectionStart") == 3
            for key in ("Space", "Enter", "Tab"):
                editor.press(key)
            assert editor.input_value() == "abc"

        self._run_playwright(flow)

    def test_word_lock_after_separator_allows_current_word_retyping_only(self):
        self.exam.backspace_policy = ExamConfiguration.BackspacePolicy.WORD_LOCK_AFTER_SEPARATOR
        self.exam.allow_backspace = True
        self.exam.space_behavior = ExamConfiguration.SpaceBehavior.COMMIT_WORD
        self.exam.enter_behavior = ExamConfiguration.EnterBehavior.NEW_LINE
        self.exam.save(update_fields=(
            "backspace_policy", "allow_backspace", "space_behavior", "enter_behavior",
        ))

        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            page.goto(self.live_server_url + f"/simulators/{self.exam.code}/passages/{self.publication.passage_id}/")
            page.locator('input[name="display_mode"][value="normal"]').check()
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=10000)
            assert "/typing/" in page.url, f"typing start failed: {page.url} — {page.locator('body').inner_text()}"
            editor = page.locator("#typed-text")
            editor.fill("one")
            editor.press("Space")
            editor.type("two")
            for _ in range(4):
                editor.press("Backspace")
            assert editor.input_value() == "one "

        self._run_playwright(flow)

    def test_typing_start_to_result_flow(self):
        def flow(page):
            self._login(page, "/institutes/student/login/", STUDENT_EMAIL)
            # Legacy passage URLs resolve into the selected exam workspace.
            detail_url = (
                f"/simulators/{self.exam.code}/passages/"
                f"{self.publication.passage_id}/"
            )
            page.goto(self.live_server_url + detail_url)
            # The passage detail page now starts the exact passage directly;
            # its mode selector is the only choice before the POST start action.
            page.locator('input[name="display_mode"][value="normal"]').check()
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
