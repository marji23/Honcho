import datetime
import difflib
import tempfile
from functools import partial
from itertools import chain, islice
from typing import Callable, Dict, Iterator, List, Optional, Tuple

import unicodecsv
from django.conf import settings
from django.core.files import File
from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from files.models import FileUpload, FileUploader
from .serializers import CsvContactSerializer
from ..contacts.models import Contact, ContactList
from ..models import Campaign, Participation


class ImportResult(object):
    def __init__(self,
                 created: int,
                 updated: int,
                 skipped: int,
                 errors: Dict[int, Optional[List]],
                 failed_rows_file: Optional[FileUpload]) -> None:
        self.created = created
        self.updated = updated
        self.skipped = skipped
        self.errors = errors
        self.failed_rows_file = failed_rows_file


class SniffResult(object):
    def __init__(self, options: dict, fields: List[str],
                 rows: List, headers: Dict[str, int]) -> None:
        self.options = options
        self.fields = fields
        self.rows = rows
        self.headers = headers


class ParsingException(Exception):
    pass


class ContactsCsvImporter(object):
    contact_serializer_class = CsvContactSerializer
    contact_serializer_context = None

    def __init__(self, **kwargs) -> None:
        self.contact_serializer_class = kwargs.pop('contact_serializer_class', self.contact_serializer_class)
        self.contact_serializer_context = kwargs.pop('contact_serializer_context', self.contact_serializer_context)

    def get_existing_contact(self, validated_data: dict) -> Optional[Contact]:
        try:
            # we expect that `email` is required field
            return Contact.objects.get(email=validated_data['email'])
        except Contact.DoesNotExist:
            return None

    def get_contact_serializer(self, data: dict) -> serializers.Serializer:
        return self.contact_serializer_class(data=data, context=self.contact_serializer_context)

    def sniff(self, file_upload: FileUpload,
              encoding: str = settings.DEFAULT_CHARSET,
              limit: int = 5) -> SniffResult:

        try:
            with file_upload.open() as csv_file:
                has_header = unicodecsv.Sniffer().has_header(csv_file.read(1024).decode(encoding))
                csv_file.seek(0)
                dialect = unicodecsv.Sniffer().sniff(csv_file.read(1024).decode(encoding))
                csv_format_opts = dict(dialect=dialect, )
                csv_file.seek(0)

                reader = unicodecsv.reader(csv_file, **csv_format_opts)
                if has_header:
                    header = next(reader)
                else:
                    header = None

                rows = list(islice(reader, max(0, limit))) if limit > 0 else []
        except (UnicodeDecodeError, unicodecsv.Error) as e:
            raise ParsingException(str(e)) from e

        contact_serializer = self.get_contact_serializer(data={})
        fields = {name: field for name, field in contact_serializer.get_fields().items() if not field.read_only}

        headers_mapping = {}
        if header:
            for num, name in enumerate(header):
                field_names = difflib.get_close_matches(name, fields.keys(), n=1)
                if field_names:
                    fields_name = field_names[0]
                    headers_mapping[fields_name] = num

        return SniffResult(
            dict(has_header=has_header, delimiter=dialect.delimiter, ),
            list(fields.keys()),
            rows,
            headers_mapping,
        )

    def parse_and_import(self,
                         file_upload: FileUpload,
                         headers: Dict[str, int],
                         has_headers: Optional[bool] = None,
                         # todo: maybe it is better to accept dialect to give more options to configure
                         delimiter: Optional[str] = None,
                         encoding: str = settings.DEFAULT_CHARSET,
                         allow_update: bool = True,
                         atomic: bool = False,
                         create_failed_rows_file: bool = False,
                         detailed_errors_limit: int = 20,
                         campaign: Optional[Campaign] = None,
                         contact_list: Optional[ContactList] = None) -> ImportResult:

        indexes = {index: header for header, index in headers.items()}

        with file_upload.open() as csv_file:
            csv_format_opts = dict(dialect=unicodecsv.excel,
                                   encoding=encoding, )

            try:
                if has_headers is None:
                    has_headers = unicodecsv.Sniffer().has_header(csv_file.read(1024).decode(encoding))
                    csv_file.seek(0)
                if delimiter is None:
                    dialect = unicodecsv.Sniffer().sniff(csv_file.read(1024).decode(encoding))
                    csv_format_opts['dialect'] = dialect
                    csv_file.seek(0)
                else:
                    csv_format_opts['delimiter'] = delimiter

                csv_reader = unicodecsv.reader(csv_file, **csv_format_opts)

                header = next(csv_reader) if has_headers else None

                process_rows = partial(
                    self._process_rows,
                    csv_reader, indexes,
                    allow_update,
                    atomic,
                    detailed_errors_limit)
            except (UnicodeDecodeError, unicodecsv.Error) as e:
                raise ParsingException(str(e)) from e

            failed_rows_file_upload = None
            with transaction.atomic(savepoint=False):
                if not create_failed_rows_file:
                    created_contacts, updated_contacts, skipped_contacts, errors = process_rows(None)
                else:
                    with tempfile.TemporaryFile() as fp, transaction.atomic(savepoint=False):
                        csv_writer = unicodecsv.writer(fp, **csv_format_opts)

                        if header:
                            csv_writer.writerow(header)

                        created_contacts, updated_contacts, skipped_contacts, errors = process_rows(
                            csv_writer.writerow
                        )

                        if errors:
                            fp.seek(0)
                            failed_rows_file_upload = FileUpload.objects.create(
                                owner=file_upload.owner,
                                uploader=FileUploader.SYSTEM,
                                ttl=datetime.timedelta(days=2),
                                file=File(fp, "failed-rows-from-%s" % file_upload.name)
                            )

                if campaign:
                    participating = set(campaign.contacts.values_list('id', flat=True))
                    Participation.objects.bulk_create((
                        Participation(
                            contact_id=contact_id,
                            campaign=campaign,
                        ) for contact_id in chain(created_contacts,
                                                  filter(lambda contact_id: contact_id not in participating,
                                                         updated_contacts)
                                                  )
                    ))

                if contact_list:
                    contact_list.contacts.add(*created_contacts)
                    contact_list.contacts.add(*updated_contacts)

            return ImportResult(
                len(created_contacts), len(updated_contacts), len(skipped_contacts),
                errors, failed_rows_file_upload
            )

    def _process_rows(self, reader: Iterator, indexes: Dict[int, str],
                      allow_update: bool, atomic: bool, detailed_errors_limit: int,
                      failed_rows_acceptor: Optional[Callable[[List], None]]) -> Tuple[
        List[int], List[int], List[int], Dict[int, Optional[List]]
    ]:
        created_contacts = list()
        updated_contacts = list()
        skipped_contacts = list()
        errors = dict()

        for num, row in enumerate(reader):
            data = {indexes[index]: field for index, field in enumerate(row) if index in indexes}
            contact_serializer = self.get_contact_serializer(data=data)

            if not contact_serializer.is_valid(raise_exception=False):
                errors[num] = contact_serializer.errors if len(errors) < detailed_errors_limit else None

                if failed_rows_acceptor:
                    failed_rows_acceptor(row)
                continue

            instance = self.get_existing_contact(contact_serializer.validated_data)
            if instance:
                if allow_update:
                    updated_contacts.append(
                        contact_serializer.update(instance, validated_data=contact_serializer.validated_data).id
                    )
                else:
                    skipped_contacts.append(instance.id)
            else:
                created_contacts.append(
                    contact_serializer.create(validated_data=contact_serializer.validated_data).id
                )

        if errors and atomic:
            raise ValidationError(errors)

        return (
            created_contacts,
            updated_contacts,
            skipped_contacts,
            errors,
        )
