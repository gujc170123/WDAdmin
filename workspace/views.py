# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import status
from utils.views import AuthenticationExceptView, WdCreateAPIView, WdRetrieveUpdateAPIView ,\
                        WdDestroyAPIView
from utils.response import general_json_response, ErrorCode
from wduser.user_utils import UserAccountUtils
from utils.logger import get_logger
from workspace.helper import OrganizationHelper
from workspace.serializers import UserSerializer,BaseOrganizationSerializer
from utils.regular import RegularUtils
from assessment.views import get_mima, get_random_char, get_active_code
from wduser.models import AuthUser, BaseOrganization

#retrieve logger entry for workspace app
logger = get_logger("workspace")

class UserLoginView(AuthenticationExceptView, WdCreateAPIView):
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
        user_info = UserSerializer(instance=user, context=self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)

class UserListCreateView(AuthenticationExceptView,WdCreateAPIView):
    """list/create person"""
    model = AuthUser
    serializer_class = UserSerializer

    def post(self, request, *args, **kwargs):
        pwd = request.data.get('password', None)
        phone = request.data.get('phone', None)
        email = request.data.get('email', None)
        nickname = request.data.get('nickname', None)
        account_name = request.data.get('account_name', None)
        organization_id = request.data.get('department', None)
        hiredate = request.data.get('hiredate', None)
        rank = request.data.get('rank', None)
        birthday = request.data.get('birthday', None)
        gender = request.data.get('gender', None)
        sequence = request.data.get('sequence', None)
        marriage = request.data.get('marriage', None)
        is_staff = request.data.get('is_staff', True)
        role_type = request.data.get('role_type', AuthUser.ROLE_NORMAL)
        is_superuser = request.data.get('is_superuser', False)
        username = nickname + get_random_char(6)
        active_code = get_active_code()
        
        organization = BaseOrganization.objects.get(pk=organization_id)
        enterprise_id = organization.enterprise_id

        #check account_name not duplicated
        if account_name:
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       account_name=account_name,
                                       organization__is_active=True).exists():  
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'msg': u'账户在本企业已存在'})
        #retrieve phone
        if phone:
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'新增用户失败，手机格式有误'})
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       phone=phone,
                                       organization__is_active=True).exists():                       
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'新增用户失败，手机已被使用'})
        #retrieve email                                
        if email:
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'新增用户失败，邮箱格式有误'})
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       email=email,
                                       organization__is_active=True).exists():  
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_EMAIL_USED_ERROR,
                                             {'msg': u'新增用户失败，邮箱已被使用'})

        try:
            #create user object
            authuser_obj = AuthUser.objects.create(
                username=username,
                account_name=account_name,
                nickname=nickname,
                password=get_mima(pwd),
                phone=phone,
                email=email,
                is_superuser=is_superuser,
                role_type=role_type,
                is_staff=is_staff,
                sequence_id=sequence,
                gender_id=gender,
                birthday=birthday,
                rank_id=rank,
                hiredate=hiredate,
                marriage_id=marriage,
                organization_id=organization.id
            )          
            
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {'msg': u'成功'})
        except Exception, e:
            logger.error("新增用户失败 %s" % e)
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {'msg': u'新增用户失败'})

    def get(self, request, *args, **kwargs):
        '''list users'''
        
        tree_ids = [request.GET.get('organization_id')] + OrganizationHelper.get_child_ids(request.GET.get('organization_id'))
        if tree_ids:
            users = UserSerializer(AuthUser.objects.filter(is_active=True,
                                                           baseorganization__in=tree_ids,
                                                           baseorganization__is_active=True),
                                   many=True)
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": users.data})
        else:
            return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.NOT_EXISTED) 
        
        
class UserDetailView(AuthenticationExceptView,WdRetrieveUpdateAPIView,WdDestroyAPIView):
    '''person detail management'''
    model = AuthUser
    serializer_class = UserSerializer

    def put(self, request, *args, **kwargs):
        '''update user's profile, password ,email ,phone and organization'''
        user = self.get_object()

        phone = request.data.get('phone', None)
        email = request.data.get('email', None)
        account_name = request.data.get('account_name', None)
        nickname = request.data.get('username', None)
        pwd = request.data.get('password', None)
        password = get_mima(pwd) if pwd else None
        organization_id = request.data.get('department', None)
        hiredate = request.data.get('hiredate', None)
        rank = request.data.get('rank', None)
        birthday = request.data.get('birthday', None)
        gender = request.data.get('gender', None)
        sequence = request.data.get('sequence', None)
        marriage = request.data.get('marriage', None)
        is_staff = request.data.get('is_staff', True)
        role_type = request.data.get('role_type', AuthUser.ROLE_NORMAL)        

        if account_name and (account_name != user.account_name):
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       account_name=account_name,
                                       organization__is_active=True).exists(): 
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'msg': u'账户在本企业已存在'})

        #check user phone
        if phone and (phone != user.phone):
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'手机格式有误'})
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       phone=phone,
                                       organization__is_active=True).exists():  
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                                {'msg': u'手机已被使用'})
        #check user email
        if email and (email != user.email):
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'邮箱格式有误'})
            if AuthUser.objects.filter(organization_id=organization_id,
                                       is_active=True,
                                       email=email,
                                       organization__is_active=True).exists(): 
                    return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'邮箱已被使用'})
        #user entity          
        user.account_name = account_name
        user.nickname = nickname
        user.phone = phone
        user.email = email
        if password:
            user.password = password
        user.hiredate = hiredate
        user.rank_id = rank
        user.birthday = birthday
        user.gender_id = gender
        user.sequence_id = sequence
        user.marriage_id = marriage
        user.is_staff = is_staff
        user.role_type = role_type
        user.organization_id = organization_id

        try:
            user.save()
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        except Exception, e:
            logger.error("update %d error %s" % (user.id, e))
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_UPDATE_ERROR, {'msg': u'modification error'})

    def delete(self, request, *args, **kwargs):
        '''delete users profile'''
        user = self.get_object()
        user.is_active=False
        user.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

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
        if BaseOrganization.objects.filter_active(pk__in=org_ids,
                                                  users__is_active=True).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.WORKSPACE_ORG_MEMBEREXISTS)
        else:
            for org in BaseOrganization.objects.filter(id__in=org_ids):
                org.users.clear()   
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
    
