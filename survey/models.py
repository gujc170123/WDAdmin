# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import models

# Create your models here.
from assessment.models import AssessProjectSurveyConfig
from question.models import Question, QuestionFacet, QuestionOption
from research.models import ResearchModel
from utils.models import BaseModel


class Survey(BaseModel):
    u"""问卷管理（组卷）时的自定义配置有：
1）组卷方式（新建问卷时选择组卷方式）
2）题目限时 问卷限时
3）按部分测试 逐题测试 （部分按维度来划分，暂不支持维度的合并和拆分）
4）选项是否打乱
5）题目顺序是否打乱
6）不答题是否可以跳转下一题
7）题目未答完是否可以提交
8）360问卷可以设置每道题几个选项
9）普通问卷下每个维度下面可以设置调整测谎题 """
    model_id = models.BigIntegerField(u"模型ID", default=0, db_index=True)
    title = models.CharField(u"问卷名称", max_length=24, db_index=True)
    en_title = models.CharField(u"英文问卷名称", default=u'', max_length=50, db_index=True, null=True, blank=True)
    SURVEY_ORG = 10
    SURVEY_PERSONAL = 20
    SURVEY_360 = 30
    SURVEY_TYPE_CHOICES = (
        (SURVEY_ORG, u"组织问卷"),
        (SURVEY_PERSONAL, u"个人问卷"),
        (SURVEY_360, u"360问卷"),
    )
    survey_type = models.PositiveSmallIntegerField(u"问卷类型", choices=SURVEY_TYPE_CHOICES, default=SURVEY_ORG, db_index=True)
    FORM_TYPE_NORMAL = 10  # 普通组卷
    FORM_TYPE_FORCE = 20  # 迫选组卷
    FORM_TYPE_CHOICES = (
        (FORM_TYPE_NORMAL, u"普通组卷"),
        (FORM_TYPE_FORCE, u"迫选组卷"),
    )
    form_type = models.PositiveSmallIntegerField(u"组卷方式", choices=FORM_TYPE_CHOICES, default=FORM_TYPE_NORMAL)
    SURVEY_STATUS_DRAFT = 10
    SURVEY_STATUS_RELEASE = 20
    SURVEY_STATUS_CHOICES = (
        (SURVEY_STATUS_DRAFT, u"草稿"),
        (SURVEY_STATUS_RELEASE, u"已发布")
    )
    survey_status = models.PositiveSmallIntegerField(u"问卷状态", choices=SURVEY_STATUS_CHOICES, default=SURVEY_STATUS_DRAFT, db_index=True)
    desc = models.CharField(u"问卷描述", max_length=2000, null=True, blank=True)
    en_desc = models.CharField(u"英文问卷描述", default=u'', max_length=2000, null=True, blank=True)
    use_count = models.PositiveIntegerField(u"使用次数", default=0, db_index=True)
    # 问卷限时 题目限时 为0时代表不限时
    time_limit = models.PositiveSmallIntegerField(u"问卷限时（分钟）", default=0)
    # 20180605 去掉题目限时
    question_time_limit = models.PositiveSmallIntegerField(u"题目限时（秒）", default=0)
    # config_info: 按部分测试 逐题测试,   选项是否打乱,题目顺序是否打乱,不答题是否可以跳转下一题,题目未答完是否可以提交
    # 按部分测试 逐题测试
    TEST_TYPE_BY_PART = 1
    TEST_TYPE_BY_QUESTION = 2
    # 项目中是否可以查看问卷详情
    SEE_DETAIL_PERMISSION = True
    #
    RANDOM_OPTION_DEFAULT = 0
    RANDOM_OPTION_RANDOM = 1
    RANDOM_OPTION_ORDER_RANDOM = 2
    # 迫选级别维度1
    # 迫选级别子标2
    BASE_LEVEL_DIMENSION = 1
    BASE_LEVEL_SUBSTANDARD = 2

    DEFAULT_CONFIG = {
        "test_type": TEST_TYPE_BY_PART,
        'random_options': RANDOM_OPTION_DEFAULT,
        'random_question': False,
        'goto_next_question': False,
        'unfinished_commit': False,
        'force_option_num': 0,
        'force_base_level': BASE_LEVEL_SUBSTANDARD,
        'see_detail_permission': True
    }
    config_info = models.CharField(u"自定义配置", max_length=256, null=True, blank=True)

    @property
    def model_name(self):
        if self.model_id == 0:
            return ""
        return ResearchModel.objects.get(id=self.model_id).name

    @property
    def custom_config(self):
        if not self.config_info:
            return self.DEFAULT_CONFIG
        config_info = json.loads(self.config_info)
        custom_config = {}
        for key in self.DEFAULT_CONFIG.keys():
            custom_config[key] = config_info.get(key, self.DEFAULT_CONFIG[key])
        return custom_config

    @property
    def force_option_num(self):
        if not self.config_info:
            return 0
        config_info = json.loads(self.config_info)
        return config_info.get('force_option_num', 0)

    @property
    def force_base_level(self):
        if not self.config_info:
            return self.BASE_LEVEL_SUBSTANDARD
        config_info = json.loads(self.config_info)
        return config_info.get('force_base_level', self.BASE_LEVEL_SUBSTANDARD)

    @property
    def test_type(self):
        if not self.config_info:
            return self.TEST_TYPE_BY_PART
        config_info = json.loads(self.config_info)
        return config_info.get('test_type', self.TEST_TYPE_BY_PART)

    @property
    def see_detail_permission(self):
        if not self.config_info:
            return self.SEE_DETAIL_PERMISSION
        config_info = json.loads(self.config_info)
        return config_info.get('see_detail_permission', self.SEE_DETAIL_PERMISSION)

    def set_custom_config(self, custom_config, force_save=True):
        set_custom_config = {}
        for key in self.DEFAULT_CONFIG:
            if key in custom_config:
                set_custom_config[key] = custom_config.get(key, self.DEFAULT_CONFIG[key])
        if not self.config_info:
            self.config_info = json.dumps(set_custom_config)
        else:
            config_info = json.loads(self.config_info)
            for key in set_custom_config:
                config_info[key] = set_custom_config[key]
            self.config_info = json.dumps(config_info)
        if force_save:
            self.save()

    def set_force_option_num(self, force_option_num, force_save=True):
        self.set_custom_config({'force_option_num': force_option_num}, force_save)

    def set_force_base_level(self, force_base_level, force_save=True):
        self.set_custom_config({'force_base_level': force_base_level}, force_save)


class SurveyModelFacetRelation(BaseModel):
    u"""问卷模型构面关联"""
    survey_id = models.BigIntegerField(u"问卷ID", default=0, db_index=True)
    # TODO：问卷变更模型时，需要把之前关联的模型题目关系去掉
    model_id = models.BigIntegerField(u"问卷关联的模型ID", default=0, db_index=True)
    RELATED_TYPE_AUTO = 10
    RELATED_TYPE_MANUAL = 20
    RELATED_CHOICES = (
        (RELATED_TYPE_AUTO, u"自动关联"),
        (RELATED_TYPE_MANUAL, u"手动关联")
    )
    related_type = models.PositiveSmallIntegerField(u"问卷题目关联方式", default=RELATED_TYPE_AUTO, choices=RELATED_CHOICES)
    # 构面关联对象类型
    RELATED_DIMENSION = 1
    RELATED_SUBSTANDARD = 2
    RELATED_CHOICES = (
        (RELATED_DIMENSION, u"维度"),
        (RELATED_SUBSTANDARD, u"指标")
    )
    # 问卷关联的是 维度 或 指标??
    related_obj_type = models.BigIntegerField(u"问卷关联的模型ID", default=0, db_index=True)
    # 维度 或 指标 的id
    related_obj_id = models.BigIntegerField(u"问卷关联对象的ID", default=0, db_index=True)
    # 构面 [{"facet_id":xx,'weight':xxx}, {"facet_id":xx,'weight':xxx}]
    # version: 仅能选择一个构面[{"facet_id":xx,'weight':xxx}]，但是可以多次选择，生成多条记录
    facet_ids = models.CharField(u"构面ID", max_length=128)
    question_count = models.PositiveIntegerField(u"题目数量", default=0)
    RELATED_FACET_TYPE_QUESTION = 30
    RELATED_FACET_TYPE_OPTION = 31
    RELATED_FACET_TYPE = (
        (RELATED_FACET_TYPE_QUESTION, u"构面问题关联"),
        (RELATED_FACET_TYPE_OPTION, u"构面选项关联")
    )
    related_facet_type = models.PositiveSmallIntegerField(u"问卷构面关联方式", default=RELATED_FACET_TYPE_QUESTION, choices=RELATED_FACET_TYPE)


    def get_facet_infos(self):
        u"""兼容旧数据，facet_ids=[1,2,3]"""
        if not self.facet_ids:
            return [], []
        facet_info = json.loads(self.facet_ids)
        if type(facet_info) == list and len(facet_info) > 0 and type(facet_info[0]) != dict:
            ids = list(set(facet_info))
            weights = []
            for facet_id in ids:
                weights.append(QuestionFacet.objects.get(id=facet_id).weight)
            return ids, weights
        else:
            ids = []
            weights = []
            for facet in facet_info:
                ids.append(facet["id"])
                weights.append(facet["weight"])
            return ids, weights

    @classmethod
    def is_need_rebuild(cls, survey_id):
        u"""检查是否SurveyModelFacetRelation有变更，有变更后需要重新组卷"""
        try:
            smfr_qs = SurveyModelFacetRelation.objects.filter_active(
                survey_id=survey_id).order_by('-update_time')
            if not smfr_qs.exists():
                return True
            smfr_update_time = smfr_qs[0].update_time
            sqr_qs = SurveyQuestionResult.objects.filter_active(
                survey_id=survey_id).order_by('-update_time')
            if not sqr_qs.exists():
                return True
            sqr_update_time = sqr_qs[0].update_time
            if smfr_update_time > sqr_update_time:
                return True
            else:
                return False
        except Exception, e:
            print e
            return True


class SurveyQuestionRelation(BaseModel):
    u"""问卷题目关联关系   0927增加问卷选项关联
    问卷关联模型，模型维度或指标关联题目，普通组卷或者迫选组卷，手动选题或者自动选题
    """
    survey_id = models.BigIntegerField(u"问卷ID", default=0, db_index=True)
    model_facet_relation_id = models.BigIntegerField(u"构面关联关系ID", default=0, db_index=True)
    question_id = models.BigIntegerField(u"关联的题目ID", default=0, db_index=True, null=True, blank=True)
    question_option_id = models.BigIntegerField(u'关联的选项ID', default=0, null=True, blank=True)
    RELATED_FACET_TYPE_QUESTION = 30
    RELATED_FACET_TYPE_OPTION = 31
    RELATED_FACET_TYPE = (
        (RELATED_FACET_TYPE_QUESTION, u"构面问题关联"),
        (RELATED_FACET_TYPE_OPTION, u"构面选项关联")
    )
    related_facet_type = models.PositiveSmallIntegerField(u"问卷构面关联方式", default=RELATED_FACET_TYPE_QUESTION,
                                                          choices=RELATED_FACET_TYPE)


class SurveyQuestionResult(BaseModel):
    u"""
    问卷题目结果
    迫选结果
    """
    survey_id = models.BigIntegerField(u"问卷ID", default=0, db_index=True)
    question_id = models.BigIntegerField(u"关联的题目ID", default=0, db_index=True)
    order_num = models.PositiveIntegerField(u"排序参数", default=0, db_index=True)
    # 一些自定义配置，比如：题目标题，选项标题，迫选标题
    config_info = models.TextField(u"配置信息", null=True, blank=True)
    DEFAULT_FORCE_QUESTION_TITLE = u"以下最符合你的是"
    EN_DEFAULT_FORCE_QUESTION_TITLE = u"Here's what works best for you"
    DEFAULT_FORCE_TITLES = [u"最符合", u"最不符合"]
    EN_DEFAULT_FORCE_TITLES = [u"Likely", u"No likely"]
    DEFAULT_SCORES = [1, -1]

    @property
    def custom_config(self):
        if not self.config_info:
            return {}
        else:
            try:
                return json.loads(self.config_info)
            except Exception, e:
                print "parse custom_config error: %s" %e, self.config_info
                return {}

    @classmethod
    def parse_config_info(cls, data, from_type=Survey.FORM_TYPE_FORCE):
        if from_type == Survey.FORM_TYPE_FORCE:
            return {
                "force_question_title": data.get("title", cls.DEFAULT_FORCE_QUESTION_TITLE),
                "force_options": data.get("options", []),
                "force_title_info": data.get("force_titles", cls.DEFAULT_FORCE_TITLES)
            }
        else:
            return {}

    @classmethod
    def get_force_question_title(cls, config_data):
        return config_data.get("force_question_title", cls.DEFAULT_FORCE_QUESTION_TITLE)

    @classmethod
    def get_force_options(cls, config_data, context=None):
        options = config_data.get("force_options", [])
        is_project_custom = False
        if context is not None:
            request = context.get("request", None)
            is_test = context.get("is_test", False)
            if is_test:
                assess_id = context.get("assess_id", None)
                survey_id = context.get("survey_id", None)
                is_project_custom = True
            elif request and request.GET.get("with_custom_config", None) == "1":
                assess_id = request.GET.get("assess_id", 0)
                survey_id = request.GET.get("survey_id", 0)
                is_project_custom = True
        for option in options:
            option["scores"] = cls.DEFAULT_SCORES
            if is_project_custom:
                qs = AssessProjectSurveyConfig.objects.filter_active(
                    assess_id=assess_id, survey_id=survey_id,
                    model_type=AssessProjectSurveyConfig.MODEL_TYPE_OPTION,
                    model_id=option["id"]
                ).order_by("-id")
                if qs.exists():
                    option["content"] = qs[0].content
        return options

    @classmethod
    def get_force_titles(cls, config_data):
        return config_data.get("force_title_info", cls.DEFAULT_FORCE_TITLES)

    @classmethod
    def get_en_force_titles(cls, config_data):
        return config_data.get("en_force_title_info", cls.EN_DEFAULT_FORCE_TITLES)

    @classmethod
    def get_en_force_question_title(cls, config_data):
        return config_data.get("en_force_question_title", cls.EN_DEFAULT_FORCE_QUESTION_TITLE)





