
To start celery:
$ celery -A hemail worker -l info

To run server worker:
$ ./manage.py runworker

To run interface server:
$ daphne hemail.asgi:application