from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from apps.pipeline.orchestrator import demo_cache_path, run_pipeline, save_demo_cache
from apps.surveys.models import Survey
from apps.surveys.services import create_or_get_survey


class Command(BaseCommand):
    help = (
        "Muat survei demo dari demo/pdfs/manifest.json ke database. "
        "Tanpa --generate-cache, hasil dimuat dari cache (tanpa LLM). "
        "Dengan --generate-cache, jalankan pipeline LLM asli sekali lalu simpan cache."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--generate-cache",
            action="store_true",
            help="Jalankan pipeline LLM asli untuk PDF yang belum punya cache.",
        )

    def handle(self, *args, **options) -> None:
        generate_cache = options["generate_cache"]
        pdf_dir = Path(settings.BASE_DIR) / "demo" / "pdfs"
        manifest_path = pdf_dir / "manifest.json"
        if not manifest_path.is_file():
            raise CommandError(
                f"Manifest tidak ditemukan: {manifest_path}. "
                "Jalankan scripts/generate_demo_pdfs.py terlebih dahulu."
            )
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))

        for entry in entries:
            pdf_path = pdf_dir / entry["file"]
            if not pdf_path.is_file():
                self.stderr.write(f"SKIP {entry['file']}: PDF tidak ada")
                continue
            cleaned = {
                "title": entry["title"],
                "publisher": entry["publisher"],
                "publication_date": date.fromisoformat(entry["publication_date"]),
                "period_start": date.fromisoformat(entry["period_start"]),
                "period_end": date.fromisoformat(entry["period_end"]),
                "source_url": entry.get("source_url", ""),
                "notes": entry.get("notes", ""),
            }
            with pdf_path.open("rb") as handle:
                uploaded = File(handle, name=entry["file"])
                survey, created = create_or_get_survey(
                    cleaned_data=cleaned, uploaded_file=uploaded
                )

            if survey.status not in (
                Survey.Status.PENDING,
                Survey.Status.PROCESSING,
            ):
                self.stdout.write(
                    f"SUDAH {entry['file']}: survey={survey.pk} status={survey.status}"
                )
                continue

            has_cache = demo_cache_path(survey).is_file()
            if generate_cache:
                if has_cache:
                    self.stdout.write(
                        f"CACHE {entry['file']}: sudah ada, lewati generate"
                    )
                with override_settings(DEMO_MODE=True):
                    survey = run_pipeline(survey.pk)
                if survey.status == Survey.Status.COMPLETED:
                    path = save_demo_cache(survey)
                    self.stdout.write(f"OK {entry['file']}: cache -> {path.name}")
                    continue
            elif has_cache:
                with override_settings(DEMO_MODE=True):
                    survey = run_pipeline(survey.pk)
                self.stdout.write(
                    f"OK {entry['file']}: survey={survey.pk} status={survey.status}"
                )
                continue
            else:
                self.stderr.write(
                    f"SKIP {entry['file']}: belum ada cache. "
                    "Jalankan dengan --generate-cache (butuh API key)."
                )
                continue

            self.stderr.write(
                f"GAGAL {entry['file']}: status={survey.status} "
                f"stage={survey.error_stage} reason={survey.error_reason[:200]}"
            )

        completed = Survey.objects.filter(status=Survey.Status.COMPLETED).count()
        self.stdout.write(self.style.SUCCESS(f"Selesai. Survei completed di DB: {completed}"))
