"""hemail URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from importlib import import_module
from urllib.parse import urljoin

from allauth.socialaccount import providers
from django.conf import settings
from django.conf.urls import include, url
from django.conf.urls.static import static
from django.contrib import admin
from django.views.generic import RedirectView
from rest_auth import views as rest_auth_views
from rest_framework_jwt.views import refresh_jwt_token

from campaigns import views as campaigns_views
from campaigns.contacts import views as contacts_views
from campaigns.importer import views as contacts_importer_views
from campaigns.notifications import views as notifications_views
from campaigns.providers import views as providers_views
from campaigns.templates import views as templates_views
from files import views as files_views
from users import views as users_views
from . import routers

app_name = 'hemail'

admin.autodiscover()

social_providers_urlpatterns = []
for provider in providers.registry.get_list():
    try:
        prov_mod = import_module(provider.get_package() + '.urls')
    except ImportError:
        continue
    prov_urlpatterns = getattr(prov_mod, 'urlpatterns', None)
    if prov_urlpatterns:
        social_providers_urlpatterns += prov_urlpatterns

router = routers.ExtendedBulkRouter()
router.register(r'users', users_views.UserViewSet)

campaign_registration = router.register(r'campaigns', campaigns_views.CampaignsViewSet, base_name='campaigns')
campaign_registration \
    .register(r'steps', campaigns_views.StepViewSet,
              base_name='campaigns-steps', parents_query_lookups=['campaign']) \
    .register(r'emails', campaigns_views.EmailStageViewSet,
              base_name='campaigns-steps-email', parents_query_lookups=['step__campaign', 'step'])
campaign_registration \
    .register(r'contacts', campaigns_views.CampaignsParticipationViewSet,
              base_name='campaigns-contacts', parents_query_lookups=['campaign'])
campaign_registration \
    .register(r'settings', campaigns_views.CampaignSettingsViewSet, parents_query_lookups=['campaign'],
              base_name='campaigns-settings')

router.register(r'providers', providers_views.EmailAccountViewSet)

router.register(r'importing/contacts/csv', contacts_importer_views.ContactsCsvSniffingViewSet,
                base_name='importing-contacts-sniffing')
router.register(r'importing/contacts', contacts_importer_views.ContactsCsvViewSet,
                base_name='importing-contacts')

contact_registration = router.register(r'contacts', contacts_views.ContactViewSet, base_name='contacts')
contact_registration \
    .register(r'campaigns', campaigns_views.ContactsParticipationViewSet,
              base_name='contacts-campaigns', parents_query_lookups=['contact'])
contact_registration \
    .register(r'notes', contacts_views.NestedContactNotesViewSet,
              base_name='contacts-notes', parents_query_lookups=['contact'])
contact_registration \
    .register(r'messages', campaigns_views.NestedContactEmailMessageViewSet,
              base_name='contacts-messaes', parents_query_lookups=['contact'])
router.register(r'lists', contacts_views.ContactListViewSet) \
    .register(r'contacts', contacts_views.NestedContactListContactViewSet,
              base_name='contacts-list', parents_query_lookups=['lists'])

router.register(r'templates/folders', templates_views.FoldersViewSet, base_name='templates-folders') \
    .register(r'templates', templates_views.NestedFolderEmailTemplateViewSet,
              base_name='templates-folders-templates', parents_query_lookups=['folder'])
router.register(r'templates', templates_views.EmailTemplateViewSet)
router.register(r'files', files_views.FileUploadViewSet, base_name='files')
router.register(r'leads/generation/requests', campaigns_views.LeadGenerationRequestViewSet,
                base_name='lead-generation-requests') \
    .register(r'contacts', campaigns_views.NestedContactLeadViewSet,
              base_name='lead-generation-requests-contacts', parents_query_lookups=['generator'])
router.register(r'messages', campaigns_views.EmailMessagesViewSet, base_name='messages')
router.register(r'notifications/settings', notifications_views.NoticeSettingsViewSet, base_name='notice-settings')
router.register(r'notifications/notice-types', notifications_views.NoticeTypesViewSet, base_name='notice-types')
router.register(r'notifications', notifications_views.NotificationsViewSet, base_name='notifications')
router.register(r'variables', campaigns_views.ContextVariablesViewSet, base_name='context-variables')

urlpatterns = [
    url(r'^jet/dashboard/', include('jet.dashboard.urls', 'jet-dashboard')),
    url(r'^jet/', include('jet.urls', 'jet')),
    url(r'^admin/', admin.site.urls),

    url(r"^api-auth/email/$", users_views.ObtainEmailMagicLinkView.as_view(), name="auth_email"),
    url(r"^api-auth/passwordless/$", users_views.ObtainJSONWebTokenFromMagicLinkView.as_view(),
        name="obtain_jwt_token"),
    url(r'^api-auth/login/$', users_views.LoginView.as_view(), name='rest_login'),
    url(r'^api-auth/refresh/', refresh_jwt_token),
    url(r'^api-auth/logout/$', rest_auth_views.LogoutView.as_view(), name='rest_logout'),
    url(r'^api-auth/password/change/$', rest_auth_views.PasswordChangeView.as_view(), name='rest_password_change'),
    url(r'^api-auth/password/reset/$', rest_auth_views.PasswordChangeView.as_view(), name='rest_password_change'),
    url(r'^api-auth/user/avatar/$', users_views.AvatarUpdateView.as_view(), name='user-avatar-updater'),
    url(r'^api-auth/user/$', users_views.ProfileView.as_view(), name='rest_user_details'),

    url(r'^api/providers/presets/$', providers_views.EmailAccountPresetsListView.as_view(),
        name='email-accounts-presets_list'),
    url(r'^api/', include((router.urls, app_name), namespace='api')),

    # we should not set namespace here or app because we override all-auth urls
    url(r'^social/', include(social_providers_urlpatterns)),

    url(r'^open/(?P<path>[\w=-]+)$', campaigns_views.EmailOpenTrackingView.as_view(), name="open_tracking"),
    url(r'^click/(?P<path>[\w=-]+)$', campaigns_views.EmailLinksClickTrackingView.as_view(), name="click_tracking"),

    # we are adding favicon.ico to url to remove spam in logs during development
    url(r'^favicon\.ico$', RedirectView.as_view(
        url=urljoin(settings.STATIC_URL, 'favicon.ico'), permanent=True), name='favicon'),
]

if settings.DEBUG and settings.FILE_STORAGES_LOCAL_MODE:
    from tenancy.views import serve

    urlpatterns += static(settings.MEDIA_URL, view=serve, document_root=settings.MEDIA_ROOT)
