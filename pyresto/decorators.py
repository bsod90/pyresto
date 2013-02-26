"""
Decorators are placed here!! :)
"""


def assert_class_instance(class_method):
    """
    :param class_method:
    """
    def asserted(cls, instance, *args, **kwargs):
        """
        :param cls:
        :param instance:
        :param args:
        :param kwargs:
        """
        assert isinstance(instance, cls)
        return class_method(cls, instance, *args, **kwargs)

    return asserted


def normalize_auth(class_method):
    """
    :param class_method:
    """
    def normalized(cls, instance, *args, **kwargs):
        """
        :param cls:
        :param instance:
        :param args:
        :param kwargs:
        """
        auth = kwargs.get('auth')
        if auth is None:
            auth = cls._auth or instance._auth
        kwargs['auth'] = auth
        return class_method(cls, instance, *args, **kwargs)
    return normalized