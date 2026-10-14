from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from common.permissions import IsAdminRole, has_role, require_writer_role
from common.serializers import BooleanQueryField, DateRangeFilterSerializer, StrictInputSerializer


class SharedPrimitiveTests(SimpleTestCase):
    def test_role_checks_reject_anonymous_inactive_and_superuser_without_business_role(self):
        for user in (None, AnonymousUser(), get_user_model()(rol="ADMIN", is_active=False),
                     get_user_model()(rol="VIEWER", is_superuser=True, is_staff=True)):
            with self.subTest(user=user):
                self.assertFalse(has_role(user, ("ADMIN", "ANALISTA")))
                with self.assertRaises(PermissionDenied):
                    require_writer_role(user)
        for role in ("ADMIN", "ANALISTA"):
            user = get_user_model()(rol=role)
            self.assertTrue(has_role(user, ("ADMIN", "ANALISTA")))
            require_writer_role(user)
            request = type("Request", (), {"user": user})()
            self.assertEqual(IsAdminRole().has_permission(request, None), role == "ADMIN")

    def test_boolean_query_filters_preserve_false_and_reject_other_spellings(self):
        class QuerySerializer(serializers.Serializer):
            flag = BooleanQueryField(required=False)

        for text, expected in (("true", True), ("false", False)):
            serializer = QuerySerializer(data={"flag": text})
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertIs(serializer.validated_data["flag"], expected)
        for invalid in ("TRUE", "False", "1", "0", "", True, False, 1, 0, None):
            with self.subTest(invalid=invalid):
                self.assertFalse(QuerySerializer(data={"flag": invalid}).is_valid())
        serializer = QuerySerializer(data={"page": "2"})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data, {})

    def test_strict_input_handles_non_object_json_and_partial_updates(self):
        class InputSerializer(StrictInputSerializer):
            nombre = serializers.CharField()

        for invalid in ([], "texto", 3):
            with self.subTest(invalid=invalid):
                self.assertFalse(InputSerializer(data=invalid).is_valid())
        serializer = InputSerializer(data={"usuario": 1}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertEqual(str(serializer.errors["usuario"]), "Campo no admitido.")
        self.assertTrue(InputSerializer(data={}, partial=True).is_valid())

    def test_date_ranges_accept_equal_and_open_ended_ranges(self):
        for data in ({"fecha_inicio": "2026-01-01"}, {"fecha_fin": "2026-01-01"},
                     {"fecha_inicio": "2026-01-01", "fecha_fin": "2026-01-01"}):
            serializer = DateRangeFilterSerializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            self.assertTrue(all(value == date(2026, 1, 1) for value in serializer.validated_data.values()))
