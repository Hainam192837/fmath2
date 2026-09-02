from django.test import TestCase

from judge.forms import ProblemSubmitForm
from judge.models import Language


class ProblemSubmitFormTestCase(TestCase):
    fixtures = ["language_all.json"]

    def test_clean_source_ignores_missing_language(self):
        form = ProblemSubmitForm()
        form.cleaned_data = {"source": 'print("hello")'}

        self.assertEqual(form.clean_source(), 'print("hello")')

    def test_is_valid_does_not_crash_for_invalid_language(self):
        language = Language.get_python3()
        form = ProblemSubmitForm(
            data={
                "source": 'print("hello")',
                "language": str(language.pk),
            }
        )
        form.fields["language"].queryset = Language.objects.filter(pk=language.pk)

        self.assertIsInstance(form.is_valid(), bool)
