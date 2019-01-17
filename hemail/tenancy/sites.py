from django.contrib import admin


class TenancyAdminSite(admin.AdminSite):
    _modified = set()

    def register(self, model_or_iterable, admin_class=None, **options):
        from .admin import TenancyAppAdminMixin

        if admin_class:
            if not issubclass(admin_class, TenancyAppAdminMixin) and admin_class not in self._modified:
                # We are going to extend original class and add tenancy mixin. I think that it is better than
                # changing __bases__ not still not good enough. Maybe it can be done with meta classes?
                self._modified.add(admin_class)
                bases = (TenancyAppAdminMixin, admin_class)
                admin_class = type('Tenancy' + admin_class.__name__, bases, {})
        else:
            class TenancyModelAdmin(TenancyAppAdminMixin, admin.ModelAdmin):
                pass

            admin_class = TenancyModelAdmin

        return super().register(model_or_iterable, admin_class, **options)
