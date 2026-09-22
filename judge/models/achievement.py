# {
#   id: 24,
#   name: "Vương Quốc Bảo",
#   award: "Giải Ba HSG Tỉnh",
#   contest: "Kỳ thi HSG Tỉnh môn Tin học lớp 12",
#   level: "THPT",
#   year: "2022-2023",
#   rank: "bronze",
# }

from django.db import models
from django.utils.translation import gettext_lazy as _


class Achievement(models.Model):
    RANK_CHOICES = [
        ('gold', _('Gold')),
        ('silver', _('Silver')),
        ('bronze', _('Bronze')),
        ('special', _('Special')),
    ]

    LEVEL_CHOICES = [
        ('primary', _('Primary')),
        ('secondary', _('Secondary')),
        ('high', _('High School')),
    ]

    name = models.CharField(max_length=255, help_text="Tên học sinh đạt thành tích")
    award = models.CharField(max_length=255, help_text="Tên giải thưởng đạt được")
    contest = models.CharField(max_length=255, help_text="Tên cuộc thi")
    level = models.CharField(max_length=255, choices=LEVEL_CHOICES, help_text="Cấp độ học sinh")
    year = models.ForeignKey('SchoolYear', on_delete=models.SET_NULL, null=True, help_text="Năm học")
    rank = models.CharField(max_length=255, choices=RANK_CHOICES, default='special', help_text="Hạng thành tích")
    featured = models.BooleanField(default=False, help_text="Hiển thị trên trang chủ")
    avatar = models.ImageField(upload_to="achievement/avatars/", null=True, blank=True, help_text="Ảnh đại diện")

    def __str__(self):
        return self.name + " - " + self.award + " (" + self.contest + ")"
