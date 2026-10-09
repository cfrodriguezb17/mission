from io import StringIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from alerts.models import Alerta, LecturaAlerta
from alerts.services import leer_alerta, leer_todas
from countries.models import Pais


class AlertTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.user = get_user_model().objects.create_user(email="alerts@example.com", nombre_completo="Alertas")
        cls.other = get_user_model().objects.create_user(email="other-alerts@example.com", nombre_completo="Otra persona")
        cls.global_alert = Alerta.objects.create(pais_id="CO", tipo_alerta="RIESGO", severidad="CRITICAL",
                                                 titulo="Global", mensaje="Visible para todos")
        cls.private = Alerta.objects.create(pais_id="CO", usuario=cls.user, tipo_alerta="INDICADOR", severidad="INFO",
                                            titulo="Privada", mensaje="Solo destinatario")
        cls.foreign = Alerta.objects.create(pais_id="BR", usuario=cls.other, tipo_alerta="TIPO_CAMBIO", severidad="WARNING",
                                            titulo="De otra persona", mensaje="No visible")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.list_url = reverse("alerts:listado")
        self.summary = reverse("alerts:resumen")
        self.all_url = reverse("alerts:leer-todas")
        self.read_url = reverse("alerts:leer", args=[self.global_alert.pk])

    def test_authentication_all_endpoints(self):
        self.client.force_authenticate(None)
        for method, url in (("get", self.list_url), ("get", self.summary), ("put", self.all_url), ("put", self.read_url)):
            self.assertEqual(getattr(self.client, method)(url).status_code, 401)

    def test_private_visibility_for_all_roles_even_superuser(self):
        for role in ("ADMIN", "ANALISTA", "VIEWER"):
            self.user.rol = role
            self.user.is_superuser = True
            response = self.client.get(self.list_url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["count"], 2)
            self.assertNotIn(self.foreign.pk, [row["id"] for row in response.data["results"]])
            self.assertEqual(self.client.put(reverse("alerts:leer", args=[self.foreign.pk])).status_code, 404)
            self.assertEqual(self.client.put(reverse("alerts:leer", args=[99999])).status_code, 404)

    def test_global_reads_are_independent_and_retries_keep_timestamp(self):
        response = self.client.put(self.read_url)
        self.assertTrue(response.data["leida"])
        first = LecturaAlerta.objects.get(usuario=self.user, alerta=self.global_alert).fecha_lectura
        self.assertEqual(self.client.put(self.read_url).status_code, 200)
        self.assertEqual(LecturaAlerta.objects.get(usuario=self.user, alerta=self.global_alert).fecha_lectura, first)
        self.assertEqual(LecturaAlerta.objects.count(), 1)
        self.client.force_authenticate(self.other)
        data = self.client.get(self.list_url, {"leida": "false"}).data
        self.assertIn(self.global_alert.pk, [row["id"] for row in data["results"]])
        self.assertEqual(self.client.put(self.read_url).status_code, 200)
        self.assertEqual(LecturaAlerta.objects.count(), 2)

    def test_read_all_is_idempotent_and_limited_to_visible(self):
        self.assertEqual(self.client.put(self.all_url).data, {"marcadas": 2})
        self.assertEqual(self.client.put(self.all_url).data, {"marcadas": 0})
        self.assertFalse(LecturaAlerta.objects.filter(alerta=self.foreign).exists())
        self.assertEqual(self.client.get(self.list_url, {"leida": "false"}).data["count"], 0)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.list_url, {"leida": "false"}).data["count"], 2)

    def test_summary_respects_privacy_and_read_state(self):
        self.client.put(self.read_url)
        data = self.client.get(self.summary).data
        self.assertEqual((data["total"], data["no_leidas"]), (2, 1))
        self.assertEqual(data["por_severidad"]["WARNING"], {"total": 0, "no_leidas": 0})
        self.assertEqual(data["por_tipo"]["RIESGO"], {"total": 1, "no_leidas": 0})
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.summary).data["no_leidas"], 2)

    def test_filters_pagination_order_and_query_count(self):
        for filters in ({"tipo_alerta": "RIESGO"}, {"severidad": "CRITICAL"}):
            response = self.client.get(self.list_url, filters)
            self.assertEqual(response.data["count"], 1)
        with self.assertNumQueries(3):  # conteo, listado e INSERT de auditoría
            data = self.client.get(self.list_url, {"page_size": 1, "ordering": "id"}).data
            self.assertEqual(data["results"][0]["id"], self.global_alert.pk)
            self.assertIsNotNone(data["next"])
        self.client.put(self.read_url)
        self.assertEqual(self.client.get(self.list_url, {"leida": "true"}).data["count"], 1)

    def test_invalid_parameters_and_write_methods(self):
        for params in ({"leida": "maybe"}, {"tipo_alerta": "X"}, {"severidad": "X"},
                       {"ordering": "password"}, {"ordering": "--id"}, {"ordering": ""}):
            self.assertEqual(self.client.get(self.list_url, params).status_code, 400)
        for method in ("post", "put", "patch", "delete"):
            self.assertEqual(getattr(self.client, method)(self.list_url).status_code, 405)
        self.assertEqual(self.client.get(self.all_url).status_code, 405)
        self.assertEqual(self.client.post(self.read_url).status_code, 405)

    def test_database_constraints_and_protected_private_recipient(self):
        for field, invalid in (("tipo_alerta", "X"), ("severidad", "X"), ("titulo", " "), ("mensaje", " ")):
            with self.assertRaises(IntegrityError), transaction.atomic():
                Alerta.objects.filter(pk=self.private.pk).update(**{field: invalid})
        with self.assertRaises(ProtectedError):
            self.user.delete()
        with self.assertRaises(ProtectedError):
            Pais.objects.get(pk="CO").delete()
        self.private.refresh_from_db()
        self.assertEqual(self.private.usuario_id, self.user.pk)
        read = leer_alerta(self.user, self.global_alert.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LecturaAlerta.objects.create(usuario=self.user, alerta=self.global_alert)
        self.global_alert.delete()
        self.assertFalse(LecturaAlerta.objects.filter(pk=read.pk).exists())

    def test_services_enforce_private_visibility(self):
        from django.http import Http404
        with self.assertRaises(Http404):
            leer_alerta(self.user, self.foreign.pk)
        self.assertEqual(leer_todas(self.user), 2)

    def test_admin_preserves_privacy_and_immutable_evidence(self):
        self.user.is_staff = self.user.is_superuser = True
        request = RequestFactory().get("/admin/")
        request.user = self.user
        model_admin = admin.site._registry[Alerta]
        self.assertEqual(model_admin.get_queryset(request).count(), 2)
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertFalse(model_admin.has_add_permission(request))
        leer_todas(self.other)
        lectura_admin = admin.site._registry[LecturaAlerta]
        self.assertEqual(lectura_admin.get_queryset(request).count(), 0)
