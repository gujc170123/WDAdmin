# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import models

# Create your models here.
from utils.models import BaseModel


class ResearchModel(BaseModel):
    u"""研究模型"""
    root_model_id = models.BigIntegerField(u"根模型", db_index=True, default=0)
    parent_model_id = models.BigIntegerField(u"父模型", db_index=True, default=0)
    model_ids_of_escape = models.CharField(u'转义模型对应的模型的ids', max_length=200, default='', null=True, blank=True)
    name = models.CharField(u"中文名称", max_length=128, db_index=True)
    en_name = models.CharField(u"英文名称", max_length=128, db_index=True, null=True, blank=True, default=u'')
    desc = models.CharField(u"描述/备注信息", max_length=200, null=True, blank=True)
    en_desc = models.CharField(u"英文描述/备注信息", max_length=2000, null=True, blank=True, default=u'')
    TYPE_STANDARD = 10
    TYPE_INHERIT = 20
    TYPE_ESCAPE = 30
    TYPE_CHOICES = (
        (TYPE_STANDARD, u'标准'),
        (TYPE_INHERIT, u'派生'),
        (TYPE_ESCAPE, u'转义')
    )
    model_type = models.PositiveSmallIntegerField(u"模型类型", choices=TYPE_CHOICES, default=TYPE_INHERIT, db_index=True)
    STATUS_DRAFT = 10
    STATUS_RELEASE = 20
    STATUS_CHOICES = (
        (STATUS_DRAFT, u'草稿'),
        (STATUS_RELEASE, u'已发布')
    )
    status = models.PositiveSmallIntegerField(u"状态", choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    ALGORITHM_WEIGHTED = 1
    ALGORITHM_GZJZG = 2
    ALGORITHM_RGFX = 3
    ALGORITHM_DISC = 4
    ALGORITHM_SWQN = 5
    ALGORITHM_XLZB = 6
    ALGORITHM_XFZS = 7
    ALGORITHM_XWFG = 8
    ALGORITHM_LDFG = 9
    ALGORITHM_YGXLJK = 10
    ALGORITHM_ZYDX = 11
    ALGORITHM_ZGC_ZP = 12
    ALGORITHM_ZGC_TP = 13
    ALGORITHM_XFZS_EN = 14
    ALGORITHM_YGXLJK_EN = 15
    ALGORITHM_XFXQ = 16
    ALGORITHM_CHOICES = (
        (ALGORITHM_WEIGHTED, u'加权平均算法'),
        (ALGORITHM_GZJZG, u'工作价值观算法'),
        (ALGORITHM_RGFX, u'人格风险算法'),
        (ALGORITHM_DISC, u'职业个性DISC算法'),
        (ALGORITHM_SWQN, u'思维潜能算法'),
        (ALGORITHM_XLZB, u"心理资本算法"),
        (ALGORITHM_XFZS, u"幸福指数算法"),
        (ALGORITHM_XWFG, u"行为风格算法"),
        (ALGORITHM_LDFG, u"领导风格算法"),
        (ALGORITHM_YGXLJK, u"员工心理健康算法"),
        (ALGORITHM_ZYDX, u"职业定向算法"),
        (ALGORITHM_ZGC_ZP, u"中高层管理能力-自评算法"),
        (ALGORITHM_ZGC_TP, u"中高层管理能力-他评算法"),
        (ALGORITHM_XFZS_EN, u"幸福指数算法英文"),
        (ALGORITHM_YGXLJK_EN, u"员工心理健康算法英文"),
        (ALGORITHM_XFXQ, u"幸福需求算法")
    )
    algorithm_id = models.BigIntegerField(u"算法", db_index=True, default=ALGORITHM_WEIGHTED, choices=ALGORITHM_CHOICES)
    inherit_count = models.PositiveIntegerField(u"派生次数", db_index=True, default=0)
    used_count = models.PositiveIntegerField(u"使用次数", db_index=True, default=0)
    CATEGORY_ORG = 10
    CATEGORY_PERSONAL = 20
    CATEGORY_CHOICES = (
        (CATEGORY_ORG, u"组织模型"),
        (CATEGORY_PERSONAL, u"个人模型")
    )
    model_category = models.PositiveSmallIntegerField(u"模型形式", default=CATEGORY_ORG, choices=CATEGORY_CHOICES, db_index=True)

    @property
    def root_model_name(self):
        if self.root_model_id == 0:
            return ""
        else:
            return ResearchModel.objects.get(id=self.root_model_id).name


class ResearchDimension(BaseModel):
    u"""维度"""
    DEFAULT_MAX_WEIGHT = 100
    model_id = models.BigIntegerField(u"所属模型", db_index=True, default=0)
    name = models.CharField(u"中文名称", max_length=128, db_index=True)
    en_name = models.CharField(u"英文名称", max_length=128, db_index=True, null=True, blank=True, default=u'')
    weight = models.FloatField(u"权重", default=0)
    # is_weight_auto = models.BooleanField(u"自动权重", default=True, db_index=True)
    model_type = models.PositiveSmallIntegerField(u"模型类型", choices=ResearchModel.TYPE_CHOICES,
                                                  default=ResearchModel.TYPE_INHERIT, db_index=True)
    model_category = models.PositiveSmallIntegerField(u"模型形式", default=ResearchModel.CATEGORY_ORG, choices=ResearchModel.CATEGORY_CHOICES,
                                                      db_index=True)
    desc = models.CharField(u"描述", max_length=512, null=True, blank=True)
    en_desc = models.CharField(u"英文描述", max_length=2048, null=True, blank=True, default=u'')
    order_number = models.PositiveSmallIntegerField(u"维度顺序", default=0)

    @property
    def model_name(self):
        try:
            return ResearchModel.objects.get(id=self.model_id).name
        except:
            return ""


class ResearchSubstandard(BaseModel):
    u"""子标
    子标，dimension_id>0, parent_id = 0
    children  dimension_id>0, parent_id > 0
    """
    DEFAULT_MAX_WEIGHT = 100
    model_id = models.BigIntegerField(u"所属模型", db_index=True, default=0)
    dimension_id = models.BigIntegerField(u"所属维度", db_index=True, default=0)
    parent_id = models.BigIntegerField(u"父子标", db_index=True, default=0)
    name = models.CharField(u"中文名称", max_length=128, db_index=True)
    en_name = models.CharField(u"英文名称", max_length=128, db_index=True, null=True, blank=True, default=u'')
    weight = models.FloatField(u"权重", default=0)
    model_type = models.PositiveSmallIntegerField(u"模型类型", choices=ResearchModel.TYPE_CHOICES,
                                                  default=ResearchModel.TYPE_INHERIT, db_index=True)
    model_category = models.PositiveSmallIntegerField(u"模型形式", default=ResearchModel.CATEGORY_ORG,
                                                      choices=ResearchModel.CATEGORY_CHOICES,
                                                      db_index=True)

    @property
    def model_name(self):
        try:

            return ResearchModel.objects.get(id=self.model_id).name
        except:
            return ""

    @property
    def dimension_name(self):
        try:
            return ResearchDimension.objects.get(id=self.dimension_id).name
        except:
            return ""


class Report(BaseModel):
    u"""报告模板"""
    report_name = models.CharField(u"报告模板名称", max_length=64)
    report_type_id = models.CharField(u"报告类型名称", max_length=64, null=True, blank=True)
    desc = models.CharField(u"报告模板描述", max_length=128, db_index=True, null=True, blank=True)
    report_url = models.URLField(u"报告模板地址", max_length=256, db_index=True)


class ReportSurveyAssessmentProjectRelation(BaseModel):
    u"""
    报告问卷项目关联关系
    """
    report_id = models.BigIntegerField(u"所属报告ID", db_index=True, default=0)
    survey_id = models.BigIntegerField(u"所属问卷ID", db_index=True, default=0)
    assessment_project_id = models.BigIntegerField(u"所属项目ID", db_index=True, default=0)
    # model_id = models.BigIntegerField(u"所属模型ID", db_index=True, default=0)

    survey_name = models.CharField(u"问卷名称", max_length=64, db_index=True, null=True, blank=True)


    # @property
    # def survey_name(self):
    #     try:
    #         from survey.models import Survey
    #         return Survey.objects.get(id=self.survey_id).title
    #     except:
    #         return ""

    @property
    def assessment_project_name(self):
        try:
            from assessment.models import AssessProject
            return AssessProject.objects.get(id=self.assessment_project_id).name
        except:
            return ""

    # @property
    # def model_name(self):
    #     try:
    #         return ResearchModel.objects.get(id=self.model_id).name
    #     except:
    #         return ""


# class ReportSurvey(BaseModel):
#     u"""问卷"""
#     survey_id = models.BigIntegerField(u"所属问卷ID", db_index=True, default=0)
#     assessment_project_id = models.BigIntegerField(u"所属项目ID", db_index=True, default=0)
#
#
#     @property
#     def survey_name(self):
#         try:
#
#             from survey.models import Survey
#             return Survey.objects.get(id=self.survey_id).name
#         except:
#             return ""
#
#     @property
#     def assessment_project_name(self):
#         try:
#             from assessment.models import AssessProject
#             return AssessProject.objects.get(id=self.assessment_project_id).name
#         except:
#             return ""

class Tag(BaseModel):
    u"""标签是好多业务模型的标签，实际上是各业务模型的自定义属性"""

    TYPE_TEXT = 10
    TYPE_INT = 20
    TYPE_OPTION = 30
    TYPE_DATE = 40
    TYPE_CHOICES = (
        (TYPE_TEXT, u"文本型"),
        (TYPE_INT, u"整形型"),
        (TYPE_OPTION, u"选项型"),
        (TYPE_DATE, u"时间型")
    )

    tag_type = models.PositiveSmallIntegerField(u"标签类型", default=TYPE_TEXT, choices=TYPE_CHOICES, db_index=True, blank=True)

    MODEL_GENERAL = 1  # 其他 / 通用
    MODEL_COMPANY = 10  # 企业
    MODEL_ORG = 20  # 组织
    MODEL_PROJECT = 30  # 项目
    MODEL_MODEL = 40  # 模型 组织模型 个人模型 360模型
    # MODEL_MODEL_PERSONAL = 41  # 模型 组织模型 个人模型
    # MODEL_MODEL_360 = 42  # 模型 组织模型 个人模型
    MODEL_DIMENSION = 50  # 维度
    MODEL_SUBSTANDARD = 60  # 子标
    MODEL_QUESTION_LIB = 70  # 题库
    MODEL_QUESTION_FOLDER = 71  # 文件夹
    # MODEL_QUESTION_SUB_FOLDER = 72  # 子文件夹
    MODEL_CONSTRUCT = 80  # 构面
    MODEL_QUESTION = 90  # 题目
    # MODEL_OPTION = 100  # 选项
    MODEL_QUESTIONNAIRE = 110  # 问卷 组织问卷 个人问卷 360 问卷
    MODEL_REPORT = 120  # 报告

    MODEL_CHOICES = (
        (MODEL_COMPANY, 'EnterpriseInfo'),
        (MODEL_ORG, 'Organization'),
        (MODEL_PROJECT, 'AssessProject'),
        (MODEL_MODEL, 'ResearchModel'),
        (MODEL_DIMENSION, 'ResearchDimension'),
        (MODEL_SUBSTANDARD, 'ResearchSubstandard'),
        (MODEL_QUESTION_LIB, 'QuestionBank'),
        (MODEL_QUESTION_FOLDER, 'QuestionFolder'),
        # (MODEL_QUESTION_SUB_FOLDER, 'QuestionFolder'),
        (MODEL_CONSTRUCT, 'QuestionFacet'),
        (MODEL_QUESTION, 'Question'),
        # (MODEL_OPTION, 'QuestionOption'),
        (MODEL_QUESTIONNAIRE, 'Survey'),
        (MODEL_REPORT, 'Report'),
    )
    TAG_MODEL_MAP = {
        "General": {"relation": "GeneralTagRelation", "index": MODEL_GENERAL},
        "EnterpriseInfo": {"relation": "EnterpriseTagRelation", "index": MODEL_COMPANY},
        "Organization": {"relation": "OrganizationTagRelation", "index": MODEL_ORG},
        "AssessProject": {"relation": "ProjectTagRelation", "index": MODEL_PROJECT},
        "ResearchModel": {"relation": "ModelTagRelation", "index": MODEL_MODEL},
        "ResearchDimension": {"relation": "DimensionTagRelation", "index": MODEL_DIMENSION},
        "ResearchSubstandard": {"relation": "SubstandardTagRelation", "index": MODEL_SUBSTANDARD},
        "QuestionBank": {"relation": "QuestionBankTagRelation", "index": MODEL_QUESTION_LIB},
        "QuestionFolder": {"relation": "QuestionFolderTagRelation", "index": MODEL_QUESTION_FOLDER},
        "QuestionFacet": {"relation": "QuestionFacetTagRelation", "index": MODEL_CONSTRUCT},
        "Question": {"relation": "QuestionTagRelation", "index": MODEL_QUESTION},
        # "QuestionOption": {"relation": "QuestionOptionTagRelation", "index": MODEL_OPTION},
        "Survey": {"relation": "SurveyTagRelation", "index": MODEL_QUESTIONNAIRE},
        "Report": {"relation": "ReportTagRelation", "index": MODEL_REPORT},
    }
    business_model = models.PositiveSmallIntegerField(u"标签业务模型", default=MODEL_GENERAL, choices=MODEL_CHOICES, db_index=True)
    tag_name = models.CharField(u"标签名称", max_length=64)
    is_required = models.BooleanField(u"是否必填", default=False, db_index=True)
    is_system = models.BooleanField(u"是否系统设置", default=True, db_index=True)
    enterprise_id = models.BigIntegerField(u"企业ID(自定义设置)", db_index=True, default=0)
    tag_config = models.CharField(u"标签选项/限制", max_length=1024, null=True, blank=True)
    is_used = models.BooleanField(u"是否被使用", default=False, db_index=True)

    @property
    def tag_rel_model(self):
        model_name_key = None
        for model_index,  model_name in self.MODEL_CHOICES:
            if model_index == self.business_model:
                model_name_key = model_name
                break
        if model_name_key is None or not self.TAG_MODEL_MAP.has_key(model_name_key):
            return "GeneralTagRelation"
        return self.TAG_MODEL_MAP[model_name_key]['relation']

    @property
    def tag_config_data(self):
        if self.tag_config:
            return json.loads(self.tag_config)
        else:
            return None


class BaseTagModel(BaseModel):
    u"""标签业务模型"""
    tag_id = models.BigIntegerField(u"标签ID", db_index=True, default=0)
    object_id = models.BigIntegerField(u"业务模型ID", db_index=True, default=0)
    tag_value = models.CharField(u"标签值", max_length=128, null=True, blank=True)

    class Meta:
        abstract = True


class GeneralTagRelation(BaseTagModel):
    pass


class EnterpriseTagRelation(BaseTagModel):
    pass


class OrganizationTagRelation(BaseTagModel):
    pass


class ProjectTagRelation(BaseTagModel):
    pass


class ModelTagRelation(BaseTagModel):
    pass


class DimensionTagRelation(BaseTagModel):
    pass


class SubstandardTagRelation(BaseTagModel):
    pass


class QuestionBankTagRelation(BaseTagModel):
    pass


class QuestionFolderTagRelation(BaseTagModel):
    pass


class QuestionFacetTagRelation(BaseTagModel):
    pass


class QuestionTagRelation(BaseTagModel):
    pass


class QuestionOptionTagRelation(BaseTagModel):
    pass


class SurveyTagRelation(BaseTagModel):
    pass


class ReportTagRelation(BaseTagModel):
    pass