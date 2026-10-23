from django.contrib import admin

from apps.surveys.models import (
    AnalysisResult,
    EvidenceRecord,
    PageText,
    PipelineAttempt,
    RuleResult,
    Survey,
    SurveyProfile,
)


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "publisher", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "publisher", "file_sha256")
    readonly_fields = ("file_sha256", "created_at")


admin.site.register(PageText)
admin.site.register(SurveyProfile)
admin.site.register(EvidenceRecord)
admin.site.register(RuleResult)
admin.site.register(AnalysisResult)
admin.site.register(PipelineAttempt)
