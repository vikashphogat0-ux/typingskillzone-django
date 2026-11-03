
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import InstituteRegistrationForm


@require_http_methods(["GET", "POST"])
def institute_register(request):
    if request.user.is_authenticated:
        messages.info(
            request,
            "Please log out before registering a new institute."
        )
        return redirect("login")

    if request.method == "POST":
        form = InstituteRegistrationForm(request.POST)

        if form.is_valid():
            institute = form.save()

            messages.success(
                request,
                "Institute registration submitted successfully. "
                "Your application is awaiting Super Admin approval."
            )

            return render(
                request,
                "institutes/registration_success.html",
                {"institute": institute},
            )
    else:
        form = InstituteRegistrationForm()

    return render(
        request,
        "institutes/register.html",
        {"form": form},
    )
