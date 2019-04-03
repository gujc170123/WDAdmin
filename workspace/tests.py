from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework.test import APIRequestFactory
from workspace.views import PeopleLoginView

class TestAPI(APITestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = PeopleLoginView.as_view({''})
