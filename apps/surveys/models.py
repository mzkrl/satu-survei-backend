from django.contrib.auth.models import User
from django.db import models


class Survey(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Menunggu"
        PROCESSING = "processing", "Diproses"
        COMPLETED = "completed", "Selesai"
        REJECTED_METADATA = "rejected_metadata", "Metadata ditolak"
        REJECTED_FILE = "rejected_file", "Berkas ditolak"
        FAILED_NORMALIZATION = "failed_normalization", "Ekstraksi gagal"
        FAILED_ANALYSIS = "failed_analysis", "Analisis gagal"
        FAILED_SYSTEM = "failed_system", "Sistem gagal"

    title = models.CharField(max_length=300)
    publisher = models.CharField(max_length=300)
    publication_date = models.DateField()
    period_start = models.DateField()
    period_end = models.DateField()
    source_url = models.URLField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    file = models.FileField(upload_to="surveys/%Y/%m/", null=True, blank=True)
    file_sha256 = models.CharField(max_length=64, unique=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    error_stage = models.CharField(max_length=32, blank=True, default="")
    error_reason = models.TextField(blank=True, default="")
    total_attempts = models.PositiveIntegerField(default=0)
    llm_model = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.CharField(max_length=50, blank=True, default="")
    schema_version = models.CharField(max_length=50, blank=True, default="")
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="surveys")
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class PageText(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="pages")
    page_no = models.PositiveIntegerField()
    text = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["survey", "page_no"], name="unique_page_per_survey"),
        ]

    def __str__(self) -> str:
        return f"{self.survey_id} p{self.page_no}"


class SurveyProfile(models.Model):
    survey = models.OneToOneField(Survey, on_delete=models.CASCADE, related_name="profile")
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"profile:{self.survey_id}"


class EvidenceRecord(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="evidence")
    key = models.CharField(max_length=10)
    label_original = models.TextField()
    label_normalized = models.TextField(blank=True, default="")
    value = models.FloatField(null=True, blank=True)
    value_raw = models.CharField(max_length=200, blank=True, default="")
    unit = models.CharField(max_length=50, blank=True, default="")
    period = models.CharField(max_length=100, blank=True, default="")
    geography = models.CharField(max_length=150, blank=True, default="")
    definition = models.TextField(blank=True, default="")
    source_page = models.PositiveIntegerField(null=True, blank=True)
    source_excerpt = models.TextField(blank=True, default="")
    unknown_fields = models.JSONField(default=list)
    grounded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["survey", "key"], name="unique_evidence_key_per_survey"),
        ]

    def __str__(self) -> str:
        return f"{self.survey_id}:{self.key}"


class RuleResult(models.Model):
    class Status(models.TextChoices):
        PASS = "pass", "Lulus"
        WARN = "warn", "Perlu perhatian"
        FAIL = "fail", "Tidak lulus"
        NA = "na", "Tidak tersedia"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="rule_results")
    rule_id = models.CharField(max_length=10)
    status = models.CharField(max_length=10, choices=Status.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["survey", "rule_id"], name="unique_rule_per_survey"),
        ]

    def __str__(self) -> str:
        return f"{self.survey_id}:{self.rule_id}:{self.status}"


class AnalysisResult(models.Model):
    survey = models.OneToOneField(Survey, on_delete=models.CASCADE, related_name="analysis")
    summary = models.TextField()
    findings = models.JSONField(default=list)
    caveats = models.JSONField(default=list)
    visualizations = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"analysis:{self.survey_id}"


class PipelineAttempt(models.Model):
    class Stage(models.TextChoices):
        NORMALIZATION = "normalization", "Normalisasi"
        ANALYSIS = "analysis", "Analisis"

    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name="attempts")
    stage = models.CharField(max_length=20, choices=Stage.choices)
    attempt_no = models.PositiveIntegerField()
    ok = models.BooleanField()
    error = models.TextField(blank=True, default="")
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    model = models.CharField(max_length=100, blank=True, default="")
    prompt_version = models.CharField(max_length=50, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.survey_id}:{self.stage}:{self.attempt_no}"
