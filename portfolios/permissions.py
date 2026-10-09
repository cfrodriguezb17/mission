from rest_framework.exceptions import NotFound, PermissionDenied

from common.permissions import require_writer_role as exigir_escritura


def puede_ver(usuario, portafolio):
    return usuario.is_active and (usuario.rol == "ADMIN" or portafolio.usuario_id == usuario.pk or portafolio.es_publico)


def exigir_edicion(usuario, portafolio, solo_propietario=False):
    if not puede_ver(usuario, portafolio):
        raise NotFound("Portafolio no encontrado.")
    exigir_escritura(usuario)
    if solo_propietario and usuario.rol != "ADMIN" and portafolio.usuario_id != usuario.pk:
        raise PermissionDenied("Solo el propietario o ADMIN puede eliminar el portafolio o cambiar su visibilidad.")
