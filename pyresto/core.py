# coding: utf-8

"""
pyresto.core
~~~~~~~~~~~~

This module contains all core pyresto classes such as Error, Model and relation
classes.

"""

import collections
import logging
import urlparse
import requests
from abc import ABCMeta, abstractproperty
from urllib import quote

try:
    import json
except ImportError:
    import simplejson as json

from decorators import assert_class_instance, normalize_auth
from exceptions import PyrestoInvalidOperationException, PyrestoServerResponseException, PyrestoInvalidRestMethodException

__all__ = ('Model', 'Many', 'Foreign')

ALLOWED_HTTP_METHODS = frozenset(('GET', 'POST', 'PUT', 'DELETE', 'PATCH'))


class ModelBase(ABCMeta):
    """
    Meta class for :class:`Model` class. This class automagically creates the
    necessary :attr:`Model._path` class variable if it is not already
    defined. The default path pattern is ``/modelname/{id}``.

    """

    def __new__(mcs, name, bases, attrs):
        new_class = super(ModelBase, mcs).__new__(mcs, name, bases, attrs)

        if name == 'Model':  # prevent unnecessary base work
            return new_class

        # don't override if defined
        if not new_class._path:
            new_class._path = u'/{0}/{{id}}'.format(quote(name.lower()))

        if not isinstance(new_class._pk, tuple):  # make sure it is a tuple
            new_class._pk = (new_class._pk,)

        new_class.update = new_class.update_with_patch if \
            new_class._update_method == 'PATCH' else new_class.update_with_put

        return new_class


class Model(object):
    """
    The base model class where every data model using pyresto should be
    inherited from. Uses :class:`ModelBase` as its metaclass for various
    reasons explained in :class:`ModelBase`.

    """

    __metaclass__ = ModelBase

    _update_method = 'PATCH'

    __footprint = None

    __pk_vals = None

    _changed = None

    #: The class variable that holds the bae uel for the API endpoint for the
    #: :class:`Model`. This should be a "full" URL including the scheme, port
    #: and the initial path if there is any.
    _url_base = None

    #: The class variable that holds the path to be used to fetch the instance
    #: from the server. It is a format string using the new format notation
    #: defined for :meth:`str.format`. The primary key will be passed under the
    #: same name defined in the :attr:`_pk` property and any other named
    #: parameters passed to the :meth:`Model.get` or the class constructor will
    #: be available to this string for formatting.
    _path = None

    #: The class variable that holds the default authentication object to be
    #: passed to :mod:`requests`. Can be overridden on either class or instance
    #: level for convenience.
    _auth = None

    @classmethod
    def _continuator(cls, response):
        """
        The class method which receives the response from the server. This
        method is expected to return a continuation URL for the fetched
        resource, if there is any (like the next page's URL for paginated
        content) and ``None`` otherwise. The default implementation uses the
        standard HTTP link header and returns the url provided under the label
        "next" for continuation and ``None`` if it cannot find this label.

        :param response: The response for the HTTP request made to fetch the
                         resources.
        :type response: :class:`requests.Response`

        """

        return None

    #: The class method which receives the class object and the body text of
    #: the server response to be parsed. It is expected to return a
    #: dictionary object having the properties of the related model. Defaults
    #: to a "staticazed" version of :func:`json.loads` so it is not necessary
    #: to override it if the response type is valid JSON.
    _parser = staticmethod(json.loads)

    #: The class method which receives the class object and a property dict of
    #: an instance to be serialized. It is expected to return a string which
    #: will be sent to the server on modification requests such as PATCH or
    #: CREATE. Defaults to a "staticazed" version of :func:`json.loads` so it
    #: is not necessary to override it if the response type is valid JSON.
    _serializer = staticmethod(json.dumps)

    @abstractproperty
    def _pk(self):
        """
        The class variable where the attribute name for the primary key for the
        :class:`Model` is stored as a string. This property is required and not
        providing a default is intentional to force developers to explicitly
        define it on every :class:`Model` class.

        """

    #: The instance variable which is used to determine if the :class:`Model`
    #: instance is filled from the server or not. It can be modified for
    #: certain usages but this is not suggested. If :attr:`_fetched` is
    #: ``False`` when an attribute, that is not in the class dictionary, tried
    #: to be accessed, the :meth:`__fetch` method is called before raising an
    #: :exc:`AttributeError`.
    _fetched = False

    #: The instance variable which holds the additional named get parameters
    #: provided to the :meth:`Model.get` to fetch the instance. It is used
    #: internally by the :class:`Relation` classes to get more info about the
    #: current :class:`Model` instance while fetching its related resources.
    _get_params = dict()

    def __init__(self, parent=None, **kwargs):
        """
        Constructor for model instances. All named parameters passed to this
        method are bound to the newly created instance. Any property names
        provided at this level which are interfering with the predefined class
        relations (especially for :class:`Foreign` fields) are prepended "__"
        to avoid conflicts and to be used by the related relation class. For
        instance if your class has ``father = Foreign(Father)`` and ``father``
        is provided to the constructor, its value is saved under ``__father``
        to be used by the :class:`Foreign` relationship class as the id of the
        foreign :class:`Model`.
        """

        self._parent = parent

        self.__dict__.update(kwargs)

        cls = self.__class__
        overlaps = set(cls.__dict__) & set(kwargs)

        for item in overlaps:
            if issubclass(getattr(cls, item), Model):
                self.__dict__['__' + item] = self.__dict__.pop(item)

        self._changed = set()

    @property
    def _id(self):
        """A property that returns the instance's primary key value."""
        if self.__pk_vals:
            return self.__pk_vals[-1]
        else:  # assuming last pk is defined on self!
            return getattr(self, self._pk[-1])

    @property
    def _pk_vals(self):
        # if not self.__pk_vals:
        #     if hasattr(self, '_pyresto_owner'):
        #         self.__pk_vals = self. \
        #                              _pyresto_owner._pk_vals[:len(self._pk) - 1] + (self._id,)
        #     else:
        #         self.__pk_vals = (None,) * (len(self._pk) - 1) + (self._id,)

        # return self.__pk_vals
        self.__pk_vals = (None,) * (len(self._pk) - 1) + (self._id,)
        return self.__pk_vals

    @_pk_vals.setter
    def _pk_vals(self, value):
        if len(value) == len(self._pk):
            self.__pk_vals = tuple(value)
        else:
            raise ValueError

    @property
    def _footprint(self):
        #if not self.__footprint:
        self.__footprint = dict(zip(self._pk, self._pk_vals))
        self.__footprint['self'] = self

        return self.__footprint

    @property
    def _current_path(self):
        return getattr(self._parent, '_current_path', "") + self._path.format(**self._footprint)

    @classmethod
    def _get_sanitized_url(cls, url):
        return urlparse.urljoin(cls._url_base, url)

    @classmethod
    def _rest_call(cls, url, method='GET', fetch_all=True, **kwargs):
        """
        A method which handles all the heavy HTTP stuff by itself. This is
        actually a private method but to let the instances and derived classes
        to call it, is made ``protected`` using only a single ``_`` prefix.

        All undocumented keyword arguments are passed to the HTTP request as
        keyword arguments such as method, url etc.

        :param fetch_all: (optional) Determines if the function should
                          recursively fetch any "paginated" resource or simply
                          return the downloaded and parsed data along with a
                          continuation URL.
        :type fetch_all: boolean

        :returns: Returns a tuple where the first part is the parsed data from
                  the server using :attr:`Model._parser`, and the second half
                  is the continuation URL extracted using
                  :attr:`Model._continuator` or ``None`` if there isn't any.
        :rtype: tuple

        """

        url = cls._get_sanitized_url(url)

        if cls._auth is not None and 'auth' not in kwargs:
            kwargs['auth'] = cls.auth

        if method in ALLOWED_HTTP_METHODS:
            response = requests.request(method.lower(), url, verify=True,
                                        **kwargs)
        else:
            raise PyrestoInvalidRestMethodException(
                'Invalid method "{0:s}" is used for the HTTP request. Can only'
                'use the following: {1!s}'.format(method,
                                                  ALLOWED_HTTP_METHODS))

        result = collections.namedtuple('result', 'data continuation_url')
        if 200 <= response.status_code < 300:
            continuation_url = cls._continuator(response)
            response_data = response.text
            data = cls._parser(response_data) if response_data else None
            if continuation_url:
                logging.debug('Found more at: %s', continuation_url)
                if fetch_all:
                    kwargs['url'] = continuation_url
                    data += cls._rest_call(**kwargs).data
                else:
                    return result(data, continuation_url)
            return result(data, None)
        else:
            msg = '%s returned HTTP %d: %s\nResponse\nHeaders: %s\nBody: %s'
            logging.error(msg, url, response.status_code, kwargs,
                          response.headers, response.text)

            raise PyrestoServerResponseException('Server response not OK. '
                                                 'Response code: {0:d}'
            .format(response.status_code))

    def __fetch(self):
        data, next_url = self._rest_call(url=self._current_path,
                                         auth=self._auth)

        if data:
            self.__dict__.update(data)

            cls = self.__class__
            overlaps = set(cls.__dict__) & set(data)

            for item in overlaps:
                if issubclass(getattr(cls, item), Model):
                    self.__dict__['__' + item] = self.__dict__.pop(item)

            self._fetched = True

    def __getattr__(self, name):
        if self._fetched:  # if we fetched and still don't have it, no luck!
            raise AttributeError
        self.__fetch()
        return getattr(self, name)  # try again after fetching

    def __setattr__(self, key, value):
        if not key.startswith('_'):
            self._changed.add(key)
        super(Model, self).__setattr__(key, value)

    def __delattr__(self, item):
        raise PyrestoInvalidOperationException(
            "Del method on Pyresto models is not supported.")

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self._id == other._id

    def __repr__(self):
        if self._path:
            descriptor = self._current_path
        else:
            descriptor = ' - {0}'.format(self._footprint)

        return '<Pyresto.Model.{0} [{1}]>'.format(self.__class__.__name__,
                                                  descriptor)

    @classmethod
    def read(cls, *args, **kwargs):
        """
        The class method that fetches and instantiates the resource defined by
        the provided pk value. Any other extra keyword arguments are used to
        format the :attr:`Model._path` variable to construct the request URL.

        :param pk: The primary key value for the requested resource.
        :type pk: string

        :rtype: :class:`Model` or None

        """

        auth = kwargs.pop('auth', cls._auth)

        ids = dict(zip(cls._pk, args))
        parent = kwargs.pop('parent', None)
        path = getattr(parent, '_current_path', "") + cls._path.format(**ids)
        data = cls._rest_call(url=path, auth=auth).data

        if not data:
            return None

        instance = cls(parent=parent, **data)
        instance._pk_vals = args
        instance._fetched = True
        if auth:
            instance._auth = auth

        return instance

    @classmethod
    @normalize_auth
    @assert_class_instance
    def update_with_patch(cls, instance, keys=None, auth=None):
        if keys:
            keys &= instance._changed
        else:
            keys = instance._changed

        data = dict((key, instance.__dict__[key]) for key in keys)
        path = instance._current_path
        resp = cls._rest_call(method="PATCH", url=path, auth=auth,
                              data=cls._serializer(data)).data
        instance.__dict__.update(resp)
        instance._changed -= keys

        return instance

    @classmethod
    @normalize_auth
    @assert_class_instance
    def update_with_put(cls, instance, auth=None):
        data = instance.__dict__.copy()
        path = instance._current_path
        resp = cls._rest_call(method="PUT", url=path, auth=auth,
                              data=cls._serializer(data)).data
        instance.__dict__.update(resp)
        instance._changed.clear()

        return instance

    @classmethod
    @normalize_auth
    @assert_class_instance
    def delete(cls, instance, auth=None):
        cls._rest_call(method="DELETE", url=instance._current_path, auth=auth)
        return True  # will raise error if server responds with non 2xx
