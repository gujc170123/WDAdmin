from django.test import TransactionTestCase
from rest_framework.test import APIClient
from django.urls import reverse
from workspace.views import PeopleLoginView,OrganizationListCreateView,\
                            OrganizationlRetrieveUpdateDestroyView,\
                            OrganizationImportExportView,\
                            UserCreateView,UseDetailView
from wduser.models import AuthUser
from wduser.models import EnterpriseInfo
from workspace.models import BaseOrganization
import time

class TestOrganizationAPI(TransactionTestCase):

    def setUp(self):
        self.client = APIClient()
        admin = AuthUser.objects.create_superuser("admin",password="000000,m",email="admin@gelue.com")
        self.client.force_authenticate(admin)        
        dic = {'cn_name':'cn_name', 'en_name':'en_name', 'short_name':'short_name'}
        EnterpriseInfo.objects.create(**dic)
        
    def test_Organization_ListCreateView(self):
        entid = EnterpriseInfo.objects.first().id
        print(entid)
        data = {'name':'org_1','enterprise_id': str(entid)}
        response = self.client.post(reverse('org-list',current_app='workspace'),data=data)
        self.assertTrue(BaseOrganization.objects.all().exists())

    def test_Organization_Detail(self):
        entid = EnterpriseInfo.objects.first().id
        data = {'name':'org_2','enterprise_id': str(entid)}
        response = self.client.post(reverse('org-list',current_app='workspace'),data=data)
        data = {'name':'org_21','enterprise_id': str(entid)}
        orgid = BaseOrganization.objects.filter(name='org_2').first().id
        response = self.client.put(reverse('org-manage', kwargs={'pk':orgid},current_app='workspace'),data=data)
        self.assertFalse(BaseOrganization.objects.filter(name='org_2').exists())
        self.assertTrue(BaseOrganization.objects.filter(name='org_21').exists())  

    def test_UserCreateView(self):
        entid = EnterpriseInfo.objects.first().id
        data = {'name':'org_3','enterprise_id': str(entid)}
        response = self.client.post(reverse('org-list',current_app='workspace'),data=data)
        orgid = BaseOrganization.objects.filter(name='org_3').first().id
        data = {'phone':'15616661999','password':'123456','email':'test@mail.com',
                'nickname':'nickname','account_name':'test001','department':orgid,
                'birthday':'1992/01/01','gender':'0','hiredate':'2016/08/08','rank':'1'}
        response = self.client.post(reverse('user-list-create',current_app='workspace'),data=data)

        infos = request.data.get('infos', None)


        response = self.client.get(reverse('user-list-create',current_app='workspace'))


    def test_UseDetailView(self):