# Application definition

SHARED_APPS = [
    'tenancy',  # you must list the app where your tenant model resides in

    'hemail',

    'jet.dashboard',
    'jet',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.messages',

    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',

    'channels',
    'corsheaders',
    'storages',

    'django_celery_beat',
    'rest_framework',
    'django_filters',
    'guardian',

    'phonenumber_field',
    'timezone_field',
    'django_countries',

    'allauth',
    'allauth.account',

    'rest_auth',
    'allauth.socialaccount',
    # 'allauth.socialaccount.providers.facebook',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.windowslive',
    'users.socialaccount.providers.yahoo',

    # 'plans', #TODO: temporary disable (https://github.com/cypreess/django-plans/pull/66)
    # 'ordered_model',
    'pinax.notifications',

    'users',
]

TENANT_APPS = [
    'corsheaders',

    'watson',

    'django_mailbox',
    'post_office',

    'files',

    'campaigns',
    'campaigns.contacts',
    'campaigns.importer',
    'campaigns.notifications',
    'campaigns.providers',
    'campaigns.templates',
]

TENANT_MODEL = 'tenancy.TenantData'
INSTALLED_APPS = ['tenant_schemas'] + SHARED_APPS + [app for app in TENANT_APPS if app not in SHARED_APPS]
