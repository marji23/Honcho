#!/usr/bin/env python

from setuptools import find_packages, setup
from setuptools.command.build_py import build_py


def _collect_static():
    import os
    import uuid
    static_root = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
    os.environ.update(dict(
        DJANGO_SETTINGS_MODULE='hemail.settings',
        AWS_ACCESS_KEY_ID='',
        AWS_SECRET_ACCESS_KEY='',
        THUMBOR_SECURITY_KEY='',
        SECRET_KEY=str(uuid.uuid4()),

        LOG_FILE='',
        STATIC_ROOT=static_root,
    ))

    import django
    django.setup(set_prefix=False)

    from django.core.management import call_command
    return call_command('collectstatic', verbosity=1, interactive=False, clear=True)


class BuildPyCommand(build_py):
    def run(self):
        _collect_static()
        return super().run()


setup(
    cmdclass=dict(build_py=BuildPyCommand),
    name='honcho-email-server',
    packages=find_packages() + ['bin'],
    version='0.0.1',
    description='Honcho Email Marketing server',
    include_package_data=True,
    package_dir={'bin': '../bin'},
    package_data={'bin': ['static/*']},
    zip_safe=True,
    install_requires=[
        # 'six>=1.7',  # for django-json-rpc

        'Django>=2.0',
        'channels_redis>=2.1.0',
        'channels>=2.0',
        'asgiref>=2.1.0',
        'Wand>=0.4.4',
        'aiounittest>=1.1.0',
        'Faker>=0.8.15',

        'django-environ>=0.4.2',
        'django-tenant-schemas>=1.8.0',
        'django-redis>=4.9.0',
        'django-postgres-extensions==0.9.3',

        'celery[redis]>=4.0.2,<4.2',
        'tenant-schemas-celery>=0.1.7',
        'django-celery-beat>=1.0.1',

        'django-enumfields>=0.9.0',

        'whitenoise>=3.3.0',
        'django-cors-headers>=2.1.0',

        'djangorestframework>=3.7,<3.8',
        'markdown>=2.6.8',
        'django-filter>=1.0.4',
        'django-guardian>=1.4.8',
        'djangorestframework-jwt>=1.11.0',
        'drf-extensions>=0.3.1',

        'django-jet>=1.0.7',

        'django-allauth>=0.32.0',
        'django-rest-auth>=0.9.1',

        'django-plans>=0.8.12',
        'django-watson>=1.5.1',

        'django-mailbox>=4.5.4',
        'django-post-office>=3.0.3',
        'pytracking[django,html]>=0.2.0',

        'pinax_notifications>=5.0.0',

        'django-phonenumber-field>=1.1.0',
        'phonenumberslite>=8.7.1',

        'django-timezone-field>=2.0',
        'django-timezone-utils>=0.11',
        'djangorestframework-bulk>=0.2.1',
        'djangorestframework-csv>=2.0.0',
        'django-countries>=5.0',
        'django-geoip2-extras>=0.1.2',

        'boto3>=1.4.7',
        'django-ses>=0.8.5',
        'django-storages>=1.6.5',
        'libthumbor>=1.3.2',
        'python-magic>=0.4.13',
        'webencodings>=0.5.1',

        # 'argparse==1.4.0',
        # 'django-rest-hooks==1.3.1',
        # 'dnspython==1.12.0',
        # 'iso8601==0.1.11',
        # 'jsonpatch==1.15',
        # 'psycopg2==2.6.1',
        # 'python-dateutil==2.5.3',
        # 'pytz==2016.4',
        # 'rfc3339==5',
        # 'whoosh==2.7.4'
    ],
)
