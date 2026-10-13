from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient


class OperationResponseTests(TestCase):
    cases = (
        ("/api/paises/sync-indicadores/", "economics.views.sincronizar_indicadores", "paises_procesados", "CO"),
        ("/api/riesgo/calcular/", "risk.views.recalcular_riesgos", "calculados", {"pais": "CO", "id": 1}),
    )

    @classmethod
    def setUpTestData(cls):
        call_command("seed_countries", stdout=StringIO())
        cls.admin = get_user_model().objects.create_user(
            email="operation-response@example.com", nombre_completo="Pruebas de resultados", rol="ADMIN")

    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_total_failures_share_envelope_and_preserve_workflow_metadata(self):
        errors = [{"pais": "CO", "mensaje": "No se pudo completar la operación."}]
        for path, target, completed_key, _ in self.cases:
            result = {completed_key: [], "errores": errors, "alertas_pendientes": True,
                      "auditoria_pendiente": True}
            original = deepcopy(result)
            with self.subTest(path=path), patch(target, return_value=result):
                response = self.api.post(path, {}, format="json")
                self.assertEqual(response.status_code, 503)
                data = response.json()
                self.assertEqual(data["error"], {
                    "codigo": "servicio_no_disponible",
                    "mensaje": "No se pudo completar la operación. Intente más tarde.",
                    "detalles": {"errores": errors},
                })
                self.assertEqual({key: value for key, value in data.items() if key != "error"}, original)
                self.assertEqual(result, original)

    def test_partial_success_remains_200_and_keeps_successes_errors_and_pending_steps(self):
        for path, target, completed_key, completed in self.cases:
            result = {completed_key: [completed], "errores": [{"pais": "BR", "mensaje": "No disponible."}],
                      "alertas_pendientes": True, "auditoria_pendiente": True}
            with self.subTest(path=path), patch(target, return_value=result):
                response = self.api.post(path, {}, format="json")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), result)

    def test_success_and_empty_results_keep_their_existing_contract(self):
        for path, target, completed_key, completed in self.cases:
            for entries in ([], [completed]):
                result = {completed_key: entries, "errores": []}
                with self.subTest(path=path, entries=entries), patch(target, return_value=result):
                    response = self.api.post(path, {}, format="json")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), result)

    def test_invalid_input_is_rejected_before_workflow_and_uses_common_envelope(self):
        for path, target, _, _ in self.cases:
            with self.subTest(path=path), patch(target) as workflow:
                response = self.api.post(path, {"paises": []}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["codigo"], "validacion")
                workflow.assert_not_called()
