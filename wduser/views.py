# -*- coding:utf-8 -*-
from __future__ import unicode_literals

# Create your views here.
import hashlib
import json

from django.contrib.auth import logout
from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.db import connection
from rest_framework import status
from rest_framework.parsers import MultiPartParser

from assessment.models import AssessProject, AssessOrganization
from survey.models import Survey
from utils import get_random_int, get_random_char
from utils.aliyun.email import EmailUtils
from utils.aliyun.sms.newsms import Sms
from utils.cache.cache_utils import VerifyCodeExpireCache
from utils.excel import ExcelUtils
from utils.logger import get_logger
from utils.regular import RegularUtils, Convert
from utils.response import general_json_response, ErrorCode
from utils.views import WdCreateAPIView, AuthenticationExceptView, WdListCreateAPIView, WdRetrieveUpdateAPIView, \
    WdDestroyAPIView, WdExeclExportView, WdListAPIView
from wduser.models import AuthUser, EnterpriseInfo, Organization, UserAdminRole, BusinessPermission, RoleUser, \
    RoleUserBusiness, RoleBusinessPermission, PeopleOrganization
from wduser.serializers import UserBasicSerializer, EnterpriseBasicSerializer, OrganizationBasicSerializer, \
    OrganizationDetailSerializer, UserAdminRoleSerializer, RoleBusinessPermissionSerializer, RoleUserSerializer, \
    UserAdminRoleDetailSerializer, RoleUserBasicSerializer, RoleUserBasicListSerializer, \
    RoleUserBusinessBasicSeriaSerializer, RoleUserBusinessListSeriaSerializer, RoleUserInfoSerializer
from wduser.tasks import import_org_task, send_general_code, enterprise_statistics_test_user
from wduser.user_utils import UserAccountUtils, OrgImportExport, OrganizationUtils


logger = get_logger('user')


def login_info(request, user, context):
    user_info = UserBasicSerializer(instance=user, context=context).data
    role_info = {
        "role_type": user.role_type,
        "permissions": []
    }
    str_permissions = []
    if user.role_type == AuthUser.ROLE_ADMIN:
        role_ids = RoleUser.objects.filter_active(
            user_id=user.id).values_list("role_id", flat=True)
        role_permissions = list(RoleBusinessPermission.objects.filter_active(
            role_id__in=role_ids
        ).values_list("permission_id", flat=True))
        role_info["permissions"] = role_permissions
        str_permissions = [str(pid) for pid in role_permissions]
    elif user.role_type == AuthUser.ROLE_SUPER_ADMIN:
        role_info["permissions"] = BusinessPermission.SUPER_USER_PERMISSIONS
        str_permissions = [str(pid) for pid in BusinessPermission.SUPER_USER_PERMISSIONS]
    request.session["wdp"] = ",".join(str_permissions)
    user_info["role_info"] = role_info
    return user_info


class LoginView(AuthenticationExceptView, WdCreateAPIView):
    u"""管理员用户登录接口
    超级管理员：账号密码
    次级管理呀/企业管理员：手机号/邮箱+密码 登录
    """
    model = AuthUser
    serializer_class = UserBasicSerializer

    def post(self, request, *args, **kwargs):
        account = request.data.get('account', None)
        pwd = request.data.get("pwd", None)
        if account is None or pwd is None:
            return general_json_response(status.HTTP_200_OK, ErrorCode.INVALID_INPUT)
        #  account check
        user, err_code = UserAccountUtils.account_check(account)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        # pwd check
        user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        if user.role_type == AuthUser.ROLE_NORMAL:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_ADMIN_PERMISSION_INVALID)
        # user info response
        user_info = login_info(request, user, self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)


class ActiveCodeCheckView(AuthenticationExceptView, WdCreateAPIView):
    u"""激活码有效性校验"""

    def post(self, request, *args, **kwargs):
        account = request.data.get('account', None)
        active_code = request.data.get("active_code", None)
        user, rst_code = UserAccountUtils.account_check(account, True, active_code)
        return general_json_response(status.HTTP_200_OK, rst_code)


class ActiveCodePwdSetView(AuthenticationExceptView, WdCreateAPIView):
    u"""用户激活码登录后，设置密码"""

    def post(self, request, *args, **kwargs):
        account = request.data.get('account', None)
        active_code = request.data.get("active_code", None)
        pwd = request.data.get("pwd", None)
        user, rst_code = UserAccountUtils.account_check(account, True, active_code)
        if rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        password = make_password(pwd)
        user.password = password
        user.active_code_valid = False
        user.save()
        user, err_code = UserAccountUtils.user_login_web(request, user, pwd)
        if err_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, err_code)
        user_info = login_info(request, user, self.get_serializer_context())
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, user_info)


class ForgetVerifyCodeCheckView(AuthenticationExceptView, WdCreateAPIView):
    u"""忘记密码 校验码验证"""

    def post(self, request, *args, **kwargs):
        account = request.data.get('account', None)
        verify_code = request.data.get("verify_code", None)
        user, rst_code = UserAccountUtils.account_check(account)
        if rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        rst = VerifyCodeExpireCache(account).check_verify_code(verify_code, False)
        if not rst:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_VERIFY_CODE_INVALID)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class UserPwdForgetView(AuthenticationExceptView, WdCreateAPIView):
    u"""用户忘记密码，修改密码"""

    def post(self, request, *args, **kwargs):
        account = request.data.get('account', None)
        pwd = request.data.get("pwd", None)
        verify_code = request.data.get("verify_code", None)
        user, rst_code = UserAccountUtils.account_check(account)
        if rst_code != ErrorCode.SUCCESS:
            return general_json_response(status.HTTP_200_OK, rst_code)
        rst = VerifyCodeExpireCache(account).check_verify_code(verify_code)
        if not rst:
            return general_json_response(status.HTTP_200_OK, ErrorCode.USER_VERIFY_CODE_INVALID)
        pwd = make_password(pwd)
        user.password = pwd
        user.active_code_valid = False
        user.save()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class LogoutView(WdCreateAPIView):
    u"""Web登出"""
    def post(self, request, *args, **kwargs):
        try:
            logout(request)
        except Exception, e:
            logger.error("web logout error, msg(%s)" % e)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class EnterpriseListCreateView(WdListCreateAPIView):
    u"""企业列表及企业新建接口
    GET：企业列表接口
    POST：企业新建接口
    """
    model = EnterpriseInfo  # 模型实例化
    serializer_class = EnterpriseBasicSerializer  # 企业信息序列化
    POST_DATA_ID_RESPONSE = True  # 选择是否返回id, True表示返回id
    POST_CHECK_REQUEST_PARAMETER = ('cn_name', 'short_name')  # 期望校验的参数
    SEARCH_FIELDS = ('cn_name', 'en_name', 'short_name')  # 检索企业信息，范围字段

    # 均继承自父类
    def post_check_parameter(self, kwargs):
        err_code = super(EnterpriseListCreateView, self).post_check_parameter(kwargs)
        if err_code == ErrorCode.SUCCESS:
            if EnterpriseInfo.objects.filter_active(cn_name=self.cn_name).exists():
                err_code = ErrorCode.ENTERPRISE_CNNAME_EXISTS
            elif EnterpriseInfo.objects.filter_active(short_name=self.short_name).exists():
                err_code = ErrorCode.ENTERPRISE_SHORT_NAME_EXISTS
        return err_code

    def perform_create(self, serializer):
        super(EnterpriseListCreateView, self).perform_create(serializer)
        try:
            obj_id = self.custom_view_cache["perform_id"]
            RoleUserBusiness.objects.create(
                user_id=self.request.user.id,
                model_type=RoleUserBusiness.MODEL_TYPE_ENTERPRISE,
                model_id=obj_id
            )
        except:
            pass

    def qs_order_by(self, qs):
        # TODO: 按测试人次和最近测验排序
        order_by = self.get_order_by_name()
        if order_by == "-create_time":
            return qs.order_by("-id")
        elif order_by == "create_time":
            return qs.order_by("id")
        elif order_by == "-name":
            return qs.order_by(Convert('cn_name', 'gbk').desc())
        elif order_by == "name":
            return qs.order_by(Convert('cn_name', 'gbk').asc())
        elif order_by == "-test_count":
            return qs.order_by("-test_count")
        elif order_by == "test_count":
            return qs.order_by("test_count")
        elif order_by == "-test_time":
            return qs.order_by("-update_time")
        elif order_by == "test_time":
            return qs.order_by("update_time")
        else:
            return super(EnterpriseListCreateView, self).qs_order_by(qs)

    def qs_business_role(self, qs):
        # check permission
        user = self.request.user
        if user.role_type == AuthUser.ROLE_SUPER_ADMIN:
            return qs
        role_ids = RoleUser.objects.filter_active(
            user_id=self.request.user.id).values_list("role_id", flat=True)
        pm_ids = RoleBusinessPermission.objects.filter_active(
            role_id__in=role_ids).values_list("permission_id", flat=True)
        if BusinessPermission.PERMISSION_ALL in pm_ids or BusinessPermission.PERMISSION_ENTERPRISE_ALL_SEE in pm_ids or BusinessPermission.PERMISSION_ENTERPRISE_BUSINESS in pm_ids:
            return qs
        role_user_qs = RoleUserBusiness.objects.filter_active(
            user_id=self.request.user.id, model_type=RoleUserBusiness.MODEL_TYPE_ENTERPRISE)

        ass_ids = list(RoleUserBusiness.objects.filter_active(
            user_id=self.request.user.id, model_type=RoleUserBusiness.MODEL_TYPE_PROJECT).values_list("model_id", flat=True))
        ap_ids = list(AssessProject.objects.filter_active(id__in=ass_ids).values_list("enterprise_id", flat=True))

        model_ids = list(role_user_qs.values_list("model_id", flat=True))
        model_ids.extend(ap_ids)
        return qs.filter(id__in=model_ids)

    def get(self, request, *args, **kwargs):
        enterprise_statistics_test_user.delay()
        return super(EnterpriseListCreateView, self).get(request, *args, **kwargs)


class EnterpriseRetrieveUpdateDestroyAPIView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""企业详情获取与修改
    GET： 获取企业详情
    PUT： 企业修改
    DELETE: 企业删除
    """

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
        return super(EnterpriseRetrieveUpdateDestroyAPIView, self).get(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        # 有测评项目不可以删除企业
        if AssessProject.objects.filter(enterprise_id=self.get_id()).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.ENTERPRISE_DELETE_FAILED_WITH_ASSESS_PROJECT)
        logger.info('user_id %s want delete enterprise_id %s' % (self.request.user.id, self.get_id()))
        return super(EnterpriseRetrieveUpdateDestroyAPIView, self).delete(request, *args, **kwargs)


class EnterpriseOpsView(WdCreateAPIView):
    u"""企业操作接口
    ops_type: delete
    """
    POST_CHECK_REQUEST_PARAMETER = ('ops_type', )
    OPS_TYPE_DELETE = 'delete'

    def delete_ops(self):
        enterprise_ids = self.request.data.get("enterprise_ids", [])
        if enterprise_ids:
            if AssessProject.objects.filter(enterprise_id__in=enterprise_ids).exists():
                return general_json_response(status.HTTP_200_OK, ErrorCode.ENTERPRISE_DELETE_FAILED_WITH_ASSESS_PROJECT)
        EnterpriseInfo.objects.filter(id__in=enterprise_ids).update(is_active=False)
        logger.info('user_id %s want delete enterprise_id %s' % (self.request.user.id, enterprise_ids))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def post(self, request, *args, **kwargs):
        if self.ops_type == self.OPS_TYPE_DELETE:
            return self.delete_ops()
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class OrganizationListCreateView(WdListCreateAPIView):
    u"""
    POST：新建组织
    GET：组织列表 树型结构
    """
    model = Organization
    serializer_class = OrganizationDetailSerializer
    # g_serializer_class = OrganizationDetailSerializer
    POST_CHECK_REQUEST_PARAMETER = ('assess_id', 'name')
    # POST_CHECK_REQUEST_PARAMETER = ('enterprise_id', 'name')
    # 这里的 enterprise_id 需要改为项目id, 企业id也可以保留?
    # GET_CHECK_REQUEST_PARAMETER = ('enterprise_id', )
    GET_CHECK_REQUEST_PARAMETER = ('assess_id', )
    SEARCH_FIELDS = ('name', 'identification_code')
    POST_DATA_RESPONSE = True

    def qs_filter(self, qs):
        # return qs.filter(enterprise_id=self.enterprise_id)
        return qs.filter(assess_id=self.assess_id)

    def get(self, request, *args, **kwargs):
        if self.request.GET.get(self.SEARCH_KEY, None) is not None:
            return super(OrganizationListCreateView, self).get(request, *args, **kwargs)
        # tree_orgs = OrganizationUtils.get_tree_organization(self.enterprise_id)
        tree_orgs = OrganizationUtils.get_tree_organization(self.assess_id)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS, {"organization": tree_orgs})

    def post_check_parameter(self, kwargs):
        err_code = super(OrganizationListCreateView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        def check_org_name(name, assess_id):
            org_qs = Organization.objects.filter_active(name=name, assess_id=assess_id, parent_id=0)
            if org_qs.count() > 0:
                return ErrorCode.ORG_NAME_DOUBLE_ERROR
            else:
                return ErrorCode.SUCCESS
        ret = check_org_name(self.name, self.assess_id)
        if ret != ErrorCode.SUCCESS:
            return ret
        # self.request.data["identification_code"] = OrganizationUtils.generate_org_code(self.enterprise_id, self.name)
        self.request.data["identification_code"] = OrganizationUtils.generate_org_code(self.assess_id, self.name)
        return err_code

    def perform_create(self, serializer):
        self.create_obj = serializer.save()
        AssessOrganization.objects.create(
            assess_id=self.assess_id,
            organization_id=self.create_obj.id,
            organization_code=self.create_obj.identification_code
        )
        if serializer.data and serializer.data.has_key("id"):
            self.custom_view_cache["perform_id"] = serializer.data["id"]
        else:
            self.custom_view_cache["perform_id"] = None
        if self.CREATE_TAG:
            self.perform_tag(self.custom_view_cache["perform_id"])


class OrganizationlRetrieveUpdateDestroyView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""
    GET：获取组织信息
    PUT：组织信息修改
    DELETE：删除组织
    """
    model = Organization
    serializer_class = OrganizationDetailSerializer
    # TODO: 删除组织 关联项目检查，已经关联或进行中的项目/问卷，是否可以删除？
    # TODO: 更改名称，组织标识不变

    def delete(self, request, *args, **kwargs):
        org = self.get_object()
        org_tree_ids = [org.id] + OrganizationUtils.get_child_orgs(org.assess_id, org.id)[1]
        codes = Organization.objects.filter_active(id__in=org_tree_ids).values_list("identification_code", flat=True)
        if PeopleOrganization.objects.filter_active(org_code__in=codes).exists():
            return general_json_response(status.HTTP_200_OK, ErrorCode.ORG_USED_IN_PROJECT_CAN_NOT_DELETE)
        Organization.objects.filter(id__in=org_tree_ids).update(is_active=False)
        logger.info('user_id %s want delete orgs %s' % (self.request.user.id,org_tree_ids))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def perform_tag(self):
        from research.models import OrganizationTagRelation
        batch_set_low_level = int(self.request.data.get("batch_set_low_level", 0))
        tag_datas = self.request.data.get("tag_datas", [])
        if not batch_set_low_level:
            return super(OrganizationlRetrieveUpdateDestroyView, self).perform_tag()

        bulk_list = []
        obj = self.get_object()
        child_info, child_ids = OrganizationUtils.get_child_orgs(obj.assess_id, obj.id)
        # child_info, child_ids = OrganizationUtils.get_child_orgs(obj.enterprise_id, obj.id)
        child_ids.append(obj.id)
        for tag_data in tag_datas:
            for obj_id in child_ids:
                qs = OrganizationTagRelation.objects.filter_active(
                    tag_id=tag_data["tag_id"],
                    object_id=obj_id
                )
                if qs.exists():
                    qs.update(tag_value=tag_data["tag_value"])
                else:
                    bulk_list.append(OrganizationTagRelation(
                        tag_id=tag_data["tag_id"],
                        object_id=obj_id,
                        tag_value=tag_data["tag_value"]
                    ))
        OrganizationTagRelation.objects.bulk_create(bulk_list)


class OrganizationImportExportView(AuthenticationExceptView, WdExeclExportView):
    u"""组织的导入导出
    GET：组织模板的导出，数据的导出
    POST：组织的提交
    """
    IMPORT_TEMPLATE = 'new_import'
    EXPORT_DATA = "export_data"

    GET_CHECK_REQUEST_PARAMETER = ("assess_id", )
    # GET_CHECK_REQUEST_PARAMETER = ("enterprise_id", )

    def get_file(self):
        export_type = self.request.GET.get("export_type", self.IMPORT_TEMPLATE)
        if export_type == self.EXPORT_DATA:
            # download org data
            return self.export_org_data()
        else:
            # download import template
            return self.export_template()

    def export_template(self):
        file_path, file_name = OrgImportExport.export_template()
        self.default_export_file_name = file_name
        return file_path

    def export_org_data(self):
        file_path, file_name = OrgImportExport.export_org_data(self.assess_id)
        # file_path, file_name = OrgImportExport.export_org_data(self.enterprise_id)
        self.default_export_file_name = file_name
        return file_path

    def post(self, request, *args, **kwargs):
        u"""组织导入"""
        self.parser_classes = (MultiPartParser,)
        file_data = request.data["file"]
        file_name = request.data["name"]
        # experise_id = request.data["experise_id"]
        assess_id = request.data["assess_id"]
        email = request.data.get("email", None)
        file_path = OrgImportExport.import_data(file_data, file_name, assess_id)
        err_code = import_org_task(assess_id, file_path, email)
        return general_json_response(status.HTTP_200_OK, err_code)


class UserAdminRoleListCreateView(WdListCreateAPIView):
    u"""角色管理
    @POST: 新建角色
    @GET: 角色列表
    """

    model = UserAdminRole
    serializer_class = UserAdminRoleSerializer
    SEARCH_FIELDS = ('role_name', )

    def post_check_parameter(self, kwargs):
        err_code = super(UserAdminRoleListCreateView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        role_name = self.request.data.get("role_name", None)
        if role_name and UserAdminRole.objects.filter_active(role_name=role_name).exists():
            return ErrorCode.USER_ADMIN_ROLE_NAME_FORBID
        return ErrorCode.SUCCESS


class UserAdminRoleDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""角色管理
    @PUT: 角色修改
    @DELETE: 角色删除
    """

    model = UserAdminRole
    serializer_class = UserAdminRoleSerializer
    g_serializer_class = UserAdminRoleDetailSerializer

    def post_check_parameter(self, kwargs):
        err_code = super(UserAdminRoleDetailView, self).post_check_parameter(kwargs)
        if err_code != ErrorCode.SUCCESS:
            return err_code
        role_name = self.request.data.get("role_name", None)
        if role_name and UserAdminRole.objects.filter_active(
                role_name=role_name).exclude(id=self.get_id()).exists():
            return ErrorCode.USER_ADMIN_ROLE_NAME_FORBID
        return ErrorCode.SUCCESS

    def perform_destroy(self, instance):
        super(UserAdminRoleDetailView, self).perform_destroy(instance)
        RoleUser.objects.filter_active(role_id=self.get_id()).update(is_active=False)
        RoleUserBusiness.objects.filter_active(role_id=self.get_id()).update(is_active=False)
        logger.info('user_id %s want delete roleuser %s' % (self.request.user.id, self.get_id()))


class PermissionListView(WdListAPIView):
    u"""权限列表"""

    def get(self, request, *args, **kwargs):
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS,
                                     {'permissions': BusinessPermission.PERMISSION_MAP})


class RolePermissionAPIView(WdListCreateAPIView):
    u"""角色权限管理"""

    model = RoleBusinessPermission
    serializer_class = RoleBusinessPermissionSerializer
    GET_CHECK_REQUEST_PARAMETER = ('role_id', )
    POST_CHECK_REQUEST_PARAMETER = ('role_id', 'permission_ids')
    FILTER_FIELDS = ('role_id', )

    def post(self, request, *args, **kwargs):
        bulk_list = []
        RoleBusinessPermission.objects.filter_active(role_id=self.role_id).update(is_active=False)
        for permission_id in self.permission_ids:
            bulk_list.append(RoleBusinessPermission(
                role_id=self.role_id,
                permission_id=permission_id
            ))
        RoleBusinessPermission.objects.bulk_create(bulk_list)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class RoleUserListCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""角色成员管理
    @GET:获取角色成员，role_id不带时，获取全部成员列表
    @POST: 添加新成员
    @DELETE： 帐号删除
    """

    model = RoleUser
    p_serializer_class = RoleUserBasicSerializer
    g_serializer_class = RoleUserInfoSerializer
    FILTER_FIELDS = ('role_id', )
    POST_CHECK_REQUEST_PARAMETER = ('role_id', 'username', 'phone', 'email')
    DELETE_CHECK_REQUEST_PARAMETER = ('user_id', )

    def qs_search(self, qs):
        role_id = self.request.GET.get("role_id", None)
        key_words = self.request.GET.get(self.SEARCH_KEY, None)
        if not role_id:
            qs = qs.filter(is_active=True, role_type=AuthUser.ROLE_ADMIN)
        if key_words is None or not key_words:
            return qs
        if not role_id:
            # 全部成员
            qs = qs.filter(
            Q(nickname__contains=key_words)|
            Q(phone=key_words)|
            Q(email=key_words))
            return qs
        user_ids = AuthUser.objects.filter(
            is_active=True).filter(
            Q(nickname__contains=key_words)|
            Q(phone=key_words)|
            Q(email=key_words)).values_list("id", flat=True).distinct()
        qs = qs.filter(user_id__in=user_ids)
        return qs

    def get_queryset(self):
        role_id = self.request.GET.get("role_id", None)
        if not role_id:
            # 获取全部成员
            self.model = AuthUser
            self.serializer_class = RoleUserInfoSerializer
            return super(RoleUserListCreateView, self).get_queryset()
            # return AuthUser.objects.filter(is_active=True, role_type=AuthUser.ROLE_ADMIN)
        else:
            # 获取角色成员
            self.model = RoleUser
            self.serializer_class = RoleUserSerializer
            return super(RoleUserListCreateView, self).get_queryset()

    def qs_filter(self, qs):
        role_id = self.request.GET.get("role_id", None)
        if not role_id:
            # 获取全部成员
            qs = qs.exclude(role_type=AuthUser.ROLE_SUPER_ADMIN)
            return qs
        # 获取角色成员
        # uids = RoleUser.objects.filter_active(role_id=role_id).values_list("user_id", flat=True).distinct()
        qs = qs.filter(role_id=role_id)
        return qs

    def post_check_parameter(self, kwargs):
        rst_code = super(RoleUserListCreateView, self).post_check_parameter(kwargs)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        if AuthUser.objects.filter(is_active=True).filter(
                        Q(phone=self.phone) | Q(email=self.email)).count() > 1:
            return ErrorCode.PERMISSION_PHONE_EMAIL_NOT_SAME_USER
        if AuthUser.objects.filter(is_active=True).filter(
                        Q(phone=self.phone) | Q(email=self.email)).count() > 0:
            return ErrorCode.USER_HAS_IN_ROLETYPE_ERROR   #, {"msg": "账号已存在"})
        return ErrorCode.SUCCESS

    def post(self, request, *args, **kwargs):
        # TODO: 发送激活码，记录激活码
        self.model = RoleUser
        self.serializer_class = RoleUserBasicSerializer
        active_code = get_random_int(8)
        remark = self.request.data.get("remark", "")
        user_qs = AuthUser.objects.filter(
            is_active=True).filter(Q(phone=self.phone)|Q(email=self.email))
        if user_qs.exists():
            user = user_qs[0]
            user.nickname = self.username
            if self.phone:
                user.phone = self.phone
            if self.email:
                user.email = self.email
            user.role_type = AuthUser.ROLE_ADMIN
            user.remark = remark
            user.save()
        else:
            # u_qs = AuthUser.objects.filter(username=self.phone)
            random_char = get_random_char(6)
            user = AuthUser.objects.create(
                username="%s%s" % (self.phone, random_char),
                nickname=self.username, phone=self.phone, email=self.email,
                role_type=AuthUser.ROLE_ADMIN,
                active_code=active_code, active_code_valid=True,
                remark=remark
            )
            # send_general_code.delay(str(active_code), str(user.phone), str(user.email))
            send_general_code(str(active_code), str(user.phone), str(user.email))
        role_user = RoleUser.objects.get_or_create(
            role_id=self.role_id, user_id=user.id, remark=self.request.data.get("remark", "")
        )
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def delete(self, request, *args, **kwargs):
        # 帐号删除
        AuthUser.objects.filter(id=self.user_id).update(role_type=AuthUser.ROLE_NORMAL)
        # 角色成员删除
        RoleUser.objects.filter_active(user_id=self.user_id).update(is_active=False)
        RoleUserBusiness.objects.filter_active(user_id=self.user_id).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


# 弃用
class AdminUserListCreateView(WdListAPIView, WdDestroyAPIView):
    u"""全部管理成员管理
    @GET:获取全部成员列表
    @DELETE： 帐号删除
    """

    model = AuthUser
    serializer_class = RoleUserInfoSerializer
    SEARCH_FIELDS = ('nickname', )
    DELETE_CHECK_REQUEST_PARAMETER = ('user_id', )

    def qs_filter(self, qs):
        # 获取全部成员
        self.serializer_class = RoleUserInfoSerializer
        qs = qs.exclude(role_type=AuthUser.ROLE_SUPER_ADMIN)
        return qs

    def delete(self, request, *args, **kwargs):
        # 帐号删除
        AuthUser.objects.filter(id=self.user_id).update(is_active=False)
        # 角色成员删除
        RoleUser.objects.filter_active(user_id=self.user_id).update(is_active=False)
        RoleUserBusiness.objects.filter_active(user_id=self.user_id).update(is_active=False)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class RoleUserDetailView(WdRetrieveUpdateAPIView, WdDestroyAPIView):
    u"""
    角色成员管理
    @PUT: 修改角色成员
    @DELETE: 删除角色成员
    """
    model = RoleUser
    serializer_class = RoleUserBasicSerializer
    POST_CHECK_REQUEST_PARAMETER = ('user_id', )

    def post_check_parameter(self, kwargs):
        rst_code = super(RoleUserDetailView, self).post_check_parameter(kwargs)
        if rst_code != ErrorCode.SUCCESS:
            return rst_code
        user_id = self.request.data.get("user_id", None)
        phone = self.request.data.get("phone", None)
        email = self.request.data.get("email", None)
        if AuthUser.objects.filter(is_active=True).filter(
                        Q(phone=phone)|Q(email=email)).exclude(id=user_id).exists():
            return ErrorCode.PERMISSION_USER_EXISTS
        return ErrorCode.SUCCESS

    def put(self, request, *args, **kwargs):
        phone = self.request.data.get("phone", None)
        email = self.request.data.get("email", None)
        username = self.request.data.get("username", None)
        remark = self.request.data.get("remark", None)
        update_dict = {}
        if phone:
            update_dict["phone"] = phone
            update_dict["username"] = phone
        if email:
            update_dict["email"] = email
        if username:
            update_dict["nickname"] = username
        if remark:
            update_dict["remark"] = remark
        if update_dict:
            AuthUser.objects.filter(is_active=True, id=self.user_id).update(**update_dict)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)
        # return super(RoleUserDetailView, self).put(request, *args, **kwargs)

    def perform_destroy(self, instance):
        obj = self.get_object()
        super(RoleUserDetailView, self).perform_destroy(instance)
        # 用户可能在多个角色下面
        # AuthUser.objects.filter(id=obj.user_id).update(is_active=False)
        RoleUserBusiness.objects.filter_active(role_id=obj.role_id, user_id=obj.user_id).update(is_active=False)
        logger.info('user_id %s want delete roleuser_Detail user %s' % (self.request.user.id, obj.user_id))


class UserRoleListCreateView(WdListCreateAPIView):
    u"""人员关联角色
    @POST：人员关联角色提交接口
    @GET：人员已经关联的角色列表接口
    """
    model = RoleUser
    serializer_class = RoleUserBasicListSerializer
    POST_CHECK_REQUEST_PARAMETER = ('role_ids', 'user_id')
    GET_CHECK_REQUEST_PARAMETER = ('user_id', )
    FILTER_FIELDS = ('user_id', )

    def post(self, request, *args, **kwargs):
        self.role_ids = [int(role_id) for role_id in self.role_ids]
        exist_role_ids = list(RoleUser.objects.filter_active(user_id=self.user_id).values_list("role_id", flat=True))
        # 保留的角色
        reserve_role_ids = list(set(self.role_ids).intersection(set(exist_role_ids)))
        # 需要删除的角色
        remove_role_ids = list(set(exist_role_ids).difference(set(reserve_role_ids)))
        # 需要新建的角色
        new_role_ids = list(set(self.role_ids).difference(set(reserve_role_ids)))
        if remove_role_ids:
            RoleUser.objects.filter_active(role_id__in=remove_role_ids, user_id=self.user_id).update(is_active=False)
        if new_role_ids:
            bulk_list = []
            for new_role_id in new_role_ids:
                bulk_list.append(RoleUser(
                    role_id=new_role_id, user_id=self.user_id
                ))
            RoleUser.objects.bulk_create(bulk_list)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)


class RoleUserBusinessListCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""
    授权的对象
    @POST：提交授权的对象
    @GET：获取授权的对象列表
    """
    model = RoleUserBusiness
    serializer_class = RoleUserBusinessBasicSeriaSerializer
    p_serializer_class = RoleUserBusinessBasicSeriaSerializer
    g_serializer_class = RoleUserBusinessListSeriaSerializer
    POST_CHECK_REQUEST_PARAMETER = ("role_id", "user_id", "model_type", "model_ids")
    GET_CHECK_REQUEST_PARAMETER = ("role_id", "user_id", "model_type")
    DELETE_CHECK_REQUEST_PARAMETER = ("user_id", "model_type", "model_id")
    FILTER_FIELDS = ("user_id", "model_type")

    def post(self, request, *args, **kwargs):
        self.model_ids = [int(model_id) for model_id in self.model_ids]
        exists_model_ids = list(RoleUserBusiness.objects.filter_active(
            role_id=self.role_id, user_id=self.user_id, model_type=self.model_type
        ).values_list("model_id", flat=True))
        new_model_ids = list(set(self.model_ids).difference(set(exists_model_ids)))
        bulk_list = []
        for model_id in new_model_ids:
            bulk_list.append(RoleUserBusiness(
                role_id=self.role_id, user_id=self.user_id, model_type=self.model_type,
                model_id=model_id
            ))
        RoleUserBusiness.objects.bulk_create(bulk_list)
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def delete(self, request, *args, **kwargs):
        RoleUserBusiness.objects.filter_active(
            user_id=self.user_id, model_type=self.model_type, model_id=self.model_id
        ).update(is_active=False)
        logger.info('user_id %s want delete role_user_business %s' % (self.request.user.id, self.user_id))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

    def get_queryset(self):
        qs = super(RoleUserBusinessListCreateView, self).get_queryset()
        self.model_type = int(self.model_type)
        if self.model_type == RoleUserBusiness.MODEL_TYPE_SURVEY:
            model_ids = Survey.objects.filter_active().values_list("id", flat=True)
        elif self.model_type == RoleUserBusiness.MODEL_TYPE_ENTERPRISE:
            model_ids = EnterpriseInfo.objects.filter_active().values_list("id", flat=True)
        elif self.model_type == RoleUserBusiness.MODEL_TYPE_PROJECT:
            model_ids = AssessProject.objects.filter_active().values_list("id", flat=True)
        return qs.filter(model_id__in=model_ids)


    def qs_search(self, qs):
        key_words = self.request.GET.get("key_words", None)
        if not key_words:
            return qs
        model_ids = []
        self.model_type = int(self.model_type)
        if self.model_type == RoleUserBusiness.MODEL_TYPE_SURVEY:
            model_ids = Survey.objects.filter_active(title__icontains=key_words).values_list("id", flat=True)
        elif self.model_type == RoleUserBusiness.MODEL_TYPE_ENTERPRISE:
            model_ids = EnterpriseInfo.objects.filter_active(cn_name__icontains=key_words).values_list("id", flat=True)
        elif self.model_type == RoleUserBusiness.MODEL_TYPE_PROJECT:
            model_ids = AssessProject.objects.filter_active(name__icontains=key_words).values_list("id", flat=True)
        return qs.filter(model_type=self.model_type, model_id__in=model_ids)


class RoleUserPartListCreateView(WdListCreateAPIView, WdDestroyAPIView):
    u"""角色成员管理授权
    """

    model = RoleUserBusiness
    g_serializer_class = RoleUserBusinessListSeriaSerializer
    POST_CHECK_REQUEST_PARAMETER = ('permission', 'user_ids', 'type', 'model_id')
    GET_CHECK_REQUEST_PARAMETER = ('type',)
    # 20 企业 ；30 项目

    def get_queryset(self):
        type_id = self.request.GET.get('type')
        model_id = self.request.GET.get('model_id', None)
        if type_id:
            type_id = int(type_id)
        if model_id:
            model_id = int(model_id)
        if type_id and (model_id is None):
            # 获取全部成员
            self.model = AuthUser
            self.serializer_class = RoleUserInfoSerializer
            # 返回有相应角色的人
            if type_id == 20:  # 企业
                permission_id = 12
            else:
                permission_id = 41
            role_ids = RoleBusinessPermission.objects.filter_active(permission_id=permission_id).values_list('role_id', flat=True).distinct()
            user_ids = RoleUser.objects.filter_active(role_id__in=role_ids).values_list('user_id', flat=True)
            return AuthUser.objects.filter(is_active=True, id__in=user_ids)
        else:
            self.type = type_id
            self.model_id = model_id
            return super(RoleUserPartListCreateView, self).get_queryset()

    def qs_filter(self, qs):
        qs = qs.filter(
            model_type=self.type,
            model_id=self.model_id
        )
        return qs

    def post(self, request, *args, **kwargs):
        RoleUserBusiness.objects.filter_active(model_type=self.type, model_id=self.model_id).update(is_active=False)
        for user_id in self.user_ids:
            ru_qs = RoleUser.objects.filter(user_id=user_id)
            if ru_qs.exists():
                role_id = ru_qs[0].role_id
            else:
                role_id = 0
            RoleUserBusiness.objects.create(
                role_id=role_id,
                user_id=user_id,
                model_type=self.type,
                model_id=self.model_id
            )
        logger.info('user %s update model type %s id %s roleuserbusiness model' % (request.user.id, self.type, self.model_id))
        return general_json_response(status.HTTP_200_OK, ErrorCode.SUCCESS)

