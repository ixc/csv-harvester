import csv

# Try to find an available ordered dictionary implementation
try:
    from collections import OrderedDict as odict
except ImportError:
    try:
        from django.utils.datastructures import SortedDict as odict
    except ImportError:
        try:
            from ordereddict import OrderedDict as odict
        except ImportError:
            raise ImportError(
                'Either Python 2.7, Django, or ordereddict required')


class ClassDict(dict):
    """
    A dictionary wrapper that allows values to be accessed as attributes,
    rather than items; i.e. opts.key instead of opts[key]. Can be initialised
    by passing in a class definition.
    """
    
    def __init__(self, init=None, defaults={}):
        """
        :param init: a class whose attributes will be used to populate the
            dictionary. Usually the "Meta" class from a Harvester.
        :param defaults: the default data dictionary to start off with.
        """
        super(ClassDict, self).__init__()
        self.update(defaults)
        # Load attributes from the provided class definition
        if init:
            for key, value in init.__dict__.items():
                if not key.startswith('__'):
                    self[key] = value
    
    def __getattr__(self, item):
        return self[item] if item in self else None
    
    def __setattr__(self, item, value):
        self[item] = value


class UTF8Recoder(object):
    def __init__(self, source, encoding):
        self._source = source
        self._encoding = encoding
    def __iter__(self):
        return self
    def next(self):
        return self._source.next().decode(self._encoding).encode('utf-8')

class CSVReader(object):
    """
    An encoding-aware CSV reader.
    """

    def __init__(self, filename, **params):
        encoding = params.pop('encoding', 'utf-8')
        self._source = open(filename, mode='Urb')
        self._reader = csv.reader(
            UTF8Recoder(self._source, encoding), **params)

    def __iter__(self):
        return self
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args, **kwargs):
        self.close()
    
    def next(self):
        return [unicode(cell, 'utf-8') for cell in self._reader.next()]
    
    def close(self):
        self._source.close()
