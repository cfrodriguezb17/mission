from django.contrib.auth import get_user_model
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm

User = get_user_model()


class NormalizedEmailMixin:
    def clean_email(self):
        # Se normaliza antes de que ModelForm compruebe la unicidad.
        return User.objects.validate_email(self.cleaned_data["email"])


class AdminUserCreationForm(NormalizedEmailMixin, BaseUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "nombre_completo", "rol", "is_active")


class AdminUserChangeForm(NormalizedEmailMixin, UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"
