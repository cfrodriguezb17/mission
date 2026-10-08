from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .forms import AdminUserChangeForm, AdminUserCreationForm

User = get_user_model()


@admin.register(User)
class AccountsUserAdmin(UserAdmin):
    form = AdminUserChangeForm
    add_form = AdminUserCreationForm
    list_display = ("email", "nombre_completo", "rol", "is_active", "is_staff")
    list_filter = ("rol", "is_active", "is_staff", "is_superuser")
    search_fields = ("email", "nombre_completo")
    ordering = ("email",)
    readonly_fields = ("username", "fecha_creacion", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password", "username")}),
        ("Perfil", {"fields": ("nombre_completo", "rol", "is_active")}),
        ("Permisos de Django", {
            "fields": ("is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Fechas", {"fields": ("fecha_creacion", "last_login")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "email", "nombre_completo", "rol", "is_active",
                "password1", "password2",
            ),
        }),
    )

    # Este panel permite gestionar roles y permisos: acceso solo a superusuarios.
    def has_module_permission(self, request):
        return request.user.is_superuser and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return request.user.is_superuser and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and super().has_delete_permission(request, obj)
