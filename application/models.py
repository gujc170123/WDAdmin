# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.db import models

class Event(models.Model):

    class Meta:
        verbose_name_plural=u'活动'
        verbose_name=u'活动'

    STATUS_CHOICES=(
            (1,'NotOpen'),
            (2,'Open'),
            (3,'Close'),)

    title = models.CharField(verbose_name='Event Title', max_length=100, unique=True)
    url = models.URLField(verbose_name='Site URL',null=True)
    datefrom = models.DateTimeField(verbose_name='Date From', db_index=True)
    dateto = models.DateTimeField(verbose_name='Date To', db_index=True)
    status = models.IntegerField(verbose_name='Event Status', choices=STATUS_CHOICES , default=1)
    memo = models.CharField(verbose_name='Memo' , max_length=200,null=True)

    def __unicode__(self):
        return self.title    

class Applier(models.Model):

    class Meta:
        verbose_name_plural=u'申请人'
        verbose_name=u'申请人'

    SIZE_CHOICES = (
            (1,'<500'),
            (2,'500-2000'),
            (3,'2000-10000'),
            (4,'>10000'),)

    INDUSTRY_CHOICES = (
            (1,u'保险业'),
            (2,u'采掘业/冶炼'),
            (3,u'电子技术'),
            (4,u'法律'),
            (5,u'房地产及中介'),
            (6,u'非盈利机构/政府'),
            (7,u'服务业'),
            (8,u'广告业'),
            (9,u'化工/能源'),
            (10,u'环保'),
            (11,u'加工/制造（工业自动化，设备，零部件）'),
            (12,u'建筑/设计/装潢'),
            (13,u'交通/航空/运输/物流'),
            (14,u'教育/培训'),
            (15,u'金融（银行，风险基金）'),
            (16,u'酒店/餐饮'),
            (17,u'快速消费品（食品，饮料，化妆品）'),
            (18,u'旅游业'),
            (19,u'贸易'),
            (20,u'媒体/出版'),
            (21,u'耐用消费品（服装，纺织，家具，家电，工艺品）'),
            (22,u'农业/林业/渔业'),
            (23,u'批发及零售'),
            (24,u'人才中介公司'),
            (25,u'生物/制药/保健/医药'),
            (26,u'信息技术及互联网（计算机软件，通讯）'),
            (27,u'学术/科研/艺术'),
            (28,u'印刷/包装'),
            (29,u'娱乐/体育'),
            (30,u'咨询业'),
            (31,u'其他行业'),)

    SOURCE_CHOICES = (
            (1,u'文化协会'),
            (2,u'新闻媒体'),
            (3,u'好友推荐'),
            (4,u'其他'),)

    title = models.CharField(verbose_name='Enterprise Title', max_length=100, db_index=True)
    appliername = models.CharField(verbose_name='Applier Name', max_length=20, null=True,  db_index=True)
    phone = models.CharField(verbose_name='Applier Mobi Phone', max_length=20, null=True,  db_index=True)
    mail = models.CharField(verbose_name='Applier Mail', max_length=50,  db_index=True)
    size = models.IntegerField(verbose_name='Enterprise Size', choices=SIZE_CHOICES , default=1)
    industry = models.IntegerField(verbose_name='Enterprise Industry', choices=INDUSTRY_CHOICES , default=1)
    source = models.IntegerField(verbose_name='Info Source', choices=SOURCE_CHOICES , default=1)

    def __unicode__(self):
        return self.title + self.appliername

class Application(models.Model):

    class Meta:
        verbose_name_plural=u'申请'
        verbose_name=u'申请'

    PROGRESS_CHOICES = (
            (1,u'审核中'),
            (2,u'审核通过'),
            (3,u'审核未通过'),)

    event = models.ForeignKey(Event, verbose_name='Event ID', on_delete=models.CASCADE)
    applydate = models.DateTimeField(verbose_name='Apply Date',auto_now_add=True)
    applier = models.ForeignKey(Applier, verbose_name='Applier ID', on_delete=models.CASCADE)
    progress = models.IntegerField(verbose_name='Application Progress', choices=PROGRESS_CHOICES , default=1) 
    rejectreason = models.CharField(verbose_name='Enterprise Title', max_length=100, null=True)

    def __unicode__(self):
        return self.applier