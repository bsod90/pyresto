try:
    import unittest2 as unittest
except ImportError:
    import unittest

from pyresto.mcash import McashModel
from pyresto.auth import Auth
from wtforms import fields
from wtforms import validators
import wtforms


class SecretAuth(Auth):
    def __call__(self, req):
        req.headers['X-Mcash-Secret'] = 'secret'
        return req


class TestModelClass(McashModel):
    _url_base = "https://playgroundmcashservice.appspot.com"
    _path = "/merchantapi/v1/merchant/{id}/"
    _list_path = "/merchantapi/v1/merchant/"
    _pk = ('id',)
    _auth = SecretAuth()
    _exclude_from_save = ('id', 'link')

    class Form(wtforms.Form):
        id = fields.StringField()
        jurisdiction = fields.StringField()
        organizationId = fields.StringField()
        businessName = fields.StringField()
        language = fields.StringField()
        mcc = fields.StringField()
        netmask = fields.StringField()
        secret = fields.StringField()
        pubkey = fields.StringField()


class TestRelatedModelClass(McashModel):
    _url_base = "https://playgroundmcashservice.appspot.com"
    _path = "pos/{id}/"
    _pk = ('id',)
    _auth = SecretAuth()
    _create_method = 'PUT'
    _exclude_from_save = ('id',)

    class Form(wtforms.Form):
        id = fields.StringField()
        name = fields.StringField()
        type = fields.StringField()
        netmask = fields.StringField()
        secret = fields.StringField()
        pubkey = fields.StringField()


class TestModel(unittest.TestCase):

    def test_constructor(self):
        obj = TestModelClass(
            secret='secret',
            businessName='ABC corp.',
            jurisdiction='NO',
            organizationId='12345678'
        )
        self.assertEqual(obj.businessName, 'ABC corp.')

    def test_setter(self):
        obj = TestModelClass()
        obj.businessName = 'ABC corp.'
        self.assertEqual(obj.businessName, 'ABC corp.')

    def test_get(self):
        obj = TestModelClass.get('f227012d1eb24a6493e9012f7a6ffc38')
        self.assertEqual(obj.businessName, 'Acme')

    def test_create(self):
        obj = TestModelClass(
            secret='secret',
            businessName='ABC corp.',
            jurisdiction='NO',
            organizationId='12345678'
        )
        obj.save()
        self.assertTrue(obj.id)

    def test_update(self):
        obj = TestModelClass(
            secret='secret',
            businessName='ABC corp.',
            jurisdiction='NO',
            organizationId='12345678'
        )
        obj.businessName = 'ACME llc'
        obj.save()
        self.assertEqual(obj.businessName, 'ACME llc')
        obj2 = TestModelClass.get(obj.id)
        obj2.businessName = 'ABC'
        obj2.save()
        self.assertEqual(obj2.businessName, 'ABC')

    def test_delete(self):
        obj = TestModelClass(
            secret='secret',
            businessName='ABC corp.',
            jurisdiction='NO',
            organizationId='12345678'
        )
        obj.save()
        self.assertRaises(Exception, obj.remove)

    def test_child_model(self):
        merchant = TestModelClass(
            secret='secret',
            businessName='ABC corp.',
            jurisdiction='NO',
            organizationId='12345678'
        )
        merchant.save()
        pos = TestRelatedModelClass(
            parent=merchant,
            name='Kasse 3',
            type='store',
            netmask='',
            secret='secret',
            id='123'
        )
        pos.save()
        pos = TestRelatedModelClass.get('123', parent=merchant)
        self.assertEqual(pos.name, 'Kasse 3')
        self.assertRaises(Exception, pos.remove)
