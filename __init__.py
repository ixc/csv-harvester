# Static variables for defining the order of applying default filters to a field
# in relation to any custom ones defined.
DEFAULTS_LAST = 0
DEFAULTS_FIRST = 1
DEFAULTS_IGNORE = 2

class PrematureAccessError(IndexError):
	def __init__(self, field):
		self._field = field
	def __str__(self):
		return 'The field "%s" was accessed before it was loaded.' % self._field

class ValidationError(ValueError):
	pass

class ConfigurationError(ValueError):
	pass