import unittest

from django.core.exceptions import ValidationError
from django.test import TestCase

from ..validators import max_users_per_tenant_validator


# todo: add tenants
class ValidatorsTestCase(TestCase):
    # fixtures = ['initial_plan',
    #             'test_django-plans_auth', 'test_django-plans_plans']

    @unittest.skip  # TODO: implement it
    def test_max_users_per_tenant_validator(self):
        validator_object = max_users_per_tenant_validator
        self.assertRaises(ValidationError,
                          validator_object, user=None,
                          quota_dict={'MAX_USERS_PER_TENANT_COUNT': 1})
        self.assertEqual(validator_object(user=None,
                                          quota_dict={'MAX_USERS_PER_TENANT_COUNT': 2}), None)
        self.assertEqual(validator_object(user=None,
                                          quota_dict={'MAX_USERS_PER_TENANT_COUNT': 3}), None)
