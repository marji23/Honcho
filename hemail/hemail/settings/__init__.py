__author__ = 'yushkovskiy'


def _eval_import(*names):
    import os
    for name in names:
        filename = os.path.join(os.path.dirname(__file__), '%s.py' % name)
        with open(filename, 'rb') as f:
            exec(compile(f.read(), filename, 'exec'), globals())


_eval_import(
    # load configurable values first
    'config',

    # override with values which should not be changed
    'applications',
    'settings',
    'internationalization',
    'logging',
)
