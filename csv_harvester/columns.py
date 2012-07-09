import decimal

from . import constants


class Field(object):
	creation_counter = 0
	
	def __init__(self, colspan=1, default=None, blank=True,
			target=None, in_file=True, in_model=True,
			defaults=constants.DEFAULTS_FIRST, filters=[]):
		"""
		:param colspan: the number of columns in the file used for the
			definition of this field. If more than one, the clean functions
			will receive a list. Has no effect if ``in_file=False``.
		:param default: the default value for the field if read column is
			empty.
		:param blank: specifies whether to throw a validation error if the
			column contains no data. The validation will fail even if a default
			value has been provided.
		:param target: the name of the field to pass the value from this column
			to. The target field will receive a list of values from all the
			fields that specify it as a target, just as a field with a
			colspan larger than 1 would. Implies ``in_model=False``.
		:param in_file: specifies whether this field is a column in the file
			being read.
		:param in_model: specifies whether a field with this name exists in the
			model associated with the harvester. If true, the value is
			automatically written into in on save().
		:type colspan: integer
		:type blank: boolean
		:type target: string
		:type in_file: boolean
		:type in_model: boolean
		"""
		# Store the creation index and increment the global counter
		self.creation_counter = Field.creation_counter
		Field.creation_counter += 1
		# Initialise properties
		self.name = None
		self.instance = None
		self.referenced_by = set()

		self.colspan = colspan
		self.default = default
		self.blank = blank
		self.target = target
		self.in_file = in_file
		self.in_model = False if target else in_model
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
		columns = self.colspan if self.in_file else 1
		return len(self.referenced_by) + columns == 1
	
	def add_referrer(self, referrer):
		self.referenced_by.add(referrer)
	
	def clean(self, data):
		if data is None and not self.blank:
			raise constants.ValidationError(
				u'Blank value in non-blank field %s.' % self)
		elif data is None:
			data = self.default		
		return data


class Ignore(Field):
	"""
	A convenience class for columns whose contents will be thrown away.
	"""
	
	def __init__(self, **kwargs):
		kwargs.pop('in_file')
		kwargs.pop('in_model')
		kwargs.pop('target')
		super(Ignore, self).__init__(
			in_file=True, in_model=False, target=None, **kwargs)
	
	def clean(self, data):
		return None


# TEXT FIELDS

class TextField(Field):
	"""
	No need for a separate CharField, since there's no real difference. An
	optional ``max_length`` argument can be provided to TextFields.
	"""
	
	def __init__(self, max_length=None, **kwargs):
		self.max_length = max_length
		if 'default' not in kwargs:
			kwargs['default'] = u''
		super(TextField, self).__init__(**kwargs)
	
	def clean(self, data):
		if not data:
			data = None
		elif self.max_length is not None and len(data) > self.max_length:
			raise constants.ValidationError(
				u'Value "%s..." exceeds the max_length of %s for field %s.'
				% (data[:min(self.max_length, 30)], self.max_length, self))
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

class ManyToManyField(Field):
	"""
	When specifying a clean_*_field method, keep in mind that the final value
	after cleaning is expected to be an iterable of values.
	"""
	
	def __init__(self, model, lookup='title', **kwargs):
		"""
		:param model: the related model class.
		:param lookup: for simple Django models, is the field name on which a
			a get_or_create call will be matched. If using a more complex
			lookup, a callable that takes a value and returns an instance of
			model matching it should be used.
		"""
		self.model = model
		self._lookup = lookup
		if 'default' not in kwargs:
			kwargs['default'] = []
		super(ManyToManyField, self).__init__(**kwargs)
	
	def lookup(self, value):
		"""
		Converts the given value into an instance of self.model. If the field
		was initialised with a callable ``lookup`` argument, returns the result
		of calling it with the provided value.
		"""
		if callable(self._lookup):
			return self._lookup(value)
		else:
			return self.model.objects.get_or_create(
				**{self._lookup: value}
			)[1]
	
	def clean(self, data):
		# Just in case we didn't receive an iterable
		if not hasattr(data, '__iter__') or isinstance(data, basestring):
			data = [data]
		# Filter out blank values, and set to None if none are left, so that
		# the regular Field logic on blank and default values can kick in
		data = filter(bool, data) or None
		return super(ManyToManyField, self).clean(data)
