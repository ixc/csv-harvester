# Static variables for defining the order of applying default filters to a field
# in relation to any custom ones defined.
DEFAULTS_LAST = 0
DEFAULTS_FIRST = 1
DEFAULTS_IGNORE = 2

class ValidationError(ValueError):
    pass

class ConfigurationError(ValueError):
    pass

class ColumnCountMismatch(RuntimeWarning):
    pass