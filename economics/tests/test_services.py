from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError

from countries.models import Pais
from countries.services import sincronizar_paises
from economics.models import IndicadorEconomico, TipoCambio
from economics.services import actualizar_tipos_cambio, sincronizar_indicadores
from integrations.http import ProviderError

from .base import EconomicsTestCase


class EconomicSyncTests(EconomicsTestCase):
    def provider(self, value=Decimal("123.4567895")):
        provider = Mock()
        provider.indicadores.return_value = [{"codigo_world_bank": "NY.GDP.MKTP.CD", "anio": 2025, "valor": value}]
        return provider

    def sync(self, provider, **kwargs):
        with self.assertLogs("economics.services", level="INFO"):
            return sincronizar_indicadores(paises=["CO"], anio_inicio=2025, anio_fin=2025, client=provider, **kwargs)

    def test_sync_is_idempotent_including_update_timestamp(self):
        provider = self.provider()
        result = self.sync(provider)
        self.assertEqual(result["creados"], 1)
        observation = IndicadorEconomico.objects.get(pais_id="CO", tipo_id="PIB")
        self.assertEqual(observation.valor, Decimal("123.456790"))
        stamp = observation.fecha_actualizacion
        result = self.sync(provider)
        self.assertEqual(result["sin_cambios"], 1)
        observation.refresh_from_db()
        self.assertEqual(observation.fecha_actualizacion, stamp)
        provider.indicadores.return_value[0]["valor"] = Decimal("200")
        self.assertEqual(self.sync(provider)["actualizados"], 1)
        self.assertEqual(IndicadorEconomico.objects.count(), 1)

    def test_sync_preserves_manual_but_replaces_simulated_observations(self):
        observation = IndicadorEconomico.objects.create(pais_id="CO", tipo_id="PIB", anio=2025, valor=17, fuente="MANUAL")
        self.assertEqual(self.sync(self.provider())["manuales_conservados"], 1)
        observation.refresh_from_db()
        self.assertEqual(observation.valor, 17)
        observation.es_simulado = True
        observation.save()
        self.assertEqual(self.sync(self.provider())["actualizados"], 1)
        observation.refresh_from_db()
        self.assertEqual(observation.fuente, "WORLD_BANK")
        self.assertFalse(observation.es_simulado)

    def test_nulls_are_reported_without_creating_zero_values_or_deleting_existing(self):
        observation = IndicadorEconomico.objects.create(pais_id="CO", tipo_id="PIB", anio=2025, valor=17, fuente="WORLD_BANK")
        result = self.sync(self.provider(None))
        self.assertEqual(result["creados"], 0)
        self.assertEqual(len(result["faltantes"]), 6)
        observation.refresh_from_db()
        self.assertEqual(observation.valor, 17)

    def test_failure_for_one_country_continues_to_next_and_logs_results(self):
        provider = self.provider()
        provider.indicadores.side_effect = [ProviderError("No disponible"), provider.indicadores.return_value]
        with self.assertLogs("economics.services", level="INFO") as logs:
            result = sincronizar_indicadores(paises=["CO", "BR"], anio_inicio=2025, anio_fin=2025, client=provider)
        self.assertEqual(result["paises_procesados"], ["BR"])
        self.assertEqual(result["errores"][0]["pais"], "CO")
        self.assertEqual(result["creados"], 1)
        self.assertTrue(any("Inicio" in entry for entry in logs.output))
        self.assertTrue(any("Fin" in entry for entry in logs.output))
        self.assertTrue(any("ERROR" in entry for entry in logs.output))

    def test_country_transaction_rolls_back_on_unrepresentable_value(self):
        provider = self.provider()
        provider.indicadores.return_value.append({"codigo_world_bank": "FP.CPI.TOTL.ZG", "anio": 2025, "valor": Decimal("1e40")})
        result = self.sync(provider)
        self.assertEqual(len(result["errores"]), 1)
        self.assertFalse(IndicadorEconomico.objects.exists())

    def test_duplicate_provider_values_roll_back_country(self):
        provider = self.provider()
        provider.indicadores.return_value *= 2
        self.assertEqual(len(self.sync(provider)["errores"]), 1)
        self.assertFalse(IndicadorEconomico.objects.exists())

    def test_exhausted_budget_or_inactive_country_never_calls_provider(self):
        provider = self.provider()
        self.assertEqual(len(self.sync(provider, presupuesto=0)["errores"]), 1)
        provider.indicadores.assert_not_called()
        Pais.objects.filter(pk="CO").update(activo=False)
        self.assertEqual(len(self.sync(provider)["errores"]), 1)
        provider.indicadores.assert_not_called()

    def test_exchange_inversion_provider_date_idempotence_and_partial_failures(self):
        provider = Mock()
        provider.cotizaciones.return_value = (date(2026, 1, 2), {"COP": Decimal("4000"), "PAB": Decimal("1"), "BRL": -1})
        with self.assertLogs("economics.services"):
            result = actualizar_tipos_cambio(client=provider)
        self.assertEqual(result["creados"], 2)
        self.assertEqual(set(result["paises_procesados"]), {"CO", "EC", "PA"})
        quote = TipoCambio.objects.get(moneda_origen_id="COP")
        self.assertEqual(quote.tasa, Decimal("0.000250000000"))
        self.assertEqual(quote.fecha, date(2026, 1, 2))
        self.assertEqual(result["estado"], "PARCIAL")
        self.assertFalse(TipoCambio.objects.filter(moneda_origen_id="USD").exists())
        with self.assertLogs("economics.services"):
            self.assertEqual(actualizar_tipos_cambio(client=provider)["sin_cambios"], 2)

    def test_exchange_failure_does_not_create_or_delete_quotes(self):
        provider = Mock()
        provider.cotizaciones.side_effect = ProviderError("No disponible")
        with self.assertLogs("economics.services"):
            result = actualizar_tipos_cambio(client=provider)
        self.assertEqual(len(result["errores"]), 1)
        self.assertFalse(TipoCambio.objects.exists())

    def test_exchange_manual_quotes_are_preserved(self):
        quote = TipoCambio.objects.create(moneda_origen_id="COP", fecha=date(2026, 1, 2), tasa="0.0003", fuente="MANUAL")
        provider = Mock()
        provider.cotizaciones.return_value = (quote.fecha, {"COP": 4000})
        with self.assertLogs("economics.services"):
            result = actualizar_tipos_cambio(client=provider)
        self.assertEqual(result["manuales_conservados"], 1)
        quote.refresh_from_db()
        self.assertEqual(quote.tasa, Decimal("0.0003"))

    def test_seed_is_repeatable_covers_history_and_preserves_real_values(self):
        call_command("seed_economics", fecha_fin=date(2026, 1, 31), stdout=StringIO())
        self.assertEqual(IndicadorEconomico.objects.count(), 300)
        self.assertEqual(TipoCambio.objects.count(), 279)
        self.assertEqual(IndicadorEconomico.objects.filter(es_simulado=True).count(), 300)
        self.assertEqual(TipoCambio.objects.filter(es_simulado=True).count(), 279)
        observation = IndicadorEconomico.objects.filter(pais_id="CO", tipo_id="PIB").first()
        observation.valor = Decimal("17")
        observation.fuente = "WORLD_BANK"
        observation.es_simulado = False
        observation.save()
        call_command("seed_economics", fecha_fin=date(2026, 1, 31), stdout=StringIO())
        observation.refresh_from_db()
        self.assertEqual(observation.valor, 17)
        self.assertEqual(IndicadorEconomico.objects.count(), 300)
        self.assertEqual(TipoCambio.objects.count(), 279)

    @patch("economics.management.commands.sync_indicadores.sincronizar_indicadores")
    def test_sync_command_fails_explicitly_on_partial_errors(self, sync):
        sync.return_value = {"errores": [{"pais": "CO"}]}
        with self.assertRaises(CommandError):
            call_command("sync_indicadores", paises=["CO"], stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("sync_indicadores", presupuesto=0, stdout=StringIO())

    def test_country_sync_validates_data_and_keeps_assigned_currency_and_region(self):
        provider = Mock()

        def country(code):
            if code != "CO":
                raise ProviderError("No disponible")
            return {"nombre": "República de Colombia", "poblacion": 52000001,
                    "latitud": Decimal("4.5709"), "longitud": Decimal("-74.2973"),
                    "bandera_url": "https://example.org/co.png", "monedas": {"COP": "Peso colombiano"}}

        provider.pais.side_effect = country
        with self.assertLogs("countries.services"):
            result = sincronizar_paises(client=provider)
        self.assertEqual(result["paises_procesados"], ["CO"])
        co = Pais.objects.get(pk="CO")
        self.assertEqual(co.poblacion, 52000001)
        self.assertEqual(co.moneda_id, "COP")
        self.assertEqual(co.region, "ANDINA")

    def test_bad_country_coordinates_roll_back_including_currency_name(self):
        provider = Mock()
        provider.pais.return_value = {"nombre": "Cambio inválido", "poblacion": 1,
                                    "latitud": Decimal("91"), "longitud": Decimal("0"),
                                    "bandera_url": "https://example.org/co.png", "monedas": {"COP": "Cambio inválido"}}
        with self.assertLogs("countries.services"):
            result = sincronizar_paises(client=provider)
        self.assertEqual(result["paises_procesados"], [])
        self.assertEqual(Pais.objects.get(pk="CO").moneda.nombre, "Peso colombiano")

    def test_exchange_replaces_simulation_then_updates_changed_real_quote(self):
        quote = TipoCambio.objects.create(moneda_origen_id="COP", fecha=date(2026, 1, 2),
                                         tasa="0.0003", fuente="DEMO_SIMULADO", es_simulado=True)
        provider = Mock()
        provider.cotizaciones.return_value = (quote.fecha, {"COP": 4000})
        with self.assertLogs("economics.services"):
            self.assertEqual(actualizar_tipos_cambio(client=provider)["actualizados"], 1)
        quote.refresh_from_db()
        self.assertFalse(quote.es_simulado)
        self.assertEqual(quote.fuente, "EXCHANGE_RATE")
        provider.cotizaciones.return_value = (quote.fecha, {"COP": 5000})
        with self.assertLogs("economics.services"):
            self.assertEqual(actualizar_tipos_cambio(client=provider)["actualizados"], 1)
        quote.refresh_from_db()
        self.assertEqual(quote.tasa, Decimal("0.0002"))
        self.assertEqual(TipoCambio.objects.count(), 1)

    def test_sync_commands_report_success_and_failures(self):
        cases = (
            ("sync_indicadores", "economics.management.commands.sync_indicadores.sincronizar_indicadores"),
            ("update_tipos_cambio", "economics.management.commands.update_tipos_cambio.actualizar_tipos_cambio"),
            ("sync_countries", "countries.management.commands.sync_countries.sincronizar_paises"),
        )
        for command, target in cases:
            with self.subTest(command=command), patch(target) as service:
                output = StringIO()
                service.return_value = {"errores": [], "paises_procesados": ["CO"]}
                call_command(command, stdout=output)
                self.assertIn('"CO"', output.getvalue())
                service.return_value = {"errores": [{"pais": "CO"}], "paises_procesados": []}
                with self.assertRaises(CommandError):
                    call_command(command, stdout=StringIO())

    def test_invalid_seed_date_and_sync_range_leave_database_unchanged(self):
        with self.assertRaises(CommandError):
            call_command("seed_economics", fecha_fin=date(9999, 1, 1), stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("sync_indicadores", anio_inicio=2025, anio_fin=2024, stdout=StringIO())
        self.assertFalse(IndicadorEconomico.objects.exists())
        self.assertFalse(TipoCambio.objects.exists())
