from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .services import obtener_ip, registrar_actividad


@receiver(user_logged_in, dispatch_uid="audit.session_login")
def registrar_login_sesion(sender, request, user, **kwargs):
    registrar_actividad(usuario=user, accion="LOGIN", entidad="Usuario", entidad_id=user.pk,
                        ip=obtener_ip(request), detalle={"operacion": "login", "origen": "ADMIN"})
