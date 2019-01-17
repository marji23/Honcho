# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

# no need of internalization
USE_I18N = False

# we don't want to localize date or number format - server will work in UTC only, clients will do localization
USE_L10N = False

USE_TZ = True
