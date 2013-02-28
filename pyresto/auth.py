__author__ = 'pavelmeshkoy'
from requests.auth import AuthBase
from abc import ABCMeta, abstractmethod
from pyresto.exceptions import *

__all__ = ('Auth', 'AuthList', 'enable_auth')


class Auth(AuthBase):
    """
    Abstract base class for all custom authentication classes to be used with
    pyresto. See `Requests Documentation <http://docs.python-requests.org/en/
    latest/user/advanced/#custom-authentication>`_ for more info.
    """
    __metaclass__ = ABCMeta

    @abstractmethod
    def __call__(self, r):
        return r


class AuthList(dict):
    """
    An "attribute dict" which is basically a dict where item access can be done
    via attributes just like normal classes. Implementation taken from
    `StackOverflow <http://stackoverflow.com/questions/4984647/accessing
    -dict-keys-like-an-attribute-in-python>`_ and the class is used for
    defining authentication methods available for a given api. See
    :data:`apis.github.auths` for example usage.

    .. literalinclude:: ../pyresto/apis/github/models.py
        :lines: 102-103

    """
    def __getattr__(self, attr):
        return self[attr]

    def __setattr__(self, attr, value):
        self[attr] = value


def enable_auth(supported_types, base_model, default_type):
    """
    A "global authentication enabler" function generator. See
    :func:`apis.github.auth` for example usage.

    .. literalinclude:: ../pyresto/apis/github/models.py
        :lines: 105-106

    :param supported_types: A dict of supported types as ``"name": AuthClass``
                            pairs
    :type supported_types: dict

    :param base_model: The base model to set the :attr:`Model._auth` on
    :type base_model: :class:`Model`

    :param default_type: Default authentication type's name
    :type default_type: string

    :returns: An ``auth`` function that passes the arguments other then
              ``type`` to the given authentication type's constructor. Uses the
              default authentication class if ``type`` is omitted.
    :rtype: ``function(type=default_type, **kwargs)``
    """
    def auth(type=default_type, **kwargs):
        if type is None:
            base_model._auth = None
            return

        if type not in supported_types:
            raise PyrestoInvalidAuthTypeException('Unsupported auth type: {0}'
            .format(type))

        base_model._auth = supported_types[type](**kwargs)

    return auth