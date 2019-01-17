from django.apps import AppConfig


class TenancyConfig(AppConfig):
    name = 'tenancy'
    icon = '<i class="material-icons">domain</i>'

    def ready(self):
        from django.contrib import admin
        from django.contrib.admin import sites

        from tenancy.sites import TenancyAdminSite
        mysite = TenancyAdminSite()

        admin.site = mysite
        sites.site = mysite
