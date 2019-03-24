# -*- coding:utf-8 -*-
from __future__ import unicode_literals

import json

from django.db import models

# Create your models here.
from utils.models import BaseModel


class QuestionBank(BaseModel):
    u"""题库"""
    name = models.CharField(u"题库名称", max_length=128, db_index=True)
    en_name = models.CharField(u"英文题库名称", max_length=128, default=u'', db_index=True, null=True, blank=True)
    code = models.CharField(u"题库编号", max_length=32, db_index=True, null=True, blank=True)
    desc = models.CharField(u"题库描述", max_length=256, db_index=True, null=True, blank=True)
    en_desc = models.CharField(u"英文题库描述", max_length=2048, default=u'', null=True, blank=True)


class QuestionFolder(BaseModel):
    u"""题目文件夹"""
    question_bank_id = models.BigIntegerField(u"题库ID", default=0, db_index=True)
    parent_id = models.BigIntegerField(u"父文件夹ID", default=0, db_index=True)
    name = models.CharField(u"文件夹名称", max_length=128, db_index=True)
    en_name = models.CharField(u"英文文件夹名称", max_length=128, db_index=True, default=u'', null=True, blank=True)
    code = models.CharField(u"文件夹编号", max_length=32, db_index=True, null=True, blank=True)
    desc = models.CharField(u"文件夹描述", max_length=256, db_index=True, null=True, blank=True)
    en_desc = models.CharField(u"英文文件夹描述", max_length=2048, default=u'', null=True, blank=True)


class QuestionFacet(BaseModel):
    u"""题目构面"""
    question_bank_id = models.BigIntegerField(u"题库ID", default=0, db_index=True)
    question_folder_id = models.BigIntegerField(u"文件夹ID", default=0, db_index=True)
    name = models.CharField(u"构面名称", max_length=128, db_index=True)
    en_name = models.CharField(u"英文构面名称", max_length=128, db_index=True, default=u'', null=True, blank=True)
    code = models.CharField(u"构面编号", max_length=32, db_index=True, null=True, blank=True)
    desc = models.CharField(u"构面描述", max_length=256, db_index=True, null=True, blank=True)
    en_desc = models.CharField(u"英文构面描述", max_length=2048, default=u'', null=True, blank=True)
    weight = models.FloatField(u"构面权重", default=0)
    config_info = models.TextField(u"构面配置", null=True, blank=True)
    FACET_TYPE_NORMAL = 10
    FACET_TYPE_PASSAGE = 20
    facet_type_choices = (
        (FACET_TYPE_NORMAL, u"题目构面"),
        (FACET_TYPE_PASSAGE, u"材料构面"),
    )
    facet_type = models.PositiveSmallIntegerField(u"构面类型", choices=facet_type_choices, default=FACET_TYPE_NORMAL)

    @property
    def default_question_type(self):
        if not self.config_info:
            return None
        config_info = json.loads(self.config_info)
        return config_info.get("default_question_type", None)

    @property
    def default_options(self):
        if not self.config_info:
            return None
        config_info = json.loads(self.config_info)
        return config_info.get("default_options", None)


class Question(BaseModel):
    u"""题目/同质题"""
    question_bank_id = models.BigIntegerField(u"题库ID", default=0, db_index=True)
    question_folder_id = models.BigIntegerField(u"文件夹ID", default=0, db_index=True)
    question_facet_id = models.BigIntegerField(u"构面ID", default=0, db_index=True)
    question_passage_id = models.BigIntegerField(u"材料ID", default=0, db_index=True)
    title = models.TextField(u"题干", null=True)
    en_title = models.TextField(u"英文题干", null=True, blank=True, default=u'')
    code = models.CharField(u"题干编号", max_length=32, db_index=True, null=True, blank=True)
    QUESTION_TYPE_SINGLE = 10
    QUESTION_TYPE_SINGLE_FILLIN = 11
    QUESTION_TYPE_MULTI = 30
    QUESTION_TYPE_MULTI_FILLIN = 31
    QUESTION_TYPE_MUTEXT = 50
    QUESTION_TYPE_SLIDE = 60
    QUESTION_TYPE_FORCE_ORDER_QUESTION = 70
    QUESTION_TYPE_NINE_SLIDE = 80
    QUESTION_TYPE_FORCE_QUESTION = 0
    QUESTION_TYPE_CHOICES = (
        (QUESTION_TYPE_SINGLE, u"单选"),
        (QUESTION_TYPE_SINGLE_FILLIN, u"单选填空"),
        (QUESTION_TYPE_MULTI, u"多选"),
        (QUESTION_TYPE_MULTI_FILLIN, u"多选填空"),
        (QUESTION_TYPE_MUTEXT, u"互斥题"),
        (QUESTION_TYPE_SLIDE, u"滑块题"),
        (QUESTION_TYPE_FORCE_QUESTION, u"迫选题(迫选/360组卷)"),
        (QUESTION_TYPE_FORCE_ORDER_QUESTION, u"迫选排序题"),
        (QUESTION_TYPE_NINE_SLIDE, u'9点量表题'),
    )
    question_type = models.PositiveSmallIntegerField(u"题目类型", default=QUESTION_TYPE_SINGLE,
                                                     choices=QUESTION_TYPE_CHOICES, db_index=True)
    CATEGORY_NORMAL = 10
    CATEGORY_UNIFORMITY = 20
    CATEGORY_PRAISE = 30
    CATEGORY_PRESSURE = 40
    CATEGORY_CHOICES = (
        (CATEGORY_NORMAL, u"普通题"),
        (CATEGORY_UNIFORMITY, u"一致性题目"),
        (CATEGORY_PRAISE, u"社会称许题"),
        (CATEGORY_PRESSURE, u"压力题"),
    )
    question_category = models.PositiveSmallIntegerField(u"题目分类", default=CATEGORY_NORMAL,
                                                         choices=CATEGORY_CHOICES, db_index=True)
    uniformity_question_id = models.BigIntegerField(u"对应一致性题", default=0, db_index=True)
    DEFAULT_MUTEX_TITLE = [u"最符合", u"最不符合"]
    # 迫排题
    DEFAULT_MUTEX_ORDER_TITLE = [u"第一", u"第二", u"第三", u"第四", u"第五"]
    EN_DEFAULT_MUTEX_ORDER_TITLE = [u"No.1", u"No.2", u"No.3", u"No.4", u"No.5"]
    DEFAULT_SCORES = [5, 4, 3, 2, 1]
    EN_DEFAULT_MUTEX_TITLE = [u"Likely", u"No likely"]
    config_info = models.CharField(u"配置信息", max_length=1024, db_index=True, null=True)
    use_count = models.PositiveIntegerField(u"使用次数", default=0, db_index=True)
    average_score = models.FloatField(u"平均分", default=0, db_index=True)
    standard_deviation = models.FloatField(u"标准差", default=0, db_index=True)


class QuestionOption(BaseModel):
    u"""题目选项"""
    question_id = models.BigIntegerField(u"题目ID", default=0, db_index=True)
    # 互斥题， 迫选选项分值记录
    parent_id = models.BigIntegerField(u"父选项ID", default=0, db_index=True)
    content = models.TextField(u"选项内容", null=True)
    en_content = models.TextField(u"英文选项内容", null=True, blank=True, default=u'')
    order_number = models.PositiveSmallIntegerField(u"序号", default=0)
    is_blank = models.BooleanField(u"填空选项", default=False)
    score = models.FloatField(u"分值", default=0)


class QuestionPassage(BaseModel):
    u"""题目文章"""
    question_facet_id = models.BigIntegerField(u"构面ID", default=0, db_index=True)
    passage = models.TextField(u"文章内容", null=True)
    en_passage = models.TextField(u"文章内容", null=True, blank=True, default=u'')


class QuestionPassageRelation(BaseModel):
    u"""题目文章关联关系"""
    question_id = models.BigIntegerField(u"题目ID", default=0, db_index=True)
    passage_id = models.BigIntegerField(u"文章ID", default=0, db_index=True)
