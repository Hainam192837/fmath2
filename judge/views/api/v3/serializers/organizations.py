from judge.views.api.v3.serializers.users import serialize_profile_summary


def serialize_organization_list_item(organization):
    return {
        "id": organization.id,
        "slug": organization.slug,
        "name": organization.name,
        "short_name": organization.short_name,
        "is_open": organization.is_open,
        "is_hidden": organization.is_hidden,
        "logo_override_image": organization.logo_override_image,
        "member_count": getattr(organization, "member_count", None),
    }


def serialize_organization_detail(organization):
    members = (
        organization.members.filter(is_unlisted=False)
        .select_related("user")
        .order_by("-performance_points", "-problem_count")[:20]
    )
    return {
        **serialize_organization_list_item(organization),
        "about": organization.about,
        "creation_date": organization.creation_date.isoformat(),
        "admins": list(organization.admins.values_list("user__username", flat=True)),
        "members_preview": [serialize_profile_summary(member) for member in members],
    }
