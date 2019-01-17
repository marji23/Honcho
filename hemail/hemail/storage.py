from threading import local

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files import storage
from django.utils.functional import LazyObject
from django.utils.module_loading import import_string


class InvalidStorageBackendError(ImproperlyConfigured):
    pass


DEFAULT_STORAGE_ALIAS = 'default'


def _create_storage(backend_alias: str, **kwargs: dict) -> storage.Storage:
    try:
        # Try to get the FILE_STORAGES entry for the given backend name first
        conf = settings.FILE_STORAGES[backend_alias]
    except KeyError:
        try:
            # Trying to import the given backend, in case it's a dotted path
            import_string(backend_alias)
        except ImportError as e:
            raise InvalidStorageBackendError("Could not find backend '%s': %s" % (backend_alias, e))
        backend_cls_name = backend_alias
        backend_options = kwargs
    else:
        params = conf.copy()
        params.update(kwargs)
        backend_cls_name = params.pop('BACKEND')
        backend_options = params.pop('OPTIONS', {})

    try:
        backend_cls = import_string(backend_cls_name)
    except ImportError as e:
        raise InvalidStorageBackendError("Could not find backend '%s': %s" % (backend_alias, e))

    return backend_cls(**backend_options)


class StorageHandler(object):
    """
    A Cache Handler to manage access to Cache instances.

    Ensures only one instance of each alias exists per thread.
    """

    def __init__(self):
        self._file_storages = local()

    def __getitem__(self, alias):
        try:
            return self._file_storages.storages[alias]
        except AttributeError:
            self._file_storages.storages = {}
        except KeyError:
            pass

        if alias not in settings.FILE_STORAGES:
            raise InvalidStorageBackendError(
                "Could not find config for '%s' in settings.FILE_STORAGES" % alias
            )

        storage = _create_storage(alias)
        self._file_storages.storages[alias] = storage
        return storage

    def all(self):
        return getattr(self._file_storages, 'storages', {}).values()


storages = StorageHandler()


class DefaultStorage(LazyObject):
    def _setup(self):
        self._wrapped = storages[DEFAULT_STORAGE_ALIAS]
