from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RemoveUsernameMigrationTests(TransactionTestCase):
    def test_existing_user_identity_password_and_permissions_are_preserved(self):
        previous = [("accounts", "0001_initial")]
        current = [("accounts", "0002_remove_username")]
        executor = MigrationExecutor(connection)
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            OldUser = apps.get_model("accounts", "User")
            Group = apps.get_model("auth", "Group")
            Permission = apps.get_model("auth", "Permission")
            password = "MigracionClave!842z"
            password_hash = make_password(password)
            user = OldUser.objects.create(
                username="existente@example.com", email="existente@example.com",
                nombre_completo="Usuario Existente", password=password_hash,
                rol="ADMIN", is_active=True, is_staff=True, is_superuser=True,
            )
            group = Group.objects.create(name="Equipo existente")
            permission = Permission.objects.first()
            self.assertIsNotNone(permission)
            user.groups.add(group)
            user.user_permissions.add(permission)
            user_id, created_at = user.pk, user.fecha_creacion
            group_id, permission_id = group.pk, permission.pk
        finally:
            # Restaurar el esquema antes de las comprobaciones y del flush.
            MigrationExecutor(connection).migrate(current)

        User = get_user_model()
        saved = User.objects.get(pk=user_id)
        self.assertEqual(saved.email, "existente@example.com")
        self.assertEqual(saved.nombre_completo, "Usuario Existente")
        self.assertEqual(saved.password, password_hash)
        self.assertEqual(saved.fecha_creacion, created_at)
        self.assertEqual(saved.rol, "ADMIN")
        self.assertTrue(saved.is_active)
        self.assertTrue(saved.is_staff)
        self.assertTrue(saved.is_superuser)
        self.assertEqual(list(saved.groups.values_list("pk", flat=True)), [group_id])
        self.assertEqual(
            list(saved.user_permissions.values_list("pk", flat=True)), [permission_id],
        )
        self.assertEqual(authenticate(email=saved.email, password=password), saved)
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, User._meta.db_table)
        self.assertNotIn("username", {column.name for column in columns})
