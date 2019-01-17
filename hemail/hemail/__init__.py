from __future__ import absolute_import, unicode_literals


def _monkey() -> None:
    import imp
    import os
    import sys

    class MonkeyImporter(object):
        def find_module(self, fullname, path=None):
            if fullname == 'django.core.urlresolvers':
                return self
            return None

        def load_module(self, name):
            if name in sys.modules:
                return sys.modules[name]

            print("generating module({name})".format(name=name))

            parent_module = sys.modules['django.core']
            module = imp.new_module(name)
            module.__path__ = [os.path.join(path, 'urlresolvers') for path in parent_module.__path__]
            module.__loader__ = self
            module_code = """
from django.urls.exceptions import *
from django.urls import *
from django.urls import URLResolver as RegexURLResolver
"""

            exec(compile(module_code, '%s.py' % module.__path__[0], 'exec'), module.__dict__)
            sys.modules[name] = module

            parent_module.__dict__['urlresolvers'] = module

            return module

    sys.meta_path.append(MonkeyImporter())


_monkey()

from . import checks  # noqa: F401
# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from ._celery import app as celery_app  # noqa: E402

__all__ = ['celery_app']
