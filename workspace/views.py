# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import status
from utils.views import AuthenticationExceptView, WdCreateAPIView, WdRetrieveUpdateAPIView ,\
                        WdDestroyAPIView
from utils.response import general_json_response, ErrorCode
from wduser.user_utils import UserAccountUtils
from utils.logger import get_logger
from workspace.helper import OrganizationHelper
from workspace.serializers import UserInfoSerializer,BaseOrganizationSerializer,PeopleSerializer
from workspace.models import BaseOrganization,BaseUserOrganization
from utils.regular import RegularUtils
from assessment.views import do_one_infos, get_mima
from wduser.models import EnterpriseAccount, People
from django.db.models import Q

#retrieve logger entry for workspace app
logger = get_logger("workspace")

class PeopleLoginView(AuthenticationExceptView, WdCreateAPIView):
    """Login API for Workspace"""

    def post(self, request, *args, **kwargs):
        """get account,pwd field from request's data"""
        account = request.data.get('account', None)
        pwd = request.data.get("pwd", None)
        #assure account and pwd be not empty
        if account is None or pwd is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        #continue unless account exists
        user, err_code = UserAccountUtils.account_check(account)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        #continue unless account/pwd is correct
        user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        #retrieve UserInfo Serialization
        user_info = UserInfoSerializer(instance=user, context=self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)

class OrganizationListCreateView(AuthenticationExceptView, WdCreateAPIView):
    """organization tree view"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer
    GET_CHECK_REQUEST_PARAMETER = {"organization_id"}

    def get(self, request, *args, **kwargs):
        """get organization tree of current user"""
        tree_orgs = OrganizationHelper.get_tree_orgs(self.organization_id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": tree_orgs})

class OrganizationlRetrieveUpdateDestroyView(AuthenticationExceptView, 
                                             WdRetrieveUpdateAPIView, WdDestroyAPIView):
    """organization management"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer

    def delete(self, request, *args, **kwargs):
        
        org = self.get_id()
        org_ids = [org] + OrganizationHelper.get_child_ids(org)
        #delete all organizations only when no active member exists
        if BasePersonOrganization.objects.filter_active(organization_id__in=org_ids).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.WORKSPACE_ORG_MEMBEREXISTS)
        else:
            BaseOrganization.objects.filter(id__in=org_ids).update(is_active=False)
            logger.info('user_id %s want delete orgs %s' % (self.request.user.id,org_ids))
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class OrganizationImportExportView(AuthenticationExceptView):
    """organization template import/export"""
    def get_template(self):
        #todo
        """get template file"""

    def post(self, request, *args, **kwargs):
        #todo
        """import organization file"""
    
class UserCreateView(WdCreateAPIView):
    """create user"""

    def post(self, request, *args, **kwargs):
        infos = request.data.get('infos', None)
        pwd = request.data.get('password', None)
        phone = request.data.get('phone', None)
        email = request.data.get('email', None)
        nickname = request.data.get('nickname', None)
        account_name = request.data.get('account_name', None)
        enterprise_id = request.data.get('enteprise_id', None)
        organization_id = request.data.get('organization_id', None)
        enterprise_id = request.data.get('enterprise_id', None)
        username = nickname + get_random_char(6)
        active_code = get_active_code()
        moreinfo = None
        
        #check account_name not duplicated
        if account_name:
            if EnterpriseAccount.objects.filter(account_name=account_name,
                                                enterprise_id=enterprise_id).exists():
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'msg': u'账户在本企业已存在'})
        #retrieve phone
        if phone:
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'新增用户失败，手机格式有误'})
            if BaseUserOrganization.objects.filter_active(organization__enterprise_id=enterprise_id,
                                                          user__phone=phone).exists():
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'新增用户失败，手机已被使用'})
        #retrieve email                                
        if email:
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'新增用户失败，邮箱格式有误'})
            if BaseUserOrganization.objects.filter_active(organization__enterprise_id=enterprise_id,
                                                          user__email=email).exists():
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_EMAIL_USED_ERROR,
                                             {'msg': u'新增用户失败，邮箱已被使用'})
        #retrieve profile
        if infos:
            key_infos = do_one_infos(infos)
            moreinfo = json.dumps(key_infos)

        try:
            #create user object
            authuser_obj = AuthUser.objects.create(
                username=username,
                account_name=account_name,
                nickname=nickname,
                password=get_mima(pwd),
                phone=phone,
                email=email
            )
            #create people object
            new_people_obj = People.objects.create(
                username=nickname,
                user_id=authuser_obj.id,
                phone=phone,
                email=email,
                active_code=active_code,
                active_code_valid=True,
                more_info=moreinfo
            )
            #create user-organization entity
            BaseUserOrganization.objects.create(
                user_id=authuser_obj.id,
                organization_id=organization_id
            )
            #create user-enterprise entity
            if account_name:
                EnterpriseAccount.objects.create(
                    user_id=authuser_obj.id,
                    people_id=new_people_obj.id,
                    enterprise_id=enterprise_id,
                    account_name=account_name
                )
            
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {'msg': u'成功'})
        except Exception, e:
            logger.error("新增用户失败 %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {'msg': u'新增用户失败'})

class UseDetailView(WdRetrieveUpdateAPIView):
    '''user detail management'''
    model = People
    serializer_class = PeopleSerializer

    def put(self, request, *args, **kwargs):
        '''update user's profile, password ,email ,phone and organization'''
        people_obj = self.get_object()
        
        try:
            authuser_obj = AuthUser.objects.get(id=people_obj.user_id,is_active=True)
            ea_obj = EnterpriseAccount.objects.get(user_id=authuser_obj.id,is_active=True)
            userorg_obj = BaseUserOrganization.objects(user_id=authuser_obj.id,is_active=True)          
        except Exception, e:
            logger.error('user not found or enterpriseaccount not found %s' % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_FOUND)

        infos = request.data.get('infos', None)
        phone = str_check(request.data.get('phone', None))
        email = request.data.get('email', None)
        account_name = request.data.get('account_name', None)
        nickname = request.data.get('username', None)
        pwd = request.data.get('password', None)
        password = get_mima(pwd) if pwd else None
        enterprise_id = people_obj.enterprise_id
        organization_id = request.data.get('organization_id', None)

        moreinfo = None
        if account_name and (account_name != authuser_obj.account_name):
            if EnterpriseAccount.objects.filter(account_name=account_name,
                                                enterprise_id=enterprise_id).exists():
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'msg': u'账户在本企业已存在'})

        #retrieve user profile
        if infos:
            key_infos = do_one_infos(infos)
            if key_infos is None:
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_INFO_ERROR, \
                                             {'msg': u'增加信息异常'})
            # 修改的时候没有dump
            moreinfo = key_infos
        #check user phone
        if phone:
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'手机格式有误'})
            phone_obj = People.objects.filter_active(~Q(id=people_obj.id),phone=phone)
            if phone_obj.exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                                {'msg': u'手机已被使用'})
        #check user email
        if email:
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'邮箱格式有误'})
            email_obj = People.objects.filter_active(~Q(id=people_obj.id),email=email)
            if email_obj.exists():
                    return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'邮箱已被使用'})
        #user entity          
        authuser_obj.account_name = account_name
        authuser_obj.nickname = nickname
        authuser_obj.phone = phone
        authuser_obj.email = email
        if password:
            authuser_obj.password = password

        #people entity
        people_obj.phone = phone
        people_obj.email = email
        people_obj.username = nickname        
        if moreinfo:
            if people_obj.more_info:
                try:
                    old_info = json.loads(people_obj.more_info) 
                    old_key_name = [x['key_name'] for x in old_info]
                    for new_key in moreinfo:
                        if new_key['key_name'] in old_key_name:
                            old_info[old_key_name.index(new_key["key_name"])]['key_value'] = new_key["key_value"]
                        else:
                            old_info.append(new_key)
                    people_obj.more_info = json.dumps(old_info)
                except:
                    people_obj.more_info = json.dumps(moreinfo)
            else:
                people_obj.more_info = json.dumps(moreinfo)

        try:
            authuser_obj.save()
            people_obj.save()
            
            #user-organization entity
            if organization_id and (organization_id!= userorg_obj.organization_id):
                userorg_obj.organization_id = organization_id      
                userorg_obj.save()

            #user-enterprise entity
            if account_name and (account_name != authuser_obj.account_name):                
                ea_obj.account_name = account_name
                ea_obj.save() 

            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        except Exception, e:
            logger.error("update %d error %s" % (people_obj.id, e))
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_UPDATE_ERROR, {'msg': u'modification error'})
