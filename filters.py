import collections

# Strip leading and trailing whitespace characters
def strip(value, chars=None):
	if hasattr(value, 'strip') and isinstance(value.strip, collections.Callable):
		return value.strip(chars)
	return value

# Strip the characters given
def stripchars(chars):
	def stripper(value):
		return strip(value, chars)
	return stripper

# A generic method caller, will raise AttributeError if method not found
def method(name, *args, **kwargs):
	def methodcaller(value):
		return getattr(value, name)(*args, **kwargs)
	return methodcaller