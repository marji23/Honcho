from django.utils.translation import ugettext_lazy as _
from rest_framework import exceptions, status


class TryLater(exceptions.APIException):
    status_code = status.HTTP_202_ACCEPTED
    default_detail = None
    default_code = 'pending'

    def __init__(self, detail, code=None, wait=None):
        super().__init__(detail, code)
        self.wait = wait


class ExpectationFailed(exceptions.APIException):
    status_code = status.HTTP_417_EXPECTATION_FAILED
    default_detail = _('Expectation failed.')
    default_code = 'expectation_failed'


class UnprocessableEntity(exceptions.APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = _('Unprocessable entity.')
    default_code = 'unprocessable_entity'
