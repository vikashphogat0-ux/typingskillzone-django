import logging

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.core.mail import send_mail
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import InstituteEnrollmentForm, StudentProfileForm, StudentRegistrationForm
from .security import is_rate_limited
from django.db.models import Q, Count

from exams.models import ExamConfiguration
from learners.models import LearnerProfile
from passages.models import PassageSource, SimulatorPassage, released_queryset
from typing_sessions.models import TypingSession
from datetime import datetime, time, timedelta

from django.utils.dateparse import parse_date
from django.core.paginator import Paginator
from io import BytesIO
import os
from xml.sax.saxutils import escape as xml_escape

User = get_user_model()
logger = logging.getLogger(__name__)
VERIFICATION_SALT = "typingskillzone.student.email-verification"
VERIFICATION_MAX_AGE = 60 * 60 * 24


def send_student_verification_email(request, user):
    issued_at = timezone.now()
    user.email_verification_sent_at = issued_at
    user.save(update_fields=["email_verification_sent_at"])
    token = signing.dumps(
        {"user_id": user.pk, "issued_at": issued_at.isoformat()},
        salt=VERIFICATION_SALT,
    )
    verify_url = request.build_absolute_uri(
        reverse("accounts:verify_email", kwargs={"token": token})
    )
    send_mail(
        "Verify your TypingSkillZone student account",
        f"Hello {user.first_name},\n\nVerify your email within 24 hours using this link:\n{verify_url}\n\nIf you did not create this account, ignore this email.",
        None,
        [user.email],
        fail_silently=False,
    )



def dashboard_url_for(user):
    """Each role lands on its own dashboard, never on another portal's page."""
    if user.is_superuser or user.role == User.Roles.SUPER_ADMIN:
        return reverse("institutes:super_admin_dashboard")
    if user.role == User.Roles.INSTITUTE_OWNER:
        return reverse("institutes:owner_dashboard")
    if user.role == User.Roles.INSTITUTE_STAFF:
        return reverse("institutes:staff_dashboard")
    return reverse("accounts:student_dashboard")


@require_http_methods(["GET", "POST"])
def student_login(request):
    """Sign-in for independent students. Institute members use the institute portal instead."""
    if request.method == "POST" and is_rate_limited(
        "account-student-login", request, identity=request.POST.get("username", ""), limit=8, window=900
    ):
        return HttpResponseForbidden("Too many login attempts. Please try again later.")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if user.role != User.Roles.STUDENT or not user.is_active:
            form.add_error(None, "The email or password is incorrect.")
        else:
            login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next") or ""
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect("accounts:student_dashboard")
    return render(request, "accounts/student_login.html", {"form": form})


def student_register(request):
    if request.user.is_authenticated:
        return redirect(dashboard_url_for(request.user))

    if request.method == "POST" and is_rate_limited("student-register", request, limit=5, window=3600):
        return HttpResponse("Too many registration attempts. Please try again later.", status=429)
    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = form.save()
        except IntegrityError:
            form.add_error("email", "An account with this email already exists.")
            return render(request, "accounts/student_register.html", {"form": form})
        try:
            send_student_verification_email(request, user)
        except Exception:
            logger.exception("Unable to send student verification email for user %s", user.pk)
            messages.warning(
                request,
                "Your account was created but the verification email could not be sent. Use the resend verification option.",
            )
        return render(request, "accounts/registration_pending.html", {"email": user.email})
    return render(request, "accounts/student_register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def resend_student_verification(request):
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if is_rate_limited("student-resend", request, identity=email, limit=3, window=3600):
            return HttpResponse("Too many requests. Please try again later.", status=429)
        if not is_rate_limited("student-resend-ip", request, limit=10, window=3600):
            user = User.objects.filter(
                email__iexact=email,
                role=User.Roles.STUDENT,
                is_active=False,
                is_email_verified=False,
            ).first()
            if user:
                try:
                    send_student_verification_email(request, user)
                except Exception:
                    logger.exception("Unable to resend student verification email for user %s", user.pk)
    # Do not reveal whether an email address belongs to an account.
    return render(request, "accounts/registration_pending.html", {
        "generic_resend_message": "If an unverified student account exists for that email, a new verification link has been sent."
    })


@require_http_methods(["GET", "POST"])
def verify_student_email(request, token):
    # Do not throttle GET previews: email security scanners may open links automatically.
    if request.method == "POST" and is_rate_limited("student-verify", request, limit=10, window=900):
        return HttpResponse("Too many verification attempts. Please try again later.", status=429)
    try:
        payload = signing.loads(token, salt=VERIFICATION_SALT, max_age=VERIFICATION_MAX_AGE)
        user = User.objects.get(pk=payload["user_id"], role=User.Roles.STUDENT)
        issued_at = payload["issued_at"]
        if not user.email_verification_sent_at or issued_at != user.email_verification_sent_at.isoformat():
            raise signing.BadSignature("Verification link has been superseded.")
    except (signing.BadSignature, signing.SignatureExpired, KeyError, ValueError, TypeError):
        return render(request, "accounts/verification_result.html", {
            "success": False,
            "message": "This verification link is invalid, has been used, or has expired. Please request a new link.",
        }, status=400)
    except User.DoesNotExist:
        return HttpResponse("Account not found.", status=404)

    if user.is_email_verified and user.is_active:
        return render(request, "accounts/verification_result.html", {
            "success": True,
            "message": "Your email is already verified. You can sign in to your student account.",
            "already_verified": True,
        })

    if request.method == "GET":
        return render(request, "accounts/verification_result.html", {
            "success": False,
            "confirmation": True,
            "token": token,
            "message": "Confirm that you want to verify this email address and activate your student account.",
        })

    user.is_email_verified = True
    user.is_active = True
    user.email_verification_sent_at = None
    user.save(update_fields=["is_email_verified", "is_active", "email_verification_sent_at"])
    login(request, user)
    return render(request, "accounts/verification_result.html", {
        "success": True,
        "message": "Your email is verified. Your student account is now active.",
    })


@login_required
@require_http_methods(["GET", "POST"])
def student_profile(request):
    if request.user.role != User.Roles.STUDENT:
        return HttpResponse("Student account required.", status=403)

    form = StudentProfileForm(request.POST or None, instance=request.user)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("accounts:student_profile")

    return render(request, "accounts/student_profile.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def enroll_institute(request):
    if request.user.role != User.Roles.STUDENT:
        return HttpResponse("Student account required.", status=403)

    form = InstituteEnrollmentForm(
        request.POST or None,
        student=request.user,
    )

    if request.method == "POST" and form.is_valid():
        try:
            membership = form.save()
        except ValidationError as error:
            form.add_error("registration_code", error)
        else:
            messages.success(
                request,
                f"You are now enrolled at {membership.institute.name}.",
            )
            return redirect("institutes:student_dashboard")

    return render(request, "accounts/enroll_institute.html", {"form": form})

@login_required
def student_result_history(request):
    if request.user.role != User.Roles.STUDENT:
        return HttpResponse("Student account required.", status=403)

    # Include submitted attempts and expired attempts with a saved score.
    sessions = TypingSession.objects.filter(
        learner=request.user,
    ).filter(
        Q(state=TypingSession.State.SUBMITTED)
        | Q(
            state=TypingSession.State.EXPIRED,
            scoring_version__gt="",
        )
    ).select_related(
        "publication__exam",
        "publication__source",
    )

    language = request.GET.get("language", "").strip()
    exam_code = request.GET.get("exam", "").strip()
    date_from = parse_date(request.GET.get("date_from", ""))
    date_to = parse_date(request.GET.get("date_to", ""))

    if date_from and date_to and date_from > date_to:
        messages.error(request, "Date From cannot be later than Date To.")
        date_from = None
        date_to = None

    if language:
        sessions = sessions.filter(
            publication__source__language=language
        )

    if exam_code:
        sessions = sessions.filter(
            publication__exam__code=exam_code
        )

    if date_from:
        start = timezone.make_aware(
            datetime.combine(date_from, time.min),
            timezone.get_current_timezone(),
        )
        sessions = sessions.filter(started_at__gte=start)

    if date_to:
        try:
            next_day = date_to + timedelta(days=1)
        except OverflowError:
            next_day = None  # 9999-12-31 has no upper bound to apply
        if next_day is not None:
            end_exclusive = timezone.make_aware(
                datetime.combine(next_day, time.min),
                timezone.get_current_timezone(),
            )
            sessions = sessions.filter(started_at__lt=end_exclusive)

    paginator = Paginator(
        sessions.order_by("-started_at"),
        20,
    )
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "sessions": page_obj,
        "page_obj": page_obj,
        "languages": TypingSession.objects.filter(
            learner=request.user,
        ).filter(
            Q(state=TypingSession.State.SUBMITTED)
            | Q(
                state=TypingSession.State.EXPIRED,
                scoring_version__gt="",
            )
        ).values_list(
            "publication__source__language",
            flat=True,
        ).distinct(),
        "exams": ExamConfiguration.objects.filter(
            published_passages__typing_sessions__learner=request.user,
        ).filter(
            Q(
                published_passages__typing_sessions__state=TypingSession.State.SUBMITTED
            )
            | Q(
                published_passages__typing_sessions__state=TypingSession.State.EXPIRED,
                published_passages__typing_sessions__scoring_version__gt="",
            )
        ).values_list("code", "name").distinct(),
        "selected_language": language,
        "selected_exam": exam_code,
        "selected_date_from": date_from,
        "selected_date_to": date_to,
    }

    return render(
        request,
        "accounts/student_result_history.html",
        context,
    )

@login_required
def passage_library(request):
    """Exam-first student passage library; a student must choose an exam first."""
    if request.user.role != User.Roles.STUDENT:
        logger.warning(
            "Student passage library access denied: user_id=%s role=%s active=%s superuser=%s",
            request.user.pk, request.user.role, request.user.is_active, request.user.is_superuser,
        )
        return HttpResponse("Student account required.", status=403)

    base_passages = released_queryset(
        SimulatorPassage.objects.filter(
            status=SimulatorPassage.Status.PUBLISHED,
            exam__is_active=True,
            source__status=PassageSource.Status.PUBLISHED,
        ).select_related("source", "exam")
    )
    exam_code = request.GET.get("exam", "").strip()
    if not exam_code:
        exams = (
            ExamConfiguration.objects.filter(
                is_active=True,
                published_passages__in=base_passages,
            ).annotate(passage_count=Count("published_passages", filter=Q(
                published_passages__status=SimulatorPassage.Status.PUBLISHED,
                published_passages__source__status=PassageSource.Status.PUBLISHED,
            ))).distinct().order_by("name")
        )
        return render(request, "accounts/passage_library.html", {
            "exams": exams,
            "exam_selection": True,
        })

    exam = get_object_or_404(ExamConfiguration, code=exam_code, is_active=True)
    passages = base_passages.filter(exam=exam)
    language = request.GET.get("language", "").strip()
    search_query = request.GET.get("search", "").strip()
    if language:
        passages = passages.filter(source__language=language)
    if search_query:
        passages = passages.filter(
            Q(source__title__icontains=search_query)
            | Q(source__content__icontains=search_query)
        )

    page_obj = Paginator(passages.order_by("serial_number", "pk"), 20).get_page(request.GET.get("page"))
    selected_id = request.GET.get("passage", "").strip()
    selected_passage = None
    if selected_id:
        try:
            selected_passage = passages.get(serial_number=int(selected_id))
        except (ValueError, SimulatorPassage.DoesNotExist):
            selected_passage = None
    if selected_passage is None and page_obj.object_list:
        selected_passage = page_obj.object_list[0]

    passage_options = base_passages.filter(exam=exam).order_by("serial_number").values(
        "serial_number", "source__title", "source__language"
    )
    context = {
        "exams": ExamConfiguration.objects.filter(is_active=True),
        "exam_selection": False,
        "exam": exam,
        "available_languages": passages.order_by().values_list("source__language", flat=True).distinct(),
        "selected_language": language,
        "search_query": search_query,
        "passages": page_obj,
        "page_obj": page_obj,
        "passage_options": passage_options,
        "selected_passage": selected_passage,
        "passage_count": base_passages.filter(exam=exam).count(),
    }
    return render(request, "accounts/passage_library.html", context)


@login_required
def download_library_passage(request, exam_code, passage_id, file_format):
    """Download a released passage only after the same student access check as the library."""
    if request.user.role != User.Roles.STUDENT:
        return HttpResponse("Student account required.", status=403)
    if file_format not in {"txt", "pdf"}:
        return HttpResponse("Unsupported download format.", status=404)

    exam = get_object_or_404(ExamConfiguration, code=exam_code, is_active=True)
    try:
        serial_number = int(passage_id)
    except (TypeError, ValueError):
        raise Http404("Passage not found.")
    passage = get_object_or_404(
        released_queryset(SimulatorPassage.objects.select_related("source", "exam")),
        exam=exam,
        serial_number=serial_number,
        status=SimulatorPassage.Status.PUBLISHED,
        source__status=PassageSource.Status.PUBLISHED,
    )
    title = passage.source.title
    content = passage.rendered_content

    if file_format == "txt":
        response = HttpResponse(content, content_type="text/plain; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="passage-{passage.passage_id}.txt"'
        return response

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        return HttpResponse("PDF export is unavailable on this server.", status=503)

    font_name = "Helvetica"
    if passage.source.language.upper() == "HINDI":
        candidates = [
            r"C:\Windows\Fonts\Nirmala.ttf",
            r"C:\Windows\Fonts\NirmalaUI.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        font_path = next((path for path in candidates if os.path.exists(path)), None)
        if not font_path:
            return HttpResponse(
                "Hindi PDF export needs a Unicode Devanagari font on the server. TXT export remains available.",
                status=503,
            )
        try:
            pdfmetrics.registerFont(TTFont("TypingSkillZoneHindi", font_path))
            font_name = "TypingSkillZoneHindi"
        except Exception:
            return HttpResponse("The server Hindi font could not be loaded. TXT export remains available.", status=503)

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=48, leftMargin=48, topMargin=52, bottomMargin=48,
        title=title, author="TypingSkillZone",
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "PassageHeading", parent=styles["Heading1"], fontName=font_name,
        fontSize=16, leading=21, textColor=colors.HexColor("#172033"), spaceAfter=8,
    )
    meta = ParagraphStyle(
        "PassageMeta", parent=styles["Normal"], fontName=font_name,
        fontSize=9, leading=13, textColor=colors.HexColor("#64748B"), spaceAfter=18,
    )
    body = ParagraphStyle(
        "PassageBody", parent=styles["BodyText"], fontName=font_name,
        fontSize=11, leading=17, alignment=TA_LEFT, spaceAfter=9,
    )
    story = [
        Paragraph(xml_escape(title), heading),
        Paragraph(xml_escape(f"{exam.name} · {passage.source.language.title()} · Passage {passage.passage_id}"), meta),
    ]
    for paragraph in content.replace("\r\n", "\n").replace("\r", "\n").split("\n\n"):
        if paragraph.strip():
            story.append(Paragraph(xml_escape(paragraph).replace("\n", "<br/>"), body))
            story.append(Spacer(1, 2))
    document.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="passage-{passage.passage_id}.pdf"'
    return response


def student_dashboard(request):
    """Student dashboard with progress, speed, accuracy, and statistics."""
    if request.user.role != User.Roles.STUDENT:
        return HttpResponse("Student account required.", status=403)

    user = request.user
    profile, created = LearnerProfile.objects.get_or_create(user=user)

    # Get all typing sessions for this student, ordered by most recent
    sessions = TypingSession.objects.filter(learner=user).select_related(
        'publication__exam'
    ).order_by('-started_at')

    # Calculate statistics from persisted records
    total_sessions = sessions.count()
    completed_sessions = sessions.filter(state=TypingSession.State.SUBMITTED).count()

    # WPM and accuracy statistics from result snapshots
    wpm_values = []
    accuracy_values = []

    scored_sessions = sessions.filter(
        state=TypingSession.State.SUBMITTED,
    ).exclude(scoring_version="")

    for result in scored_sessions.values_list("result_snapshot", flat=True).iterator(chunk_size=200):
        if not isinstance(result, dict):
            continue

        net_wpm = result.get("net_wpm")
        accuracy = result.get("accuracy_percent")

        if isinstance(net_wpm, (int, float)) and not isinstance(net_wpm, bool):
            wpm_values.append(float(net_wpm))

        if isinstance(accuracy, (int, float)) and not isinstance(accuracy, bool):
            accuracy_values.append(float(accuracy))

    avg_wpm = sum(wpm_values) / len(wpm_values) if wpm_values else 0
    avg_accuracy = (
        sum(accuracy_values) / len(accuracy_values)
        if accuracy_values else 0
    )
    # Recent completed attempts
    recent = sessions.filter(
        state=TypingSession.State.SUBMITTED
    ).order_by('-started_at')[:5]

    # Practice goals
    daily_goal_minutes = profile.daily_practice_goal_minutes
    target_wpm = profile.target_wpm
    target_accuracy = profile.target_accuracy

    context = {
        'profile': profile,
        'total_sessions': total_sessions,
        'completed_sessions': completed_sessions,
        'avg_wpm': round(avg_wpm, 1),
        'avg_accuracy': round(avg_accuracy, 1),
        'recent': recent,
        'target_wpm': target_wpm,
        'target_accuracy': target_accuracy,
        'daily_goal_minutes': daily_goal_minutes,
    }

    return render(
        request,
        "accounts/student_dashboard.html",
        context,
    )
