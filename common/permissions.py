from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    message = "Esta operación requiere el rol ADMIN."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_active and request.user.rol == "ADMIN")
