import os
from optparse import make_option, OptionError
from django.core.management.base import BaseCommand

class CSVHarvestCommand(BaseCommand):
	processor = None
	option_list = BaseCommand.option_list + (
		make_option('--csv', action='store', dest='csv_path', help='The path to the CSV file to import.'),
		make_option('--validate', action='store_true', dest='validate', default=False, help='Validate only, do not save.'),
		)
	help = 'Parse the CSV file and populate the database.'

	def handle(self, *args, **options):
		csv_path = options.get('csv_path', None)
		if not csv_path:
			raise OptionError('Please provide the path to the CSV file to import.', '--csv')
		if not os.access(csv_path, os.R_OK):
			raise IOError('The CSV file "%s" could not be opened.' % csv_path)
		if not self.processor or not hasattr(self.processor, 'parse'):
			raise ValueError('No valid harvest processor was specified.')
		self.processor.parse(csv_path)
		if not options.get('validate', False):
			self.processor.save()
			