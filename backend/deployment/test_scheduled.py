from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from deployment.scheduled import commands_for, run


class ScheduledTests(TestCase):
    def at(self, hour, minute):
        return datetime(2026, 10, 14, hour, minute, tzinfo=timezone.utc)

    def test_daily_windows_and_alert_recovery(self):
        for hour, minute, daily in [(2, 59, None), (3, 0, "update_tipos_cambio"),
                                    (3, 14, "update_tipos_cambio"), (3, 15, "sync_indicadores"),
                                    (3, 29, "sync_indicadores"), (3, 30, None), (22, 0, None)]:
            with self.subTest(hour=hour, minute=minute):
                commands = commands_for(self.at(hour, minute))
                self.assertEqual(commands, ([[daily]] if daily else []) +
                                 [["generar_alertas", "--limite", "1000"]])

    @patch("deployment.scheduled.subprocess.run")
    def test_partial_failure_still_recovers_alerts_and_exits_unsuccessfully(self, execute):
        execute.side_effect = [SimpleNamespace(returncode=1), SimpleNamespace(returncode=0)]
        self.assertEqual(run(self.at(3, 0)), 1)
        self.assertEqual(execute.call_count, 2)
        self.assertIn("generar_alertas", execute.call_args.args[0])

    @patch("deployment.scheduled.subprocess.run", return_value=SimpleNamespace(returncode=0))
    def test_success(self, execute):
        self.assertEqual(run(self.at(3, 15)), 0)


if __name__ == "__main__":
    main()
