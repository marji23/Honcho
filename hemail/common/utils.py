import collections
import datetime
import os
import re
import shutil
import tarfile
import tempfile
from contextlib import closing
from datetime import timedelta
from logging.handlers import QueueHandler, QueueListener
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytz
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.functional import cached_property
from django.utils.log import AdminEmailHandler as DjangoAdminEmailHandler


def introspect(d: collections.MutableMapping, parent_key: str = '', sep: str = '.') -> dict:
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + str(k) if parent_key else str(k)
        if isinstance(v, collections.MutableMapping):
            items.extend(introspect(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def time_delta(start: datetime.time, end: datetime.time) -> datetime.timedelta:
    return datetime.datetime.combine(datetime.date.min, start) - datetime.datetime.combine(datetime.date.min, end)


class GeoLiteUpdater(object):
    MODIFIED_HEADER_FORMAT = '%a, %d %b %Y %H:%M:%S GMT'

    DB = {
        'GEOIP_COUNTRY': 'http://geolite.maxmind.com/download/geoip/database/GeoLite2-Country.tar.gz',
        'GEOIP_CITY': 'http://geolite.maxmind.com/download/geoip/database/GeoLite2-City.tar.gz',
    }

    @classmethod
    def check(cls):
        result = []
        for db, (download_url, target_path,) in cls._read_from_settings().items():
            try:
                response = cls._get_response(download_url, target_path)
                if response is not None:
                    result.append(db)
                    response.close()
            except ValueError:
                pass

        return result

    @classmethod
    def update(cls):
        for db, (download_url, target_path,) in cls._read_from_settings().items():
            cls._update(download_url, target_path)

    @classmethod
    def _read_from_settings(cls) -> dict:
        geoip_dir_path = settings.GEOIP_PATH
        if not os.path.isdir(geoip_dir_path):
            raise ImproperlyConfigured("GEOIP_PATH should point to existing directory ('%s')" % geoip_dir_path)

        arguments = {}
        for db, download_url in cls.DB.items():
            file_path = getattr(settings, db, None)
            if not file_path:
                continue
            target_path = os.path.join(geoip_dir_path, file_path)
            arguments[db] = (download_url, target_path,)

        return arguments

    @classmethod
    def _get_response(cls, download_url, target_path):
        q = Request(download_url)
        if os.path.isfile(target_path):
            modified_time = os.path.getmtime(target_path)
            modified_datetime = datetime.datetime.utcfromtimestamp(modified_time)
            q.add_header('If-Modified-Since', modified_datetime.strftime(cls.MODIFIED_HEADER_FORMAT))

        try:
            return urlopen(q, timeout=10)
        except HTTPError as e:
            if e.code == 304:
                return None
            raise ValueError("Failed to open url: %s" % download_url) from e
        except (ConnectionError, URLError) as e:
            raise ValueError("Failed to open url: %s" % download_url) from e

    @classmethod
    def _update(cls, download_url, target_path, ):
        response = cls._get_response(download_url, target_path)
        if response is None:
            return
        try:
            modified_response = response.headers.get('Last-Modified')

            modified_datetime = datetime.datetime.strptime(modified_response, cls.MODIFIED_HEADER_FORMAT)
            modified_time = modified_datetime.replace(tzinfo=datetime.timezone.utc).timestamp()

            with tempfile.TemporaryFile() as fp:
                shutil.copyfileobj(response, fp)
                fp.seek(0)

                with closing(tarfile.TarFile.open(mode='r:gz', fileobj=fp)) as tar:
                    tar_mmdb_members = [tarinfo for tarinfo in tar if os.path.splitext(tarinfo.name)[1] == ".mmdb"]
                    assert len(tar_mmdb_members) == 1
                    tar_info = tar_mmdb_members[0]
                    tar_file_obj = tar.extractfile(tar_info)

                    with open(target_path, 'wb') as target_file:
                        shutil.copyfileobj(tar_file_obj, target_file)

                    os.utime(target_path, (modified_time, modified_time))
        finally:
            response.close()


class FixedOffset(pytz._FixedOffset):
    _offset_re = re.compile(r'UTC(?P<sign>[-+])(?P<hours>\d{2})(?P<minutes>\d{2})')

    @classmethod
    def parse(cls, value: str) -> Optional['FixedOffset']:
        match = cls._offset_re.match(value)
        if not match:
            return None
        offset = int(match.group('hours')) * 60 + int(match.group('minutes'))
        if match.group('sign') == '-':
            offset = -offset
        return cls(offset)

    def tzname(self, dt) -> str:
        return self.zone

    @cached_property
    def zone(self) -> str:
        offset = self.utcoffset(None)
        if isinstance(offset, timedelta):
            offset = offset.total_seconds() // 60
        sign = '-' if offset < 0 else '+'
        hhmm = '%02d%02d' % divmod(abs(offset), 60)
        return 'UTC' + sign + hhmm

    def __repr__(self) -> str:
        return 'pytz.FixedOffset(%d)' % self._minutes

    def __str__(self) -> str:
        return self.zone


class AdminEmailHandler(QueueHandler):

    def emit(self, record) -> None:
        if not settings.ADMINS:
            return

        super().emit(record)


class AdminEmailQueueListener(QueueListener):

    def __init__(self, queue, include_html=False, email_backend=None) -> None:
        super().__init__(queue, DjangoAdminEmailHandler(include_html, email_backend))
