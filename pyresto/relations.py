try:
    import json
except ImportError:
    import simplejson as json
import re

class WrappedList(list):
    """
    Wrapped list implementation to dynamically create models as someone tries
    to access an item or a slice in the list. Returns a generator instead, when
    someone tries to iterate over the whole list.

    """

    def __init__(self, iterable, wrapper):
        super(self.__class__, self).__init__(iterable)
        self.__wrapper = wrapper

    def __getitem__(self, key):
        item = super(self.__class__, self).__getitem__(key)
        # check if we need to wrap the item, or if this is a slice, then check
        # if we need to wrap any item in the slice
        should_wrap = (isinstance(item, dict) or isinstance(key, slice) and
                       any(isinstance(it, dict) for it in item))

        if should_wrap:
            item = ([self.__wrapper(_) for _ in item]
                    if isinstance(key, slice) else self.__wrapper(item))

            self[key] = item  # cache wrapped item/slice

        return item

    def __getslice__(self, i, j):
        # We need this implementation for backwards compatibility.
        items = super(self.__class__, self).__getslice__(i, j)
        if any(isinstance(it, dict) for it in items):
            items = [self.__wrapper(_) for _ in items]
            self[i:j] = items  # cache wrapped slice
        return items

    def __iter__(self):
        # Call the base __iter__ to avoid infinite recursion and then simply
        # return an iterator.
        iterator = super(self.__class__, self).__iter__()
        return (self.__wrapper(item) for item in iterator)

    def __contains__(self, item):
        # Not very performant but necessary to use Model instances as operands
        # for the in operator.
        return item in iter(self)


class LazyList(object):
    """
    Lazy list implementation for continuous iteration over very large lists
    such as commits in a large repository. This is essentially a chained and
    structured generator. No caching and memoization at all since the intended
    usage is for small number of iterations.

    """

    def __init__(self, wrapper, fetcher):
        self.__wrapper = wrapper
        self.__fetcher = fetcher

    def __iter__(self):
        fetcher = self.__fetcher
        while fetcher:
            # fetcher is stored locally to prevent interference between
            # possible multiple iterations going at once
            data, fetcher = fetcher()  # this part never gets hit if the below
            # loop is not exhausted.
            for item in data:
                yield self.__wrapper(item)

class Relation(object):
    """Base class for all relation types."""


class Many(Relation):
    """
    Class for 'many' :class:`Relation` type which is essentially a collection
    for a certain model. Needs a base :class:`Model` for the collection and a
    `path` to get the collection from. Falls back to provided model's
    :attr:`Model.path` if not provided.

    """

    def __init__(self, model, path=None, lazy=False, preprocessor=None):
        """
        Constructor for Many relation instances.

        :param model: The model class that each instance in the collection
                      will be a member of.
        :type model: Model
        :param path: (optional) The unicode path to fetch the collection items,
                     if different than :attr:`Model._path`, which usually is.
        :type path: string or None

        :param lazy: (optional) A boolean indicator to determine the type of
                     the :class:`Many` field. Normally, it will be a
                     :class:`WrappedList` which is essentially a list. Use
                     ``lazy=True`` if the number of items in the collection
                     will be uncertain or very large which will result in a
                     :class:`LazyList` property which is practically a
                     generator.
        :type lazy: boolean

        """

        self.__model = model
        self.__path = path or model._path
        self.__lazy = lazy
        self.__preprocessor = preprocessor
        self.__cache = dict()

    def _with_owner(self, owner):
        """
        A function factory method which returns a mapping/wrapping function.
        The returned function creates a new instance of the :class:`Model` that
        the :class:`Relation` is defined with, sets its owner and
        "automatically fetched" internal flag and returns it.

        :param owner: The owner Model for the collection and its items.
        :type owner: Model

        """

        def mapper(data):
            if isinstance(data, dict):
                instance = self.__model(**data)
                instance._pyresto_owner = owner
                return instance
            elif isinstance(data, self.__model):
                return data
            else:
                raise TypeError("Invalid type passed to Many.")

        return mapper

    def __sanitize_data(self, data):
        if not data:
            return list()
        elif self.__preprocessor:
            return self.__preprocessor(data)
        return data

    def __make_fetcher(self, url, instance):
        """
        A function factory method which creates a simple fetcher function for
        the :class:`Many` relation, that is used internally. The
        :meth:`Model._rest_call` method defined on the models is expected to
        return the data and a continuation URL if there is any. This method
        generates a bound, fetcher function that calls the internal
        :meth:`Model._rest_call` function on the :class:`Model`, and processes
        its results to satisfy the requirements explained above.

        :param url: The url which the fetcher function will be bound to.
        :type url: unicode

        """

        def fetcher():
            data, new_url = self.__model._rest_call(url=url,
                                                    auth=instance._auth,
                                                    fetch_all=False)
            # Note the fetch_all=False in the call above, since this method is
            # intended for iterative LazyList calls.
            data = self.__sanitize_data(data)

            new_fetcher = self.__make_fetcher(new_url,
                                              instance) if new_url else None
            return data, new_fetcher

        return fetcher

    def __get__(self, instance, owner):
        # This method is called whenever a field defined as Many is tried to
        # be accessed. There is also another usage which lacks an object
        # instance in which case this simply returns the Model class then.
        if not instance:
            return self.__model

        cache = self.__cache
        if instance not in cache:
            model = self.__model

            path = self.__path.format(**instance._footprint)

            if self.__lazy:
                cache[instance] = LazyList(self._with_owner(instance),
                                           self.__make_fetcher(path, instance))
            else:
                data, next_url = model._rest_call(url=path,
                                                  auth=instance._auth)
                cache[instance] = WrappedList(self.__sanitize_data(data),
                                              self._with_owner(instance))
        return cache[instance]


class Foreign(Relation):
    """
    Class for 'foreign' :class:`Relation` type which is essentially a reference
    to a certain :class:`Model`. Needs a base :class:`Model` for obvious
    reasons.

    """

    def __init__(self, model, key_property=None, key_extractor=None,
                 embedded=False):
        """
        Constructor for the :class:`Foreign` relations.

        :param model: The model class for the foreign resource.
        :type model: Model

        :param key_property: (optional) The name of the property on the base
                             :class:`Model` which contains the id for the
                             foreign model.
        :type key_property: string or None

        :param key_extractor: (optional) The function that will extract the id
                              of the foreign model from the provided
                              :class:`Model` instance. This argument is
                              provided to make it possible to handle complex id
                              extraction operations for foreign fields.
        :type key_extractor: function(model)

        """

        self.__model = model
        self.__cache = dict()
        self.__embedded = embedded and not key_extractor

        self.__key_property = key_property or '__' + model.__name__.lower()

        if key_extractor:
            self.__key_extractor = key_extractor
        elif not embedded:
            def extract(instance):
                footprint = instance._footprint
                ids = list()

                for k in self.__model._pk[:-1]:
                    ids.append(footprint[k] if k in footprint
                    else getattr(instance, k))

                item, key = re.match(r'(\w+)(?:\[(\w+)\])?',
                                     key_property).groups()
                item = getattr(instance, item)
                ids.append(item[key] if key else item)

                return tuple(ids)

            self.__key_extractor = extract

    def __get__(self, instance, owner):
        # Please see Many.__get__ for more info on this method.
        if not instance:
            return self.__model

        if instance not in self.__cache:
            if self.__embedded:
                self.__cache[instance] = self.__model(
                    **getattr(instance, self.__key_property))
                self.__cache[instance]._auth = instance._auth
            else:
                self.__cache[instance] = self.__model.get(
                    *self.__key_extractor(instance), auth=instance._auth)

            self.__cache[instance]._pyresto_owner = instance

        return self.__cache[instance]
