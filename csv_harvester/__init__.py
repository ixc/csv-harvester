import bisect
import collections
import csv
import operator
import pprint
import warnings

from . import columns, constants
from .constants import ConfigurationError, ValidationError
from .utils import odict, ClassDict, CSVReader


class Processor(object):
	harvester = None
	encoding = 'utf-8'
	tab_separated = False
	row_offset = 0
	column_offset = 0
	rows_to_read = None
	ignore_errors = False
	
	def __init__(self):
		self._harvesters = []
		if not self.harvester:
			raise ConfigurationError('No harvester specified for processor %s.' % self.__class__.__name__)

	def load(self, filename, **kwargs):
		"""
		
		"""
		params = {
			'encoding': self.encoding,
			'dialect': csv.excel_tab if self.tab_separated else csv.excel,
		}
		params.update(kwargs)
		with CSVReader(filename, **params) as reader:
			# Skip lines based on the row offset specified
			[reader.next() for i in range(self.row_offset)]
			# Read the rows
			rows_read = 0
			rows_parsed = 0
			for row in reader:
				try:
					parsed = self.harvester(row[self.column_offset:])
					self._harvesters += [parsed]
					rows_parsed += 1
				except ValidationError, e:
					if not self.ignore_errors:
						raise
					warnings.warn(e.message)
				rows_read += 1
				if self.rows_to_read and rows_parsed >= self.rows_to_read:
					break
			print '%s of %s rows parsed.' % (rows_parsed, rows_read)
	
	def save(self):
		for harvester in self._harvesters:
			harvester.save()


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
		klass._meta = ClassDict(meta, defaults={
			'default_filters': [],
			'default_column_filters': {},
		})
		fields = []
		for key, value in attrs.items():
			if isinstance(value, columns.Field):
				value.name = key
				value.instance = klass
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
			if field.target:
				if field.target in self._meta.fields:
					self._meta.fields[field.target].add_referrer(field_name)
				else:
					raise ConfigurationError(
						'%s.%s references non-existent field "%s".' % (
							type(self).__name__, field_name, field.target, 
					))
			# Check that model fields exist on the model. Checking if the model
			# class or instance has that attribute, rather than via ._meta, to
			# avoid a hard dependency with Django.
			if field.in_model \
			and 'model' in self._meta \
			and not (hasattr(self._meta.model, field_name)
			or hasattr(self._meta.model(), field_name)):
				raise ConfigurationError(
					'The model %s does not have an attribute named %s, which '
					'was defined in the %s harvester.' % (
						self._meta.model, field.name, type(self).__name__,
				))
		

class Harvester(object):
	"""
	Subclass this class to define the data structure of a CSV file. Any 
	attributes of type :class:`columns.Field` are treated as definitions of
	the CSV columns in the order they are defined.
	
	You can also specify a ``class Meta:`` attribute, which in turn can contain
	the following attributes:
	
		**model**: the Django model or similar object to load the data into.
	"""
	
	__metaclass__ = HarvesterBase
	
	def __init__(self, data):
		"""
		:param data: iterable of data, usually the row read from the CSV file
		"""
		# Validate the number of columns in data against the number of fields
		# expected by this harvester and warn as necessary
		count_difference = len(data) - reduce(
			operator.add,
			[f.colspan for f in self._meta.fields.values() if f.in_file]
		)
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
		
		# Parse the provided data and load into the raw data store
		row = data.__iter__()
		for field_name, field in self._meta.fields.items():
			if not field.in_file:
				continue
			# Raw data store values are always lists for consistency across
			# single- and multi- column fields
			if field_name not in self._data.raw:
				self._data.raw[field_name] = []
			# The value will be modified below via append() calls, so the value
			# inside the dictionary will be modified by reference
			value = self._data.raw[field_name]
			for i in range(field.colspan):
				try:
					value.append(row.next())
				# If we run out of columns, pad the rest with Nones
				except StopIteration:
					value.append(None)
			# If the field has a target field, append the values to that field
			# as well
			if field.target:
				if field.target not in self._data.raw:
					self._data.raw[field.target] = []
				self._data.raw[field.target].extend(value)
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
						_meta.fields[item], _data.raw.get(item, [None]))
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
		
		:param field: A Field instance representing the field being parsed.
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
		if hasattr(self, 'clean_%s_field' % field.name):
			value = getattr(self, 'clean_%s_field' % field.name)(value)
		if field.defaults == constants.DEFAULTS_LAST:
			value = self._apply_default_filters(field, value)
		# Apply the column type validation, which is usually type conversion
		value = field.clean(value)
		return value
	
	def save(self):
		# Can't save without a model
		if 'model' not in self._meta:
			raise ConfigurationError(
				'No model defined for harvester %s.' % type(self).__name__
			)
		model = self._meta.model()
		for name, field in self._meta.fields.items():
			if field.in_model:
				if isinstance(field, columns.ForeignKey):
					setattr(model, name, field.lookup(getattr(self, name)))
				else:
					setattr(model, name, getattr(self, name))
		model.save()
		# Now that we have a PK, we can save the M2Ms and inlines
		self.save_m2m(model)
		self.save_inlines(model)
		return model
	
	def save_m2m(self, model):
		"""
		:param model: A model instance to which to .add() the M2Ms.
		"""
		for field_name, field in self._meta.fields.items():
			if not isinstance(field, columns.ManyToManyField):
				continue
			for value in getattr(self, field_name):
				related_object = field.lookup(value)
				if related_object:
					if hasattr(related_object, '__iter__'):
						getattr(model, field_name).add(*related_object)
					else:
						getattr(model, field_name).add(related_object)
	
	def save_inlines(self, model):
		"""
		  :param model: A model instance to which to associate the inlines with.
		  """
		for field_name, field in self._meta.fields.items():
			if not isinstance(field, columns.InlineField):
				continue
			for value in getattr(self, field_name):
				for related_object in field.lookup(value):
					setattr(related_object, field.fk_name, model)
					related_object.save()
	
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