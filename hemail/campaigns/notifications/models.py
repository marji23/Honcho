from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from pinax.notifications.models import NoticeType


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("user"),
        on_delete=models.CASCADE
    )

    created = models.DateTimeField(auto_now_add=True)

    action = models.ForeignKey(
        NoticeType,
        verbose_name=_("action"),
        on_delete=models.CASCADE
    )

    read_datetime = models.DateTimeField(blank=True, null=True)

    extra_context = JSONField(_('Meta'), blank=True, null=True)

    def mark_as_read(self) -> None:
        if self.read_datetime is not None:
            return
        self.read_datetime = now()
        self.save(update_fields=['read_datetime', ])

    @classmethod
    def send(cls, user, label: str, extra_context: dict = None, scoping=None) -> None:
        assert scoping is None, "scoping is not supported yet"

        # checks if similar message was just created
        cls.objects.get_or_create(
            user=user,
            action=NoticeType.objects.get(label=label),
            extra_context=extra_context,
        )
