from django.db import models


class EmailAccountQuerySet(models.QuerySet):
    def active(self, user, **kwargs):
        return self.filter(user=user, incoming__active=True)


EmailAccountManager = EmailAccountQuerySet.as_manager
