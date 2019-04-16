# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import hashlib
import json
import urllib2
import datetime

from rest_framework import serializers

from WeiDuAdmin import settings
from assessment.models import AssessProject, AssessUser
from front.models import PeopleSurveyRelation
from utils import get_random_int
from utils.serializers import WdTagListSerializer
from wduser.models import AuthUser, EnterpriseInfo, Organization, UserAdminRole, RoleBusinessPermission, \
    BusinessPermission, RoleUser, RoleUserBusiness, People, PeopleOrganization, PeopleAccount
from wduser.user_utils import OrganizationUtils, logger


class UserBasicSerializer(serializers.ModelSerializer):
    u"""用户基础信息序列化"""

    extra_account_name = serializers.SerializerMethodField()

    class Meta:
        model = AuthUser
        fields = ('id', 'username', 'nickname', 'phone', 'email', 'role_type', 'headimg', 'display_name', 'remark', 'account_name', "extra_account_name")

    def get_extra_account_name(self, obj):
        try:
            peo_obj = People.objects.filter_active(user_id=obj.id)[0]
            pa = PeopleAccount.objects.filter_active(people_id=peo_obj.id)
            a_n_dict = {}
            for x in pa:
                a_n_dict[x.account_type] = x.account_value
            return a_n_dict
        except:
            return {}


class PeopleSerializer(serializers.ModelSerializer):
    u"""用户序列化"""

    org_names = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()
    infos = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    extra_account_name = serializers.SerializerMethodField()

    class Meta:
        model = People
        fields = ("id", "username", "user_id", "phone", "email", "org_names", 'infos', 'status', 'account_name', "extra_account_name")

    def get_extra_account_name(self, obj):
        try:
            pa = PeopleAccount.objects.filter_active(people_id=obj.id)
            a_n_dict = {}
            for x in pa:
                a_n_dict[x.account_type] = x.account_value
            return a_n_dict
        except:
            return {}

    def get_infos(self, obj):
        if obj.more_info:
            return json.loads(obj.more_info)
        else:
            return []

    def get_status(self, obj):
        request = self.context.get("request", None)
        if not request or request.GET.get("assess_id", None) is None:
            return u"未知"
        assess_id = request.GET.get("assess_id")
        surery_rels = PeopleSurveyRelation.objects.filter_active(project_id=assess_id, people_id=obj.id)
        if not surery_rels.exists():
            return u"未分发"
        if surery_rels.filter(status=PeopleSurveyRelation.STATUS_EXPIRED).exists():
            return u"已过期"
        if surery_rels.filter(status=PeopleSurveyRelation.STATUS_FINISH).count() == surery_rels.count():
            return u'已结束'
        if surery_rels.filter(status__in=[PeopleSurveyRelation.STATUS_DOING_PART, PeopleSurveyRelation.STATUS_FINISH]).exists():
            return u'答卷中'
        else:
            try:
                now = datetime.datetime.now()
                p_obj_time = AssessProject.objects.get(id=assess_id).begin_time
                if now > p_obj_time:
                    return u'已分发'
            except:
                pass
            if surery_rels.filter(
                    status=PeopleSurveyRelation.STATUS_NOT_BEGIN).exists():
                return u"未开放"
            return u'已分发'



    def get_org_names(self, obj):
        org_info_list = []
        identification_codes = PeopleOrganization.objects.filter_active(people_id=obj.id).values_list('org_code', flat=True)
        identification_codes = Organization.objects.filter_active(identification_code__in=identification_codes).order_by('parent_id').values_list('identification_code', flat=True)
        def get_infos(org_obj):
            return {"id": org_obj.id, "name": org_obj.name, "identification_code": org_obj.identification_code}
        for identification_code in identification_codes:
            org_qs = Organization.objects.filter_active(identification_code=identification_code)
            if org_qs.count() > 1:
                logger.error('identificationn org has org,error %s ' % identification_code)
                return []
            if org_qs.exists():
                org_obj = org_qs[0]
                org_info_list.append(get_infos(org_obj))
                # while True:
                #     if org_obj.parent_id:
                #         try:
                #             org_obj = Organization.objects.get(id=org_obj.parent_id)
                #         except Exception, e:
                #             logger.error('org has two parent org,error %s '% e)
                #             return []
                #         org_info_list.append(get_infos(org_obj))
                #     else:
                #         break
        return org_info_list

        # request = self.context.get("request", None)
        # if request and request.GET.get("assess_id", None) is not None:
        #     assess_id = request.GET.get("assess_id")
        #     assess = AssessProject.objects.get(id=assess_id)
        #     org_codes = Organization.objects.filter_active(
        #         identification_code__in=obj.org_codes, assess_id=assess.id).values_list("identification_code", flat=True)
        #         identification_code__in=obj.org_codes, enterprise_id=assess.enterprise_id).values_list("identification_code", flat=True)
        # else:
            # org_codes = Organization.objects.filter_active(
            #     identification_code__in=obj.org_codes).values_list("identification_code", flat=True)
            # org_codes = obj.org_codes
        #     已经没有这个了
        # if not identification_code:
        #     identification_code = None
        # return OrganizationUtils.get_parent_org_names(identification_code)

    def get_user_id(self, obj):
        return obj.id

    def get_account_name(self, obj):
        user_id = obj.user_id
        try:
            account_name = AuthUser.objects.get(id=user_id).account_name
            return account_name
        except Exception, e:
            logger.error("people has no user error,%s, people - %s" % (e, obj.id))
            return None


class EnterpriseBasicSerializer(WdTagListSerializer, serializers.ModelSerializer):
    u"""企业基本信息序列化
    GET：企业列表
    POST：企业新建
    """
    industry = serializers.SerializerMethodField()
    user_assess_time = serializers.SerializerMethodField()
    enterprise_url_link = serializers.SerializerMethodField()

    class Meta:
        model = EnterpriseInfo
        fields = ('id', 'cn_name', 'en_name', 'short_name', 'linkman', 'phone', 'fax_number',
                  'email', 'remark', 'enterprise_url_link', 'industry', 'user_assess_time')

    def get_industry(self, obj):
        return u"行业保留字段"

    def get_user_assess_time(self, obj):
        # 企业的人员完成次数
        return obj.test_count

    def get_enterprise_url_link(self, obj):
        if not obj.enterprise_dedicated_link:
            id_str = "%10d" % obj.id
            sha1 = hashlib.sha1()
            sha1.update(id_str)
            enterprise_dedicated_link = sha1.hexdigest()
            obj.enterprise_dedicated_link = enterprise_dedicated_link
            obj.save()
        return settings.CLIENT_HOST + "/#/enterprise" + "/" + str(obj.enterprise_dedicated_link)


class OrganizationBasicSerializer(serializers.ModelSerializer):
    u"""组织基本信息序列化
    组织新建 组织列表

    @version: 20180806
    @summary: list_custom_attrs 单独获取，因为新建组织后需要返回标签信息，一边向下层组织使用
    """
    list_custom_attrs = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        # 增加项目id 8.22
        fields = ('id', 'enterprise_id', 'parent_id', 'name', 'en_name', 'identification_code', "list_custom_attrs",
                  "assess_id")
        # fields = ('id', 'parent_id', 'name', 'identification_code', "list_custom_attrs", "assess_id")

    def get_list_custom_attrs(self, obj):
        from research.models import OrganizationTagRelation
        return OrganizationTagRelation.objects.filter_active(object_id=obj.id).values("tag_value", "tag_id")


class OrganizationDetailSerializer(OrganizationBasicSerializer):
    u"""组织基本信息序列化
    组织新建 组织列表
    """
    child_orgs = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = OrganizationBasicSerializer.Meta.fields + ("child_orgs", )

    def get_child_orgs(self, obj):
        # return OrganizationUtils.get_child_orgs(obj.enterprise_id, obj.id, 1)[0]
        return OrganizationUtils.get_child_orgs(obj.assess_id, obj.id, 1)[0]


class UserAdminRoleSerializer(serializers.ModelSerializer):
    u"""角色序列化"""

    class Meta:
        model = UserAdminRole
        fields = ('id', 'role_name', 'role_desc', 'create_time')


class UserAdminRoleDetailSerializer(serializers.ModelSerializer):
    u"""角色序列化"""

    permissions = serializers.SerializerMethodField()

    class Meta:
        model = UserAdminRole
        fields = ('id', 'role_name', 'role_desc', 'create_time', 'permissions')

    def get_permissions(self, obj):
        return RoleBusinessPermission.objects.filter_active(role_id=obj.id).values_list('permission_id', flat=True)


class RoleBusinessPermissionSerializer(serializers.ModelSerializer):
    u"""角色权限"""

    permission_info = serializers.SerializerMethodField()

    class Meta:
        model = RoleBusinessPermission
        fields = ('id', 'role_id', 'permission_info')

    def get_permission_info(self, obj):
        for info in BusinessPermission.PERMISSION_MAP:
            if info["pid"] == obj.permission_id:
                return info
        return {}


class RoleUserBasicSerializer(serializers.ModelSerializer):
    u"""角色人员关联 基础序列化"""

    class Meta:
        model = RoleUser
        fields = ('id', 'role_id', 'user_id')


class RoleUserBasicListSerializer(RoleUserBasicSerializer):
    u"""角色人员关联 基础序列化"""

    role_name = serializers.SerializerMethodField()

    class Meta:
        model = RoleUser
        fields = RoleUserBasicSerializer.Meta.fields + ('role_name', )

    def get_role_name(self, obj):
        return UserAdminRole.objects.get(id=obj.role_id).role_name


class RoleUserInfoSerializer(serializers.ModelSerializer):

    user_id = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()

    class Meta:
        model = AuthUser
        fields = ('id', 'user_id', 'username', 'phone', 'email', 'remark')

    def get_user_id(self, obj):
        return obj.id

    def get_username(self, obj):
        return obj.nickname


class RoleUserSerializer(RoleUserBasicListSerializer):
    u"""角色人员管理"""

    username = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    remark = serializers.SerializerMethodField()

    class Meta:
        model = RoleUser
        fields = RoleUserBasicListSerializer.Meta.fields + ('username', 'phone', 'email', 'remark')

    def __get_user_info(self, obj):
        print "__get_user_info query begin"
        if hasattr(obj, '__cache__') and 'user_info' in obj.__cache__:
            print "__get_user_info query in cache"
            return obj.__cache__['user_info']
        print "__get_user_info query in db"
        if not hasattr(obj, '__cache__'):
            obj.__cache__ = {}
        obj.__cache__['user_info'] = UserBasicSerializer(instance=AuthUser.objects.get(id=obj.user_id)).data
        return obj.__cache__['user_info']

    def get_username(self, obj):
        return self.__get_user_info(obj)['nickname']

    def get_phone(self, obj):
        return self.__get_user_info(obj)['phone']

    def get_email(self, obj):
        return self.__get_user_info(obj)['email']

    def get_remark(self, obj):
        return self.__get_user_info(obj)['remark']


class RoleUserBusinessBasicSeriaSerializer(serializers.ModelSerializer):
    u"""用户授权对象序列化"""

    class Meta:
        model = RoleUserBusiness
        fields = ('id', 'role_id', 'user_id', 'model_type', 'model_id')


class RoleUserBusinessListSeriaSerializer(RoleUserBusinessBasicSeriaSerializer):
    u"""用户授权对象序列化"""

    model_info = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = RoleUserBusiness
        fields = RoleUserBusinessBasicSeriaSerializer.Meta.fields + ('model_info', "user_name")

    def get_model_info(self, obj):
        from survey.models import Survey
        from wduser.models import EnterpriseInfo
        from assessment.models import AssessProject
        if obj.model_type == RoleUserBusiness.MODEL_TYPE_SURVEY:
            model_obj = Survey.objects.get(id=obj.model_id)
            return {
                "title": model_obj.title,
                "survey_type": model_obj.survey_type,
                "desc": model_obj.desc,
                "id": model_obj.id
            }
        elif obj.model_type == RoleUserBusiness.MODEL_TYPE_ENTERPRISE:
            model_obj = EnterpriseInfo.objects.get(id=obj.model_id)
            return {
                "name": model_obj.cn_name,
                "short_name": model_obj.short_name,
                "remark": model_obj.remark,
                "id": model_obj.id
            }
        elif obj.model_type == RoleUserBusiness.MODEL_TYPE_PROJECT:
            model_obj = AssessProject.objects.get(id=obj.model_id)
            return {
                "id": model_obj.id,
                "name": model_obj.name,
                "enterprise_id": model_obj.enterprise_id,
                "enterprise_name": EnterpriseInfo.objects.get(id=model_obj.enterprise_id).cn_name
            }
        else:
            return {}

    def get_user_name(self, obj):
        try:
            return AuthUser.objects.get(id=obj.user_id).nickname
        except:
            return u''


class PeopleSerializer360(serializers.ModelSerializer):
    u"""360 用户序列化"""

    org_names = serializers.SerializerMethodField()
    infos = serializers.SerializerMethodField()
    account_name = serializers.SerializerMethodField()
    people_role = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()

    class Meta:
        model = People
        fields = ("id", "username", "phone", "email", "org_names", 'infos', 'account_name', 'people_role', "user_id")

    def get_infos(self, obj):
        if obj.more_info:
            return json.loads(obj.more_info)
        else:
            return []

    def get_user_id(self, obj):
        return obj.id

    def get_org_names(self, obj):
        org_info_list = []
        identification_codes = PeopleOrganization.objects.filter_active(people_id=obj.id).values_list('org_code', flat=True)
        identification_codes = Organization.objects.filter_active(identification_code__in=identification_codes).order_by('parent_id').values_list('identification_code', flat=True)
        def get_infos(org_obj):
            return {"id": org_obj.id, "name": org_obj.name, "identification_code": org_obj.identification_code}
        for identification_code in identification_codes:
            org_qs = Organization.objects.filter_active(identification_code=identification_code)
            if org_qs.count() > 1:
                logger.error('identificationn org has org,error %s ' % identification_code)
                return []
            if org_qs.exists():
                org_obj = org_qs[0]
                org_info_list.append(get_infos(org_obj))
                # while True:
                #     if org_obj.parent_id:
                #         try:
                #             org_obj = Organization.objects.get(id=org_obj.parent_id)
                #         except Exception, e:
                #             logger.error('org has two parent org,error %s '% e)
                #             return []
                #         org_info_list.append(get_infos(org_obj))
                #     else:
                #         break
        return org_info_list

        # request = self.context.get("request", None)
        # if request and request.GET.get("assess_id", None) is not None:
        #     assess_id = request.GET.get("assess_id")
        #     assess = AssessProject.objects.get(id=assess_id)
        #     org_codes = Organization.objects.filter_active(
        #         identification_code__in=obj.org_codes, assess_id=assess.id).values_list("identification_code", flat=True)
        #         identification_code__in=obj.org_codes, enterprise_id=assess.enterprise_id).values_list("identification_code", flat=True)
        # else:
            # org_codes = Organization.objects.filter_active(
            #     identification_code__in=obj.org_codes).values_list("identification_code", flat=True)
            # org_codes = obj.org_codes
        #     已经没有这个了
        # if not identification_code:
        #     identification_code = None
        # return OrganizationUtils.get_parent_org_names(identification_code)

    def get_account_name(self, obj):
        user_id = obj.user_id
        try:
            account_name = AuthUser.objects.get(id=user_id).account_name
            return account_name
        except Exception, e:
            logger.error("people has no user error,%s, people - %s" % (e, obj.id))
            return None

    def get_people_role(self, obj):
        request = self.context.get('request', None)
        user_id = request.GET.get('user_id', None)
        assess_id = request.GET.get('assess_id', None)
        au_qs = AssessUser.objects.filter_active(
            assess_id=assess_id,
            people_id=user_id,
            role_people_id=obj.id,
            role_type__in=[AssessUser.ROLE_TYPE_HIGHER_LEVEL,
                           AssessUser.ROLE_TYPE_LOWER_LEVEL,
                           AssessUser.ROLE_TYPE_SAME_LEVEL,
                           AssessUser.ROLE_TYPE_SUPPLIER_LEVEL]
        )
        if au_qs.count() > 1:
            ids = list(au_qs.values_list("id", flat=True))[1:]
            au_qs.filter(id__in=ids).update(is_active=False)
        if au_qs.exists():
            ret = au_qs[0].role_type
        else:
            ret = 10
        return ret