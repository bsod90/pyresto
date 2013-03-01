from core import Model
from wtforms.form import Form
from wtforms import fields


class McashModel(Model):

    class Data():
        pass

    # WTForm used to validate responses
    __form = None
    # Objects contains model fields.
    # Moved from __ditc__ in original Model class
    __data = None
    # By default use POST for creating new items.
    # But also can be a PUT
    _create_method = 'POST'

    def __init__(self, parent=None, *args, **kwargs):

        self._parent = parent

        self.__data = McashModel.Data()
        self.__data.__dict__.update(kwargs)

        # Fulfill relations. Commented out for now
        # Should figure out with this later
        # TODO: figure out with this

        cls = self.__class__
        overlaps = set(cls.__dict__) & set(kwargs)

        for item in overlaps:
            if issubclass(getattr(cls, item), Model):
                self.__data.__dict__['__' + item] = self.__data.__dict__.pop(item)

        self.__form = cls.Form(obj=self.__data)
        if not self.__form.validate():
            raise ValueError  # TODO: raise more valuable info about Error

        self._changed = set()

    def __fetch(self):
        # Overriden __fetch
        # Original used self.__dict__ to store the data
        # We would like to move everything to __data
        # And use WTForms for validation
        data, next_url = self._rest_call(url=self._current_path,
                                         auth=self._auth)

        if data:
            self.__data.__dict__.update(data)

            cls = self.__class__
            overlaps = set(cls.__dict__) & set(data)

            for item in overlaps:
                if issubclass(getattr(cls, item), Model):
                    self.__data.__dict__['__' + item] = self.__data.__dict__.pop(item)

            self._fetched = True

    def __getattr__(self, name):
        # Getting here if :name is not in self.__dict__
        # Trying to find attribute in __form first
        # Other way look it up in __data object
        if name in self.__form:
            return self.__form[name].data
        return getattr(self.__data, name)

    def __setattr__(self, key, value):
        # Store everything in __data
        # And don't forget to validate everything
        # That comes using __form
        if not key.startswith('_'):
            if key in self.__form:
                self._changed.add(key)
                setattr(self.__data, key, value)
                self.__form = self.__class__.Form(obj=self.__data)
                if not self.__form.validate():
                    raise ValueError  # TODO: raise more valuable info about Error
                else:
                    return
        super(Model, self).__setattr__(key, value)

    @property
    def _current_list_path(self):
        return getattr(self._parent, '_current_list_path', "") + self._list_path.format(**self._footprint)

    def _do_post(self, data={}, *args, **kwargs):
        path = self._current_list_path
        auth = kwargs.pop('auth', self._auth)
        cls = self.__class__
        resp = cls._rest_call(method="POST", url=path, auth=auth,
                              data=cls._serializer(data),
                              headers={'content-type': 'application/json'}).data
        return resp

    def _do_put(self, data={}, *args, **kwargs):
        path = self._current_path
        auth = kwargs.pop('auth', self._auth)
        cls = self.__class__
        resp = cls._rest_call(method="PUT", url=path, auth=auth,
                              data=cls._serializer(data),
                              headers={'content-type': 'application/json'}).data
        return resp

    @classmethod
    def get(cls, *args, **kwargs):
        """Alias for Pyresto read() method"""
        return cls.read(*args, **kwargs)

    def save(self, *args, **kwargs):
        """
            Tries to use POST if we haven't specified pk
            other way uses PUT request.
            Doesn't support PATCH for now (we just don't need it)
        """
        # Form contains all user entered data
        # But something probably will be in Relations
        # We want all the data in the same place
        # So, we just populate form on our __data object
        self.__form.populate_obj(self.__data)
        # Prepare data
        # Exclude everything that should be
        # Excluding accrding config
        # + Everything that is None
        data = self.__data.__dict__.copy()
        for key in data.keys():
            if data[key] is None or key in self._exclude_from_save:
                del data[key]

        # Check if we want use POST or PUT
        post = self._create_method == 'POST'
        for key in self._pk:
            post = post and not bool(getattr(self.__data, key, None))

        # Doing an appropriate call
        if post:
            resp = self._do_post(data=data, *args, **kwargs)
        else:
            resp = self._do_put(data=data, *args, **kwargs)

        # Update data object with data from response
        # And revalidate form
        # raise and Error if we got something that wouldn't
        # like to get
        self.__data.__dict__.update(resp)
        self.__form = self.__class__.Form(obj=self.__data)
        if not self.__form.validate():
            raise ValueError  # TODO: raise more valuable info about Error

        self._pk_vals = [getattr(self, key) for key in self._pk]

        self._changed.clear()
        return self

    def delete(self):
        """
            Does DELETE request on resource Url
            delete() originally a classmethod in Pyresto
            It's better to keep it in instance
        """
        return self.__class__.delete(self)
