# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import ugettext_lazy as _
# Create your models here.
from utils.models import BaseModel


class AuthUser(AbstractUser):
    u"""
    用户账号表
    version：2018/04/05
    summary: 支持超级管理员 一般管理员 企业用户 普通用户
    """
    account_name = models.CharField(u"账户", max_length=200, db_index=True, blank=True, null=True)
    phone = models.CharField(u"电话", max_length=20, db_index=True, blank=True, null=True)
    email = models.EmailField(u'邮箱', db_index=True, blank=True, null=True)
    dedicated_link = models.CharField(u"专属链接", max_length=60, blank=True, null=True)
    # add index on AbstractUser
    is_active = models.BooleanField(u"是否有效", default=True, db_index=True)
    #
    ROLE_NORMAL = 100
    ROLE_ENTERPRISE = 200
    ROLE_SUPER_ADMIN = 300
    ROLE_ADMIN = 400
    ROLE_TYPE_CHOICES = (
        (ROLE_NORMAL, "普通用户"),
        (ROLE_ENTERPRISE, "企业管理员"),
        (ROLE_SUPER_ADMIN, "超级管理员"),
        (ROLE_ADMIN, "一般管理员")
    )
    role_type = models.PositiveIntegerField(u"账户类型", default=ROLE_NORMAL, choices=ROLE_TYPE_CHOICES, db_index=True)
    nickname = models.CharField(u"名称", max_length=64, blank=True, null=True)
    headimg = models.URLField(u"头像/Logo", blank=True, null=True)
    active_code = models.CharField(u"激活码", max_length=20, db_index=True, blank=True, null=True)
    active_code_valid = models.BooleanField(u"激活码是否有效", default=False, db_index=True)
    remark = models.CharField(u"备注", max_length=400, null=True, db_index=True)

    class Meta:
        verbose_name = '基本信息'
        verbose_name_plural = '用户基本信息'

    @classmethod
    def create_superuser(cls, pwd, username):
        from wduser.user_utils import UserAccountUtils
        user, code = UserAccountUtils.user_register(pwd, username, role_type=AuthUser.ROLE_SUPER_ADMIN)
        print "create_superuser rst code is: %s" % code
        return user

    @property
    def display_name(self):
        if self.nickname:
            return self.nickname
        if self.phone:
            return self.phone
        if self.email:
            return self.email
        return self.username


class People(BaseModel):
    u"""参与测评的用户，active_code，active_code_valid 不需要"""
    user_id = models.BigIntegerField(u"用户ID", db_index=True, default=0)
    username = models.CharField(u"姓名nickname", max_length=128, null=True, db_index=True)
    phone = models.CharField(u"电话", max_length=20, db_index=True, blank=True, null=True)
    email = models.EmailField(u'邮箱', db_index=True, blank=True, null=True)
    # org_code = models.CharField(u"组织码", max_length=200, db_index=True, blank=True, null=True)
    #
    active_code = models.CharField(u"激活码", max_length=20, db_index=True, blank=True, null=True)
    active_code_valid = models.BooleanField(u"激活码是否有效", default=False, db_index=True)
    # [{'key_name':xxx,'key_value':xxx}]
    more_info = models.CharField(u"导入的其他信息", max_length=4096, null=True, blank=True)

    @property
    def org_codes(self):
        try:
            return list(PeopleOrganization.objects.filter_active(
                people_id=self.id).values_list("org_code", flat=True))
            #return self.org_code.split("/")
        except:
            return []

    def get_info_value(self, key_name, default_value=None):
        import json
        if key_name == u"姓名":
            name = self.username if self.username else default_value
            if name:
                return name
            else:
                return ""
        if self.more_info:
            info = json.loads(self.more_info)
            for o in info:
                if o["key_name"] == key_name:
                    return o["key_value"]
        if default_value:
            return default_value
        return u""

    @property
    def display_name(self):
        if self.username:
            return self.username
        if self.phone:
            return self.phone
        if self.email:
            return self.email
        try:
            user = AuthUser.objects.get(id=self.user_id)
            if user.nickname:
                return user.nickname
            if user.phone:
                return user.phone
            if user.email:
                return user.email
        except:
            return ""
        return ""


class PeopleAccount(BaseModel):
    u"""用户多账户登陆表"""
    people_id = models.BigIntegerField(u"peopleID", db_index=True)
    TYPE_1 = 4  # 1-> 4
    TYPE_2 = 5  # 2-> 5
    TYPE_3 = 1  # 3-> 1
    TYPE_4 = -1
    ACCOUNT_TYPE = (
        (TYPE_1, u"联合办公账号OA"),
        (TYPE_2, u"身份证号"),
        (TYPE_3, u"员工编号"),
        (TYPE_4, u"飞行网账号"),
    )
    account_type = models.PositiveSmallIntegerField(u"账户类型", default=TYPE_1, db_index=True)
    account_value = models.CharField(u"账户值", max_length=128, db_index=True)
    enterprise_id = models.BigIntegerField(u"企业ID", null=True, blank=True, default=0, db_index=True)


class PeopleOrganization(BaseModel):
    u"""用户组织关系"""
    people_id = models.BigIntegerField(u"用户ID", db_index=True, default=0)
    # org_id = models.BigIntegerField(u"组织ID", db_index=True, default=0)
    org_code = models.CharField(u"组织码", max_length=32, db_index=True, blank=True, null=True)


class EnterpriseInfo(BaseModel):
    u"""企业的基本信息表
    user_id：企业用户暂设置为0即无，企业超级管理员
    """
    cn_name = models.CharField(u"中文名称", max_length=200, db_index=True)
    en_name = models.CharField(u"英文名称", max_length=200, db_index=True, blank=True, null=True, default=u'')
    short_name = models.CharField(u"企业简写", max_length=64, db_index=True, blank=True, null=True)
    linkman = models.CharField(u"联系人", max_length=64, blank=True, null=True)
    phone = models.CharField(u"联系人电话", max_length=20, blank=True, null=True)
    fax_number = models.CharField(u"传真", max_length=20, blank=True, null=True)
    email = models.EmailField(u'联系人邮箱', blank=True, null=True)
    remark = models.CharField(u"备注", max_length=200, blank=True, null=True)
    test_count = models.PositiveIntegerField(u"测验人次", default=0)
    enterprise_dedicated_link = models.CharField(u"企业专属链接", max_length=60, blank=True, null=True)


# 9.15
class EnterpriseAccount(BaseModel):
    # 识别企业下不同账户
    enterprise_id = models.BigIntegerField(u"企业ID", db_index=True, default=0)
    account_name = models.CharField(u"账户", max_length=200, db_index=True, blank=True, null=True)
    user_id = models.BigIntegerField(u"authuser_ID", db_index=True, default=0)
    people_id = models.BigIntegerField(u"people_ID", db_index=True, default=0)


class EnterpriseAdmin(BaseModel):
    u"""企业管理员"""
    enterprise_id = models.BigIntegerField(u"企业ID", db_index=True)
    user_id = models.BigIntegerField(u"用户(管理员)ID", db_index=True)


class Organization(BaseModel):
    u"""组织表"""
    enterprise_id = models.BigIntegerField(u"企业ID", db_index=True, default=None, null=True)
    parent_id = models.BigIntegerField(u"父组织ID", db_index=True, default=0)
    name = models.CharField(u"中文名称", max_length=200, db_index=True)
    en_name = models.CharField(u"英文名称", max_length=200, db_index=True, default=u'', null=True)
    identification_code = models.CharField(u"标识码", max_length=20, db_index=True)
    assess_id = models.BigIntegerField(u"项目ID", db_index=True, null=True)


class UserAdminRole(BaseModel):
    u"""用户管理员角色"""
    role_name = models.CharField(u"角色名称", max_length=64, db_index=True)
    role_desc = models.CharField(u"角色描述", max_length=256, db_index=True)


class BusinessPermission(object):
    u"""业务权限"""
    # permission_name = models.CharField(u"权限名称", max_length=64, db_index=True)
    # permission_desc = models.CharField(u"权限描述", max_length=256, db_index=True)
    # 0
    PERMISSION_NONE = 0
    # 1，
    PERMISSION_ALL = 1
    # 2，
    PERMISSION_ENTERPRISE_ALL = 10
    # PERMISSION_ENTERPRISE_CREATE = 11
    # PERMISSION_ENTERPRISE_DELETE = 12
    # PERMISSION_ENTERPRISE_UPDATE = 13
    # PERMISSION_ENTERPRISE_QUERY = 14
    PERMISSION_ENTERPRISE_ALL_SEE = 11
    PERMISSION_ENTERPRISE_PART = 12   # 企业管理权限
    PERMISSION_ENTERPRISE_BUSINESS = 10
    PERMISSION_ENTERPRISE_MASTER = 20
    PERMISSION_ENTERPRISE_PROJECT = 21

    # 2.1
    PERMISSION_ORG_ALL = 30
    # 2.2
    PERMISSION_PROJECT_ALL = 40
    PERMISSION_PROJECT_PART = 41   # 项目管理权限
    # 3
    PERMISSION_MODEL_ORG_ALL = 50
    # 4
    PERMISSION_MODEL_PERSONAL_ALL = 60
    # 5
    PERMISSION_SURVEY_ORG_ALL = 70
    PERMISSION_SURVEY_ORG_USE = 71
    # 6
    PERMISSION_SURVEY_PERSONAL_ALL = 80
    PERMISSION_SURVEY_PERSONAL_USE = 81
    # 7
    PERMISSION_SURVEY_360_ALL = 90
    PERMISSION_SURVEY_360_USE = 91
    # 8
    PERMISSION_QUESTION_ALL = 100
    # 9
    PERMISSION_TAG_ALL = 110
    # 10
    PERMISSION_PERMISSION_ALL = 120
    PERMISSION_PERMISSION_ROLE = 121
    PERMISSION_PERMISSION_ROLE_USER = 122
    PERMISSION_PERMISSION_PROJECT_ASSIGNED = 123
    # 11 管理画像
    PERMISSION_NORMAL_PORTRAY = 130
    # 12 专业画像
    PERMISSION_PROFESSIONAL_PORTRAY = 140
    # 13 报告模板
    PERMISSION_REPORT_TEMPLATE = 150
    # 14 控制台
    PERMISSION_CONSOLE = 160

    # PERMISSION_URL_MAP = {
    #     # (PERMISSION_NONE, u"无权限"),
    #     # PERMISSION_ALL: {"model": 'all'},
    #     # PERMISSION_ENTERPRISE_ALL: {"model": 'user'},
    #     # (PERMISSION_ENTERPRISE_PART, u"管理部分企业权限"),
    #     # (PERMISSION_ORG_ALL, u"企业组织管理权限"),
    #     # (PERMISSION_PROJECT_ALL, u"企业项目管理权限"),
    #     # (PERMISSION_PROJECT_PART, u"企业部分项目管理权限"),
    #     # (PERMISSION_MODEL_ORG_ALL, u"组织模型管理权限"),
    #     # (PERMISSION_MODEL_PERSONAL_ALL, u"个人模型管理权限"),
    #     # (PERMISSION_SURVEY_ORG_ALL, u"组织问卷管理权限"),
    #     # (PERMISSION_SURVEY_PERSONAL_ALL, u"个人问卷管理权限"),
    #     # (PERMISSION_SURVEY_360_ALL, u"360部分问卷管理权限"),
    #     # (PERMISSION_SURVEY_ORG_USE, u"部分组织问卷管理权限"),
    #     # (PERMISSION_SURVEY_PERSONAL_USE, u"部分个人问卷管理权限"),
    #     # (PERMISSION_SURVEY_360_USE, u"360问卷管理权限"),
    #     # (PERMISSION_QUESTION_ALL, u"题库管理权限"),
    #     # (PERMISSION_TAG_ALL, u"标签管理权限"),
    #     # (PERMISSION_PERMISSION_ALL, u"权限管理权限")
    # }
    # permission 1.0
    # PERMISSION_MAP = [
    #     # {"pid": PERMISSION_NONE, "pname": u"无权限", "pdesc": u"无任何操作权限"},
    #     {"pid": PERMISSION_ALL, "pname": u"全部权限", "pdesc": u"具有任何操作权限"},
    #     {"pid": PERMISSION_ENTERPRISE_BUSINESS, "pname": u"业务管理员", "pdesc": u"除删除外的所有企业管理权限、除删除外的项目管理权限"},
    #     {"pid": PERMISSION_ENTERPRISE_MASTER, "pname": u"企业主管理员", "pdesc": u"特定企业的所有项目管理权限，新建的项目自动赋予管理权限给自身"},
    #     {"pid": PERMISSION_ENTERPRISE_PROJECT, "pname": u"企业项目管理员", "pdesc": u"特定企业的特定项目管理权限，新建的项目自动赋予管理权限给自身和企业主管理员"},
    #     # {"pid": PERMISSION_ENTERPRISE_ALL, "pname": u"管理企业权限", "pdesc": u"可以管理所有企业，包括企业的查询、新建、修改、删除"},
    #     # {"pid": PERMISSION_ENTERPRISE_PART, "pname": u"管理企业部分权限", "pdesc": u"可以管理部分企业，包括企业的查询、新建、修改、删除"},
    #     # {"pid": PERMISSION_ORG_ALL, "pname": u"企业组织管理权限", "pdesc": u"可以管理企业的组织，包括组织的查询、新建、修改、删除"},
    #     # {"pid": PERMISSION_PROJECT_ALL, "pname": u"企业项目管理权限", "pdesc": u"可以管理企业的项目，包括项目的查询、新建、修改、删除，以及项目问卷的分发等"},
    #     # {"pid": PERMISSION_PROJECT_PART, "pname": u"企业部分项目管理权限", "pdesc": u"可以管理企业的部分项目，包括项目的查询、新建、修改、删除，以及项目问卷的分发等"},
    #     {"pid": PERMISSION_MODEL_ORG_ALL, "pname": u"组织模型管理权限", "pdesc": u"可以管理企业的组织模型，包括组织模型/维度/指标的查询、新建、修改、删除"},
    #     {"pid": PERMISSION_MODEL_PERSONAL_ALL, "pname": u"个人模型管理权限", "pdesc": u"可以管理企业的个人模型，包括组织模型/维度/指标的查询、新建、修改、删除"},
    #     {"pid": PERMISSION_SURVEY_ORG_ALL, "pname": u"组织问卷管理权限", "pdesc": u"可以管理企业的组织问卷，包括组织问卷的查询、新建、修改、删除，以及组织问卷的组卷、预览"},
    #     {"pid": PERMISSION_SURVEY_PERSONAL_ALL, "pname": u"个人问卷管理权限", "pdesc": u"可以管理企业的个人问卷，包括个人问卷的查询、新建、修改、删除，以及个人问卷的组卷、预览"},
    #     {"pid": PERMISSION_SURVEY_360_ALL, "pname": u"360问卷管理权限", "pdesc": u"可以管理企业的360问卷，包括360问卷的查询、新建、修改、删除，以及组织问卷的组卷、预览"},
    #     # {"pid": PERMISSION_SURVEY_ORG_USE, "pname": u"组织问卷使用授权",
    #     #  "pdesc": u"可以管理企业的部分组织问卷，包括组织问卷的查询、新建、修改、删除，以及组织问卷的组卷、预览"},
    #     # {"pid": PERMISSION_SURVEY_PERSONAL_USE, "pname": u"个人问卷使用权限",
    #     #  "pdesc": u"可以管理企业的个人问卷，包括个人问卷的查询、新建、修改、删除，以及个人问卷的组卷、预览"},
    #     # {"pid": PERMISSION_SURVEY_360_USE, "pname": u"360问卷使用权限",
    #     #  "pdesc": u"可以管理企业的360问卷，包括360问卷的查询、新建、修改、删除，以及组织问卷的组卷、预览"},
    #     {"pid": PERMISSION_QUESTION_ALL, "pname": u"题库管理权限", "pdesc": u"可以管理企业的题库，包括题库/文件夹/子文件夹/题目的查询、新建、修改、删除"},
    #     {"pid": PERMISSION_TAG_ALL, "pname": u"标签管理权限", "pdesc": u"可以管理标签，包括标签的查询、新建、修改、删除"},
    #     {"pid": PERMISSION_PERMISSION_ALL, "pname": u"权限管理权限", "pdesc": u"可以管理标签，包括权限的分配等"}
    # ]
    # permission_type = models.PositiveSmallIntegerField(u"权限类型", choices=PERMISSION_CHOICES, default=PERMISSION_NONE)
    # permision 2.0
    PERMISSION_MAP = [
        {"pid": PERMISSION_PERMISSION_ROLE, "pname": u"增加/删除/修改/查看角色", "pdesc": u"具有增加/删除/修改/查看角色权限"},
        {"pid": PERMISSION_PERMISSION_ROLE_USER, "pname": u"增加/删除/修改/查看用户", "pdesc": u"具有增加/删除/修改/查看角色用户权限"},
        # {"pid": PERMISSION_PERMISSION_PROJECT_ASSIGNED, "pname": u"项目分配权限", "pdesc": u"可以通过权限管理，查看具有项目管理权限的角色用户，并进行项目分配"},
        {"pid": PERMISSION_ENTERPRISE_ALL_SEE, "pname": u"企业查看权限", "pdesc": u"查看所有企业信息，包括查看项目信息"},
        {"pid": PERMISSION_ENTERPRISE_PART, "pname": u"企业管理权限", "pdesc": u"查看和编辑自己建立的企业和企业下的所有项目"},
        {"pid": PERMISSION_PROJECT_PART, "pname": u"项目管理权限", "pdesc": u"查看和编辑分配的项目"},
        {"pid": PERMISSION_SURVEY_ORG_ALL, "pname": u"问卷管理权限", "pdesc": u"可以对问卷（组织问卷/个人问卷）进行管理"},
        {"pid": PERMISSION_MODEL_ORG_ALL, "pname": u"模型管理权限", "pdesc": u"可以对模型（组织模型/个人模型）进行管理"},
        {"pid": PERMISSION_QUESTION_ALL, "pname": u"题库管理权限", "pdesc": u"可以对题库进行管理"},
        {"pid": PERMISSION_TAG_ALL, "pname": u"标签管理权限", "pdesc": u"可以对标签进行管理"}
    ]
    SUPER_USER_PERMISSIONS = [
        PERMISSION_PERMISSION_ROLE,
        PERMISSION_PERMISSION_ROLE_USER,
        PERMISSION_PERMISSION_PROJECT_ASSIGNED,
        PERMISSION_ENTERPRISE_PART,
        PERMISSION_ENTERPRISE_ALL,
        PERMISSION_PROJECT_PART,
        PERMISSION_TAG_ALL,
        PERMISSION_QUESTION_ALL,
        PERMISSION_SURVEY_ORG_ALL,
        PERMISSION_MODEL_ORG_ALL,
        PERMISSION_NORMAL_PORTRAY,
        PERMISSION_PROFESSIONAL_PORTRAY,
        PERMISSION_REPORT_TEMPLATE,
        PERMISSION_CONSOLE
    ]


class RoleBusinessPermission(BaseModel):
    u"""角色权限"""
    role_id = models.BigIntegerField(u"角色ID", db_index=True, default=0)
    permission_id = models.BigIntegerField(u"权限ID", db_index=True, default=0)


class RoleUser(BaseModel):
    u"""角色有哪些人"""
    role_id = models.BigIntegerField(u"角色ID", db_index=True, default=0)
    user_id = models.BigIntegerField(u"人员ID", db_index=True, default=0)
    # username = models.CharField(u"姓名", max_length=128, null=True, db_index=True)
    # phone = models.CharField(u"电话", max_length=20, db_index=True, blank=True, null=True)
    # email = models.EmailField(u'邮箱', db_index=True, blank=True, null=True)
    remark = models.CharField(u"备注", max_length=128, null=True, db_index=True)
    # active_code = models.CharField(u"激活码", max_length=20, db_index=True, blank=True, null=True)
    # active_code_valid = models.BooleanField(u"激活码是否有效", default=False, db_index=True)


class RoleUserBusiness(BaseModel):
    u"""角色人授权对象"""
    role_id = models.BigIntegerField(u"角色ID", db_index=True, default=0)
    user_id = models.BigIntegerField(u"人员ID", db_index=True, default=0)
    MODEL_TYPE_SURVEY = 10
    MODEL_TYPE_ENTERPRISE = 20
    MODEL_TYPE_PROJECT = 30
    MODEL_TYPE_CHOICES = (
        (MODEL_TYPE_SURVEY, u'问卷'),
        (MODEL_TYPE_ENTERPRISE, u'企业'),
        (MODEL_TYPE_PROJECT, u'项目')
    )
    model_type = models.PositiveSmallIntegerField(u"授权对象类型", db_index=True, default=0)
    model_id = models.BigIntegerField(u"授权对象ID", db_index=True, default=0)