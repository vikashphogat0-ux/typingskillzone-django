from django.shortcuts import render


def home(request):
    """Public landing page with links to each sign-in and registration flow."""
    return render(request, "passages/home.html")
