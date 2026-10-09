"""Verifica migraciones y tests en una base temporal, eliminada al pasar."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

import psycopg
from psycopg import sql

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verifica migraciones desde cero y elimina la base temporal si todo pasa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fresh", action="store_true",
            help="Migra usando una nueva 0001 generada desde los modelos actuales, sin el historial original.",
        )

    def handle(self, *args, **options):
        config = settings.DATABASES["default"]
        if config["ENGINE"] != "django.db.backends.postgresql":
            raise CommandError("Esta comprobación requiere PostgreSQL.")

        database = f"datapulse_prueba_{uuid.uuid4().hex[:12]}"
        params = {
            "user": config["USER"],
            "password": config["PASSWORD"],
            "host": config["HOST"],
            "port": config["PORT"],
            "connect_timeout": 5,
        }
        project = Path(settings.BASE_DIR)
        environment = os.environ.copy()
        environment["POSTGRES_DB"] = database
        environment["DJANGO_SETTINGS_MODULE"] = "backend.settings"

        try:
            with psycopg.connect(dbname="postgres", autocommit=True, **params) as conn:
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        except psycopg.Error as exc:
            raise CommandError(f"No se pudo crear la base temporal: {exc}") from exc

        self.stdout.write(f"Base temporal creada: {database}")

        def run(*arguments, overrides=None):
            child_env = environment.copy()
            if overrides:
                child_env.update(overrides)
            subprocess.run(
                [sys.executable, str(project / "manage.py"), *arguments],
                cwd=project,
                env=child_env,
                check=True,
            )

        try:
            with tempfile.TemporaryDirectory(prefix="datapulse-migrations-") as folder:
                scratch = Path(folder)
                package = scratch / "fresh_accounts_migrations"
                package.mkdir()
                (package / "__init__.py").write_text("")
                (scratch / "fresh_settings.py").write_text(
                    "from backend.settings import *\n"
                    "MIGRATION_MODULES = {'accounts': 'fresh_accounts_migrations'}\n"
                )
                temporary_env = {
                    "PYTHONPATH": str(scratch) + os.pathsep + str(project),
                    "DJANGO_SETTINGS_MODULE": "fresh_settings",
                }
                run("makemigrations", "accounts", overrides=temporary_env)
                if not (package / "0001_initial.py").exists():
                    raise CommandError("No se generó la migración inicial de accounts.")

                migration_env = temporary_env if options["fresh"] else None
                run("makemigrations", "--check", "--dry-run", overrides=migration_env)
                run("migrate", "--noinput", overrides=migration_env)
                run("migrate", "--check", overrides=migration_env)
                run("check", "--database", "default", overrides=migration_env)

                if options["fresh"]:
                    with psycopg.connect(dbname=database, **params) as conn:
                        migrations = conn.execute(
                            "SELECT name FROM django_migrations WHERE app = 'accounts' ORDER BY name"
                        ).fetchall()
                        if migrations != [("0001_initial",)]:
                            raise CommandError("La base no contiene únicamente la nueva migración inicial de accounts.")
                        username = conn.execute(
                            "SELECT 1 FROM information_schema.columns "
                            "WHERE table_schema = 'public' AND table_name = 'accounts_user' "
                            "AND column_name = 'username'"
                        ).fetchone()
                        if username:
                            raise CommandError("El esquema nuevo conserva la columna username.")
                    self.stdout.write("Esquema nuevo confirmado: solo accounts.0001_initial, sin columna username.")

                # El runner usa esta misma base y la conserva hasta conocer el resultado.
                (scratch / "verification_settings.py").write_text(
                    ("from fresh_settings import *\n" if options["fresh"] else "from backend.settings import *\n")
                    + "DATABASES['default']['TEST'] = "
                    "{'NAME': DATABASES['default']['NAME']}\n"
                )
                # La prueba incremental requiere 0001 + 0002 originales y no aplica
                # cuando solo existe una nueva 0001; probar todos los flujos funcionales.
                test_labels = [
                    "accounts.tests.test_models", "accounts.tests.test_auth_api",
                    "accounts.tests.test_admin",
                    "countries",
                    "economics",
                    "risk",
                ] if options["fresh"] else []
                run("test", *test_labels, "--keepdb", "--noinput", overrides={
                    "PYTHONPATH": str(scratch) + os.pathsep + str(project),
                    "DJANGO_SETTINGS_MODULE": "verification_settings",
                })
        except (subprocess.CalledProcessError, CommandError, OSError, KeyboardInterrupt) as exc:
            raise CommandError(
                f"La verificación no terminó correctamente. "
                f"Se conserva {database} para revisar el problema: {exc}"
            ) from exc

        try:
            with psycopg.connect(dbname="postgres", autocommit=True, **params) as conn:
                conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
                remaining = conn.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (database,),
                ).fetchone()
                if remaining:
                    raise CommandError(f"No se eliminó la base temporal {database}.")
        except psycopg.Error as exc:
            raise CommandError(
                f"Las comprobaciones pasaron, pero no se pudo eliminar {database}: {exc}"
            ) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Migraciones y tests correctos. Base temporal eliminada: {database}."
        ))
