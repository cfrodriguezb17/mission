from .services import obtener_ip, registrar_actividad


class ConsultaAuditadaMixin:
    """Una consulta GET autorizada y correcta produce un evento sin filtros ni datos."""
    audit_entidad = None
    audit_id_kwarg = None

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method == "GET" and 200 <= response.status_code < 300 and request.user.is_authenticated:
            entity_id = self.kwargs.get(self.audit_id_kwarg, "") if self.audit_id_kwarg else ""
            if self.audit_entidad == "Usuario":
                entity_id = request.user.pk
            registrar_actividad(usuario=request.user, accion="CONSULTAR", entidad=self.audit_entidad,
                                entidad_id=str(entity_id).upper(), ip=obtener_ip(request),
                                detalle={"operacion": "consulta", "origen": "HTTP"})
        return response
