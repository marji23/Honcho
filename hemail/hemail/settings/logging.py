def _require(var):
    try:
        return globals()[var]
    except KeyError:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("'%s' expected to be configured" % var)


# Logging setup

LOGGING = dict(
    version=1,
    disable_existing_loggers=False,
    filters={
        'tenant_context': {
            '()': 'tenant_schemas.log.TenantContextFilter'
        },
    },
    formatters={
        'standard': {
            'format': "[%(asctime)s]: %(process)d %(thread)d: "
                      "[%(schema_name)s:%(domain_url)s]: "
                      "%(levelname)s [%(name)s:%(lineno)s] %(message)s",
            'datefmt': "%d/%b/%Y %H:%M:%S"
        },
    },
    handlers=dict(
        console={
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'filters': ['tenant_context'],
        },
    ),
    loggers={
        'django': {
            'handlers': ['console'],
            'propagate': True,
            'level': 'WARN',
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        '': {
            'handlers': ['console', ],
            'level': 'DEBUG',
        },
    }
)

if _require('LOG_FILE'):
    LOGGING['handlers']['logfile'] = {
        'level': 'DEBUG',
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': _require('LOG_FILE'),
        'maxBytes': 5 * 1024 * 1024,
        'backupCount': 3,
        'formatter': 'standard',
        'filters': ['tenant_context'],
    }
    LOGGING['loggers']['']['handlers'].append('logfile')

if 'django.core.mail.backends.console.EmailBackend' != _require('EMAIL_BACKEND'):
    import queue

    q = queue.Queue(-1)

    LOGGING['handlers']['mail_admins'] = {
        'level': 'ERROR',
        'class': 'common.utils.AdminEmailHandler',
        'queue': q,
    }
    LOGGING['loggers']['']['handlers'].append('mail_admins')

    from common.utils import AdminEmailQueueListener

    # TODO: set separate backend for exception sending
    AdminEmailQueueListener(q, include_html=True).start()
