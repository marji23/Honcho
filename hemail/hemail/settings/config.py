import os
import sys
from typing import Optional
from urllib.parse import urljoin

import environ


def _fix_base_path_for_pex(origin: environ.Path) -> environ.Path:
    """ Fix path in case we are in pex. """

    if '/.pex/' in origin.root:
        return environ.Path(os.path.basename(origin.root))
    return origin


BASE_DIR = environ.Path(__file__) - 2
ROOT = BASE_DIR - 2
BIN_DIRECTORY = _fix_base_path_for_pex(ROOT.path('bin'))
PRODUCT = 'honcho-email-server'

ZONE = 'honchocrm.org'


class Env(environ.Env):
    ENVIRON = os.environ.copy()

    EMAIL_SCHEMES = {**environ.Env.EMAIL_SCHEMES, **dict(
        ses='django_ses.SESBackend'
    )}

    @classmethod
    def read_env(cls, env_file: Optional[str] = None, **overrides) -> None:
        # TODO: check if overrides are used for override as defaults
        super().read_env(env_file, **cls.ENVIRON)


env = Env(
    DEBUG=(bool, False),
)

_configuration_files = (
    '/etc/honchocrm/%s.conf' % PRODUCT,
    BIN_DIRECTORY('%s.conf' % PRODUCT),
    '%s.conf' % PRODUCT,
    os.environ.get("HCRM_CONF"),
)
for env_file in _configuration_files:
    if env_file and os.path.isfile(env_file):
        sys.stdout.write("Using config file: %s\n\n" % env_file)
        sys.stdout.flush()
        Env.read_env(env_file)

DEBUG = env('DEBUG')
ROLE = env('ROLE', default=None)
LOG_FILE = env('LOG_FILE', default=BIN_DIRECTORY('%s%s.log' % (
    PRODUCT,
    ('.%s' % ROLE) if ROLE else '',
))).format(role=ROLE)

FRONTEND_BASE_URL = env('FRONTEND_BASE_URL', default='http://email.%s' % ZONE)
USERS_ACTIVATION_URL = env('USERS_ACTIVATION_URL', default=urljoin(FRONTEND_BASE_URL, '/accounts'))
SOCIAL_AUTHENTICATION_ERROR_REDIRECT_URL = env('SOCIAL_AUTHENTICATION_ERROR_REDIRECT_URL',
                                               default=USERS_ACTIVATION_URL)
SOCIAL_AUTHENTICATION_DEFAULT_HTTP_PROTOCOL = env('SOCIAL_AUTHENTICATION_DEFAULT_HTTP_PROTOCOL',
                                                  default='http')

BASE_TRACKING_URL = env('BASE_TRACKING_URL', default='http://email.%s' % ZONE)

STATIC_ROOT = BIN_DIRECTORY('static')
MEDIA_ROOT = BIN_DIRECTORY('media')

AWS_REGION_NAME = env('AWS_REGION_NAME', default=None)

AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME', default=PRODUCT)
AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')
AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', default=AWS_REGION_NAME)

AWS_SES_REGION_NAME = env('AWS_SES_REGION_NAME', default=AWS_REGION_NAME)
AWS_SES_REGION_ENDPOINT = env(
    'AWS_SES_REGION_ENDPOINT',
    default=('email.%s.amazonaws.com' % AWS_SES_REGION_NAME) if AWS_SES_REGION_NAME else None
)

AWS_SES_RETURN_PATH = env('AWS_SES_RETURN_PATH', default=None)

EMAIL_BACKEND = 'django_ses.SESBackend'

# Make this unique, and don't share it with anybody.
SECRET_KEY = env('SECRET_KEY')

THUMBOR_THUMBNAILING_URL = env('THUMBOR_THUMBNAILING_URL', default='http://thumbnailing.%s' % ZONE)
THUMBOR_SECURITY_KEY = env('THUMBOR_SECURITY_KEY')

_EMAIL_CONFIG = env.email_url(
    'EMAIL_URL', default='dummymail://notifier%40gmail.com:secret@localhost/')

vars().update(_EMAIL_CONFIG)

DEFAULT_FROM_EMAIL = _EMAIL_CONFIG['EMAIL_HOST_USER']
SERVER_EMAIL = _EMAIL_CONFIG['EMAIL_HOST_USER']

DATABASES = {
    'default': env.db(default='tpsql://hcrm_admin:hcrm_admin@localhost/hemail_db',
                      engine='tenant_schemas.postgresql_backend'),
}

FILE_STORAGES_LOCAL_MODE = env.bool('FILE_STORAGES_LOCAL_MODE', default=False)

# todo: should be configurable
CELERY_BROKER = 'amqp://localhost'
CELERY_RESULT_BACKEND = 'redis://localhost'

GEOIP_PATH = env('GEOIP_PATH', default=BIN_DIRECTORY('GeoIP'))
