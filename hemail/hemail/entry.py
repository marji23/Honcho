from __future__ import absolute_import

import argparse
import os
import sys


def run_celery(args):
    os.environ.setdefault("ROLE", 'celery')

    from celery.bin.celery import main
    return main(sys.argv[:1] + ['-A', 'hemail', 'worker'] + args)


def run_beat(args):
    os.environ.setdefault("ROLE", 'beat')

    from celery.bin.celery import main
    return main(sys.argv[:1] + [
        '-A', 'hemail',
        'beat',
        '--scheduler', 'django_celery_beat.schedulers:DatabaseScheduler',
    ] + args)


def run_daphne(args):
    os.environ.setdefault("ROLE", 'daphne')

    from daphne.cli import CommandLineInterface
    CommandLineInterface().run(args + ['hemail.asgi:application'])


def run_manage(args):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hemail.settings")

    from django.core.management import execute_from_command_line
    return execute_from_command_line(sys.argv[:1] + args)


def run_worker(args):
    os.environ.setdefault("ROLE", 'worker')

    return run_manage(['runworker', 'default'] + args)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='Honcho Email Marketing server')

    subparsers = parser.add_subparsers(dest='mode')

    manage_parser = subparsers.add_parser('manage', help='runs django manage command')

    daphne_parser = subparsers.add_parser('daphne', help='runs daphne service')

    celery_parser = subparsers.add_parser('celery', help='runs celery service')

    beat_parser = subparsers.add_parser('beat', help='runs beat scheduler service')

    worker_parser = subparsers.add_parser('worker', help='runs django worker')

    namespace, args = parser.parse_known_args()

    mode = namespace.mode
    dict(
        celery=run_celery,
        beat=run_beat,
        daphne=run_daphne,
        manage=run_manage,
        worker=run_worker,
    ).get(namespace.mode, lambda ignored: parser.print_help() or sys.exit(-1))(args)
