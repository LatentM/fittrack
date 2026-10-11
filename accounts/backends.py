from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameBackend(ModelBackend):
    """Lets people sign in with either their username or their email address."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None
        user = (
            UserModel._default_manager.filter(Q(username__iexact=username) | Q(email__iexact=username))
            .order_by("id")
            .first()
        )
        if user is None:
            # Run the hasher anyway so response time doesn't reveal whether the account exists.
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
