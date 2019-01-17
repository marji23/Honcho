#!/usr/bin/env python
import os
import shutil
from contextlib import contextmanager
from os.path import abspath, dirname, join
from tempfile import mkdtemp

from pex.bin import pex

BASE_PATH = abspath(dirname(__file__))


@contextmanager
def collect(*sources):
    dst = mkdtemp(prefix='pexerize-')

    try:
        for src in sources:
            for item in os.listdir(src):
                s = join(src, item)
                d = join(dst, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, symlinks=True)
                else:
                    shutil.copy2(s, d)
        yield dst
    finally:
        shutil.rmtree(dst)


def find_setups(where):
    import setuptools

    grabbed = dict(kwargs={})

    def _setup(*args, **kwargs):
        assert not args
        grabbed['kwargs'] = kwargs

    origin_setup = setuptools.setup
    setuptools.setup = _setup

    result = {}
    try:
        import glob

        for filename in glob.glob(os.path.join(where, '**', 'setup.py')):
            assert os.path.isfile(filename)
            with open(filename, 'rb') as f:
                exec(compile(f.read(), filename, 'exec'))
                parameters = grabbed['kwargs']
                result[parameters['name']] = dirname(filename), parameters

        return result.values()
    finally:
        setuptools.setup = origin_setup


if __name__ == '__main__':

    dest = join(BASE_PATH, 'bin')
    if not os.path.isdir(dest):
        os.makedirs(dest, )
    os.chdir(dest)

    for path, setup in find_setups(BASE_PATH):
        pex_target = join(dest, '%s.%s.pex' % (setup['name'], setup['version'],))

        for f in os.listdir(path):
            if f.endswith('.egg-info'):
                ff = os.path.join(path, f)
                if os.path.isdir(ff):
                    shutil.rmtree(ff)

        pex.main(args=[
            '-v',
            '-e', 'hemail.entry',  # TODO: does not make sense for all setups
            '--not-zip-safe',
            '--always-write-cache',
            '--disable-cache',  # disable pex cache to make sure to really recent file with be in target
            '-o', pex_target,
            path,
        ])
