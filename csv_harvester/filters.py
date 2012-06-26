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

# A function caller that calls the given function with the arguments specified
# and the data to parse as either the first argument, or as the argument defined
# by an "attr_index" keyword argument
def function(func, *args, **kwargs):
	def funcaller(value):
		idx = kwargs.pop('attr_index', 0)
		if isinstance(idx, int):
			lst = list(args)
			lst.insert(idx, value)
			args = tuple(lst)
		elif isinstance(idx, str):
			kwargs[idx] = value
		else:
			raise AttributeError('The "attr_index" argument must be either an integer or string; was %s.' % type(idx))
		return func(*args, **kwargs)
	return funcaller