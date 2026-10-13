from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from threading import Barrier, Event

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

from countries.models import Pais
from portfolios.models import Portafolio, Posicion
from portfolios.services import agregar_posicion, editar_portafolio


class PortfolioConcurrencyTests(TransactionTestCase):
    def setUp(self):
        call_command("seed_countries", stdout=StringIO())
        self.users = [get_user_model().objects.create_user(email=f"concurrent-{i}@example.com", nombre_completo="Analista", rol="ANALISTA") for i in range(2)]
        self.portfolio = Portafolio.objects.create(usuario=self.users[0], nombre="Compartido", es_publico=True)

    def together(self, operation):
        barrier = Barrier(2)

        def run(index):
            try:
                barrier.wait(timeout=10)
                return operation(index)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, index) for index in range(2)]
            return [future.result(timeout=20) for future in futures]

    def data(self, code="CO", amount="1000"):
        return {"pais": Pais.objects.get(pk=code), "tipo_activo": "RENTA_FIJA",
                "monto_inversion_usd": Decimal(amount), "fecha_entrada": timezone.localdate() - timedelta(days=2)}

    def test_two_analysts_save_shared_portfolio_only_one_wins_over_api(self):
        def save(index):
            api = APIClient()
            api.force_authenticate(self.users[index])
            response = api.put(f"/api/portafolios/{self.portfolio.pk}/", {"version": 1, "descripcion": f"Cambio {index}"}, format="json")
            return response.status_code, response.data

        results = self.together(save)
        self.assertEqual(sorted(status for status, _ in results), [200, 409])
        winner = next(data for status, data in results if status == 200)
        self.portfolio.refresh_from_db()
        self.assertEqual((self.portfolio.version, self.portfolio.descripcion), (2, winner["descripcion"]))

    def test_two_creates_after_available_name_still_enforce_owner_uniqueness(self):
        checked = Barrier(2)

        def create(index):
            api = APIClient()
            api.force_authenticate(self.users[0])
            response = api.get("/api/portafolios/validar-nombre/", {"nombre": "Concurrente"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.data["disponible"])
            checked.wait(timeout=10)
            return api.post("/api/portafolios/", {"nombre": "Concurrente"}, format="json").status_code

        self.assertEqual(sorted(self.together(create)), [201, 400])
        self.assertEqual(Portafolio.objects.filter(usuario=self.users[0], nombre="Concurrente").count(), 1)

    def test_simultaneous_position_additions_do_not_exceed_two_active(self):
        _, self.portfolio = agregar_posicion(self.users[0], self.portfolio.pk, 1, self.data())

        def add(index):
            try:
                agregar_posicion(self.users[index], self.portfolio.pk, 2, self.data())
                return 201
            except APIException as exc:
                return exc.status_code

        self.assertEqual(sorted(self.together(add)), [201, 409])
        self.portfolio.refresh_from_db()
        self.assertEqual((self.portfolio.version, self.portfolio.posiciones.count()), (3, 2))
        with self.assertRaises(APIException) as context:
            agregar_posicion(self.users[1], self.portfolio.pk, 3, self.data())
        self.assertEqual(context.exception.status_code, 400)

    def test_simultaneous_additions_cannot_exceed_capital_limit(self):
        for code in ("CO", "BR", "CL", "PE"):
            _, self.portfolio = agregar_posicion(self.users[0], self.portfolio.pk, self.portfolio.version, self.data(code, "10000000"))

        def add(index):
            try:
                agregar_posicion(self.users[index], self.portfolio.pk, 5, self.data(("MX", "AR")[index], "10000000"))
                return 201
            except APIException as exc:
                return exc.status_code

        self.assertEqual(sorted(self.together(add)), [201, 409])
        total = sum(Posicion.objects.values_list("monto_inversion_usd", flat=True))
        self.assertEqual(total, Decimal("50000000"))

    def test_visibility_is_rechecked_after_waiting_for_portfolio_lock(self):
        started = Event()

        def edit():
            try:
                started.set()
                editar_portafolio(self.users[1], self.portfolio.pk, 1, {"descripcion": "Ya no permitido"})
                return 200
            except APIException as exc:
                return exc.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Portafolio.objects.select_for_update().get(pk=self.portfolio.pk)
                future = pool.submit(edit)
                self.assertTrue(started.wait(timeout=10))
                Portafolio.objects.filter(pk=self.portfolio.pk).update(es_publico=False, version=2)
            self.assertEqual(future.result(timeout=20), 404)
        self.portfolio.refresh_from_db()
        self.assertEqual(self.portfolio.descripcion, "")
