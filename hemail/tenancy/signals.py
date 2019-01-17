from django.db.models.signals import ModelSignal

tenant_prepared = ModelSignal(providing_args=["tenant"])
