import sys
from collections import OrderedDict

from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models import Count
from django_postgres_extensions.models.functions import ArrayAppend, ArrayRemove
from tenant_schemas.utils import get_tenant_model


class Command(BaseCommand):
    """
    Fixes the campaigns and steps problems with recheck.
    """

    help = 'Used to create tenant data.'

    def __init__(self, *args, **kwargs) -> None:
        super(Command, self).__init__(*args, **kwargs)
        self.TenantModel = get_tenant_model()

    def add_arguments(self, parser) -> None:
        parser.add_argument('--database', action='store', dest='database',
                            default=DEFAULT_DB_ALIAS, help='Specifies the database to use. Default is "default".'),

    def handle(self, *args, **options) -> None:
        verbosity = int(options.get('verbosity', 1))

        database = options.get('database')

        try:
            from campaigns.models import Campaign
            from campaigns.models import CampaignStatus
            from campaigns.models import CampaignProblems
            from campaigns.models import Step
            from campaigns.models import StepProblems

            results = OrderedDict()
            with transaction.atomic():
                results["add NO_STEPS to campaigns"] = Campaign.objects.using(database).annotate(
                    steps_count=Count('steps')
                ).filter(
                    steps_count=0,
                ).exclude(
                    problems__contains=[CampaignProblems.NO_STEPS],
                ).update(problems=ArrayAppend('problems', CampaignProblems.NO_STEPS))
                results['remove NO_STEPS from campaigns'] = Campaign.objects.using(database).annotate(
                    steps_count=Count('steps')
                ).filter(
                    steps_count__gt=0,
                    problems__contains=[CampaignProblems.NO_STEPS],
                ).update(problems=ArrayRemove('problems', CampaignProblems.NO_STEPS))

                results['add NO_CONTACTS to campaigns'] = Campaign.objects.using(database).annotate(
                    contacts_count=Count('contacts')).filter(
                    contacts_count=0,
                ).exclude(
                    problems__contains=[CampaignProblems.NO_CONTACTS],
                ).update(problems=ArrayAppend('problems', CampaignProblems.NO_CONTACTS))
                results['remove NO_CONTACTS from campaigns'] = Campaign.objects.using(database).annotate(
                    contacts_count=Count('contacts')
                ).filter(
                    contacts_count__gt=0,
                    problems__contains=[CampaignProblems.NO_CONTACTS],
                ).update(problems=ArrayRemove('problems', CampaignProblems.NO_CONTACTS))

                results['add EMPTY_STEPS to campaigns'] = Campaign.objects.using(database).annotate(
                    email_stages_count=Count('steps__emails')
                ).filter(
                    email_stages_count=0,
                ).exclude(
                    problems__contains=[CampaignProblems.EMPTY_STEP],
                ).update(problems=ArrayAppend('problems', CampaignProblems.EMPTY_STEP))
                results['remove EMPTY_STEPS from campaigns'] = Campaign.objects.using(database).annotate(
                    email_stages_count=Count('steps__emails')
                ).filter(
                    email_stages_count__gt=0,
                    problems__contains=[CampaignProblems.EMPTY_STEP],
                ).update(problems=ArrayRemove('problems', CampaignProblems.EMPTY_STEP))

                results['add EMPTY_STEPS to steps'] = Step.objects.using(database).annotate(
                    email_stages_count=Count('emails')
                ).filter(
                    email_stages_count=0,
                ).exclude(
                    problems__contains=[StepProblems.EMPTY_STEP],
                ).update(problems=ArrayAppend('problems', StepProblems.EMPTY_STEP))
                results['remove EMPTY_STEPS from steps'] = Step.objects.using(database).annotate(
                    email_stages_count=Count('emails')
                ).filter(
                    email_stages_count__gt=0,
                    problems__contains=[StepProblems.EMPTY_STEP],
                ).update(problems=ArrayRemove('problems', StepProblems.EMPTY_STEP))

                results['set campaigns status from DRAFT to PAUSED'] = Campaign.objects.using(database).filter(
                    status=CampaignStatus.DRAFT,
                    problems__len=0,
                    # steps__problems__len=0,
                ).update(status=CampaignStatus.PAUSED)
                results['set campaigns status from ACTIVE or PAUSED back to DRAFT'] = (
                    Campaign.objects.using(database).filter(
                        problems__len__gt=0,
                        # Q(problems__len__gt=0) | Q(steps__problems__len__gt=0),
                    ).exclude(
                        status=CampaignStatus.DRAFT
                    ).update(
                        status=CampaignStatus.DRAFT
                    )
                )

            if verbosity >= 1:
                self.stdout.write(
                    'Problems successfully rechecked:\n\t%s' % '\n\t'.join(
                        '%s: %d' % (name, count) for name, count in results.items()
                    )
                )

        except KeyboardInterrupt:
            self.stderr.write("\nOperation cancelled.")
            sys.exit(1)

        except BaseException as e:
            self.stderr.write("Error: %s" % str(e))
            sys.exit(1)
