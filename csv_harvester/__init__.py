import bisect
import collections
import csv
import pprint
import warnings

# Try to find an available ordered dictionary implementation
try:
	from collections import OrderedDict as odict
except ImportError:
	try:
		from django.utils.datastructures import SortedDict as odict
	except ImportError:
		try:
			from ordereddict import OrderedDict as odict
		except ImportError:
			raise ImportError(
				'Either Python 2.7, Django, or ordereddict required')
	

from . import columns, constants
from .constants import ConfigurationError, ValidationError


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
			self.harvester.parse(row[self.start_column - 1:])
			self._rows_parsed += 1
			if self.rows_to_read and self._rows_parsed >= self.rows_to_read:
				break
		print '%s rows parsed.' % self._rows_parsed
	
	def save(self):
		self.harvester.save()


class ClassDict(dict):
	"""
	A dictionary wrapper that allows values to be accessed as attributes,
	rather than items; i.e. opts.key instead of opts[key]. Can be initialised
	by passing in a class definition.
	"""
	
	def __init__(self, init=None):
		"""
		:param init: a class whose attributes will be used to populate the
			dictionary. Usually the "Meta" class from a Harvester.
		"""
		super(ClassDict, self).__init__()
		# Initialise default attributes
		self.default_filters = []
		self.default_column_filters = {}
		# Load attributes from the provided class definition
		if init:
			for key, value in init.__dict__.items():
				if not key.startswith('__'):
					self[key] = value
	
	def __getattr__(self, item):
		return self[item] if item in self else None
	
	def __setattr__(self, item, value):
		self[item] = value


class HarvesterBase(type):
	"""
	The metaclass used by Harvester classes to track the order of the field
	definition and to populate/validate the ClassDict object in _meta.
	"""
	
	def __new__(cls, name, bases, attrs):
		# Save the Meta for later
		meta = attrs.pop('Meta', None)
		# Create the new class
		klass = super(HarvesterBase, cls).__new__(cls, name, bases, attrs)
		# Load the options from Meta into the "_meta" attribute of the new class
		klass._meta = ClassDict(meta)
		fields = []
		for key, value in attrs.items():
			if isinstance(value, columns.Column):
				value.name = key
				# Get the index the field needs to have in the fields array
				# to maintain the order by creation_counter
				idx = bisect.bisect(fields, value)
				# Insert the field into its spot in the list
				fields.insert(idx, value)
		klass._meta.fields = odict((f.name, f) for f in fields)
		# If it's not the Harvester class defined below, validate it
		if attrs['__module__'] != __name__:
			klass._validate()
		return klass
	
	def _validate(self):
		"""
		Gets called at class definition time, throws ConfigurationErrors if a
		Harvester subclass has been poorly defined.
		"""
		for field_name, field in self._meta.fields.items():
			# Check that the fields referenced by other fields actually exist,
			# and populate their referenced_by attribute if they do
			if isinstance(field, columns.Reference):
				if field.to_name in self._meta.fields:
					self._meta.fields[field.to_name].referenced_by.add(field_name)
				else:
					raise ConfigurationError(
						'The field %s in harvester %s references non-existent '
						'field %s.' % (
							field_name, type(self).__name__, field.to_name, 
					))
			# Check that model fields exist on the model. Checking if the model
			# has that attribute, rather than ._meta.get_all_field_names(), to
			# avoid a hard dependency with Django
			if isinstance(field, columns.Field) \
			and 'model' in self._meta \
			and not hasattr(self._meta.model, field_name):
				raise ConfigurationError(
					'The model %s does not have an attribute named %s, which '
					'was defined in the %s harvester.' % (
						self._meta.model, field.name, type(self).__name__,
				))
		

class Harvester(object):
	__metaclass__ = HarvesterBase
	
	def __init__(self, data):
		"""
		:param data: iterable of data, usually the row read from the CSV file
		"""
		# Validate the number of columns in data against the number of fields
		# expected by this harvester and warn as necessary
		count_difference = len(data) - len(self._meta.fields)
		if count_difference < 0:
			warnings.warn(
				'Number of columns defined in harvester exceeds the number of '
				'columns in the file.',
				constants.ColumnCountMismatch,
			)
		elif count_difference > 0:
			warnings.warn(
				'%s trailing columns will be ignored.' % count_difference,
				constants.ColumnCountMismatch,
			)
		
		# Initialise the data store
		self._data = ClassDict()
		self._data.raw = {}
		self._data.clean = {}
		
		self._data.main_models = []
		self._data.referred_models = []
		self._data.referring_models = []
		
		# Parse the provided data and load into the raw data store
		row = data.__iter__()
		for field_name, field in self._meta.fields.items():
			if isinstance(field, columns.Reference):
				destination = field.to_name
			else:
				destination = field_name
			# Raw data store values are always lists for consistency across
			# single- and multi- column fields
			if destination not in self._data.raw:
				self._data.raw[destination] = []
			# The value will be modified below via append() calls, so the value
			# inside the dictionary will be modified by reference
			value = self._data.raw[destination]
			for i in range(field.colspan):
				try:
					value.append(row.next())
				# If we run out of columns, pad the rest with Nones
				except StopIteration:
					value.append(None)
		# Access all the fields to trigger parsing/validation
		for field_name in self._meta.fields.keys():
			getattr(self, field_name)
		self.final_clean()
	
	def __getattribute__(self, item):
		"""
		When accessing a field attribute, return the data in that field,
		parsing it if necessary.
		"""
		_meta = object.__getattribute__(self, '_meta')
		if item in _meta.fields:
			_data = object.__getattribute__(self, '_data')
			# Check if the field has already been parsed
			if item not in _data.clean:
				try:
					_data.clean[item] = self._parse_field(
						_meta.fields[item], _data.raw[item])
				except RuntimeError, e:
					# Check for a cyclical dependency between fields
					if 'recursion' in e.message:
						raise ConfigurationError(
							'A cyclical dependency was encountered in '
							'harvester %s triggered by field %s' % (
								type(self).__name__, item
						))
					raise
			return _data.clean[item]
		else:
			# Not a field, get attribute in the usual way
			return object.__getattribute__(self, item)

	def __setattr__(self, item, value):
		if item in self._meta.fields:
			self._data.clean[item] = value
		else:
			super(Harvester, self).__setattr__(item, value)
	
	def __unicode__(self):
		"""
		A pretty-formatted dictionary of all the data for this instance.
		"""
		return pprint.pformat(dict(
			(f, getattr(self, f)) for f in self._meta.fields.keys()
		))
	
	def _apply_filter(self, filters, data):
		if filters:
			if isinstance(filters, collections.Callable):
				return filters(data)
			if hasattr(filters, '__iter__'):
				for fltr in filters:
					data = fltr(data)
			else:
				raise TypeError(
					'Invalid filter specified. Expected iterable or callable '
					'but got %s.' % type(filters))
		return data
	
	def _apply_default_filters(self, field, data):
		if field.filters:
			return self._apply_filter(field.filters, data)
		fieldtype_filters = self._meta.default_column_filters.get(field.__class__)
		if fieldtype_filters:
			return self._apply_filter(fieldtype_filters, data)
		return self._apply_filter(self._meta.default_filter, data)
	
	def _parse_field(self, field, values):
		"""
		Parse the data for the provided field using whatever validation, clean
		methods, and filters have been defined for that field.
		
		:param field: A Column instance representing the field being parsed.
		:param values: A list of values to be stored in that field. Values for
			single-column fields should contain only one item.
		:returns: The validated and cleaned value for the field, the type of
			which depends on the type of the field.
		"""
		value = values[0] if field.single_column() else values[:]
		# Call the default filters for the field and any defined custom
		# clean functions in order defined by the "defaults" argument
		if field.defaults == constants.DEFAULTS_FIRST:
			value = self._apply_default_filters(field, value)
		if hasattr(self, 'clean_%s_column' % field.name):
			value = getattr(self, 'clean_%s_column' % field.name)(value)
		if field.defaults == constants.DEFAULTS_LAST:
			value = self._apply_default_filters(field, value)
		# Apply the column type validation, which is usually type conversion
		value = field.clean(value)
		return value
	
	def save(self):
		raise NotImplementedError()

	def final_clean(self):
		"""
		This method can be overriden to implement cross-field validation once
		all the individual fields have been validated.
		"""
		pass

"""
The idea is that field.clean() is mostly for validation, and making sure that it's
actually possible to assign the value to the field. The clean_field_column()
function is generally for handling special cases. Then there's the filter hierarchy,
which goes like default_filters < default_column_filters < column(filters=[]), which
would handle the more generic characteristics of the source data.
"""