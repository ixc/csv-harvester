from bisect import bisect
import collections
import csv
import pprint

from constants import ConfigurationError, ValidationError, PrematureAccessError, DEFAULTS_FIRST, DEFAULTS_LAST
from columns import Column, Field, AutoReference, ForeignKey

class Processor(object):
	harvester = None
	label_row = None # Must be less than or equal to start_row
	start_row = 1
	start_column = 1
	rows_to_read = None
	
	def __init__(self):
		self._rows_parsed = 0
		self._row_count_validated = False
		if not self.harvester:
			raise ConfigurationError('No harvester specified for processor %s.' % self.__class__.__name__)

	def parse(self, csv_path):
		reader = csv.reader(open(csv_path))
		# Skip lines until the start row
		for i in range(1, self.start_row):
			skip_row = reader.next()
			if i == self.label_row:
				self.harvester._meta.labels = skip_row
		# Read the rows
		for row in reader:
			if not self._row_count_validated:
				self.validate_row(row[self.start_column - 1:])
			self.harvester.parse(row[self.start_column - 1:])
			self._rows_parsed += 1
			if self.rows_to_read and self._rows_parsed >= self.rows_to_read:
				break
		print '%s rows parsed.' % self._rows_parsed
	
	def save(self):
		self.harvester.save()
	
	# Compare the number of columns in the CSV file with the number of fields
	# defined in the harvester and inform the user of any discrepancy
	def validate_row(self, row):
		if len(row) < len(self.harvester._meta.fields):
			print 'Warning: number of columns defined in harvester exceeds the number of columns in the file.'
		elif len(row) > len(self.harvester._meta.fields):
			print 'Warning: %s trailing columns will be ignored.' % (len(row) - len(self.harvester._meta.fields))
		self._row_count_validated = True

# A dictionary wrapper that allows values to be accessed as attributes, rather
# than items; i.e. opts.key instead of opts[key].
class Options(dict):
	# Initialise the dictionary using the properties of a class passed as "init",
	# used to initialise the _meta Options object using the Meta class definition.
	def __init__(self, init=None):
		super(Options, self).__init__()
		# Initialise default attributes
		self.process_first = []
		self.process_last = []
		self.default_filters = []
		self.default_column_filters = {}
		# Load attributes from the Meta object
		if init:
			for key, value in init.__dict__.items():
				if not key.startswith('__'):
					self[key] = value
	
	def __getattr__(self, item):
		return self[item] if item in self else None
	
	def __setattr__(self, item, value):
		self[item] = value

# A metaclass used by all Harvesters to track the order of the columns
class HarvesterBase(type):
	def __new__(cls, name, bases, attrs):
		# Save the Meta for later
		meta = attrs.pop('Meta', None)
		# Check that a model has been specified
		if attrs['__module__'] != __name__ and (not meta or not hasattr(meta, 'model')):
			raise ConfigurationError('No model defined for harvester %s.' % name)
		# Create the new class
		klass = super(HarvesterBase, cls).__new__(cls, name, bases, attrs)
		# Load the options from Meta into the "_meta" attribute of the new class
		klass._meta = Options(meta)
		fields = []
		for key, value in attrs.items():
			if isinstance(value, Column):
				# Column definition validation:
				# For columns that are fields, make sure the field is defined
				# in the model definition
#				if isinstance(value, Field):
#					if not [f for f in klass._meta.model._meta.fields if f.name == key]:
#						raise ConfigurationError('The model %s does not have a field named %s, which was defined in the harvester.' % (klass._meta.model.__name__, key))
				value.name = key
				# Get the index the field needs to have in the fields array
				# to maintain the order by creation_counter
				idx = bisect(fields, value)
				# Handle fields that span more than one column by filling the
				# spanned columns except the last one with reference fields.
				# The last column in the span will contain the actual field
				# and will receive a list of all values in the span
				for col in range(1, value.colspan):
					fields.insert(idx, AutoReference(value, col))
					idx += 1
				# Insert the field into its spot in the list
				fields.insert(idx, value)
		klass._meta.raw_fields = fields
		# A convenience attribute for quick name-to-field lookups
		klass._meta.fields = dict([(f.name, f) for f in fields])
		# This will be populated with the actual values read from the file
		klass._meta.data = {}
		# This will contain the column titles, if available
		klass._meta.labels = []
		return klass

class Harvester(object):
	__metaclass__ = HarvesterBase
	
	def __init__(self):
		# Initialise the row processing order based on the process_first/last
		# meta attributes
		insert_point = 0
		self._meta.processing_order = []
		# Load the indices of the process_first fields into the order array
		for name in self._meta.process_first:
			# Check if the field exists in the harvester definition
			if name not in self._meta.fields:
				raise ConfigurationError('The field "%s" referred to in "process_first" is undefined.' % name)
			self._meta.processing_order.append(self._meta.raw_fields.index(self._meta.fields[name]))
		# Append the indices of the process_last fields into the order array,
		# keeping track of how many were inserted using "insert_point"
		for name in self._meta.process_last:
			# Check if the field exists in the harvester definition
			if name not in self._meta.fields:
				raise ConfigurationError('The field "%s" referred to in "process_last" is undefined.' % name)
			self._meta.processing_order.append(self._meta.raw_fields.index(self._meta.fields[name]))
			insert_point -= 1
		# Now insert all the remaining field indices between the process first
		# and last indices
		for index, field in enumerate(self._meta.raw_fields):
			if field.name not in self._meta.process_first + self._meta.process_last:
				if insert_point < 0:
					self._meta.processing_order.insert(insert_point, index)
				else:
					# No process_last fields given, append to the end
					self._meta.processing_order.append(index)
		self._meta.main_models = []
		self._meta.referred_models = []
		self._meta.referring_models = []
	
	def __getattribute__(self, item):
		_meta = object.__getattribute__(self, '_meta')
		if item in _meta.fields:
			if item in _meta.data:
				return _meta.data[item]
			else:
				raise PrematureAccessError(item)
		else:
			return object.__getattribute__(self, item)

	def __setattr__(self, item, value):
		if item in self._meta.fields:
			self._meta.data[item] = value
		else:
			super(Harvester, self).__setattr__(item, value)
	
	def _apply_filter(self, filters, data):
		if filters:
			if isinstance(filters, collections.Callable):
				return filters(data)
			if hasattr(filters, '__iter__'):
				for fltr in filters:
					data = fltr(data)
			else:
				raise TypeError('Invalid filter specified. Expected iterable or callable but got %s.', type(filters))
		return data
	
	def _apply_default_filters(self, field, data):
		if field.filters:
			return self._apply_filter(field.filters, data)
		fieldtype_filters = self._meta.default_column_filters.get(field.__class__)
		if fieldtype_filters:
			return self._apply_filter(fieldtype_filters, data)
		return self._apply_filter(self._meta.default_filter, data)
	
	def parse(self, row):
		# Clear the data from the last parsed row
		self._meta.data = {}
		
		# call the filters for all fields
		for index in self._meta.processing_order:
			if index < len(row) and index < len(self._meta.raw_fields):
				field = self._meta.raw_fields[index]
				data = row[index]
				# Call the default filters for the field and any defined custom
				# clean functions in order defined by the "defaults" argument
				if field.defaults == DEFAULTS_FIRST:
					data = self._apply_default_filters(field, data)
				if hasattr(self, 'clean_%s_column' % field.name):
					data = getattr(self, 'clean_%s_column' % field.name)(data)
				if field.defaults == DEFAULTS_LAST:
					data = self._apply_default_filters(field, data)
				# Final field validation
				data = field.clean(data)
				# For foreign keys, first check referred models to see if it
				# has already been created
				if isinstance(field, ForeignKey):
					already_created = [mdl for mdl in self._meta.referred_models if field.match(mdl, data)]
					if already_created:
						data = already_created[0]
					else:
						data = field.create(data)
						self._meta.referred_models.append(data)
				self._meta.data[field.name] = data
		self.final_clean()
		#make a model with the attributes in data
		model = self._meta.model()
		for field in self._meta.raw_fields:
			if isinstance(field, Field):
				if not [f for f in model._meta.fields if f.name == field.name]:
					raise ConfigurationError('The model %s does not have a field named %s, which was defined in the harvester.' % (model._meta, field.name))
				setattr(model, field.name, self._meta.data[field.name])
		self._meta.main_models.append((model, self._meta.data.copy())) #fugly hack to get the post-save data in
	
	def save(self):
		for model in self._meta.referred_models:
			if not getattr(model, '_do_not_save', False):
				model.save()
		for (model, data) in self._meta.main_models:
			# Temporary hacks to make ArtsNSW work
			if hasattr(model, 'lga'):
				model.lga = model.lga
			if hasattr(model, 'information_source'):
				model.information_source = 0
			try:
				model.save()
			except Exception as e:
				import pdb; pdb.set_trace()
				
			if data.has_key('activities'):
				for a in data['activities']:
					model.activities.add(a)
					
			if data.has_key('access_features'):
				for a in data['access_features']:
					model.access_features.add(a)

	
	# This can be overriden to implement multi-column validation once all
	# column values have been loaded
	def final_clean(self):
		pass

"""
The idea is that field.clean() is mostly for validation, and making sure that it's
actually possible to assign the value to the field. The clean_field_column()
function is generally for handling special cases. Then there's the filter hierarchy,
which goes like default_filters < default_column_filters < column(filters=[]), which
would handle the more generic characteristics of the source data.
"""