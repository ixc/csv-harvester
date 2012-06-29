import decimal

from . import constants


class Column(object):
	creation_counter = 0
	
	def __init__(self, colspan=1, default=None, blank=True,
			defaults=constants.DEFAULTS_FIRST, filters=[]):
		# Store the creation index and increment the global counter
		self.creation_counter = Column.creation_counter
		Column.creation_counter += colspan
		# Initialise properties
		self.name = None
		self.instance = None
		self.referenced_by = set()

		self.colspan = colspan
		self.default = default
		self.blank = blank
		self.defaults = defaults
		self.filters = filters
	
	def __cmp__(self, other):
		"""
		Compare columns using their creation counters, allowing them to be
		sorted in declaration order.
		"""
		return cmp(self.creation_counter, other.creation_counter)
	
	def __unicode__(self):
		if self.instance is None:
			return '<Unbound %s column>' % type(self).__name__
		return '<Bound %s on %s.%s>' % (
			type(self).__name__, self.instance.__name__, self.name)
	
	def single_column(self):
		return len(self.referenced_by) == 0
	
	def clean(self, data):
		if data is None:
			data = self.default
		if data is None and not self.blank:
			raise constants.ValidationError(
				u'Blank value in non-blank field %s.' % self)
		return data

# An ignored column
class Ignore(Column):
	pass

class Reference(Column):
	"""
	A Reference column is initialised with the name of a column it will be
	contributing to, allowing non-sequential multi-column columns to be
	defined in the Harvester declaration. The actual column must be defined
	last and will receive all values from the Reference column referring to it.
	"""
	
	def __init__(self, to, *args, **kwargs):
		super(Reference, self).__init__(*args, **kwargs)
		self.to_name = to

#GT: No idea how this is supposed to work but here's a guess that makes ArtsNSW work
class MultiColumn(Column):
    pass

class VirtualField(Column):
	"""
	A field that does not exist in the model, but should store the value
	nonetheless, allowing it to be used in the logic.
	"""
	pass

class Field(Column):
	"""
	A superclass for all columns that correspond to a field on the model.
	"""
	pass


# TEXT FIELDS

class TextField(Field):
	"""
	No need for a separate CharField, since there's no real difference. An
	optional ``max_length`` argument can be provided to TextFields.
	"""
	
	def __init__(self, max_length=None, **kwargs):
		self.max_length = max_length
		super(TextField, self).__init__(**kwargs)
	
	def clean(self, data):
		data = unicode(data)
		if self.max_length is not None and len(data) > self.max_length:
			raise constants.ValidationError(
				u'Value "%s" exceeds the max_length of %s for field %s.'
				% (data, self.max_length, self))
		return super(TextField, self).clean(data)

# TODO: Text pattern matching fields, e.g. EmailField, URLField


# NUMERIC FIELDS

class _NumericField(Field):
	"""
	Do not use directly. Inherit and specify a ``datatype`` argument, which
	should be a :class:`type` object.
	"""
	
	def clean(self, data):
		try:
			data = self.datatype(data)
		except (ValueError, TypeError, decimal.InvalidOperation):
			# For empty (or otherwise False) strings, pass it up for checking
			# against the blank and default parameters.
			if not data:
				data = None
			else:
				raise constants.ValidationError(
					u'Value "%s" could not be converted to %s for field %s.'
					% (data, self.datatype.__name__, self))
		return super(_NumericField, self).clean(data)

class IntegerField(_NumericField):
	datatype = int

class FloatField(_NumericField):
	datatype = float

class DecimalField(_NumericField):
	datatype = decimal.Decimal


# OTHER DATA TYPES

class BooleanField(Field):
	"""
	No need for separate NullBooleanField, the ``blank`` argument can be used
	when initialising instead.
	"""
	
	def __init__(self,
			true_values=constants.TRUE_VALUES,
			false_values=constants.FALSE_VALUES,
			null_values=constants.NULL_VALUES,
			case_sensitive=False,
			**kwargs):
		self.true_values = true_values
		self.false_values = false_values
		self.null_values = null_values
		self.case_sensitive = case_sensitive
		super(BooleanField, self).__init__(**kwargs)
		
	def clean(self, data):
		value = unicode(data)
		if not self.case_sensitive:
			value = data.lower()
		if value in self.true_values:
			return True
		elif value in self.false_values:
			return False
		elif value in self.null_values:
			return super(BooleanField, self).clean(data)
		# If the value is not explicitly recognised as a true or false value,
		# make no assumptions, refuse to validate
		raise constants.ValidationError(
			u'Value "%s" could not be converted to a boolean for field %s.'
			% (data, self))


# RELATIONAL FIELDS

class ForeignKey(Field):
	def __init__(self, model, unique_field, *args, **kwargs):
		self._model = model
		self._unique_field = unique_field
		super(ForeignKey, self).__init__(*args, **kwargs)
	
	def match(self, model, data):
		#if hasattr(data, '__iter__'): # Multi-column; not implemented yet
		return getattr(model, self._unique_field) == data
	
	def create(self, data):
		#if hasattr(data, '__iter__'): # Multi-column; not implemented yet
		# First, check the database
		try:
			model = self._model.objects.get(**{self._unique_field: data})
			model._do_not_save = True
		except self._model.DoesNotExist:
			model = self._model()
			setattr(model, self._unique_field, data)
		return model
