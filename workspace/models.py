# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.db import models
from utils.models import BaseModel


class FactOEIFacet(models.Model):
    assess_id = models.IntegerField(db_index=True)
    user_id = models.IntegerField()
    organization_id = models.IntegerField(db_index=True)
    facet_id =  models.IntegerField(db_index=True)
    score = models.DecimalField(max_digits=5, decimal_places=2)

class DimensionOEI(BaseModel):
    name = models.CharField(max_length=20,db_index=True)
    description = models.CharField(max_length=200, null=True, blank=True)

class DimensionOEIPaths(models.Model):
    """tree path close"""
    assess_id = models.IntegerField(db_index=True,default=0)
    parent = models.ForeignKey(DimensionOEI,related_name='parentnode', on_delete=models.CASCADE, null=True)
    child = models.ForeignKey(DimensionOEI,related_name='childnode', on_delete=models.CASCADE, null=True)
    depth = models.IntegerField(default=0)

class FactOEIFacetDistributions(models.Model):
    assess_id = models.IntegerField(db_index=True)
    organization_id = models.IntegerField(db_index=True)
    facet_id =  models.IntegerField(db_index=True)
    N = models.IntegerField(default=0)
    Mean = models.DecimalField(max_digits=5, decimal_places=2)
    STD = models.DecimalField(max_digits=5, decimal_places=2)
    Min = models.DecimalField(max_digits=5, decimal_places=2)
    Max = models.DecimalField(max_digits=5, decimal_places=2)

class FactOEI(models.Model):
    AssessKey = models.IntegerField(db_index=True)
    DW_Person_ID = models.IntegerField(db_index=True)
    organization1 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    organization2 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    organization3 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    organization4 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    organization5 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    organization6 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile1 = models.CharField(max_length=30, db_index=True, null=True, blank=True, verbose_name="年龄")
    profile2 = models.CharField(max_length=30, db_index=True, null=True, blank=True, verbose_name="性别")
    profile3 = models.CharField(max_length=30, db_index=True, null=True, blank=True, verbose_name="岗位序列")
    profile4 = models.CharField(max_length=30, db_index=True, null=True, blank=True, verbose_name="工龄")
    profile5 = models.CharField(max_length=30, db_index=True, null=True, blank=True, verbose_name="层级")
    profile6 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile7 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile8 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile9 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile10 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    model = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="幸福指数")
    dimension1 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="工作环境")
    dimension2 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="生活愉悦")
    dimension3 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="成长环境")
    dimension4 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="人际环境")
    dimension5 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="领导方式")
    dimension6 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="组织环境")
    dimension7 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="心理资本")
    scale1 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="幸福效能")
    scale2 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="岗位压力")
    scale3 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="幸福度")
    quota1 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="安全健康")
    quota2 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="环境舒适")
    quota3 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="条件支持")
    quota4 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="角色清晰")
    quota5 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="任务安排")
    quota6 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="工作成就")
    quota7 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="薪酬保障")
    quota8 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="生活平衡")
    quota9 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="福利关爱")
    quota10 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="家庭关爱")
    quota11 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="身心关爱")
    quota12 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="成长路径")
    quota13 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="系统培养")
    quota14 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="成长机制")
    quota15 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="共同担当")
    quota16 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="跨界协作")
    quota17 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="开放包容")
    quota18 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="人际吸引")
    quota19 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="相互促进")
    quota20 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="目标引领")
    quota21 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="系统把握")
    quota22 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="激发信任")
    quota23 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="读懂他人")
    quota24 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="释放潜能")
    quota25 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="促进成长")
    quota26 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="愿景激发")
    quota27 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="组织配置")
    quota28 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="流程高效")
    quota29 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="授权赋能")
    quota30 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="纵向支持")
    quota31 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="信息透明")
    quota32 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="价值激励")
    quota33 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="鼓励创新")
    quota34 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="文化优秀")
    quota35 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="品牌影响")
    quota36 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="工作状态")
    quota37 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="留任倾向")
    quota38 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="组织认同")
    quota39 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="敬业投入")
    quota40 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="团队活力")
    quota41 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="岗位压力")
    quota42 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="幸福度")
    quota43 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="自主定向")
    quota44 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="意义寻求")
    quota45 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="自我悦纳")
    quota46 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="自我拓展")
    quota47 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="情绪调节")
    quota48 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="专注投入")
    quota49 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="亲和利他")
    quota50 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="包容差异")
    quota51 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="乐观积极")
    quota52 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="自信坚韧")
    quota53 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="合理归因")
    quota54 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="灵活变通")
    # 自主定向、意义寻求、专注投入、自我拓展 合并  43+44+46+48
    quota55 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="解决问题",default=0)
    # 乐观积极、自信坚韧、合理归因、情绪调节 合并 47+51+52+53
    quota56 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="追求发展",default=0)
    # 包容差异、亲和利他、灵活变通、自我悦纳 合并 45+49+50+54
    quota57 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="适应环境")
    # 所有指标分
    G1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    G2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    G3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    G4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    G5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    G6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    G7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    G8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    S9 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C9 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    C10 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    R8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L9 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L10 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L11 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L12 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L13 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L14 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L15 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L16 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L17 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L18 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L19 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    L20 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z9 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z10 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z11 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z12 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z13 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z14 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z15 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z16 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z17 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z18 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z19 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z20 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z21 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z22 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    Z23 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X9 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X10 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X11 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X12 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X13 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X14 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X15 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X16 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X17 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    X18 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    BENM1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    BENM2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    MASK1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    MASK2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    MASK3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    MASK4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N5 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N6 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N7 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N8 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N9 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N10 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N11 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N12 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N13 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N14 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N15 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N16 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N17 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N18 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N19 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N20 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N21 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N22 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N23 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    N24 = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    hidden = models.BooleanField(default=False)

    class Meta:
        unique_together = ("DW_Person_ID", "AssessKey")
