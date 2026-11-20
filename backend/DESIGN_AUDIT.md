# DESIGN_AUDIT.md — Stage 1 (read-only audit)

Scope: every route in `config/`, `accounts/`, `institutes/`, `passages/`, `typing_sessions/`, `exams/` and every template in the repository.

## Pages and their state

| Area | Route | Template | State |
|---|---|---|---|
| Homepage | `/` | passages/home.html | Redesigned (light system) |
| Exam catalogue | `/exams/` | exams/catalogue.html | New, light system |
| Exam detail | `/exams/<code>/` | exams/exam_detail.html | New, light system |
| Student sign-in (account) | `/accounts/student/login/` | accounts/student_login.html | Redesigned |
| Student sign-in (institute) | `/institutes/student/login/` | institutes/student_login.html | Redesigned |
| Owner sign-in | `/institutes/owner/login/` | institutes/owner_login.html | Redesigned |
| Staff sign-in | `/institutes/staff/login/` | institutes/staff_login.html | Redesigned |
| Student registration | `/accounts/student/register/` | accounts/student_register.html | Old dark styling |
| Registration pending / verification result | — | accounts/registration_pending.html, verification_result.html | Old dark styling |
| Password reset (4 pages) | — | accounts/password_reset_*.html | Old dark styling |
| Student profile | `/accounts/student/profile/` | accounts/student_profile.html | Old dark styling |
| Enrol in institute | `/accounts/student/enroll/` | accounts/enroll_institute.html | Old dark styling |
| Student dashboard | `/accounts/dashboard/` | accounts/student_dashboard.html | Old dark styling |
| Passage library | `/accounts/passage-library/` | accounts/passage_library.html | Old dark styling (dropdowns removed) |
| Result history | `/accounts/...` | accounts/student_result_history.html | Old dark styling (dropdowns removed) |
| Simulator passage list | `/simulators/<code>/passages/` | passages/simulator_list.html | Old dark styling |
| Simulator passage detail | `/simulators/<code>/passages/<n>/` | passages/simulator_detail.html | Old dark styling |
| Typing test (live) | `/typing/<id>/` | typing_sessions/live.html | Old dark styling; engine untouched |
| Typing result | — | typing_sessions/result.html | Old dark styling |
| Typing error | — | typing_sessions/error.html | Old dark styling |
| Owner dashboard | `/institutes/owner/dashboard/` | institutes/owner_dashboard.html | Old dark styling |
| Owner members | `/institutes/owner/institutes/<id>/members/` | institutes/owner_member_list.html | Old dark styling |
| Owner add member | `.../members/add/` | institutes/owner_member_add.html | Old dark styling |
| Owner access / verification pages | — | institutes/owner_*_result.html, owner_access_status.html | Old dark styling |
| Institute registration | `/institutes/register/` | institutes/register.html | Old dark styling |
| Registration success | — | institutes/registration_success.html | Old dark styling |
| Staff dashboard | `/institutes/staff/dashboard/` | institutes/staff_dashboard.html | Old dark styling |
| Member dashboard (institute student) | `/institutes/student/dashboard/` | institutes/student_dashboard.html | Old dark styling |
| Member access status | — | institutes/member_access_status.html | Old dark styling |
| Super-admin dashboard | `/institutes/dashboard/super-admin/` | institutes/super_admin_dashboard.html | Old dark styling |
| Institute list / detail / edit | `/institutes/dashboard/super-admin/institutes/...` | institutes/institute_*.html | Old dark styling |
| Django admin | `/admin/` | Django default | Not redesigned (admin theme) |

## Current problems

1. **Two visual systems.** The public pages and sign-in use the new light system. Every dashboard, the typing pages and the result pages still use the old dark palette, so the site looks inconsistent.
2. **Old dropdowns.** Filters on the passage library and result history used native selects. They are replaced with chips, and exams are browsed through the catalogue.
3. **Hard-coded colours.** Old templates embed hex values (`#14243a`, `#091321`, `#45d5e8`) inline instead of using tokens.
4. **Inline `<style>` blocks** in most templates duplicate layout rules.
5. **Missing pages.** There is no pricing page, no about or contact page, and no legal pages. No payment code exists, so pricing cannot show real prices.
6. **Accessibility gaps.** Several legacy templates have low-contrast muted text on dark backgrounds and no skip link.

## Proposed improvements

- One token set (see DESIGN_SYSTEM.md) applied to every template, with inline colours removed in stages.
- A shared dashboard shell (sidebar on desktop, top bar on mobile) for student, owner and staff pages.
- Exam catalogue as the main entry point for students, linked from the dashboards.
- Typing pages: restyle the surroundings only; the timer, input and element IDs stay as they are.
- Pricing, about, contact and legal pages: added only after the plans and content are provided.
