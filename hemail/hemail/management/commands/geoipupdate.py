from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Install or update GeoIP db'

    def handle(self, *args, **options):

        from common.utils import GeoLiteUpdater
        try:
            GeoLiteUpdater.update()

            self.stdout.write(self.style.SUCCESS('Successfully update'))
        except Exception as e:
            raise CommandError('Failed to update Geo IP dbs') from e
