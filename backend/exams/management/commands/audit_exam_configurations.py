import json

from django.core.management.base import BaseCommand
from exams.configuration_audit import audit_exam_configuration
from exams.models import ExamConfiguration


class Command(BaseCommand):
    help = "Audit all exam configurations without changing stored settings."

    def add_arguments(self, parser):
        parser.add_argument("--only-incomplete", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        records = []
        for exam in ExamConfiguration.objects.order_by("category", "display_order", "name"):
            audit = audit_exam_configuration(exam)
            if options["only_incomplete"] and audit["ready"]:
                continue
            records.append({
                "code": exam.code,
                "name": exam.name,
                "category": exam.category,
                "status": audit["status"],
                "errors": audit["errors"],
                "warnings": audit["warnings"],
            })

        ready = sum(item["status"] == "READY" for item in records)
        incomplete = len(records) - ready
        if options["as_json"]:
            self.stdout.write(json.dumps({
                "total": len(records),
                "ready": ready,
                "incomplete": incomplete,
                "profiles": records,
            }, ensure_ascii=False, indent=2))
            return

        self.stdout.write(f"Exam configuration audit: {len(records)} profiles")
        self.stdout.write(self.style.SUCCESS(f"Ready: {ready}"))
        self.stdout.write(self.style.WARNING(f"Incomplete: {incomplete}"))
        for item in records:
            if item["status"] == "READY":
                continue
            self.stdout.write(f'\n[{item["code"]}] {item["name"]}')
            for issue in item["errors"]:
                self.stdout.write(self.style.ERROR(f"  BLOCKER: {issue}"))
            for warning in item["warnings"]:
                self.stdout.write(self.style.WARNING(f"  WARNING: {warning}"))
