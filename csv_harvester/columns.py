from decimal import Decimal

from .constants import ValidationError, DEFAULTS_FIRST


class Column(object):
	creation_counter = 0
	
	def __init__(self, colspan=1, default=None, defaults=DEFAULTS_FIRST, filters=[], **kwargs):
		# Store the creation index and increment the global counter
		self.creation_counter = Column.creation_counter
		Column.creation_counter += 1
		# Initialise properties
		self.name = None
		self.colspan = colspan
		self.default = default
		self.defaults = defaults
		self.filters = filters
	
	def __cmp__(self, other):
		# This specifies that fields should be compared based on their creation
		# counters, allowing sorted lists to be built using bisect.
		return cmp(self.creation_counter, other.creation_counter)
	
	def clean(self, data):
		return data

# An ignored column
class Ignore(Column):
	pass

# A Reference column is initialised with the name of a column it will be
# contributing to, allowing non-sequential multi-column columns to be
# defined in the Harvester declaration. The actual column must be defined
# last and will receive all values from the Reference column referring to it.
class Reference(Column):
	def __init__(self, to, *args, **kwargs):
		super(Reference, self).__init__(*args, **kwargs)
		self.to_name = to

#GT: No idea how this is supposed to work but here's a guess that makes ArtsNSW work
class MultiColumn(Column):
    pass

# AutoReference columns are created automatically when multi-column columns
# are encountered. Their creation_couter is a float, placing them between
# the previous column and the final column that will receive the values from
# all preceding AutoReference columns.
class AutoReference(Column):
	def __init__(self, val, col):
		self.creation_counter = val.creation_counter + float(col)/val.colspan - 1
		self.to_name = val.name

# A field that does not exist in the model, but should store the value
# nonetheless, allowing it to be used in the logic
class VirtualField(Column):
	pass

# A superclass for all columns that correspond to a field on the model
class Field(Column):
	pass

class CharField(Field):
	def __init__(self, max_length=None, blank=False, **kwargs):
		self.max_length = max_length
		if 'null' not in kwargs:
			kwargs['null'] = blank
		super(CharField, self).__init__(**kwargs)
	
	def clean(self, data):
		if self.max_length and len(data) > self.max_length:
			raise ValidationError('The value in column %s, with a length of %s, exceeds maximum allowed length of %s.\nThe value was: %s' %
								  (self.name, len(data), self.max_length, data))
		return data

class TextField(Field):
	pass

class EmailField(CharField):
	pass

class URLField(CharField):
	pass

class IntegerField(Field):
	pass

class DecimanField(Field):
	def clean(self, data):
		return Decimal(data)

class FloatField(Field):
	def clean(self, data):
		if data in [None, '']:
			return None
		return float(data)

class BooleanField(Field):
	def __init__(self, true_values=['y', 'yes', 't', 'true', '1'], false_values=['n', 'no', 'f', 'false', '0'], null_values=['na', 'nil', 'not applicable', 'not available', 'information not available', 'information unavailable', 'unknown', 'don\'t know', '-', '',], **kwargs):
		self.true_values = true_values
		self.false_values = false_values
		self.null_values = null_values
		super(BooleanField, self).__init__(**kwargs)
		
	def clean(self, data):
		if isinstance(data, str):
			if data.lower() in self.true_values:
				return True
			elif data.lower() in self.false_values:
				return False
			elif data.lower() == '':
				return self.default
		
		raise ValidationError('The value in column %s could not be evaluated to boolean. The value was: \'%s\'' % (self.name, data))

class NullBooleanField(BooleanField):
	def __init__(self, **kwargs):
		kwargs['null'] = True
		super(NullBooleanField, self).__init__( **kwargs)

	def clean(self, data):
		if isinstance(data, str):
			if data.lower() in self.true_values:
				return True
			elif data.lower() in self.false_values:
				return False
			elif data.lower() in self.null_values:
				return None
		
		raise ValidationError('The value in column %s could not be evaluated to boolean (or None). The value was: \'%s\'' % (self.name, data))	


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