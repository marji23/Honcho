import datetime

from celery import shared_task
from celery.schedules import schedule
from celery.task import periodic_task
from celery.utils.log import get_task_logger
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from tenancy.utils import map_task_per_tenants, tenant_context_or_raise_reject
from . import utils
from .contacts.models import Contact
from .models import (
    CompanyEmployeeCountLevel, CompanyRevenue, ContactLead, ContactLeadStatus, LeadDepartment, LeadGenerationRequest,
    LeadGenerationRequestStatus, LeadLevel, Participation
)

logger = get_task_logger(__name__)


@shared_task
def submit_campaigns_email(tenant_id: int):
    with tenant_context_or_raise_reject(tenant_id) as tenant:
        submitted_emails_number = len(utils.submit_emails())
        logger.info("[%d: %s]: Emails %d submitted", tenant_id, tenant.schema_name, submitted_emails_number)
        return submitted_emails_number


@periodic_task(run_every=schedule(run_every=datetime.timedelta(minutes=5)))
def submit_tenants_emails():
    return map_task_per_tenants(submit_campaigns_email)


@shared_task
def send_queued_emails(tenant_id: int):
    with tenant_context_or_raise_reject(tenant_id) as tenant:
        total_sent, total_failed = utils.send_queued()
        logger.info("[%d: %s]: Emails %d sent, %d failed", tenant_id, tenant.schema_name, total_sent, total_failed)
        return total_sent, total_failed


@periodic_task(run_every=schedule(run_every=datetime.timedelta(minutes=5)))
def send_queued_tenants_emails():
    return map_task_per_tenants(send_queued_emails)


@shared_task
def process_lead_generation_request(tenant_id: int, lead_generation_request_id: int):
    with tenant_context_or_raise_reject(tenant_id):
        request = LeadGenerationRequest.objects.get(id=lead_generation_request_id)

        # calculate seed for stable generation first
        seed = request.campaign_id
        for field_name in [
            # 'campaign',
            'company_name',
            'company_industry_name',
            'company_sic_code',
            'company_employee_count',
            'company_revenue',

            'name',
            'title',
            'department',
            'level',

            'email_deliverability',

            'city',
            'state',
            'country',
            'zip_code',
        ]:
            value = getattr(request, field_name)
            seed = seed * 51 | hash(tuple(value) if isinstance(value, list) else value)

        from faker import Faker
        fake = Faker()
        fake.seed_instance(seed)

        # todo: can respect employee count (NB: we can generate companies first)
        count = fake.random.randrange(5, 10)
        leads = dict()
        for _ in range(count):
            email = fake.email()
            if email in leads:
                continue

            leads[email] = ContactLead(
                generator=request,

                email=email,
                phone_number=fake.msisdn(),

                # TODO: respect request.name
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                title=request.title if request.title else fake.prefix(),

                # timezone=TimeZoneField(blank=True),

                company_name=request.company_name if request.company_name else fake.company(),
                company_employee_count=fake.random_element(
                    request.company_employee_count if request.company_employee_count
                    else list(CompanyEmployeeCountLevel)),
                company_revenue=fake.random_element(
                    request.company_revenue if request.company_revenue else list(CompanyRevenue)),

                department=fake.random_element(
                    request.department if request.department else list(LeadDepartment)),
                level=fake.random_element(
                    request.level if request.level else list(LeadLevel)),

                city=request.city if request.city else fake.city(),
                state=request.state if request.state else fake.state(),
                country=fake.country(),
                street_address=fake.street_address(),
                zip_code=request.zip_code if request.zip_code else fake.zipcode(),

            )

        ContactLead.objects.bulk_create(list(leads.values()))
        request.status = LeadGenerationRequestStatus.PROCESSED
        request.save()


@shared_task
def add_leads_into_campaigns(tenant_id: int):
    with tenant_context_or_raise_reject(tenant_id):
        current_datetime = now()
        day_ago = current_datetime - datetime.timedelta(days=1)
        generators = LeadGenerationRequest.objects.filter(
            Q(last_update=None) | Q(last_update__gte=day_ago),
            status=LeadGenerationRequestStatus.WORKING,
        )

        for generator in generators:
            with transaction.atomic():
                import_per_day = generator.import_per_day
                leads = generator.leads.filter(status=ContactLeadStatus.CREATED).order_by('pk')[:import_per_day]
                leads_by_email = dict()
                for lead in leads:
                    leads_by_email[lead.email] = lead

                existed = Contact.objects.filter(email__in=list(leads_by_email.keys())).values_list('email', flat=True)
                for existed_contact_email in existed:
                    lead = leads_by_email.pop(existed_contact_email, None)
                    if lead:
                        lead.status = ContactLeadStatus.DUPLICATES
                        lead.save()

                if not leads_by_email:
                    return

                contacts = [l.to_contact() for l in leads_by_email.values()]
                contacts = Contact.objects.bulk_create(contacts)

                Participation.objects.bulk_create((
                    Participation(
                        contact=contact,
                        campaign=generator.campaign,
                    ) for contact in contacts
                ))

                generator.last_update = current_datetime

                for lead in leads_by_email.values():
                    lead.status = ContactLeadStatus.PROCESSED
                    lead.save()


@periodic_task(run_every=schedule(run_every=datetime.timedelta(minutes=5)))
def add_leads_into_campaigns_in_tenants():
    return map_task_per_tenants(add_leads_into_campaigns)
