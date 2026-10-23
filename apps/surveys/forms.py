from django import forms

from apps.surveys.models import Survey


class SurveyUploadForm(forms.ModelForm):
    file = forms.FileField(label="Berkas PDF laporan survei")
    source_url = forms.URLField(required=False, assume_scheme="https", label="URL sumber (opsional)")

    class Meta:
        model = Survey
        fields = [
            "title",
            "publisher",
            "publication_date",
            "period_start",
            "period_end",
            "source_url",
            "notes",
            "file",
        ]
        widgets = {
            "publication_date": forms.DateInput(attrs={"type": "date"}),
            "period_start": forms.DateInput(attrs={"type": "date"}),
            "period_end": forms.DateInput(attrs={"type": "date"}),
        }
