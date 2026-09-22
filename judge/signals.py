import errno
import os

from django.conf import settings
from django.contrib.auth import user_logged_in
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db.models import F
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_save
from django.dispatch import receiver

from .caching import finished_submission
from .models import (
    EFFECTIVE_MATH_ENGINES,
    Achievement,
    BlogPost,
    Comment,
    Contest,
    ContestProblem,
    ContestSubmission,
    Judge,
    Language,
    License,
    LoggedInUser,
    Metadata,
    MiscConfig,
    Organization,
    Problem,
    Profile,
    SchoolYear,
    Submission,
    WebAuthnCredential,
)


def bump_api_metadata_prefix(*prefixes):
    for prefix in prefixes:
        Metadata.bump_prefix(prefix)


def bump_problem_version(problem_id):
    Problem.objects.filter(id=problem_id).update(version_update=F("version_update") + 1)


def bump_contest_version(contest_id):
    Contest.objects.filter(id=contest_id).update(version_update=F("version_update") + 1)


def get_pdf_path(basename):
    return os.path.join(settings.PDF_PROBLEM_CACHE, basename)


def get_pdf_contest_path(basename):
    return os.path.join(settings.PDF_CONTEST_CACHE, basename)


def unlink_if_exists(file):
    try:
        os.unlink(file)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise


@receiver(post_save, sender=Problem)
def problem_update(sender, instance, **kwargs):
    if hasattr(instance, "_updating_stats_only"):
        return

    cache.delete_many(
        [
            make_template_fragment_key("submission_problem", (instance.id,)),
            make_template_fragment_key("problem_feed", (instance.id,)),
            "problem_tls:%s" % instance.id,
            "problem_mls:%s" % instance.id,
        ]
    )
    cache.delete_many(
        [
            make_template_fragment_key("problem_html", (instance.id, engine, lang))
            for lang, _ in settings.LANGUAGES
            for engine in EFFECTIVE_MATH_ENGINES
        ]
    )
    cache.delete_many(
        [make_template_fragment_key("problem_authors", (instance.id, lang)) for lang, _ in settings.LANGUAGES]
    )
    cache.delete_many(["generated-meta-problem:%s:%d" % (lang, instance.id) for lang, _ in settings.LANGUAGES])

    for lang, _ in settings.LANGUAGES:
        unlink_if_exists(get_pdf_path("%s.%s.pdf" % (instance.code, lang)))

    bump_api_metadata_prefix("api:v3:problems:list:", f"api:v3:problems:{instance.code}:", "api:v3:contests:")


@receiver(post_delete, sender=Problem)
def problem_delete(sender, instance, **kwargs):
    bump_api_metadata_prefix("api:v3:problems:list:", f"api:v3:problems:{instance.code}:", "api:v3:contests:")


@receiver(post_save, sender=Profile)
def profile_update(sender, instance, **kwargs):
    if hasattr(instance, "_updating_stats_only"):
        return

    cache.delete_many(
        [make_template_fragment_key("user_about", (instance.id, engine)) for engine in EFFECTIVE_MATH_ENGINES]
        + [
            make_template_fragment_key("org_member_count", (org_id,))
            for org_id in instance.organizations.values_list("id", flat=True)
        ]
    )
    bump_api_metadata_prefix(
        "api:v3:users:list:",
        f"api:v3:users:{instance.user.username}:",
        "api:v3:organizations:list:",
    )


@receiver(post_delete, sender=Profile)
def profile_delete(sender, instance, **kwargs):
    bump_api_metadata_prefix(
        "api:v3:users:list:",
        f"api:v3:users:{instance.user.username}:",
        "api:v3:organizations:list:",
    )


@receiver(post_delete, sender=WebAuthnCredential)
def webauthn_delete(sender, instance, **kwargs):
    profile = instance.user
    if profile.webauthn_credentials.count() == 0:
        profile.is_webauthn_enabled = False
        profile.save(update_fields=["is_webauthn_enabled"])


@receiver(post_save, sender=Contest)
def contest_update(sender, instance, **kwargs):
    if hasattr(instance, "_updating_stats_only"):
        return

    for lang, _ in settings.LANGUAGES:
        unlink_if_exists(get_pdf_contest_path("%s.%s.pdf" % (instance.key, lang)))

    cache.delete_many(
        ["generated-meta-contest:%d" % instance.id]
        + [make_template_fragment_key("contest_html", (instance.id, engine)) for engine in EFFECTIVE_MATH_ENGINES]
    )
    bump_api_metadata_prefix("api:v3:contests:list:", f"api:v3:contests:{instance.key}:")


@receiver(post_delete, sender=Contest)
def contest_delete(sender, instance, **kwargs):
    bump_api_metadata_prefix("api:v3:contests:list:", f"api:v3:contests:{instance.key}:")


@receiver(post_save, sender=License)
def license_update(sender, instance, **kwargs):
    cache.delete(make_template_fragment_key("license_html", (instance.id,)))


@receiver(post_save, sender=Language)
def language_update(sender, instance, **kwargs):
    cache.delete_many([make_template_fragment_key("language_html", (instance.id,)), "lang:cn_map"])


@receiver(post_save, sender=Judge)
def judge_update(sender, instance, **kwargs):
    cache.delete(make_template_fragment_key("judge_html", (instance.id,)))


@receiver(post_save, sender=Comment)
def comment_update(sender, instance, **kwargs):
    cache.delete("comment_feed:%d" % instance.id)


@receiver(post_save, sender=BlogPost)
def post_update(sender, instance, **kwargs):
    cache.delete_many(
        [
            make_template_fragment_key("post_summary", (instance.id,)),
            "blog_slug:%d" % instance.id,
            "blog_feed:%d" % instance.id,
        ]
    )
    cache.delete_many(
        [make_template_fragment_key("post_content", (instance.id, engine)) for engine in EFFECTIVE_MATH_ENGINES]
    )


@receiver(post_delete, sender=Submission)
def submission_delete(sender, instance, **kwargs):
    finished_submission(instance)
    instance.user._updating_stats_only = True
    instance.user.calculate_points()
    instance.problem._updating_stats_only = True
    instance.problem.update_stats()


@receiver(post_delete, sender=ContestSubmission)
def contest_submission_delete(sender, instance, **kwargs):
    participation = instance.participation
    participation.recompute_results()
    Submission.objects.filter(id=instance.submission_id).update(contest_object=None)


@receiver(post_save, sender=Organization)
def organization_update(sender, instance, **kwargs):
    cache.delete_many(
        [make_template_fragment_key("organization_html", (instance.id, engine)) for engine in EFFECTIVE_MATH_ENGINES]
    )
    bump_api_metadata_prefix("api:v3:organizations:list:", f"api:v3:organizations:{instance.id}:")


@receiver(post_delete, sender=Organization)
def organization_delete(sender, instance, **kwargs):
    bump_api_metadata_prefix("api:v3:organizations:list:", f"api:v3:organizations:{instance.id}:")


@receiver(post_save, sender=ContestProblem)
def contest_problem_update(sender, instance, **kwargs):
    bump_contest_version(instance.contest_id)
    bump_api_metadata_prefix("api:v3:contests:list:", f"api:v3:contests:{instance.contest.key}:")


@receiver(post_delete, sender=ContestProblem)
def contest_problem_delete(sender, instance, **kwargs):
    bump_contest_version(instance.contest_id)
    bump_api_metadata_prefix("api:v3:contests:list:", f"api:v3:contests:{instance.contest.key}:")


@receiver(m2m_changed, sender=Contest.tags.through)
@receiver(m2m_changed, sender=Contest.authors.through)
@receiver(m2m_changed, sender=Contest.curators.through)
@receiver(m2m_changed, sender=Contest.organizations.through)
@receiver(m2m_changed, sender=Contest.testers.through)
@receiver(m2m_changed, sender=Contest.view_contest_scoreboard.through)
@receiver(m2m_changed, sender=Contest.banned_users.through)
def contest_m2m_update(sender, instance, action, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if isinstance(instance, Contest):
        bump_contest_version(instance.id)
        bump_api_metadata_prefix("api:v3:contests:list:", f"api:v3:contests:{instance.key}:")
        return

    bump_api_metadata_prefix("api:v3:contests:list:")
    pk_set = kwargs.get("pk_set")
    if pk_set:
        for contest in Contest.objects.filter(id__in=pk_set).only("id", "key"):
            bump_contest_version(contest.id)
            bump_api_metadata_prefix(f"api:v3:contests:{contest.key}:")


@receiver(m2m_changed, sender=Problem.authors.through)
@receiver(m2m_changed, sender=Problem.curators.through)
@receiver(m2m_changed, sender=Problem.testers.through)
@receiver(m2m_changed, sender=Problem.types.through)
@receiver(m2m_changed, sender=Problem.allowed_languages.through)
@receiver(m2m_changed, sender=Problem.organizations.through)
def problem_m2m_update(sender, instance, action, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if isinstance(instance, Problem):
        bump_problem_version(instance.id)
        bump_api_metadata_prefix(f"api:v3:problems:{instance.code}:")
    else:
        pk_set = kwargs.get("pk_set")
        if pk_set:
            for problem in Problem.objects.filter(id__in=pk_set).only("id", "code"):
                bump_problem_version(problem.id)
                bump_api_metadata_prefix(f"api:v3:problems:{problem.code}:")
    bump_api_metadata_prefix("api:v3:problems:list:", "api:v3:contests:")


@receiver(m2m_changed, sender=Profile.organizations.through)
def profile_organizations_update(sender, instance, action, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if not isinstance(instance, Profile):
        bump_api_metadata_prefix(
            "api:v3:users:list:",
            "api:v3:organizations:list:",
            "api:v3:problems:",
            "api:v3:contests:",
        )
        pk_set = kwargs.get("pk_set")
        if pk_set:
            for profile in Profile.objects.filter(id__in=pk_set).select_related("user").only("id", "user__username"):
                bump_api_metadata_prefix(f"api:v3:users:{profile.user.username}:")
        return

    bump_api_metadata_prefix(
        "api:v3:users:list:",
        f"api:v3:users:{instance.user.username}:",
        "api:v3:organizations:list:",
        "api:v3:problems:",
        "api:v3:contests:",
    )


@receiver(m2m_changed, sender=Organization.admins.through)
def organization_admins_update(sender, instance, action, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if not isinstance(instance, Organization):
        bump_api_metadata_prefix("api:v3:organizations:list:")
        pk_set = kwargs.get("pk_set")
        if pk_set:
            for organization_id in pk_set:
                bump_api_metadata_prefix(f"api:v3:organizations:{organization_id}:")
        return

    bump_api_metadata_prefix("api:v3:organizations:list:", f"api:v3:organizations:{instance.id}:")


@receiver(post_save, sender=Achievement)
@receiver(post_delete, sender=Achievement)
@receiver(post_save, sender=SchoolYear)
@receiver(post_delete, sender=SchoolYear)
def achievement_api_cache_invalidate(sender, instance, **kwargs):
    cache.delete_many(
        [
            "api_app_v3:achievement:years",
            "api_app_v3:achievement:featured",
            "api_app_v3:achievement:all",
        ]
    )


_misc_config_i18n = [code for code, _ in settings.LANGUAGES]
_misc_config_i18n.append("")


def misc_config_cache_delete(key):
    cache.delete_many(
        [
            "misc_config:%s:%s:%s" % (domain, lang, key.split(".")[0])
            for lang in _misc_config_i18n
            for domain in Site.objects.values_list("domain", flat=True)
        ]
    )


@receiver(pre_save, sender=MiscConfig)
def misc_config_pre_save(sender, instance, **kwargs):
    try:
        old_key = MiscConfig.objects.filter(id=instance.id).values_list("key").get()[0]
    except MiscConfig.DoesNotExist:
        old_key = None
    instance._old_key = old_key


@receiver(post_save, sender=MiscConfig)
def misc_config_update(sender, instance, **kwargs):
    misc_config_cache_delete(instance.key)
    if instance._old_key is not None and instance._old_key != instance.key:
        misc_config_cache_delete(instance._old_key)


@receiver(post_delete, sender=MiscConfig)
def misc_config_delete(sender, instance, **kwargs):
    misc_config_cache_delete(instance.key)


@receiver(post_save, sender=ContestSubmission)
def contest_submission_update(sender, instance, **kwargs):
    Submission.objects.filter(id=instance.submission_id).update(contest_object_id=instance.participation.contest_id)


@receiver(user_logged_in)
def user_logged_in_signal(sender, **kwargs):
    LoggedInUser.objects.get_or_create(user=kwargs.get("user"))


# @receiver(user_logged_out)
# def user_logged_out_signal(sender, **kwargs):
#     LoggedInUser.objects.filter(user=kwargs.get('user')).delete()
