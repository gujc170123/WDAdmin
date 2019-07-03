# -*- coding:utf-8 -*-
from __future__ import unicode_literals
import hashlib
import base64
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
                          BaseOrganizationPaths, EnterpriseInfo
from wduser.serializers import EnterpriseBasicSerializer                          
from assessment.models import AssessProject, AssessSurveyRelation, AssessProjectSurveyConfig, \
                              AssessSurveyUserDistribute,AssessUser, AssessOrganization
from survey.models import Survey
from utils.cache.cache_utils import FileStatusCache
from rest_framework.views import APIView
from front.models import PeopleSurveyRelation
from assessment.tasks import send_survey_active_codes
from django.db import connection,transaction,connections
from django.conf import settings
from survey.models import Survey
from rest_framework.parsers import FileUploadParser
from tasks import userimport_task,CreateNewUser

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
        hiredate = convertempty2none(request.data.get('hiredate', None))
        rank = convertempty2none(request.data.get('rank', None))
        birthday = convertempty2none(request.data.get('birthday', None))
        gender = convertempty2none(request.data.get('gender', None))
        sequence = convertempty2none(request.data.get('sequence', None))
        marriage = convertempty2none(request.data.get('marriage', None))
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
                          role_type,is_staff,sequence,gender,birthday,rank,hiredate,marriage,
                          organization.id)

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
       
        
        alluser = AuthUser.objects.filter(is_active=True,organization__childorg__parent_id=org,organization__is_active=True,is_staff=True)
        if keyword:
            alluser = alluser.filter(Q(nickname__contains=keyword) | Q(phone__contains=keyword) | Q(email__contains=keyword))
        
        alluser = alluser.all().order_by('id','organization__id')
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
        hiredate = convertempty2none(request.data.get('hiredate', None))
        rank = convertempty2none(request.data.get('rank', None))
        birthday = convertempty2none(request.data.get('birthday', None))
        gender = convertempty2none(request.data.get('gender', None))
        sequence = convertempty2none(request.data.get('sequence', None))
        marriage = convertempty2none(request.data.get('marriage', None))
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
        user.hiredate = hiredate
        user.rank_id = rank
        user.birthday = birthday
        user.gender_id = gender
        user.sequence_id = sequence
        user.marriage_id = marriage
        user.is_staff = is_staff
        user.role_type = role_type
        user.organization_id = organization_id
        user.is_superuser = is_superuser

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
    model = EnterpriseInfo
    serializer_class = EnterpriseBasicSerializer

    def get(self, request, *args, **kwargs):
        enterprise_obj = self.get_object()
        if not enterprise_obj.enterprise_dedicated_link:
            id_str = "%10d" % enterprise_obj.id
            sha1 = hashlib.sha1()
            sha1.update(id_str)
            enterprise_dedicated_link = sha1.hexdigest()
            enterprise_obj.enterprise_dedicated_link = enterprise_dedicated_link
            enterprise_obj.save()

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,{'url':settings.CLIENT_HOST + "/#/enterprise" + "/" + str(enterprise_obj.enterprise_dedicated_link)})

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
        filecsv = request.FILES.get("file", None)
        enterprise_id = self.enterprise_id

        if not filecsv:
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {
            'data_index': -1,
            "data_msg": u'未检测到任何上传文件'
        })

        if filetype.upper()!='CSV':
            return general_json_response(status.HTTP_200_OK, ErrorCode.FAILURE, {
            'data_index': -1,
            "data_msg": u'请确认上传文件类型是否为csv'
        })

        result,errdata = userimport_task(filecsv,filename,enterprise_id,4,',')
        
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
        alluser = AuthUser.objects.filter(is_active=True,organization__childorg__parent_id=org,organization__is_active=True,is_staff=True)
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

    SURVEY_DISC = 89
    SURVEY_OEI = 147
    SURVEY_IEC = 163
    ASSESS_STA = 286

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
            AssessSurveyRelation.objects.create(assess_id=assess.id,survey_id=survey)
            if int(survey) == self.SURVEY_OEI:
                qs = AssessProjectSurveyConfig.objects.filter_active(survey_id=survey,
                                                                     assess_id=self.ASSESS_STA).all()
                for x in qs:
                    x.id = None
                    x.assess_id=assess.id
                AssessProjectSurveyConfig.objects.bulk_create(qs)

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,{'id':assess.id})
    
    def get(self, request, *args, **kwargs):
        assesses = AssessProject.objects.filter_active(enterprise_id=self.enterprise,has_distributed=True).order_by('-id')
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
                            b.assess_id=%s \
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
                            (SELECT b.parent_id id,count(f.people_id) staff,count(if(f.status=20,true,null)) completed\
                            From assessment_assessorganizationpathssnapshots b\
                            LEFT JOIN wduser_organization d\
                            on b.child_id=d.baseorganization_id and b.assess_id=b.assess_id\
                            LEFT JOIN wduser_peopleorganization e\
                            on d.identification_code=e.org_code and d.assess_id=b.assess_id\
                            LEFT JOIN " + frontname + ".front_peoplesurveyrelation f\
                            on e.people_id=f.people_id and f.project_id=b.assess_id and f.survey_id=%s\
                            WHERE b.parent_id=%s and b.assess_id=%s \
                            group by b.parent_id) b WHERE a.id=b.id"

            cursor.execute(sql_query, [survey,orgid,assess,])
            columns = [column[0] for column in cursor.description]
            result= dict(zip(columns, cursor.fetchone()))
        data = {"progress" : result}
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)