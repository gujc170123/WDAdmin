# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import datetime
import json

import pytz
from django.db import models

from WeiDuAdmin import settings
from utils.models import BaseModel
from wduser.models import Organization, BaseOrganization, AuthUser


class AssessProject(BaseModel):

    enterprise_id = models.BigIntegerField(u"企业ID", db_index=True, default=0)
    name = models.CharField(u"项目名称", max_length=100, db_index=True)
    en_name = models.CharField(u"英文项目名称", max_length=100, default=u'', db_index=True, blank=True, null=True)
    begin_time = models.DateTimeField(u"开始时间", db_index=True, blank=True, null=True)
    end_time = models.DateTimeField(u"结束时间", db_index=True, blank=True, null=True)
    FINISH_URL = 100
    FINISH_TXT = 200
    FINISH_CHOICES = (
        (FINISH_URL, u'跳转链接'),
        (FINISH_TXT, u'富文本'),
    )
    finish_choices = models.PositiveIntegerField(u"跳转类型", default=FINISH_URL, db_index=True, choices=FINISH_CHOICES)
    finish_txt = models.CharField(u"富文本", max_length=4096, blank=True, null=True)
    finish_redirect = models.CharField(u"完成后跳转链接", max_length=264, blank=True, null=True)
    assess_logo = models.URLField(u"自定义LOGO", blank=True, null=True)
    advert_url = models.URLField(u"广告横幅", blank=True, null=True)
    TYPE_ORGANIZATION = 100
    TYPE_PERSON = 200
    TYPE_360 = 300
    TYPE_CHOICES = (
        (TYPE_ORGANIZATION, u"组织测评"),
        (TYPE_PERSON, u"个人测评"),
        (TYPE_360, u"360测评")
    )
    assess_type = models.PositiveIntegerField(u"项目类型", default=TYPE_ORGANIZATION, db_index=True, choices=TYPE_CHOICES)
    user_count = models.PositiveIntegerField(u"测验人次", default=0, db_index=True)
    DISTRIBUTE_OPEN = 10
    DISTRIBUTE_IMPORT = 20
    DISTRIBUTE_CHOICES = (
        (DISTRIBUTE_OPEN, u"公开测评"),
        (DISTRIBUTE_IMPORT, u"导入测评"),
    )
    distribute_type = models.PositiveIntegerField(u"分发类型", default=DISTRIBUTE_OPEN, choices=DISTRIBUTE_CHOICES, db_index=True)
    has_distributed = models.BooleanField(u"是否分发过", default=False)
    is_answer_survey_by_order = models.BooleanField(u"是否按顺序做问卷", default=False)
    has_survey_random = models.BooleanField(u"是否有问卷随机", default=False)
    survey_random_number = models.BigIntegerField(u"问卷随机数量", null=True)
    survey_random_index = models.BigIntegerField(u"问卷标志位", null=True, default=0, blank=True)
    show_people_info = models.BooleanField(u"个人信息", default=True)

    STATUS_WAITING = 0
    STATUS_WORKING = 10
    STATUS_END = 20

    @property
    def project_status(self):
        now = datetime.datetime.now()
        if self.begin_time is None or self.end_time is None:
            return self.STATUS_WAITING
        elif now < self.begin_time:
            return self.STATUS_WAITING
        elif self.begin_time < now < self.end_time:
            return self.STATUS_WORKING
        elif now > self.end_time:
            return self.STATUS_END
        else:
            return self.STATUS_WAITING

    @property
    def org_infos(self):
        org_ids = AssessOrganization.objects.filter_active(assess_id=self.id).values_list("organization_id", flat=True)
        return Organization.objects.filter_active(id__in=org_ids).values("id", "name")

    @property
    def finish_url(self):
        if self.finish_choices == self.FINISH_TXT:
            return settings.CLIENT_HOST + "/#/complete"
        else:
            return self.finish_redirect


class AssessOrganization(BaseModel):
    u"""测评归属组织, 包括父组织和所有子组织"""
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    organization_id = models.BigIntegerField(u"组织ID", db_index=True, default=0)
    organization_code = models.CharField(u"组织标识码", max_length=20, db_index=True, null=True)

class AssessSurveyOrganization(BaseModel):
    u"""测评问卷组织关联
    @version: 20180725 弃用
    """
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    survey_id = models.BigIntegerField(u"测评问卷ID", db_index=True, default=0)
    organization_id = models.BigIntegerField(u"组织ID", db_index=True)
    organization_code = models.CharField(u"组织标识码", max_length=20, db_index=True, null=True)

class FullOrganization(BaseModel):
    assess = models.ForeignKey(AssessProject)
    organization = models.ForeignKey(Organization)
    organization1 = models.BigIntegerField(db_index=True, null=True)
    organization2 = models.BigIntegerField(db_index=True, null=True)
    organization3 = models.BigIntegerField(db_index=True, null=True)
    organization4 = models.BigIntegerField(db_index=True, null=True)
    organization5 = models.BigIntegerField(db_index=True, null=True)
    organization6 = models.BigIntegerField(db_index=True, null=True)

class AssessUser(BaseModel):
    u"""项目所有用户
    @version:20180622 @summary:
    """
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    people_id = models.BigIntegerField(u"测评用户ID/自评用户ID", db_index=True, default=0)
    ROLE_TYPE_NORMAL = 10
    ROLE_TYPE_SELF = 20
    ROLE_TYPE_HIGHER_LEVEL = 30
    ROLE_TYPE_LOWER_LEVEL = 40
    ROLE_TYPE_SAME_LEVEL = 50
    ROLE_TYPE_SUPPLIER_LEVEL = 60
    ROLE_CHOICES = (
        (ROLE_TYPE_NORMAL, u"普通"),
        (ROLE_TYPE_SELF, u"自评"),
        (ROLE_TYPE_HIGHER_LEVEL, u"上级"),
        (ROLE_TYPE_LOWER_LEVEL, u"下级"),
        (ROLE_TYPE_SAME_LEVEL, u"同级"),
        (ROLE_TYPE_SUPPLIER_LEVEL, u"供应商")
    )
    role_type = models.PositiveSmallIntegerField(u"测评角色", default=ROLE_TYPE_NORMAL, choices=ROLE_CHOICES, db_index=True)
    role_people_id = models.BigIntegerField(u"测评角色人员ID", default=0, db_index=True)


# 弃用 ，  PeopleSurveyRelation 代替
class AssessSurveyUser(BaseModel):
    u"""项目问卷的参与用户
    @version:20180622 @summary: 测评端系统记录，后台需要的话，从测评端系统获取
    """
    # TODO: 问卷开始后需要修改
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    survey_id = models.BigIntegerField(u"测评问卷ID", db_index=True, default=0)
    people_id = models.BigIntegerField(u"测评用户ID", db_index=True, default=0)
    evaluated_people_id = models.BigIntegerField(u"被评价人员ID", db_index=True, default=0)
    STATUS_NOT_BEGIN = 10
    STATUS_DOING = 20
    STATUS_FINISH = 30
    STATUS_EXPIRED = 40
    STATUS_CHOICES = (
        (STATUS_NOT_BEGIN, u"未开始"),
        (STATUS_DOING, u"进行中"),
        (STATUS_FINISH, u"已完成"),
        (STATUS_EXPIRED, u"已过期/未完成")
    )
    status = models.PositiveSmallIntegerField(u"测评状态", db_index=True, default=STATUS_NOT_BEGIN, choices=STATUS_CHOICES)


class AssessSurveyUserDistribute(BaseModel):
    u"""项目问卷的参与用户
        @version:20180622 @summary: 分发状态
        """
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    survey_id = models.BigIntegerField(u"测评问卷ID", db_index=True, default=0)
    role_type = models.PositiveSmallIntegerField(
        u"测评角色", default=AssessUser.ROLE_TYPE_NORMAL, choices=AssessUser.ROLE_CHOICES, db_index=True)
    evaluated_people_id = models.BigIntegerField(u"被评价人员ID", db_index=True, default=0)
    people_ids = models.TextField(u"分发人员ID数组", null=True, blank=True)


class AssessSurveyRelation(BaseModel):
    u"""项目与问卷关联"""
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    survey_id = models.BigIntegerField(u"测评问卷ID", db_index=True, default=0)
    survey_been_random = models.BooleanField(u"该问卷是否随机", db_index=True, default=False)
    role_type = models.PositiveSmallIntegerField(
        u"测评角色", default=AssessUser.ROLE_TYPE_NORMAL, choices=AssessUser.ROLE_CHOICES, db_index=True)
    user_count = models.PositiveIntegerField(u"测验人次", default=0, db_index=True)
    DISTRIBUTE_OPEN = 10
    DISTRIBUTE_IMPORT = 20
    custom_config = models.CharField(u"问卷配置信息", max_length=2048)
    order_number = models.PositiveSmallIntegerField(u"问卷顺序", default=0)
    CAN_VIEW_REPORT = 1
    CAN_NOT_VIEW_REPORT = 0
    people_view_report = models.PositiveSmallIntegerField(u"报告个人是否可以查看", default=CAN_NOT_VIEW_REPORT, db_index=True)

    def get_project(self):
        if hasattr(self, '__cache__') and self.__cache__.get("project", None) is not None:
            return self.__cache__["project"]
        if not hasattr(self, '__cache__'):
            self.__cache__ = {}
        self.__cache__["project"] = AssessProject.objects.get(id=self.assess_id)
        return self.__cache__["project"]

    @property
    def begin_time(self):
        return self.get_project().begin_time

    @property
    def end_time(self):
        return self.get_project().end_time

    @property
    def survey_status(self):
        now = datetime.datetime.now()
        if self.begin_time is None or self.end_time is None:
            return AssessProject.STATUS_WAITING
        elif now < self.begin_time:
            return AssessProject.STATUS_WAITING
        elif now < self.end_time:
            return AssessProject.STATUS_WORKING
        else:
            return AssessProject.STATUS_END

    @property
    def finish_redirect(self):
        if not self.custom_config:
            return None
        custom_config = json.loads(self.custom_config)
        return custom_config.get("finish_redirect", None)

    @property
    def assess_logo(self):
        if not self.custom_config:
            return self.get_project().assess_logo
        custom_config = json.loads(self.custom_config)
        logo = custom_config.get("assess_logo", None)
        if not logo:
            logo = self.get_project().assess_logo
        return logo

    @property
    def advert_url(self):
        return self.get_project().advert_url

    @property
    def distribute_type(self):
        return self.get_project().distribute_type


class AssessGatherInfo(BaseModel):
    u"""收集的信息"""
    info_name = models.CharField(u"信息名称", max_length=512, db_index=True)
    # 是否归属于某个项目， == 0时，是系统收集
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    INFO_TYPE_STR = 10
    INFO_TYPE_INT = 20
    INFO_TYPE_LIST = 30
    INFO_TYPE_DATE = 40
    INFO_TYPE_CHOICES = (
        (INFO_TYPE_STR, u"字符串"),
        (INFO_TYPE_INT, u"整形"),
        (INFO_TYPE_LIST, u"列表"),
        (INFO_TYPE_DATE, u"日期")
    )
    info_type = models.PositiveSmallIntegerField(u"信息类型", choices=INFO_TYPE_CHOICES, default=INFO_TYPE_STR)
    # 列表值 ['','']
    config_info = models.CharField(u"信息配置", max_length=1024)
    is_required = models.BooleanField(u"是否必填", default=False, db_index=True)
    is_modified = models.BooleanField(u"是否可以修改", default=True, db_index=True)

class AssessProjectSurveyConfig(BaseModel):
    u"""项目问卷自定义配置
    可以配置 维度名称 维度说明 指标名称 指标说明 题干 选项
    """
    assess_id = models.BigIntegerField(u"测评项目ID", db_index=True, default=0)
    survey_id = models.BigIntegerField(u"测评问卷ID", db_index=True, default=0)
    MODEL_TYPE_NONE = 0
    MODEL_TYPE_DIMENSION = 10
    MODEL_TYPE_DIMENSION_DESC = 11
    MODEL_TYPE_SUBSTANDARD = 20
    MODEL_TYPE_SUBSTANDARD_DESC = 21
    MODEL_TYPE_QUESTION = 30
    MODEL_TYPE_OPTION = 40
    MODEL_TYPE_SLIDE_OPTION = 41
    MODEL_TYPE_CHOICES = (
        (MODEL_TYPE_NONE, u"无"),
        (MODEL_TYPE_DIMENSION, u"维度"), # 10
        (MODEL_TYPE_DIMENSION_DESC, u"维度描述"), # 11
        (MODEL_TYPE_SUBSTANDARD, u"指标"), # 20
        (MODEL_TYPE_SUBSTANDARD_DESC, u"指标描述"), # 21
        (MODEL_TYPE_QUESTION, u"题干"), # 30
        (MODEL_TYPE_OPTION, u"选项"), # 40
        (MODEL_TYPE_SLIDE_OPTION, u"滑块设置") # 41
    )
    # 要支持单选、多选、滑块、互斥， 滑块题选项
    model_type = models.PositiveSmallIntegerField(u"自定义配置对象", choices=MODEL_TYPE_CHOICES,
                                                  default=MODEL_TYPE_NONE, db_index=True)
    model_id = models.BigIntegerField(u"自定义配置对象ID", db_index=True, default=0)
    # @version: 20180725 @summary: 支持滑块题设置
    content = models.TextField(u"自定义配置内容", null=True, blank=True)
    en_content = models.TextField(u"英文自定义配置内容", null=True, blank=True, default=u'')