from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def has_role(user, roles):
    return bool(user and user.is_authenticated and user.is_active and user.rol in roles)


def require_writer_role(user):
    if not has_role(user, ("ADMIN", "ANALISTA")):
        raise PermissionDenied("Esta operación requiere el rol ADMIN o ANALISTA.")


class IsAdminRole(BasePermission):
    message = "Esta operación requiere el rol ADMIN."

    def has_permission(self, request, view):
        return has_role(request.user, ("ADMIN",))
