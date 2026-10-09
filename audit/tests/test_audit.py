from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import LogActividad
from audit.services import obtener_ip, registrar_actividad
from alerts.models import Alerta
from backend.workflows import recalcular_con_alertas, sincronizar_y_recalcular
from portfolios.models import Portafolio
from portfolios.services import crear_portafolio


class AuditTests(TestCase):
    password = "TemporalClave!842z"

    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.user = get_user_model().objects.create_user(
            email="audit@example.com", nombre_completo="Auditoría", password=cls.password, rol="ANALISTA")
        cls.viewer = get_user_model().objects.create_user(email="reader@example.com", nombre_completo="Lector")
        cls.admin = get_user_model().objects.create_superuser(
            email="audit-admin@example.com", password=cls.password, rol="ADMIN")

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_event_survives_deleted_actor_and_entity(self):
        event = registrar_actividad(usuario=self.viewer, accion="CONSULTAR", entidad="Pais", entidad_id="CO")
        self.viewer.delete()
        event.refresh_from_db()
        self.assertIsNone(event.usuario_id)
        self.assertEqual(event.entidad_id, "CO")
        self.assertIsNotNone(event.fecha)

    def test_invalid_action_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            LogActividad.objects.create(accion="INVALIDA", entidad_afectada="Pais")

    def test_only_typed_metadata_can_be_persisted(self):
        for payload in (
            {"password": self.password}, {"access": "secret"}, {"refresh": "secret"},
            {"headers": {"Authorization": "Bearer secret"}}, {"detalle": {"token": "secret"}},
            {"campos": ["password"]}, {"operacion": "Bearer secret"},
            {"creados": "secret"}, {"paises": ["secret"]}, {"origen": "secret"},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                registrar_actividad(accion="CREAR", entidad="Usuario", detalle=payload)
        self.assertFalse(LogActividad.objects.exists())

    def test_ip_uses_peer_and_ignores_untrusted_forwarded_headers(self):
        request = RequestFactory().get("/", REMOTE_ADDR="2001:db8::1", HTTP_X_FORWARDED_FOR="1.2.3.4")
        self.assertEqual(obtener_ip(request), "2001:db8::1")
        request.META["REMOTE_ADDR"] = "invalid"
        self.assertIsNone(obtener_ip(request))
        self.assertIsNone(obtener_ip(None))

    def test_register_login_and_profile_never_store_credentials_or_values(self):
        self.api.force_authenticate(None)
        response = self.api.post("/api/auth/register/", {
            "email": "new-audit@example.com", "nombre_completo": "Nuevo",
            "password": self.password,
        }, format="json", REMOTE_ADDR="192.0.2.10")
        self.assertEqual(response.status_code, 201)
        new = get_user_model().objects.get(pk=response.data["id"])
        event = LogActividad.objects.get(accion="CREAR")
        self.assertEqual(event.usuario, new)
        self.assertEqual(event.ip_address, "192.0.2.10")
        tokens = self.api.post("/api/auth/login/", {"email": new.email, "password": self.password}, format="json")
        self.assertEqual(tokens.status_code, 200)
        self.assertEqual(LogActividad.objects.filter(accion="LOGIN", usuario=new).count(), 1)
        self.api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens.data['access']}")
        self.assertEqual(self.api.put("/api/auth/me/", {
            "email": new.email, "nombre_completo": "Editado", "password": "NuevaClave!842z",
        }, format="json").status_code, 200)
        event = LogActividad.objects.get(accion="EDITAR", usuario=new)
        self.assertTrue(event.detalle["credenciales_actualizadas"])
        self.assertEqual(event.detalle["campos"], ["email", "nombre_completo"])
        evidence = str(list(LogActividad.objects.values("detalle")))
        for secret in (self.password, "NuevaClave!842z", tokens.data["access"], tokens.data["refresh"], "Editado"):
            self.assertNotIn(secret, evidence)

    def test_denied_invalid_and_failed_logins_do_not_create_success_events(self):
        self.api.force_authenticate(None)
        self.assertEqual(self.api.post("/api/auth/login/", {
            "email": self.user.email, "password": "wrong",
        }, format="json").status_code, 401)
        self.assertEqual(self.api.get("/api/paises/").status_code, 401)
        self.api.force_authenticate(self.viewer)
        self.assertEqual(self.api.post("/api/portafolios/", {"nombre": "Denegado"}, format="json").status_code, 403)
        self.assertEqual(self.api.get("/api/paises/CO/indicadores/?anio=invalid").status_code, 400)
        self.assertFalse(LogActividad.objects.exists())

    def test_authorized_reads_record_identifiers_not_filters_or_responses(self):
        self.assertEqual(self.api.get("/api/paises/?search=Bearer-secret").status_code, 200)
        self.assertEqual(self.api.get("/api/paises/co/").status_code, 200)
        event = LogActividad.objects.filter(entidad_id="CO").get()
        self.assertEqual(event.accion, "CONSULTAR")
        self.assertEqual(event.usuario, self.user)
        self.assertNotIn("Bearer-secret", str(list(LogActividad.objects.values())))
        count = LogActividad.objects.count()
        self.assertEqual(self.api.head("/api/paises/").status_code, 200)
        self.assertEqual(LogActividad.objects.count(), count)

    def test_portfolio_crud_records_shared_actor_version_and_ip(self):
        response = self.api.post("/api/portafolios/", {"nombre": "Mi inversión", "es_publico": True}, format="json")
        self.assertEqual(response.status_code, 201)
        pk = response.data["id"]
        event = LogActividad.objects.get(accion="CREAR")
        self.assertEqual(event.detalle["version"], 1)
        collaborator = get_user_model().objects.create_user(email="collaborator@example.com", nombre_completo="Otro", rol="ANALISTA")
        self.api.force_authenticate(collaborator)
        self.assertEqual(self.api.put(f"/api/portafolios/{pk}/", {
            "version": 1, "descripcion": "Bearer secret en descripción",
        }, format="json", REMOTE_ADDR="192.0.2.20").status_code, 200)
        event = LogActividad.objects.get(accion="EDITAR")
        self.assertEqual(event.usuario, collaborator)
        self.assertEqual(event.ip_address, "192.0.2.20")
        self.assertEqual(event.detalle["version"], 2)
        self.assertNotIn("secret", str(event.detalle))
        count = LogActividad.objects.count()
        self.assertEqual(self.api.put(f"/api/portafolios/{pk}/", {"version": 1, "descripcion": "Conflicto"}, format="json").status_code, 409)
        self.assertEqual(LogActividad.objects.count(), count)
        self.api.force_authenticate(self.user)
        self.assertEqual(self.api.delete(f"/api/portafolios/{pk}/", {"version": 2}, format="json").status_code, 204)
        event = LogActividad.objects.get(accion="ELIMINAR")
        self.assertEqual(event.entidad_id, str(pk))
        self.assertEqual(event.detalle["version"], 3)

    def test_positions_audit_create_edit_and_logical_close(self):
        portfolio = crear_portafolio(self.user, {"nombre": "Posiciones"})
        response = self.api.post(f"/api/portafolios/{portfolio.pk}/posiciones/", {
            "version": 1, "pais": "CO", "tipo_activo": "RENTA_FIJA", "monto_inversion_usd": "1000",
            "fecha_entrada": (timezone.localdate() - timedelta(days=2)).isoformat(), "notas": self.password,
        }, format="json")
        self.assertEqual(response.status_code, 201)
        pk = response.data["id"]
        url = f"/api/portafolios/{portfolio.pk}/posiciones/{pk}/"
        self.assertEqual(self.api.put(url, {"version": 2, "notas": "Private"}, format="json").status_code, 200)
        self.assertEqual(self.api.delete(url, {"version": 3}, format="json").status_code, 200)
        events = LogActividad.objects.filter(entidad_afectada="Posicion").order_by("id")
        self.assertEqual(list(events.values_list("accion", flat=True)), ["CREAR", "EDITAR", "ELIMINAR"])
        self.assertEqual([e.detalle["version"] for e in events], [2, 3, 4])
        self.assertNotIn(self.password, str(list(events.values())))

    def test_audit_failure_rolls_back_portfolio_write(self):
        with patch("portfolios.services.registrar_actividad", side_effect=IntegrityError("Audit unavailable")):
            with self.assertRaises(IntegrityError):
                crear_portafolio(self.user, {"nombre": "Debe revertirse"})
        self.assertFalse(Portafolio.objects.filter(nombre="Debe revertirse").exists())
        self.assertFalse(LogActividad.objects.exists())

    def test_audit_failure_rolls_back_profile_write(self):
        with patch("accounts.serializers.registrar_actividad", side_effect=IntegrityError("Audit unavailable")):
            response = self.api.put("/api/auth/me/", {"email": self.user.email, "nombre_completo": "Debe revertirse"}, format="json")
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.data["error"]["codigo"], "error_interno")
            self.assertNotIn("Audit unavailable", str(response.data))
        self.user.refresh_from_db()
        self.assertEqual(self.user.nombre_completo, "Auditoría")

    def test_enclosing_transaction_rolls_back_event_and_business_row(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            crear_portafolio(self.user, {"nombre": "Temporal"})
            raise RuntimeError("Cancelada")
        self.assertFalse(Portafolio.objects.filter(nombre="Temporal").exists())
        self.assertFalse(LogActividad.objects.exists())

    def test_hidden_portfolio_read_does_not_leave_a_success_event(self):
        portfolio = Portafolio.objects.create(usuario=self.admin, nombre="Privado ajeno")
        self.assertEqual(self.api.get(f"/api/portafolios/{portfolio.pk}/").status_code, 404)
        self.assertFalse(LogActividad.objects.exists())

    def test_alert_reads_are_audited_once_and_keep_recipient_privacy(self):
        from countries.models import Pais
        alerta = Alerta.objects.create(pais=Pais.objects.get(pk="CO"), tipo_alerta="RIESGO", severidad="INFO",
                                       titulo="Prueba", mensaje="Privado", clave_evento="audit-test")
        private = Alerta.objects.create(pais=alerta.pais, usuario=self.admin, tipo_alerta="RIESGO", severidad="INFO",
                                        titulo="Oculta", mensaje="Privado", clave_evento="audit-private")
        self.assertEqual(self.api.put(f"/api/alertas/{private.pk}/leer/").status_code, 404)
        self.assertFalse(LogActividad.objects.exists())
        for _ in range(2):
            self.assertEqual(self.api.put(f"/api/alertas/{alerta.pk}/leer/").status_code, 200)
        self.assertEqual(LogActividad.objects.filter(accion="EDITAR", entidad_id=str(alerta.pk)).count(), 1)

    def test_workflow_partial_summary_excludes_provider_payloads(self):
        with patch("backend.workflows.sincronizar_indicadores", return_value={
            "paises_procesados": ["CO"], "creados": 2, "actualizados": 0,
            "errores": [{"pais": "BR", "mensaje": "Bearer provider-secret"}],
        }), patch("backend.workflows.recalcular_riesgos", return_value={"calculados": [], "errores": []}), \
                patch("backend.workflows.generar_alertas", return_value={"creadas": 0, "errores": []}):
            sincronizar_y_recalcular(usuario=self.admin, ip="192.0.2.30")
        event = LogActividad.objects.get()
        self.assertEqual(event.usuario, self.admin)
        self.assertEqual(event.detalle["estado"], "PARCIAL")
        self.assertEqual(event.detalle["errores"], 1)
        self.assertEqual(event.detalle["creados"], 2)
        self.assertEqual(event.detalle["origen"], "HTTP")
        self.assertNotIn("provider-secret", str(event.detalle))

    def test_command_recalculation_has_no_actor_or_ip(self):
        with patch("backend.workflows.recalcular_riesgos", return_value={"calculados": [], "errores": []}), \
                patch("backend.workflows.generar_alertas", return_value={"creadas": 0, "errores": []}):
            recalcular_con_alertas()
        event = LogActividad.objects.get()
        self.assertIsNone(event.usuario_id)
        self.assertIsNone(event.ip_address)
        self.assertEqual(event.detalle["origen"], "COMANDO")

    def test_sync_summary_preserves_partial_state_without_transport_errors(self):
        with patch("backend.workflows.sincronizar_indicadores", return_value={
            "paises_procesados": ["CO"], "errores": [], "estado": "PARCIAL",
        }), patch("backend.workflows.recalcular_riesgos", return_value={"calculados": [], "errores": []}), \
                patch("backend.workflows.generar_alertas", return_value={"creadas": 0, "errores": []}):
            sincronizar_y_recalcular()
        event = LogActividad.objects.get()
        self.assertEqual(event.detalle["estado"], "PARCIAL")
        self.assertEqual(event.detalle["errores"], 0)

    def test_audit_failure_reports_partial_workflow_without_reverting_completed_stages(self):
        with patch("backend.workflows.recalcular_riesgos", return_value={"calculados": [], "errores": []}), \
                patch("backend.workflows.generar_alertas", return_value={"creadas": 0, "errores": []}), \
                patch("audit.services.registrar_actividad", side_effect=IntegrityError("secret provider error")):
            with self.assertLogs("audit.services", level="ERROR") as logs:
                result = recalcular_con_alertas()
        self.assertTrue(result["auditoria_pendiente"])
        self.assertEqual(result["estado"], "PARCIAL")
        self.assertEqual(result["calculados"], [])
        self.assertNotIn("secret provider error", str(logs.output))

    def test_command_fails_when_audit_is_pending(self):
        from django.core.management.base import CommandError
        with patch("risk.management.commands.calcular_riesgos.recalcular_riesgos", return_value={
            "calculados": [], "errores": [], "auditoria_pendiente": True,
        }), self.assertRaises(CommandError):
            call_command("calcular_riesgos", stdout=StringIO())

    def test_admin_is_read_only_and_restricted_by_role(self):
        model_admin = admin.site._registry[LogActividad]
        request = RequestFactory().get("/")
        request.user = self.admin
        self.assertTrue(model_admin.has_view_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        request.user = self.user
        self.assertFalse(model_admin.has_view_permission(request))

    def test_admin_create_edit_and_delete_are_audited_without_form_values(self):
        self.client.force_login(self.admin)
        url = reverse("admin:countries_moneda_add")
        response = self.client.post(url, {"codigo": "EUR", "nombre": "Euro", "_save": "Guardar"})
        self.assertEqual(response.status_code, 302)
        event = LogActividad.objects.get(accion="CREAR", entidad_afectada="Moneda")
        self.assertEqual(event.entidad_id, "EUR")
        response = self.client.post(reverse("admin:countries_moneda_change", args=["EUR"]), {
            "codigo": "EUR", "nombre": "Euro editado", "_save": "Guardar"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogActividad.objects.filter(accion="EDITAR", entidad_id="EUR").count(), 1)
        response = self.client.post(reverse("admin:countries_moneda_delete", args=["EUR"]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LogActividad.objects.filter(accion="ELIMINAR", entidad_id="EUR").count(), 1)
        self.assertNotIn("Euro editado", str(list(LogActividad.objects.values("detalle"))))

    def test_admin_bulk_delete_keeps_an_event_per_entity(self):
        from countries.models import Moneda
        Moneda.objects.create(codigo="EUR", nombre="Euro")
        Moneda.objects.create(codigo="GBP", nombre="Libra")
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:countries_moneda_changelist"), {
            "action": "delete_selected", "_selected_action": ["EUR", "GBP"], "post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(LogActividad.objects.filter(accion="ELIMINAR").values_list("entidad_id", flat=True)), {"EUR", "GBP"})

    def test_admin_password_change_has_no_secret_evidence(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("admin:auth_user_password_change", args=[self.user.pk]), {
            "password1": "OtraClave!842z", "password2": "OtraClave!842z", "usable_password": "true"})
        self.assertEqual(response.status_code, 302)
        event = LogActividad.objects.get(accion="EDITAR", entidad_id=str(self.user.pk))
        self.assertTrue(event.detalle["credenciales_actualizadas"])
        self.assertNotIn("OtraClave!842z", str(event.detalle))
