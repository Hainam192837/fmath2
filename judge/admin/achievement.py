from django.contrib import admin

# from judge.models import Achievement


class AchievementAdmin(admin.ModelAdmin):
    list_display = ["name", "award", "contest", "level", "year", "rank", "featured", "avatar"]
    list_filter = ["level", "year", "rank", "featured"]
    search_fields = ["name", "award", "contest"]
    # autocomplete_fields = ["year"]
    actions_on_top = True
    actions_on_bottom = True
