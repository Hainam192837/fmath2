from django.db import migrations


def reset_limit_problem(apps, schema_editor):
    ContestProblem = apps.get_model("judge", "ContestProblem")
    ContestProblem.objects.exclude(limit_problem=0).update(limit_problem=0)


class Migration(migrations.Migration):
    dependencies = [
        ("judge", "0200_alter_contest_is_exam_contest"),
    ]

    operations = [
        migrations.RenameField(
            model_name="contestproblem",
            old_name="limit_point",
            new_name="limit_problem",
        ),
        migrations.RunPython(reset_limit_problem, migrations.RunPython.noop),
    ]
