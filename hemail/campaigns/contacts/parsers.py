from django.conf import settings
from rest_framework.parsers import FileUploadParser
from rest_framework_csv.parsers import unicode_csv_reader


class CSVFileParser(FileUploadParser, ):
    media_type = 'text/csv'

    def parse(self, stream, media_type=None, parser_context=None):
        parser_context = parser_context or {}
        delimiter = parser_context.get('delimiter', ',')
        encoding = parser_context.get('encoding', settings.DEFAULT_CHARSET)

        data_and_files = super().parse(stream=stream, media_type=media_type, parser_context=parser_context)
        file_obj = data_and_files.files['file'].file
        rows = unicode_csv_reader(file_obj, delimiter=delimiter, charset=encoding)
        return rows
