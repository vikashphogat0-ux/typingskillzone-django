"""Local-only Cloudflare Worker entrypoint for Django WSGI smoke testing.

Do not use this entrypoint for preview or production deployment. It uses
isolated Django test settings and does not configure Hyperdrive or secrets.
"""

import os
import sys
from pathlib import Path

from workers import WorkerEntrypoint, wsgi

BACKEND_DIR = str(Path(__file__).resolve().parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ["DJANGO_SETTINGS_MODULE"] = "config.cloudflare_test_settings"
os.environ["DJANGO_DEBUG"] = "true"
os.environ["DJANGO_DB_ENGINE"] = "django.db.backends.sqlite3"


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        from django.core.wsgi import get_wsgi_application

        application = get_wsgi_application()
        return await wsgi.fetch(application, request, self.env)
