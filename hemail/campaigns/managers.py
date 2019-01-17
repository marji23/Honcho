from typing import Iterable, Optional

from django.db import models, router
from django.db.models.signals import post_save


class ParticipationQuerySet(models.QuerySet):

    def bulk_create(self, objs: Iterable['Participation'],
                    batch_size: Optional[int] = None) -> 'ParticipationQuerySet':
        participations = list(objs)
        for participation in participations:
            participation.update_activation()
        participations = super().bulk_create(participations, batch_size)
        for participation in participations:
            using = router.db_for_write(router, instance=participation)
            post_save.send(sender=participation.__class__, instance=participation, created=True, using=using)
        return participations


ParticipationManager = ParticipationQuerySet.as_manager
