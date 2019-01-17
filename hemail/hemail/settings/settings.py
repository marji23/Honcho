import datetime
from typing import Any

from urllib.parse import urljoin


def _require(var: str) -> Any:
    try:
        return globals()[var]
    except KeyError:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("'%s' expected to be configured" % var)


SILENCED_SYSTEM_CHECKS = [
    'tenant_schemas.W003',
]

ADMINS = (
    ('Pavel Yushkovskiy', 'pavel@honchocrm.com'),
)

MANAGERS = ADMINS

# Hosts/domain names that are valid for this site; required if DEBUG is False
# See https://docs.djangoproject.com/en/1.9/ref/settings/#allowed-hosts
ALLOWED_HOSTS = [
    '.%s' % _require('ZONE'),
    'localhost',
    'localhost.localdomain',
    '127.0.0.1',
    '[::1]',
]

CHANNEL_LAYERS = {
    'default': dict(
        BACKEND='channels_redis.core.RedisChannelLayer',
        CONFIG={
            'hosts': [('localhost', 6379)],
        },
    )
}

CACHES = {
    'default': dict(
        KEY_FUNCTION='tenant_schemas.cache.make_key',
        REVERSE_KEY_FUNCTION='tenant_schemas.cache.reverse_key',
        BACKEND='django.core.cache.backends.locmem.LocMemCache',
        LOCATION='default',
    ),
    'deferred-tasks': dict(
        BACKEND="django_redis.cache.RedisCache",
        LOCATION="redis://localhost:6379/1",
    ),
    'providers-isp-configurations': dict(
        BACKEND='django.core.cache.backends.locmem.LocMemCache',
        LOCATION='providers-isp-configurations',
    ),
}

ORIGINAL_BACKEND = 'django_postgres_extensions.backends.postgresql'
DATABASE_ROUTERS = (
    'tenant_schemas.routers.TenantSyncRouter',
)

AUTHORIZATION_PROCESSORS = (
    'common.authentication.RestFrameworkAuthorizationProcessor',
)

AUTHENTICATION_BACKENDS = [
    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',
    'guardian.backends.ObjectPermissionBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',

    # 'authentication_proxy.authentication.JWTAuthenticationBackend',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',

    'django.middleware.security.SecurityMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'geoip2_extras.middleware.GeoIP2Middleware',

    # auth middleware
    'common.authentication.AuthorizationMiddleware',

    'tenancy.middleware.UserBasedTenantMiddleware',

    # we need this for session authorization csrf check in rest browsable api
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  # clickjacking protection
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

TENANTS_PREFIX = 'hemail'

ROOT_URLCONF = 'hemail.urls'

TEMPLATES = [
    dict(
        BACKEND='django.template.backends.django.DjangoTemplates',
        DIRS=[
            _require('BASE_DIR')('templates')
        ],
        APP_DIRS=True,
        OPTIONS={
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        }
    ),
]

WATSON_BACKEND = 'hemail.backends.PostgresSearchBackend'

REST_FRAMEWORK = dict(
    DEFAULT_AUTHENTICATION_CLASSES=[
        'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
        'rest_framework.authentication.BasicAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    DEFAULT_PERMISSION_CLASSES=[
        'rest_framework.permissions.IsAuthenticated',
        'rest_framework.permissions.DjangoModelPermissions'
    ],
    DEFAULT_FILTER_BACKEND=[
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    DEFAULT_PAGINATION_CLASS='rest_framework.pagination.LimitOffsetPagination',
    EXCEPTION_HANDLER='common.views.exception_handler',
)

SOCIALACCOUNT_PROVIDERS = dict(
    google={
        'SCOPE': [
            'profile',
            'email',
            'https://mail.google.com/',
        ],
        'AUTH_PARAMS': {
            'access_type': 'offline',
        },
        'REFRESH_TOKEN_URL': 'https://accounts.google.com/o/oauth2/token?access_type=offline',
    },
    windowslive={
        'SCOPE': [
            'wl.imap',
            'wl.offline_access',
        ],
        'REFRESH_TOKEN_URL': 'https://login.live.com/oauth20_token.srf?grant_type=refresh_token',
    }
)

ACCOUNT_DEFAULT_HTTP_PROTOCOL = _require('SOCIAL_AUTHENTICATION_DEFAULT_HTTP_PROTOCOL')
ACCOUNT_ADAPTER = 'users.adapter.AccountAdapter'
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
SOCIALACCOUNT_ADAPTER = 'users.adapter.SocialAccountAdapter'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'mandatory'

REST_USE_JWT = True
JWT_AUTH = dict(
    JWT_ENCODE_HANDLER='users.jwt_handlers.jwt_encode_handler',
    JWT_DECODE_HANDLER='users.jwt_handlers.jwt_decode_handler',
    JWT_GET_USER_SECRET_KEY='users.jwt_handlers.get_user_secret_key',
    # todo: setup crypted tokens alg
    # JWT_ALGORITHM = '',
    JWT_ALLOW_REFRESH=True,
    JWT_AUTH_HEADER_PREFIX='Bearer',
    JWT_EXPIRATION_DELTA=datetime.timedelta(days=2),
    JWT_REFRESH_EXPIRATION_DELTA=datetime.timedelta(days=5),
)

# todo: we'll need to one more option to control availability of accounts views in production
# and check it here instead of debug flag
LOGIN_REDIRECT_URL = '/api/?format=api'

PLANS_DEFAULT_GRACE_PERIOD = 14
PLANS_CURRENCY = 'EN'
PLANS_INVOICE_ISSUER = {
    "issuer_name": "Joe Doe Company",
    "issuer_street": "Django street, 34",
    "issuer_zipcode": "123-3444",
    "issuer_city": "Djangoko",
    "issuer_country": "DJ",  # Must be a country code with 2 characters
    "issuer_tax_number": "1222233334444555",
}
PLANS_TAXATION_POLICY = 'plans.taxation.eu.EUTaxationPolicy'

PLANS_VALIDATORS = {
    'MAX_STORAGE': 'users.validators.max_users_per_tenant_validator',
}

DJANGO_MAILBOX_ADMIN_ENABLED = False

PYTRACKING_CONFIGURATION = {
    "base_open_tracking_url": urljoin(_require('BASE_TRACKING_URL'), '/open/'),
    "base_click_tracking_url": urljoin(_require('BASE_TRACKING_URL'), '/click/'),
}

PINAX_NOTIFICATIONS_BACKENDS = [
    ('email', 'campaigns.notifications.backends.email.EmailBackend'),
    ('channels', 'campaigns.notifications.backends.channels.ChannelsBackend'),
]

GEOIP_COUNTRY = 'GeoLite2-Country.mmdb'
GEOIP_CITY = 'GeoLite2-City.mmdb'

SITE_ID = 1

ASGI_APPLICATION = 'hemail.routing.application'
WSGI_APPLICATION = 'hemail.wsgi.application'

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Make things more secure by default. Run "python manage.py check --deploy"
# for even more suggestions that you might want to add to the settings, depending
# on how the site uses SSL.
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = 'DENY'

# have to use pickle serialization because of geoip2_extras.middleware.GeoData in session
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.PickleSerializer'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# CSRF_COOKIE_SECURE = True
# CSRF_COOKIE_HTTPONLY = True
# CSRF_COOKIE_DOMAIN = ''

# SESSION_COOKIE_SECURE = True
# SESSION_COOKIE_HTTPONLY = True
CORS_ORIGIN_REGEX_WHITELIST = (
    r'^(https?://)?(\w+\.)?%s$' % (_require('ZONE').replace('.', '\.')),
    r'^(https?://)?(localhost|127\.0\.0\.1)?(:\d+)?$',
)
# CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_ALLOW_ALL = True  # TODO: remove this

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
STATICFILES_DIRS = [
    _require('BASE_DIR')('static'),
]

MEDIA_URL = '/media/'

if _require('FILE_STORAGES_LOCAL_MODE'):
    FILE_STORAGES = {
        'default': {
            'BACKEND': 'tenancy.storage.TenantFileSystemStorage',
            'OPTIONS': {
                'location': (_require('MEDIA_ROOT'), 'campaign-materials',),
                'base_url': urljoin(MEDIA_URL, 'campaign-materials'),
            }
        },
        'public-attachments': 'default',
        'file-storage': {
            'BACKEND': 'tenancy.storage.TenantFileSystemStorage',
            'OPTIONS': {
                'location': (_require('MEDIA_ROOT'), 'file-storage',),
                'base_url': urljoin(MEDIA_URL, 'file-storage'),
            }
        },
        'private-attachments': {
            'BACKEND': 'tenancy.storage.TenantFileSystemStorage',
            'OPTIONS': {
                'location': (_require('MEDIA_ROOT'), 'private-attachments',),
                'base_url': urljoin(MEDIA_URL, 'private-attachments'),
            }
        },
    }
else:
    FILE_STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
            'OPTIONS': {
                'location': 'campaign-materials',
            }
        },
        'public-attachments': 'default',
        'file-storage': {
            'BACKEND': 'tenancy.storage.PrivateMediaRootTenancyS3BotoStorage',
            'OPTIONS': {
                'location': 'file-storage',
            }
        },
        'private-attachments': {
            'BACKEND': 'tenancy.storage.PrivateMediaRootTenancyS3BotoStorage',
            'OPTIONS': {
                'location': 'private-attachments',
            }
        },
    }

DEFAULT_FILE_STORAGE = 'hemail.storage.DefaultStorage'

#
TEST_RUNNER = 'django.test.runner.DiscoverRunner'
