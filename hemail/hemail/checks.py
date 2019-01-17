from django.conf import settings
from django.core.checks import Error, Tags as DjangoTags, Warning, register


class Tags(DjangoTags):
    geoip = 'geoip'


@register(Tags.geoip)
def check_geoip(app_configs, **kwargs):
    checks = []

    if not hasattr(settings, 'GEOIP_PATH'):
        msg = ("GeoIP is not enabled. Add directory where db will be stored in settings as eg: "
               "`GEOIP_PATH = '/opt/geoip/dbs-directory/`.")
        checks.append(Error(msg, id='geoip.E001'))
    else:
        if not hasattr(settings, 'GEOIP_COUNTRY'):
            msg = "To use countries info with GeoIP provide GEOIP_COUNTRY in settings as filename where db is stored"
            checks.append(Warning(msg, id='geoip.W001'))

        if not hasattr(settings, 'GEOIP_CITY'):
            msg = "To use cities info with GeoIP provide GEOIP_CITY in settings as filename where db is stored"
            checks.append(Warning(msg, id='geoip.W002'))

        from common.utils import GeoLiteUpdater
        can_be_updated = GeoLiteUpdater.check()
        if can_be_updated:
            msg = "You can install a new versions of: %s" % ', '.join(can_be_updated)
            checks.append(Warning(msg,
                                  hint="Run manage.py geoipupdate",
                                  id='geoip.W003'))

    return checks
