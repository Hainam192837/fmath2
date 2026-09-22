from django.contrib.auth.backends import ModelBackend
from django.utils import timezone


class CustomAuthBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):
        user = super().authenticate(
            request, username=username, password=password, **kwargs
        )
        if user is not None:
            # Dùng getattr để nếu không có profile sẽ trả về None thay vì sập web
            profile = getattr(user, "profile", None)
            if (
                profile
                and profile.expiration_date is not None
                and profile.expiration_date < timezone.now()
            ):
                return None
        return user