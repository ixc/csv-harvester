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
    def __init__(self, message, *args, **kwargs):
        """
        Python refuses to print exception messages if they contin non-ASCII
        characters, but if we encode them to UTF-8 it will, and most terminals
        will display them correctly.
        """
        if isinstance(message, unicode):
            message = message.encode('utf-8')
        super(ValidationError, self).__init__(message, *args, **kwargs)

class ConfigurationError(ValueError):
    pass

class ColumnCountMismatch(RuntimeWarning):
    pass