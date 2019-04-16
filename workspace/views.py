# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from rest_framework import status
from utils.views import AuthenticationExceptView, WdCreateAPIView, WdRetrieveUpdateAPIView ,\
                        WdDestroyAPIView, WdListCreateAPIView
from utils.response import general_json_response, ErrorCode
from wduser.user_utils import UserAccountUtils
from utils.logger import get_logger
from workspace.helper import OrganizationHelper
from workspace.serializers import UserSerializer,BaseOrganizationSerializer,AssessSerializer
from utils.regular import RegularUtils
from assessment.views import get_mima, get_random_char, get_active_code
from wduser.models import AuthUser, BaseOrganization, People, EnterpriseAccount
from assessment.models import AssessProject, AssessSurveyRelation, AssessProjectSurveyConfig, \
                              AssessSurveyUserDistribute,AssessUser
from front.models import PeopleSurveyRelation
from assessment.tasks import send_survey_active_codes

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
            user = AuthUser.objects.create(
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

            #create people object
            people = People.objects.create(user_id=user.id, 
                                           username=account_name, 
                                           phone=phone,
                                           email=email)
            #create enterprise-account object
            EnterpriseAccount.objects.create(user_id=id,
                                             people_id=people.id,
                                             account_name=account_name,
                                             enterprise_id=enterprise_id)

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

class AssessCreateView(AuthenticationExceptView, WdCreateAPIView):
    '''create assess view'''
    model = AssessProject
    serializer_class = AssessSerializer

    SURVEY_DISC = 89
    SURVEY_OEI = 147
    SURVEY_IEC = 163
    ASSESS_STA = 286

    def post(self, request, *args, **kwargs):
        name = request.data.get('name', None)
        distribute_type = request.data.get('distribute_type', None)
        surveys = request.data.getlist('surveys')                
        assess = AssessProject.objects.create(name=name,
                                              distribute_type=distribute_type)

        for survey in surveys:
            AssessSurveyRelation.objects.create(assess_id=assess.id,survey_id=survey)
            if survey == SURVEY_OEI:
                qs = AssessProjectSurveyConfig.objects.filter_active(survey_id=survey,
                                                                     assess_id=ASSESS_STA)
                qs_new = copy.copy(qs)
                for x in qs_new:
                    x.id = None
                    x.assess_id=assess.id
                AssessProjectSurveyConfig.objects.bulk_create(qs_new)

        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class AssessDetailView(AuthenticationExceptView, WdCreateAPIView):
    '''update/delete assess view'''
    model = AssessProject
    serializer_class = AssessSerializer

    def delete(self, request, *args, **kwargs):
        assess = self.get_object()
        assess.is_active = False
        assess.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

class AssessSurveyRelationDistributeView(WdListCreateAPIView):
    u"""
    项目与问卷的分发信息
    @GET: 查看关联的问卷分发信息
    @POST：分发按钮

    @version: 20180725 分发
    @GET：查看项目的分发信息
    @POST: 分发按钮
    """
    model = AssessSurveyRelation
    POST_CHECK_REQUEST_PARAMETER = ("assess_id", )
    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )

    def get_all_survey_finish_people_count(self, finish_people_ids, assess_id):
        not_finish_count = PeopleSurveyRelation.objects.filter_active(project_id=assess_id,
                                                                      people_id__in=finish_people_ids,
                                                                      status__in=[
                                                                          PeopleSurveyRelation.STATUS_NOT_BEGIN,
                                                                          PeopleSurveyRelation.STATUS_DOING,
                                                                          PeopleSurveyRelation.STATUS_DOING_PART,
                                                                          PeopleSurveyRelation.STATUS_EXPIRED
                                                                      ]
                                                                      ).values_list(
            "people_id", flat=True).distinct().count()
        f_count = len(finish_people_ids) - not_finish_count
        return f_count

    def get_doing_survey_people_count(self, people_ids, assess_id):
        beign_count = PeopleSurveyRelation.objects.filter_active(project_id=assess_id,
                                                                      people_id__in=people_ids,
                                                                      status__in=[
                                                                          PeopleSurveyRelation.STATUS_FINISH,
                                                                          PeopleSurveyRelation.STATUS_DOING_PART
                                                                      ]
                                                                      ).values_list(
            "people_id", flat=True).distinct().count()
        not_count = len(people_ids) - beign_count
        return not_count

    def send_active_code(self, people_ids):
        send_survey_active_codes.delay(people_ids)

    def distribute360(self):
        role_surveys = AssessSurveyRelation.objects.filter_active(
            assess_id=self.assess_id).values("role_type", "survey_id")
        role_survey_map = dict()
        for role_survey in role_surveys:
            role_survey_map[role_survey["role_type"]] = role_survey["survey_id"]
        assess_users = AssessUser.objects.filter_active(
            assess_id=self.assess_id, role_type=AssessUser.ROLE_TYPE_SELF
        )
        new_distribute_people_ids = []
        for assess_user in assess_users:
            evaluated_people = People.objects.get(id=assess_user.people_id)
            for role_types in AssessUser.ROLE_CHOICES:
                role_type = role_types[0]
                if role_type == AssessUser.ROLE_TYPE_NORMAL:
                    continue
                if role_type in role_survey_map:
                    survey_id = role_survey_map[role_type]
                else:
                    return ErrorCode.PROJECT_SURVEY_RELATION_VALID
                survey = Survey.objects.get(id=survey_id)
                distribute_users = AssessSurveyUserDistribute.objects.filter_active(
                    assess_id=self.assess_id, evaluated_people_id=evaluated_people.id,
                    role_type=role_type, survey_id=survey_id
                )
                has_distribute = distribute_users.exists()
                if has_distribute:
                    distribute_user_ids = json.loads(
                        distribute_users.values_list("people_ids", flat=True)[0])
                else:
                    distribute_user_ids = []
                role_people_ids = AssessUser.objects.filter_active(
                    assess_id=self.assess_id, people_id=evaluated_people.id, role_type=role_type
                ).values_list("role_people_id", flat=True)

                people_survey_list = []
                for people_id in role_people_ids:
                    if people_id not in distribute_user_ids:
                        survey_name = survey.title
                        if role_type != AssessUser.ROLE_TYPE_SELF:
                            survey_name = u"%s(评价%s)" %(survey.title, evaluated_people.username)
                        people_survey_list.append(PeopleSurveyRelation(
                            people_id=people_id,
                            survey_id=survey_id,
                            project_id=self.assess_id,
                            survey_name=survey_name,
                            role_type=role_type,
                            evaluated_people_id=evaluated_people.id

                        ))
                        distribute_user_ids.append(people_id)
                        if people_id not in new_distribute_people_ids:
                            new_distribute_people_ids.append(people_id)
                PeopleSurveyRelation.objects.bulk_create(people_survey_list)
                if has_distribute:
                    distribute_users.update(people_ids=json.dumps(distribute_user_ids))
                else:
                    AssessSurveyUserDistribute.objects.create(
                        assess_id=self.assess_id, survey_id=survey_id,
                        people_ids=json.dumps(distribute_user_ids),
                        evaluated_people_id=evaluated_people.id,
                        role_type=role_type
                    )
        self.send_active_code(new_distribute_people_ids)
        return ErrorCode.SUCCESS

    def distribute_normal(self):
        def get_random_survey_distribute_info(assess_id, random_survey_qs):
            random_survey_ids = random_survey_qs.values_list("survey_id", flat=True)
            random_survey_total_ids = []
            for random_survey_id in random_survey_ids:
                asud_qs = AssessSurveyUserDistribute.objects.filter_active(
                    assess_id=assess_id, survey_id=random_survey_id
                )
                if asud_qs.exists():
                    d_user_ids = json.loads(asud_qs[0].people_ids)
                    if type(d_user_ids) != list:
                        d_user_ids = []
                    random_survey_total_ids.extend(d_user_ids)
            return random_survey_total_ids

        def polling_survey(random_num, random_index, polling_list):
            y = random_num * random_index % len(polling_list)
            his_survey_list = polling_list[y:y + random_num]
            if y + random_num > len(polling_list):
                his_survey_list += polling_list[0: (random_num - (len(polling_list) - y))]
            return his_survey_list, random_index + 1

        assess_id = self.assess_id
        people_ids = self.request.data.get("ids", None)
        if not people_ids:
            people_ids = AssessUser.objects.filter_active(assess_id=assess_id).values_list("people_id", flat=True).distinct()
            if not people_ids:
                return ErrorCode.ORG_PEOPLE_IN_ASSESS_ERROR 
        new_distribute_ids = []
        assessment_obj = AssessProject.objects.get(id=assess_id)
        status = PeopleSurveyRelation.STATUS_DOING if assessment_obj.project_status == AssessProject.STATUS_WORKING else PeopleSurveyRelation.STATUS_NOT_BEGIN
        all_survey_qs = AssessSurveyRelation.objects.filter_active(assess_id=assess_id).distinct().order_by("-order_number")
        if all_survey_qs.count() == 0:
            return ErrorCode.PROJECT_SURVEY_RELATION_VALID
        all_survey_ids = all_survey_qs.values_list("survey_id", flat=True)
        survey_assess_distribute_dict = {}
        for survey_id in all_survey_ids:
            asud_qs = AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id, survey_id=survey_id)
            if asud_qs.exists():
                dist_people_ids = json.loads(asud_qs[0].people_ids)
                if type(dist_people_ids) != list:
                    dist_people_ids = []
            else:
                AssessSurveyUserDistribute.objects.create(assess_id=assess_id, survey_id=survey_id, people_ids=json.dumps([]))
                dist_people_ids = []
            survey_assess_distribute_dict[survey_id] = dist_people_ids

        random_survey_qs = all_survey_qs.filter(survey_been_random=True)
        normal_survey_qs = all_survey_qs.filter(survey_been_random=False)

        normal_survey_ids = list(normal_survey_qs.values_list('survey_id', flat=True))
        row_random_survey_ids = list(random_survey_qs.values_list('survey_id', flat=True))
        random_distribute_people_info_out = get_random_survey_distribute_info(assess_id, random_survey_qs)

        random_num = assessment_obj.survey_random_number
        if random_num:
            if len(random_survey_qs) < random_num:
                random_num = len(random_survey_qs)
        random_index = assessment_obj.survey_random_index

        people_survey_b_create_list = []
        for people_id in people_ids:
            if random_num and random_survey_qs.exists() and (people_id not in random_distribute_people_info_out):
                random_survey_ids, random_index = polling_survey(random_num, random_index, row_random_survey_ids)
            else:
                random_survey_ids, random_index = [], random_index
            person_survey_ids_list = [i for i in all_survey_ids if i in list(set(normal_survey_ids).union(set(random_survey_ids)))]
            for survey_id in person_survey_ids_list:
                survey = Survey.objects.get(id=survey_id)
                distribute_users = survey_assess_distribute_dict[survey_id]
                if people_id not in distribute_users:
                    people_survey_b_create_list.append(PeopleSurveyRelation(
                        people_id=people_id,
                        survey_id=survey_id,
                        project_id=assess_id,
                        survey_name=survey.title,
                        status=status
                    ))
                    survey_assess_distribute_dict[survey_id].append(people_id)
                    if people_id not in new_distribute_ids:
                        new_distribute_ids.append(people_id)
            # 批量创建
            if len(people_survey_b_create_list) > 2000:
                PeopleSurveyRelation.objects.bulk_create(people_survey_b_create_list)
                logger.info("people_b_create_survey")
                people_survey_b_create_list = []
        # 发送最后一批问卷
        if people_survey_b_create_list:
            logger.info("people_b_create_survey")
            PeopleSurveyRelation.objects.bulk_create(people_survey_b_create_list)
        # 发激活码
        if new_distribute_ids:
            self.send_active_code(new_distribute_ids)
        # 保留发卷信息
        for survey_id in survey_assess_distribute_dict:
            AssessSurveyUserDistribute.objects.filter_active(assess_id=assess_id, survey_id=survey_id).update(people_ids=json.dumps(survey_assess_distribute_dict[survey_id]))
        # 轮询标志位
        assessment_obj.survey_random_index = random_index
        assessment_obj.save()
        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        self.assessment = AssessProject.objects.get(id=self.assess_id)
        if self.assessment.assess_type == AssessProject.TYPE_360:
            rst_code = self.distribute360()
        else:
            rst_code = self.distribute_normal()
        return general_json_response(status.HTTP_200_OK, rst_code)

    def get_project_url(self):
        # TODO: join-project interface
        project_id_bs64 = quote(base64.b64encode(str(self.assess_id)))
        return settings.CLIENT_HOST + '/people/join-project/?ba=%s&bs=0' % (project_id_bs64)

    def get_open_project_user_statistics(self):

        user_qs = PeopleSurveyRelation.objects.filter_active(project_id=self.assess_id)
        all_count = user_qs.values_list("people_id", flat=True).distinct().count()
        people_with_survey_ids = user_qs.values_list('people_id', flat=True).distinct()
        wei_fen_fa = all_count - people_with_survey_ids.count()
        yi_wan_cheng = self.get_all_survey_finish_people_count(people_with_survey_ids, self.assess_id)
        yi_fen_fa = self.get_doing_survey_people_count(people_with_survey_ids, self.assess_id)
        da_juan_zhong = people_with_survey_ids.count() - yi_wan_cheng - yi_fen_fa
        distribute_count = 0
        return {
            "count": all_count,
            "doing_count": da_juan_zhong,
            "not_begin_count": yi_fen_fa,
            "finish_count": yi_wan_cheng,
            "not_started": wei_fen_fa,
            "distribute_count": distribute_count
        }

    def get_import_project_user_statistics(self):
        po_qs = AssessUser.objects.filter_active(assess_id=self.assess_id).values_list("people_id", flat=True).distinct()
        all_count = po_qs.count()
        user_qs = PeopleSurveyRelation.objects.filter_active(project_id=self.assess_id)
        people_ids = user_qs.values_list('people_id', flat=True).distinct()
        wei_fen_fa = all_count - people_ids.count() 
        yi_wan_cheng = self.get_all_survey_finish_people_count(list(people_ids), self.assess_id)
        yi_fen_fa = self.get_doing_survey_people_count(list(people_ids), self.assess_id)
        da_juan_zhong = people_ids.count() - yi_wan_cheng - yi_fen_fa
        distribute_count = people_ids.count()
        return {
            "count": all_count,
            "doing_count": da_juan_zhong,
            "not_begin_count": yi_fen_fa,
            "finish_count": yi_wan_cheng,
            "not_started": wei_fen_fa,
            "distribute_count": distribute_count 
        }

    def get_distribute_info(self):
        project = AssessProject.objects.get(id=self.assess_id)
        if project.distribute_type == AssessProject.DISTRIBUTE_OPEN:
            user_statistics = self.get_open_project_user_statistics()
        else:
            user_statistics = self.get_import_project_user_statistics()
        org_ids = AssessOrganization.objects.filter_active(
            assess_id=self.assess_id).values_list("organization_id", flat=True)
        org_infos = Organization.objects.filter_active(id__in=org_ids).values("id", "name", "identification_code")
        return {
            "user_statistics": user_statistics,
            "distribute_type": project.distribute_type,
            "org_infos": org_infos
        }

    def get(self, request, *args, **kwargs):
        data = {
            "url": self.get_project_url(),
            "distribute_info": self.get_distribute_info()
        }
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, data)