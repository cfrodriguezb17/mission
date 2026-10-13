from copy import deepcopy

from django.db import connection
from django.db.backends.postgresql.base import DatabaseWrapper
from django.test import TransactionTestCase


class DatabaseRuntimeTests(TransactionTestCase):
    def test_pool_reuses_physical_connection_and_prepared_statement(self):
        config = deepcopy(connection.settings_dict)
        config.update(CONN_MAX_AGE=0, CONN_HEALTH_CHECKS=True)
        config['OPTIONS'] = {'pool': {'min_size': 1, 'max_size': 1, 'timeout': 3},
                             'server_side_binding': True, 'prepare_threshold': 2}
        probe = DatabaseWrapper(config, alias='runtime_probe')
        try:
            with probe.cursor() as cursor:
                for number in range(8):
                    cursor.execute('SELECT %s::bigint', [number])
                    self.assertEqual(cursor.fetchone()[0], number)
                pid = probe.connection.info.backend_pid
            probe.close()
            with probe.cursor() as cursor:
                self.assertEqual(probe.connection.info.backend_pid, pid)
                cursor.execute("SELECT count(*) FROM pg_prepared_statements WHERE statement LIKE 'SELECT%bigint%'")
                self.assertGreaterEqual(cursor.fetchone()[0], 1)
                self.assertEqual(probe.pool.get_stats()['pool_size'], 1)
        finally:
            probe.close()
            probe.close_pool()

    def test_preparation_can_be_disabled_on_real_connection(self):
        config = deepcopy(connection.settings_dict)
        config.update(CONN_MAX_AGE=0)
        config['OPTIONS'] = {}
        probe = DatabaseWrapper(config, alias='runtime_probe_disabled')
        try:
            with probe.cursor() as cursor:
                for number in range(8):
                    cursor.execute('SELECT %s::bigint', [number])
                    self.assertEqual(cursor.fetchone()[0], number)
                self.assertIsNone(probe.connection.prepare_threshold)
                cursor.execute('SELECT count(*) FROM pg_prepared_statements')
                self.assertEqual(cursor.fetchone()[0], 0)
        finally:
            probe.close()
