# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.db import models
from utils.models import BaseModel
from wduser.models import EnterpriseInfo

class BaseOrganization(BaseModel):
    """base organization object"""

    name = models.CharField(max_length=40)
    parent_id = models.BigIntegerField(db_index=True,default=0)
    enterprise = models.ForeignKey(EnterpriseInfo,
                                      related_name="organ_enterprise",
                                      on_delete=models.CASCADE)

class BasePersonOrganization(BaseModel):
    """base Person organization relation object"""

    user_id = models.BigIntegerField(db_index=True)
    organization = models.ForeignKey(BaseOrganization,
                                        related_name="person_organ",
                                        on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    ismanager = models.BooleanField(default=False)


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
    profile4 = models.IntegerField(db_index=True, null=True, blank=True, verbose_name="工龄")
    profile5 = models.CharField(max_length=30, db_index=True, null=True, blank=True, verbose_name="层级")
    profile6 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile7 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile8 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile9 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    profile10 = models.CharField(max_length=30, db_index=True, null=True, blank=True)
    model = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="幸福指数")
    dimension1 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="工作投入")
    dimension2 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="生活愉悦")
    dimension3 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="成长有力")
    dimension4 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="人际和谐")
    dimension5 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="领导激发")
    dimension6 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="组织卓越")
    dimension7 = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="个人幸福能力")
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

    class Meta:
        unique_together = ("DW_Person_ID", "AssessKey")
