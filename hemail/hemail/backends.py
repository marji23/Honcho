from django.db import connections, router
from watson.backends import PostgresSearchBackend as WatsonPostgresSearchBackend
from watson.models import SearchEntry


class PostgresSearchBackend(WatsonPostgresSearchBackend):

    def is_installed(self):
        """Checks whether django-watson is installed."""
        connection = connections[router.db_for_read(SearchEntry)]

        # `::regclass` respects search path and make it work for tenant
        cursor = connection.cursor()
        cursor.execute("""
          SELECT attname FROM pg_attribute
          WHERE attrelid = 'watson_searchentry'::regclass AND attname = 'search_tsv';
        """)
        return bool(cursor.fetchall())
