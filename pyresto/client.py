import logging
import requests
import urlparse
from abc import ABCMeta, abstractproperty


__doc__ = """
            Base http client for sending http requests of different types
                We decided to make full refactoring of the pyresto lib,
                This client uses the requests library
            """

class AbstractBaseClient(object):
    """
    Abstract Base client. For now it's empty :(
    """
    __metaclass__ = ABCMeta


class BaseClient(AbstractBaseClient):
    """
    Base http client what implements the basics requests
    __base_url: it's basic url, with what will join our uri's
    the full url is generated automaticly joining base url, what is set as client attr
    and uri, what is sent to the client by the user
    """

    __base_url = None

    def __init__(self, uri=None, auth=None):
        if uri:
            self.url = urlparse.urljoin(self.__base_url, uri)
        self.auth = auth

    def get(self, **kwargs):
        kwargs['auth'] = self.auth
        try:
            response = requests.get(self.url, kwargs)
            response.raise_for_status()
        except requests.HTTPError, e:
            logging.error(e)
            raise e
        return response

    def post(self, data=None, **kwargs):
        kwargs['auth'] = self.auth
        try:
            response = requests.post(self.url, data=data, **kwargs)
            response.raise_for_status()
        except requests.HTTPError, e:
            logging.error(e)
            raise e
        return response

    def put(self, data=None, **kwargs):
        kwargs['auth'] = self.auth
        try:
            response = requests.put(self.url, data, **kwargs)
            response.raise_for_status()
        except requests.HTTPError, e:
            logging.error(e)
            raise e
        return response

    def delete(self, **kwargs):
        kwargs['auth'] = self.auth
        try:
            response = requests.delete(self.url, **kwargs)
            response.raise_for_status()
        except requests.HTTPError, e:
            logging.error(e)
            raise e
        return response




