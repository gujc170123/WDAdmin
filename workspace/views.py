# -*- coding:utf-8 -*-
from __future__ import unicode_literals
import hashlib
import base64
import json
from urllib import quote
from django.db.models import F,Q
from django.contrib.auth import logout
from django.http import QueryDict
from rest_framework import status
from utils.views import AuthenticationExceptView, WdCreateAPIView, WdRetrieveUpdateAPIView ,\
                        WdDestroyAPIView, WdListCreateAPIView
from utils.response import general_json_response, ErrorCode
from rest_framework.response import Response
from wduser.user_utils import UserAccountUtils
from utils.logger import err_logger, info_logger
from workspace.helper import OrganizationHelper,convertempty2none
from workspace.serializers import UserSerializer,BaseOrganizationSerializer,AssessSerializer,\
                                  AssessListSerializer,SurveyListSerializer,UserDetailSerializer
from utils.regular import RegularUtils
from assessment.views import get_mima, get_random_char, get_active_code
from wduser.models import AuthUser, BaseOrganization, People, EnterpriseAccount, Organization, \
                          BaseOrganizationPaths, EnterpriseInfo, PeopleOrganization
from wduser.serializers import EnterpriseBasicSerializer                          
from assessment.models import AssessProject, AssessSurveyRelation, AssessProjectSurveyConfig, \
                              AssessSurveyUserDistribute,AssessUser, AssessOrganization
from survey.models import Survey
from utils.cache.cache_utils import FileStatusCache
from rest_framework.views import APIView
from front.models import PeopleSurveyRelation, SurveyInfo, SurveyQuestionInfo
from assessment.tasks import send_survey_active_codes
from django.db import connection,transaction,connections
from django.conf import settings
from survey.models import Survey
from rest_framework.parsers import FileUploadParser
from tasks import userimport_task,CreateNewUser
from workspace.models import PagePrivis,EnterpriseRole,RolePrivis
import pandas as pd

#retrieve logger entry for workspace app

class UserLoginView(AuthenticationExceptView, WdCreateAPIView):
    """Login API for Workspace"""

    model = AuthUser
    serializer_class = UserSerializer

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
        #retire unless user is enterprise admin
        if user.role_type < AuthUser.ROLE_ENTERPRISE:
            logout(request)
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ACCOUNT_NOT_FOUND)
        #retrieve UserInfo Serialization
        user_info = UserSerializer(instance=user, context=self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info.data)

class LogoutView(AuthenticationExceptView, WdCreateAPIView):
    u"""Web登出"""
    def post(self, request, *args, **kwargs):
        try:
            logout(request)
        except Exception, e:
            err_logger.error("web logout error, msg(%s)" % e)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class UserListCreateView(AuthenticationExceptView,WdCreateAPIView):
    """list/create person"""
    model = AuthUser
    serializer_class = UserSerializer    
    GET_CHECK_REQUEST_PARAMETER = ("organization_id",)

    def post(self, request, *args, **kwargs):
        pwd = request.data.get('password', None)
        phone = convertempty2none(request.data.get('phone', None))
        email = convertempty2none(request.data.get('email', None))
        nickname = convertempty2none(request.data.get('nickname', None))
        account_name = convertempty2none(request.data.get('account_name', None))
        organization_id = convertempty2none(request.data.get('organization', None))
        seniority = convertempty2none(request.data.get('seniority', None))
        rank = convertempty2none(request.data.get('rank', None))
        age = convertempty2none(request.data.get('age', None))
        gender = convertempty2none(request.data.get('gender', None))
        sequence = convertempty2none(request.data.get('sequence', None))
        marriage = convertempty2none(request.data.get('marriage', None))
        politics = convertempty2none(request.data.get('politics', None))
        education = convertempty2none(request.data.get('education', None))
        is_staff = request.data.get('is_staff', True)
        role_type = convertempty2none(request.data.get('role_type', AuthUser.ROLE_NORMAL))
        is_superuser = request.data.get('is_superuser', False)
        username = nickname + get_random_char(6)
        active_code = get_active_code()
        
        organization = BaseOrganization.objects.get(pk=organization_id)
        enterprise_id = organization.enterprise_id

        #check account_name not duplicated
        if account_name:
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
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
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
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
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
                                       is_active=True,
                                       email=email,
                                       organization__is_active=True).exists():  
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_EMAIL_USED_ERROR,
                                             {'msg': u'新增用户失败，邮箱已被使用'})
        if not email and not phone and not account_name:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'必须填写手机，工号，邮箱中任一项信息作为登录帐号'})
        try:
            user = CreateNewUser(username,account_name,nickname,pwd,phone,email,is_superuser,
                          role_type,is_staff,sequence,gender,age,rank,seniority,marriage,
                          politics,education,organization.id,enterprise_id)

            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {'id':user.id})
        except Exception, e:
            err_logger.error("新增用户失败 %s" % e.message)
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {'msg': u'新增用户失败:%s' % e.message})


    def get(self, request, *args, **kwargs):
        '''list users'''
        
        curPage = int(request.GET.get('curPage', '1'))
        pagesize = int(request.GET.get('pagesize', 20))
        pageType = str(request.GET.get('pageType', ''))
        org = request.GET.get('organization_id')
        keyword = str(request.GET.get('search',''))
        
        if pageType == 'pageDown':
            curPage += 1
        elif pageType == 'pageUp':
            curPage -= 1

        startPos = (curPage - 1) * pagesize
        endPos = startPos + pagesize
       
        
        alluser = AuthUser.objects.filter(is_active=True,organization__childorg__parent_id=org,organization__is_active=True,is_staff=True,role_type__gt=0)
        if keyword:
            alluser = alluser.filter(Q(account_name__contains=keyword) |Q(nickname__contains=keyword) | Q(phone__contains=keyword) | Q(email__contains=keyword))
        
        alluser = alluser.all().order_by('organization__id','-id')
        allUserCounts =alluser.count()
        if allUserCounts>0:
            if endPos>allUserCounts:
                startPos = (allUserCounts/pagesize)*pagesize
                endPos = allUserCounts
                curPage = allUserCounts/pagesize + 1
            users = UserSerializer(alluser[startPos:endPos],many=True)
            allPage = (allUserCounts+pagesize-1) / pagesize            
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"allPage":allPage, "curPage":curPage,"data":users.data })
        else:
            return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.NOT_EXISTED)
        
class UserDetailView(AuthenticationExceptView,WdRetrieveUpdateAPIView,WdDestroyAPIView):
    '''person detail management'''
    model = AuthUser
    serializer_class = UserDetailSerializer
    POST_CHECK_REQUEST_PARAMETER = ("organization",)    

    def post(self, request, *args, **kwargs):
        '''update user's profile, password ,email ,phone and organization'''
        user = self.get_object()

        phone = convertempty2none(request.data.get('phone', None))
        email = convertempty2none(request.data.get('email', None))
        account_name = convertempty2none(request.data.get('account_name', '').strip())
        nickname = convertempty2none(request.data.get('nickname', None))
        pwd = convertempty2none(request.data.get('password', None))
        password = get_mima(pwd) if pwd else None
        organization_id = convertempty2none(request.data.get('organization', None))
        seniority = convertempty2none(request.data.get('seniority', None))
        rank = convertempty2none(request.data.get('rank', None))
        age = convertempty2none(request.data.get('age', None))
        gender = convertempty2none(request.data.get('gender', None))
        sequence = convertempty2none(request.data.get('sequence', None))
        marriage = convertempty2none(request.data.get('marriage', None))
        politics = convertempty2none(request.data.get('politics', None))
        education = convertempty2none(request.data.get('education', None))        
        is_staff = request.data.get('is_staff', True)
        role_type = convertempty2none(request.data.get('role_type', AuthUser.ROLE_NORMAL))
        is_superuser = request.data.get('is_superuser', False)

        organization = BaseOrganization.objects.get(pk=organization_id)
        enterprise_id = organization.enterprise_id

        if account_name and (account_name != user.account_name):
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
                                       is_active=True,
                                       account_name=account_name,
                                       organization__is_active=True,
                                       ).exclude(id=user.id).exists(): 
                return general_json_response(status.HTTP_200_OK,
                                             ErrorCode.USER_ACCOUNT_NAME_ERROR,
                                             {'msg': u'工号在本企业已存在'})

        #check user phone
        if phone and (phone != user.phone):
            if not RegularUtils.phone_check(phone):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_REGUL_ERROR,
                                             {'msg': u'手机格式有误'})
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
                                       is_active=True,
                                       phone=phone,
                                       organization__is_active=True).exclude(id=user.id).exists():  
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                                {'msg': u'手机已被使用'})
        #check user email
        if email and (email != user.email):
            if not RegularUtils.email_check(email):
                return general_json_response(status.HTTP_200_OK, ErrorCode.USER_EMAIL_REGUL_ERROR,
                                             {'msg': u'邮箱格式有误'})
            if AuthUser.objects.filter(organization__enterprise_id=enterprise_id,
                                       is_active=True,
                                       email=email,
                                       organization__is_active=True).exclude(id=user.id).exists(): 
                    return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'邮箱已被使用'})
        if not email and not phone and not account_name:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_PHONE_USED_ERROR,
                                             {'msg': u'必须填写手机，工号，邮箱中任一项信息作为登录帐号'})
        #user entity
        user.account_name = account_name
        user.nickname = nickname
        user.phone = phone
        user.email = email
        if password:
            user.password = password
        user.seniority_id = seniority
        user.rank_id = rank
        user.age_id  = age
        user.gender_id = gender
        user.sequence_id = sequence
        user.marriage_id = marriage
        user.is_staff = is_staff
        user.role_type = role_type
        user.organization_id = organization_id
        user.is_superuser = is_superuser
        user.politics_id = politics
        user.education_id = education

        try:
            user.save()
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        except Exception, e:
            err_logger.error("update %d error %s" % (user.id, e))
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_UPDATE_ERROR, {'msg': u'modification error'})

    def delete(self, request, *args, **kwargs):
        '''delete users profile'''
        user = self.get_object()
        user.is_active=False
        user.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class AssessShareView(AuthenticationExceptView,WdCreateAPIView):
    model = AssessProject
    serializer_class = AssessSerializer

    def get_share_url(self,assess_id,distribute_type):
        project_id_bs64 = quote(base64.b64encode(str(assess_id)))
        if distribute_type == AssessProject.DISTRIBUTE_OPEN:
            return settings.CLIENT_HOST + '/people/join-project/?ba=%s&bs=0' % (project_id_bs64)
        else:
            return settings.CLIENT_HOST + '/people/anonymous/?ba=%s&bs=0' % (project_id_bs64)

    def get(self, request, *args, **kwargs):
        id = self.kwargs['pk']
        project = AssessProject.objects.get(id=id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,{'url':self.get_share_url(id,project.distribute_type)})

class UserBatchDeleteView(AuthenticationExceptView,WdDestroyAPIView):
    model = None
    serializer_class = None
    GET_CHECK_REQUEST_PARAMETER = ("users",)

    def post(self, request, *args, **kwargs):
        '''batch delete'''
        users = self.request.data.get("users")
        AuthUser.objects.filter(id__in=users.split(","),is_active=True,is_staff=True).update(is_active=False)

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class UserImportExportView(AuthenticationExceptView,WdCreateAPIView):

    POST_CHECK_REQUEST_PARAMETER = ("enterprise_id",)

    """organization template import/export"""
    def get_template(self):
        #todo
        """get template file"""

    def post(self, request, *args, **kwargs):
        self.parser_classes = (FileUploadParser,)
        filename = request.data["name"]
        filetype = filename.split('.')[-1]
        fileexcel = request.FILES.get("file", None)
        enterprise_id = self.enterprise_id

        if not fileexcel:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {
            'err_code': u'未检测到任何上传文件'
        })

        if filetype.upper()!='XLSX':
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {
            'err_code': u'请确认上传文件类型是否为xlsx格式'
        })

        result,errdata = userimport_task(fileexcel,filename,enterprise_id)
        
        if result:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {
                'err_code': errdata
            })

class OrganizationListCreateView(AuthenticationExceptView, WdCreateAPIView):
    """organization tree view"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer
    GET_CHECK_REQUEST_PARAMETER = {"organization_id"}
    POST_DATA_ID_RESPONSE=True
    
    def get(self, request, *args, **kwargs):
        """get organization tree of current user"""
        organizations = BaseOrganization.objects.filter_active(childorg__parent_id=self.organization_id).order_by('childorg__depth','id').\
                                                                values('id','name','parent_id').all()
                                                            
        nodes = {}
        for record in organizations:
            nodes[record['id']] = {'id':record['id'],'name':record['name'],'papa':record['parent_id']}
            nodes[record['id']]['children']=[]
        for record in organizations:
            if record['parent_id'] in nodes:
                nodes[record['parent_id']]['children'].append(nodes[record['id']])
            else:
                top = nodes[record['id']]
        for record in organizations:
            if len(nodes[record['id']]['children'])==0:
                nodes[record['id']].pop('children')
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": top})

class OrganizationListView(AuthenticationExceptView, WdCreateAPIView):
    """enterprise-organization tree view"""
    model = None
    serializer_class = None
    GET_CHECK_REQUEST_PARAMETER = {"enterprise_id"}
    
    def get(self, request, *args, **kwargs):
        """get organization tree of current user"""
        toporg = BaseOrganization.objects.filter_active(enterprise_id=self.enterprise_id,parent_id=0).first()
        if not toporg:
            return general_json_response(status.HTTP_200_OK, ErrorCode.NOT_EXISTED)

        organizations = BaseOrganization.objects.filter_active(childorg__parent_id=toporg.id).order_by('childorg__depth').\
                                                                values('id','name','parent_id').all()
                                                            
        nodes = {}
        for record in organizations:
            nodes[record['id']] = {'id':record['id'],'name':record['name'],'papa':record['parent_id']}
            nodes[record['id']]['children']=[]
        for record in organizations:
            if record['parent_id'] in nodes:
                nodes[record['parent_id']]['children'].append(nodes[record['id']])
            else:
                top = nodes[record['id']]
        for record in organizations:
            if len(nodes[record['id']]['children'])==0:
                nodes[record['id']].pop('children')
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": top})

class OrganizationlRetrieveUpdateDestroyView(AuthenticationExceptView,
                                             WdRetrieveUpdateAPIView, WdDestroyAPIView):
    """organization management"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer

    def delete(self, request, *args, **kwargs):
        
        org = self.get_id()

        if not BaseOrganization.objects.filter_active(id=org).first():
            return general_json_response(status.HTTP_200_OK, ErrorCode.NOT_EXISTED)

        #delete all organizations only when no active member exists
        alluser = AuthUser.objects.filter(is_active=True,organization__childorg__parent_id=org,organization__is_active=True).first()
        if alluser is None:
            BaseOrganization.objects.filter_active(childorg__parent_id=org).update(is_active=False)
            BaseOrganization.objects.get(pk=org)._closure_deletelink()
            info_logger.info('user_id %s want delete organization %s' % (self.request.user.id,org))
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        else:
            return general_json_response(status.HTTP_200_OK, ErrorCode.WORKSPACE_ORG_MEMBEREXISTS)

class OrganizationlUsersDestroyView(AuthenticationExceptView,WdDestroyAPIView):
    """organization management"""
    model = None
    serializer_class = None

    def delete(self, request, *args, **kwargs):
        
        org = self.get_id()

        if not BaseOrganization.objects.filter_active(id=org).first():
            return general_json_response(status.HTTP_200_OK, ErrorCode.NOT_EXISTED)

        #delete all organizations only when no active member exists
        alluser = AuthUser.objects.filter(is_active=True,organization__childorg__parent_id=org,organization__is_active=True,role_type__lt=300)
        alluser.update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class OrganizationImportExportView(AuthenticationExceptView):
    """organization template import/export"""
    def get_template(self):
        #todo
        """get template file"""

    def post(self, request, *args, **kwargs):
        #todo
        """import organization file"""

class AssessCreateView(AuthenticationExceptView, WdListCreateAPIView):
    '''create assess view'''
    model = AssessProject
    serializer_class = AssessSerializer

    POST_CHECK_REQUEST_PARAMETER = {"name","distribute_type","surveys","begin","end","enterprise"}
    POST_CHECK_NONEMPTYREQUEST_PARAMETER = {"name","distribute_type","surveys","begin","end","enterprise"}
    GET_CHECK_REQUEST_PARAMETER = {"enterprise"}

    def post(self, request, *args, **kwargs):
        name = request.data.get('name')
        distribute_type = request.data.get('distribute_type')
        begin_time = request.data.get('begin')
        end_time = request.data.get('end')
        enterprise = request.data.get('enterprise')
        surveys = request.data.get('surveys').split(",")
        assess = AssessProject.objects.create(name=name,
                                              distribute_type=distribute_type,
                                              begin_time = begin_time,
                                              end_time = end_time,
                                              enterprise_id=enterprise)

        for survey in surveys:
            AssessSurveyRelation.objects.create(assess_id=assess.id,survey_id=survey,people_view_report=True)
            qs = AssessProjectSurveyConfig.objects.filter_active(survey_id=survey,
                                                                    assess_id=0).all()
            qs2 = SurveyInfo.objects.filter_active(survey_id=survey,project_id=0).all()
            qs3 = SurveyQuestionInfo.objects.filter_active(survey_id=survey,project_id=0).all()                                                                    
            for x in qs:
                x.id = None
                x.assess_id=assess.id
            AssessProjectSurveyConfig.objects.bulk_create(qs)
            for y in qs2:
                y.id=None
                y.project_id = assess.id
                y.begin_time = assess.begin_time
                y.end_time = assess.end_time
                y.project_name = name
            SurveyInfo.objects.bulk_create(qs2)
            for z in qs3:
                z.id = None
                z.project_id = assess.id
            SurveyQuestionInfo.objects.bulk_create(qs3)              

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,{'id':assess.id})
    
    def get(self, request, *args, **kwargs):
        assesses = AssessProject.objects.filter_active(enterprise_id=self.enterprise).order_by('-id')
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,AssessListSerializer(assesses,many=True).data)

class SurveyListView(AuthenticationExceptView, WdListCreateAPIView):
    '''list survey view'''
    model = Survey
    serializer_class = SurveyListSerializer
    GET_CHECK_REQUEST_PARAMETER={"assess"}

    def get(self, request, *args, **kwargs):
        surveys = Survey.objects.filter_active(id__in=AssessSurveyRelation.objects.filter_active(assess_id=self.assess).values_list('survey_id'))
        surveyinfo = SurveyListSerializer(instance=surveys, many=True).data
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,surveyinfo)    

class AssessDetailView(AuthenticationExceptView, WdCreateAPIView):
    '''update/delete assess view'''
    model = AssessProject
    serializer_class = AssessSerializer

    def delete(self, request, *args, **kwargs):
        assess = self.get_object()
        assess.is_active = False
        assess.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class StdAssessListView(AuthenticationExceptView,WdCreateAPIView):
    model = AssessProject
    serializer_class = AssessSerializer

    POST_CHECK_REQUEST_PARAMETER = {"name","surveys","begin","end","user_id","orgid_list"}

    def post(self, request, *args, **kwargs):
        user_id = request.data.get('user_id')
        name = request.data.get('name')
        begin_time = request.data.get('begin')
        end_time = request.data.get('end')
        surveys = request.data.get('surveys').split(",")
        orgs = request.data.get('orgid_list')
        enterprise = self.kwargs['enterprise_id']
        anonymous = int(request.data.get('anonymous',0))
        distribute_type = AssessProject.DISTRIBUTE_OPEN
        if anonymous:
            distribute_type = AssessProject.DISTRIBUTE_ANONYMOUS

        assess = AssessProject.objects.create(name=name,
                                              distribute_type=distribute_type,
                                              begin_time=begin_time,
                                              end_time=end_time,
                                              enterprise_id=enterprise)

        for survey in surveys:
            AssessSurveyRelation.objects.create(assess_id=assess.id,survey_id=survey,people_view_report=True)
            qs = AssessProjectSurveyConfig.objects.filter_active(survey_id=147,
                                                                    assess_id=0).all()
            qs2 = SurveyInfo.objects.filter_active(survey_id=survey,project_id=0).all()
            qs3 = SurveyQuestionInfo.objects.filter_active(survey_id=survey,project_id=0).all()
            for x in qs:
                x.id = None
                x.survey_id=survey
                x.assess_id=assess.id
            AssessProjectSurveyConfig.objects.bulk_create(qs)
            for y in qs2:
                y.id=None
                y.project_id = assess.id
                y.begin_time = assess.begin_time
                y.end_time = assess.end_time
                y.project_name = name
                if anonymous:
                    config = json.loads(y.config_info)
                    config['test_type']=SurveyInfo.TEST_TYPE_BY_QUESTION
                    y.config_info = json.dumps(config)
            SurveyInfo.objects.bulk_create(qs2)
            for z in qs3:
                z.id = None
                z.project_id = assess.id
            SurveyQuestionInfo.objects.bulk_create(qs3)

        with connection.cursor() as cursor:
            ret = cursor.callproc("StdAssess_Save", (assess.enterprise_id,assess.id,user_id,orgs,))

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,{'id':assess.id})


class StdAssessManageView(AuthenticationExceptView,WdCreateAPIView,WdDestroyAPIView,WdRetrieveUpdateAPIView):
    model = AssessProject
    serializer_class = AssessSerializer

    def get_share_url(self,assess_id,distribute_type):
        project_id_bs64 = quote(base64.b64encode(str(assess_id)))
        if distribute_type == AssessProject.DISTRIBUTE_OPEN:
            return settings.CLIENT_HOST + '/people/join-project/?ba=%s&bs=0' % (project_id_bs64)
        else:
            return settings.CLIENT_HOST + '/people/anonymous/?ba=%s&bs=0' % (project_id_bs64)

    def post(self, request, *args, **kwargs):
        assess_id = self.kwargs['assess_id']
        user_id = self.request.data.get("user_id")
        assess = AssessProject.objects.get(pk=assess_id)
        if assess.has_distributed:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE,{'msg': u'已发布的调研不可重复发布'})
        assess.has_distributed=True
        assess.save()        
        with connection.cursor() as cursor:
            ret = cursor.callproc("StdAssess_Confirm", (assess.enterprise_id,assess_id,user_id,))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,{'url':self.get_share_url(assess_id,assess.distribute_type)})
    
    def delete(self, request, *args, **kwargs):
        assess_id = self.kwargs['assess_id']
        Organization.objects.filter(assess_id=assess_id).delete()
        AssessOrganization.objects.filter(assess_id=assess_id).delete()
        AssessUser.objects.filter(assess_id=assess_id).delete()
        AssessProject.objects.filter(pk=assess_id).delete()
        
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def put(self, request, *args, **kwargs):
        assess_id = self.kwargs['assess_id']
        user_id = self.request.data.get("user_id")
        end_time = request.data.get('end')
        AssessProject.objects.filter(pk=assess_id).update(end_time=end_time,last_modify_user_id=user_id)
        SurveyInfo.objects.filter_active(project_id=assess_id).update(end_time=end_time,last_modify_user_id=user_id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class AssessSurveyRelationDistributeView(AuthenticationExceptView,WdCreateAPIView):

    model = AssessSurveyRelation
    POST_CHECK_REQUEST_PARAMETER = ("enterprise_id","user_id","org_ids" )

    def distribute_normal(self,assess_id,enterprise_id,user_id,orgid_list):

        #copy base organization into assess organization
        with connection.cursor() as cursor:
            ret = cursor.callproc("DistributeAssess", (enterprise_id,assess_id,user_id,orgid_list,))

        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        self.assessment = AssessProject.objects.get(id=self.kwargs.get('pk'))
        assess_id = self.assessment.id
        enterprise_id = self.request.data.get("enterprise_id")
        user_id = self.request.data.get("user_id")
        orgid_list = self.request.data.get("org_ids")
        rst_code = self.distribute_normal(assess_id,enterprise_id,user_id,orgid_list)
        return general_json_response(status.HTTP_200_OK, rst_code)

class AssessOrganizationView(AuthenticationExceptView,WdCreateAPIView):
    """assess organization tree view"""
    model = BaseOrganization
    serializer_class = BaseOrganizationSerializer
    GET_CHECK_REQUEST_PARAMETER = {"assess","organization_id"}
    
    def get(self, request, *args, **kwargs):
        """get organization tree of current user"""
        organizations = BaseOrganization.objects.raw("SELECT a.id,a.parent_id,a.name,if(c.id is null,False,True) is_active FROM wduser_baseorganization a\
                                                      INNER JOIN assessment_assessorganizationpathssnapshots b\
                                                      ON b.child_id=a.id\
                                                      LEFT JOIN assessment_assessjoinedorganization c\
                                                      ON a.id=c.organization_id and c.assess_id=b.assess_id\
                                                      WHERE b.assess_id=%s AND b.parent_id=%s",[self.assess,self.organization_id])

        if not list(organizations):
            return general_json_response(status.HTTP_200_OK, ErrorCode.NOT_EXISTED)
        nodes = {}
        for record in organizations:
            nodes[record.id] = {'id':record.id,'name':record.name,'papa':record.parent_id,'enable':record.is_active}
            nodes[record.id]['children']=[]
        for record in organizations:
            if record.parent_id in nodes:
                nodes[record.parent_id]['children'].append(nodes[record.id])
            else:
                top = nodes[record.id]
        for record in organizations:
            if len(nodes[record.id]['children'])==0:
                nodes[record.id].pop('children')
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": top})

class AssessProgressView(AuthenticationExceptView,WdCreateAPIView):

    model = None
    serializer_class = None

    def get(self, request, *args, **kwargs):
        orgid =  request.GET.get('organization')
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')

        frontname = settings.DATABASES['front']['NAME']
        with connection.cursor() as cursor:
            sql_query = "SELECT b.*,a.name FROM wduser_baseorganization a,\
                            (SELECT b.child_id id,count(f.people_id) staff,count(if(f.status=20,true,null)) completed\
                            From assessment_assessorganizationpathssnapshots b\
                            INNER JOIN assessment_assessorganizationpathssnapshots c\
                            on c.parent_id=b.child_id\
                            LEFT JOIN wduser_organization d\
                            on c.child_id=d.baseorganization_id and c.assess_id=b.assess_id\
                            LEFT JOIN wduser_peopleorganization e\
                            on d.identification_code=e.org_code and d.assess_id=b.assess_id\
                            LEFT JOIN " + frontname + ".front_peoplesurveyrelation f\
                            on e.people_id=f.people_id and f.project_id=b.assess_id and f.survey_id=%s\
                            WHERE b.parent_id=%s and b.depth=1 and\
                            b.assess_id=%s and f.is_active=True \
                            group by b.child_id) b WHERE a.id=b.id"
            cursor.execute(sql_query, [survey,orgid,assess,])
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
        data = {"progress" : results}
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)

class AssessProgressTotalView(AuthenticationExceptView,APIView):

    def get(self, request, *args, **kwargs):
        orgid =  request.GET.get('organization')
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')

        frontname = settings.DATABASES['front']['NAME']

        with connection.cursor() as cursor:
            sql_query = "SELECT b.*,a.name FROM wduser_baseorganization a,\
                            (SELECT b.parent_id id,count(f.people_id) staff,count(if(f.status=20,true,null)) j completed\
                            From assessment_assessorganizationpathssnapshots b\
                            LEFT JOIN wduser_organization d\
                            on b.child_id=d.baseorganization_id and b.assess_id=b.assess_id\
                            LEFT JOIN wduser_peopleorganization e\
                            on d.identification_code=e.org_code and d.assess_id=b.assess_id\
                            LEFT JOIN " + frontname + ".front_peoplesurveyrelation f\
                            on e.people_id=f.people_id and f.project_id=b.assess_id and f.survey_id=%s\
                            WHERE b.parent_id=%s and b.assess_id=%s and f.is_active=True \
                            group by b.parent_id) b WHERE a.id=b.id"

            cursor.execute(sql_query, [survey,orgid,assess,])
            columns = [column[0] for column in cursor.description]
            result= dict(zip(columns, cursor.fetchone()))
        data = {"progress" : result}
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)


class ManagementAssess(AuthenticationExceptView,WdCreateAPIView):
    """
    测评管理
    """

    def get(self, request, ass):
        curPage = int(request.GET.get('curPage', 1))
        pagesize = int(request.GET.get('pagesize', 20))
        pageType = str(request.GET.get('pageType', ''))
        org = request.GET.get('organization_id')
        keyword = str(request.GET.get('search',''))
        keyword2 = request.GET.get('onlynotjoined',False)
        order = str(request.GET.get('order',"child_id,joined,nickname,email,phone"))
        if not order:
            order = "child_id,joined,nickname,email,phone"
        
        if pageType == 'pageDown':
            curPage += 1
        elif pageType == 'pageUp':
            curPage -= 1

        startPos = (curPage - 1) * pagesize
        endPos = startPos + pagesize
        allPage = 0

        frontname = settings.DATABASES['front']['NAME']
        sql_query =  "select c.id,e.name organization,c.nickname,c.account_name,c.email,c.phone,not isnull(d.user_id) joined,\
                    d1.value age,d2.value education,d3.value politics,d4.value seniority \
                    from assessment_assessorganizationpathssnapshots a\
                    inner join assessment_assessjoinedorganization b\
                    on a.child_id=b.organization_id\
                    and a.assess_id=b.assess_id\
                    inner join wduser_authuser c\
                    on c.organization_id=a.child_id\
                    left join (select user_id from assessment_assessuser a1,\
                    wduser_people a2 where a1.people_id=a2.id and assess_id=" + str(ass) + ") d\
                    on c.id=d.user_id\
                    left join wduser_dim_age d1\
                    on c.age_id=d1.id\
                    left join wduser_dim_education d2\
                    on c.education_id=d2.id\
                    left join wduser_dim_politics d3\
                    on c.politics_id=d3.id\
                    left join wduser_dim_seniority d4\
                    on c.seniority_id=d4.id\
                    inner join wduser_baseorganization e\
                    on a.child_id=e.id\
                    where a.parent_id=" + org + " and a.assess_id="+ ass+ "\
                    and c.is_active=true and c.is_staff=true and c.role_type>0"
        if keyword2:
            sql_query += " and d.user_id is null "
        if keyword:
            sql_query += " and (c.nickname like '%" + keyword + "%' or c.account_name  like '%" + keyword + "%' or c.email like '%" + keyword +  "%' or c.phone like '%" + keyword + "%')"
        sql_query += " order by " + order + " limit " + str(startPos) + ","+ str(endPos)
        sql_query_aggregate = "select count(1)\
                                from assessment_assessorganizationpathssnapshots a\
                                inner join assessment_assessjoinedorganization b\
                                on a.child_id=b.organization_id\
                                and a.assess_id=b.assess_id\
                                inner join wduser_authuser c\
                                on c.organization_id=a.child_id\
                                left join (select user_id from assessment_assessuser a1,\
                                wduser_people a2 where a1.people_id=a2.id and assess_id=" + str(ass) + ") d\
                                on c.id=d.user_id\
                                where c.is_active=true and c.is_staff=true and c.role_type>0 and a.parent_id=" + org + " and a.assess_id="+ ass
        if keyword2:
            sql_query_aggregate += " and d.user_id is null "                                
        if keyword:
            sql_query_aggregate += r" and (c.nickname like '%" + keyword + r"%' or c.email like '%" + keyword +  r"%' or c.phone like '%" + keyword + r"%')"
        with connection.cursor() as cursor:
            cursor.execute(sql_query_aggregate)
            allPage = (cursor.fetchone()[0] +pagesize-1) / pagesize
            cursor.execute(sql_query)
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"allPage":allPage, "curPage":curPage,"data":results })

    def post(self, request, ass):
        modify_pid = request.data.get("pid",None)
        org = request.data.get('organization_id',None)

        if modify_pid:
            modify_pid = set(list(map(int,modify_pid.split(","))))

        surveys = SurveyInfo.objects.filter_active(project_id=ass)
        sql_query =  "select f.id as pid,c.id as user_id,g.identification_code\
                    from assessment_assessorganizationpathssnapshots a\
                    inner join assessment_assessjoinedorganization b\
                    on a.child_id=b.organization_id\
                    and a.assess_id=b.assess_id\
                    inner join wduser_authuser c\
                    on c.organization_id=a.child_id\
                    left join (select user_id from assessment_assessuser a1,\
                    wduser_people a2 where a1.people_id=a2.id and assess_id=" + str(ass) + ") d\
                    on c.id=d.user_id\
                    inner join wduser_baseorganization e\
                    on a.child_id=e.id\
                    inner join wduser_people f\
                    on c.id=f.user_id\
                    inner join wduser_organization g\
                    on e.id=g.baseorganization_id\
                    where a.parent_id=" + org + " and a.assess_id="+ ass+ "\
                    and c.is_active=true and c.is_staff=true and c.role_type>0 and d.user_id is null and f.is_active=true"
        results = {}
        userorgrelations = {}
        user_toadd = set()
        with connection.cursor() as cursor:
            cursor.execute(sql_query)
            for row in cursor.fetchall():
                user_toadd.add(row[1])
                results[row[1]]=row[0]
                userorgrelations[row[1]]=row[2]

        if modify_pid:
            user_toadd = user_toadd & modify_pid

        i = True
        people_survey = []
        people_organization = []
        survey_user = []        

        for uid in user_toadd:
            people_organization.append(
                    PeopleOrganization(
                        people_id=results[uid],org_code=userorgrelations[uid]
                    )
                )        
        for survey in surveys:
            for uid in user_toadd:
                people_survey.append(
                    PeopleSurveyRelation(
                        people_id=results[uid],survey_id=survey.survey_id, project_id=ass, survey_name=survey.survey_name
                    )
                )                
                if i:                    
                    survey_user.append(
                        AssessUser(
                            assess_id=ass,people_id=results[uid],role_type=10,role_people_id=0
                        )
                    )
            i = False
        PeopleOrganization.objects.bulk_create(people_organization)
        PeopleSurveyRelation.objects.bulk_create(people_survey)
        AssessUser.objects.bulk_create(survey_user)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class AssessProgressTreeView(AuthenticationExceptView,WdCreateAPIView):

    model = None
    serializer_class = None

    def get(self, request, *args, **kwargs):
        orgid =  request.GET.get('organization')
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')

        frontname = settings.DATABASES['front']['NAME']
        with connection.cursor() as cursor:
            sql_query ="""
            SELECT a.id,a.parent_id,a.name,if(c.id is null,False,True) is_active,
            ifnull(d.staff,0) staff,ifnull(d.completed,0) completed,
            if(ifnull(d.staff,0)<0,null,ifnull(d.completed,0)/ifnull(d.staff,0)) as ratio
            FROM wduser_baseorganization a
            INNER JOIN assessment_assessorganizationpathssnapshots b
            ON b.child_id=a.id
            LEFT JOIN assessment_assessjoinedorganization c
            ON a.id=c.organization_id and c.assess_id=b.assess_id
            left join 
            (select a.parent_id,count(c.people_id) as staff,count(d.id) as completed from 
            assessment_assessorganizationpathssnapshots a
            inner join wduser_organization b
            on a.child_id=b.baseorganization_id
            inner join wduser_peopleorganization c
            on c.org_code=b.identification_code
            left join """ + frontname + """.front_peoplesurveyrelation d
            on c.people_id=d.people_id and d.status=20 and d.survey_id=%s
            where a.assess_id=%s and c.is_active=True and b.is_active=True
            group by a.parent_id) d
            on a.id=d.parent_id
            WHERE b.assess_id=%s AND b.parent_id=%s
            """
            cursor.execute(sql_query, [survey,assess,assess,orgid,])
            columns = [column[0] for column in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(row)

        if not results:
            return general_json_response(status.HTTP_200_OK, ErrorCode.NOT_EXISTED)
        nodes = {}
        for record in results:
            nodes[record[0]] = {'id':record[0],'name':record[2],'papa':record[1],'enable':record[3],'staff':record[4],'completed':record[5],'ratio':record[6]}
            nodes[record[0]]['children']=[]
        for record in results:
            if record[1] in nodes:
                nodes[record[1]]['children'].append(nodes[record[0]])
            else:
                top = nodes[record[0]]
        for record in results:
            if len(nodes[record[0]]['children'])==0:
                nodes[record[0]].pop('children')
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"data": top})

class OrganizationAnswerSheetView(AuthenticationExceptView,WdCreateAPIView):

    def get(self, request, *args, **kwargs):
        orgid =  request.GET.get('organization')
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')
        profiles = request.GET.get('profiles')
        
        questions = {'question_id':[],'question_text':[],'No':[],'option_id':[],'label':[],'option':[]}
        questions_keys = {'question_id':[],'option_id':[],}
        question_id = 0
        blockquery = SurveyQuestionInfo.objects.filter_active(project_id=assess,survey_id=survey).order_by('block_id')        
        import json
        for block in blockquery:
            info = json.loads(block.question_info)
            for question in info:
                question_id += 1
                # multichoice(10,11,30,31)
                if question['question_type'] in (10,11,30,31):
                    for option in question['options']['option_data']:
                        questions['question_id'].append(question['id'])
                        questions['option_id'].append(option['id'])
                        questions['No'].append(question_id)
                        questions['question_text'].append(question['title'])
                        questions['label'].append(chr(65+option['order_number']))
                        questions['option'].append(option['content'])
                        # with blanket
                        if option['is_blank']:
                            questions['question_id'].append(question['id'])
                            questions['option_id'].append(-option['id'])
                            questions['No'].append(question_id)
                            questions['question_text'].append(None)
                            questions['label'].append(None)
                            questions['option'].append(None)
                # matrix select
                elif  question['question_type']==50:
                    for option in question['options']['options']:
                        questions['question_id'].append(question['id'])
                        questions['option_id'].append(option['id'])
                        questions['No'].append(question_id)
                        questions['question_text'].append(question['title'])
                        questions['label'].append(chr(65+option['order_number']))
                        questions['option'].append(option['content'])
                # slider (60, 80)
                elif question['question_type'] in (60,80):
                    questions['question_id'].append(question['id'])
                    questions['option_id'].append(0)
                    questions['No'].append(question_id)
                    questions['question_text'].append(question['title'])
                    questions['label'].append(None)
                    questions['option'].append(None)
        frontname = settings.DATABASES['front']['NAME']
        strsqlPeopleQuery = """
                            select d.people_id
                            from assessment_assessorganizationpathssnapshots a
                            inner join assessment_assessjoinedorganization b
                            on a.child_id=b.organization_id
                            and a.assess_id=b.assess_id
                            inner join wduser_organization c
                            on c.baseorganization_id=a.child_id
                            inner join wduser_peopleorganization d
                            on d.org_code=c.identification_code
                            inner join """ + frontname +""".front_peoplesurveyrelation e
                            on d.people_id=e.people_id
                            and b.assess_id=e.project_id
                            where a.assess_id=%s
                            and e.survey_id=%s
                            and a.parent_id=%s
                            and e.is_active=true
                            and d.is_active=true
        """
        strsqlAnswerQuery = """
                            select d.people_id as pid,f.question_id as qid,answer_id,answer_score
                            from assessment_assessorganizationpathssnapshots a
                            inner join assessment_assessjoinedorganization b
                            on a.child_id=b.organization_id
                            and a.assess_id=b.assess_id
                            inner join wduser_organization c
                            on c.baseorganization_id=a.child_id
                            inner join wduser_peopleorganization d
                            on d.org_code=c.identification_code
                            inner join """ + frontname +""".front_peoplesurveyrelation e
                            on d.people_id=e.people_id
                            and b.assess_id=e.project_id
                            inner join """ + frontname +""".front_userquestionanswerinfo f
                            on e.people_id=f.people_id
                            and b.assess_id=f.project_id
                            and f.survey_id=e.survey_id
                            where a.assess_id=%s
                            and e.survey_id=%s
                            and a.parent_id=%s
                            and e.is_active=true
                            and f.is_active=true
                            and d.is_active=true
        """
        import pandas as pd
        question_frame = pd.DataFrame.from_dict(questions)
        people_frame = pd.read_sql_query(strsqlPeopleQuery,connection,params=[assess,survey,orgid])
        answers_frame = pd.read_sql_query(strsqlAnswerQuery,connection,params=[assess,survey,orgid])
        question_frame['tmp'] = 1
        people_frame['tmp'] = 1
        merged_main_frame = people_frame.merge(question_frame,how='outer',on='tmp')
        merged_main_frame = merged_main_frame.drop('tmp', axis=1)
        merged_main_frame = merged_main_frame.merge(answers_frame,how='left',left_on=['people_id','question_id','option_id'],right_on=['pid','qid','answer_id'])
        merged_main_frame = merged_main_frame.drop(['pid','qid','answer_id','question_id','option_id','option',''], axis=1)
        merged_main_frame = merged_main_frame.set_index(['people_id','No','label'])
        merged_main_frame = merged_main_frame.unstack([1,2])
        import datetime
        filename = datetime.datetime.now().strftime('%Y%m%d%H%M%S') + ".xls"
        merged_main_frame.to_excel(filename)
        from django.http.response import HttpResponse
        from django.utils.encoding import escape_uri_path
        content =  ErrorCode.SUCCESS
        response = HttpResponse(content, content_type='application/octet-stream')
        response['Content-Disposition'] = "attachment; filename*=utf-8''{}".format(escape_uri_path(filename))
        return response

# todo point view
class OrganizationPointSheetView(AuthenticationExceptView,WdCreateAPIView):
    def get(self, request, *args, **kwargs):
        orgid =  request.GET.get('organization')
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')

        frontname = settings.DATABASES['front']['NAME']
        sql_query = "select a.people_id,b.tag_value ,sum(a.score) as score, avg(answer_time) as answer_time from\
            (select question_id,answer_score score, answer_time\
            from " + frontname + ".front_peoplesurveyrelation a,\
            " + frontname + ".front_userquestionanswerinfo b\
            where  a.id=%s and a.survey_id=b.survey_id and a.people_id=b.people_id\
            and a.project_id=b.project_id and a.is_active=true and b.is_active=true) a,research_questiontagrelation b\
            where a.question_id=b.object_id and b.tag_id=54\
            and b.is_active=True group by b.tag_value"
        
        with connection.cursor() as cursor:
            cursor.execute(sql_query, [personal_result_id])
            columns = [col[0] for col in cursor.description]
            dictscore = {}
            for row in cursor.fetchall():
                if dictscore.has_key(row[0]):
                    dictscore[row[0]]=dictscore[row[0]]+row[1]
                else:
                    dictscore[row[0]]=row[1]

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, None)

# todo sheet view
class UserAnswerSheetView(AuthenticationExceptView,WdCreateAPIView):
    
    def get(self, request, *args, **kwargs):
        orgid =  request.GET.get('user')
        survey =  request.GET.get('survey')
        assess =  self.kwargs.get('pk')

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, None)

class RolePrivisView(APIView):

    def get(self, request, enterprise, role):
                
        roleprivis = RolePrivis.objects.filter(Role__Enterprise=enterprise,Role__Code=role)
        if not roleprivis:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, None)               
        valuemap = {'c':4,'r':3,'u':2,'d':1,'a':0}
        ret = {} 
        for privis in roleprivis:
            ret[privis.ContentType_id] = {} 
            for key, value in valuemap.items():
                ret[privis.ContentType_id][key] = bool((privis.Value & (1 << value)) >> value)

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,ret)
        
    def post(self, request, enterprise, role):

        data = request.data.copy()
        if not data:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, None)
        valuemap = {'c':4,'r':3,'u':2,'d':1,'a':0}
        roleprivis = RolePrivis.objects.filter(Role__Enterprise=enterprise,Role__Code=role)
        for privis in roleprivis:
            res = 0
            for key, value in valuemap.items():
                res += int(data[str(privis.ContentType_id)][key]) << value
            privis.Value = res
            privis.save()

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)            

class GrantPagePrivisView(APIView):

    def get(self, request, enterprise, role):
        pagename = request.GET.get('pagename',None)
        if not pagename:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT, None)
        pageprivis = PagePrivis.objects.filter(Name=pagename)
        
        # Temporary Compatiablity
        if not pageprivis:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, None)
        contents = RolePrivis.objects.filter(Role__Enterprise=enterprise,Role__Code=role)
        if not contents:
            return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, None)

        PageFunctionDict = {}
        for pageprivi in pageprivis:
            PageFunctionDict[pageprivi.Function] = False

        for content in contents:
            for pageprivi in pageprivis:
                if content.ContentType_id == pageprivi.ContentType_id:
                    if (content.Value & pageprivi.Value)>0:
                        PageFunctionDict[pageprivi.Function] = True        
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, PageFunctionDict)