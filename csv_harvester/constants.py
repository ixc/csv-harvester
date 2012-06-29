# Static variables for defining the order of applying default filters to a field
# in relation to any custom ones defined.
DEFAULTS_LAST = 0
DEFAULTS_FIRST = 1
DEFAULTS_IGNORE = 2

# Used for decyphering boolean columns
TRUE_VALUES = ('y', 'yes', 't', 'true', '1')
FALSE_VALUES = ('n', 'no', 'f', 'false', '0')
NULL_VALUES = (
    'na', 'nil', 'not applicable', 'not available', 'information unavailable',
    'information not available', 'unknown', 'don\'t know', '-', '',
)

class ValidationError(ValueError):
    pass

class ConfigurationError(ValueError):
    pass

class ColumnCountMismatch(RuntimeWarning):
    pass