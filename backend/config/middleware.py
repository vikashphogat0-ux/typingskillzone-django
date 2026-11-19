"""Security-header middleware."""


class ContentSecurityPolicyMiddleware:
    """Adds a Content-Security-Policy header to every response that lacks one.

    'unsafe-inline' remains for scripts and styles because several templates still use
    inline <script> and style attributes. Removing it requires moving those into static files.
    """

    POLICY = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.POLICY)
        return response
