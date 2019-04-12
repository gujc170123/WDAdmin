# -*- coding:utf-8 -*-
from __future__ import unicode_literals
from django.db import models
from utils.models import BaseModel
from wduser.models import EnterpriseInfo, AuthUser
from assessment.models import AssessGatherInfo

class BaseOrganization(BaseModel):
    """base organization object"""

    name = models.CharField(max_length=40)
    parent_id = models.BigIntegerField(db_index=True, default=0)
    enterprise = models.ForeignKey(EnterpriseInfo,
                                   on_delete=models.CASCADE)

class BaseUserOrganization(BaseModel):
    """base Person organization relation object"""

    user = models.ForeignKey(AuthUser, on_delete=models.CASCADE)
    organization = models.ForeignKey(BaseOrganization,
                                     on_delete=models.CASCADE)

class BaseProfile(BaseModel):
    """base user profile"""
    name = models.CharField(max_length=40)
    options = models.CharField(max_length=50)
    INFO_TYPE_STR = 10
    INFO_TYPE_INT = 20
    INFO_TYPE_LIST = 30
    INFO_TYPE_DATE = 40
    INFO_TYPE_CHOICES = (
        (INFO_TYPE_STR, "string"),
        (INFO_TYPE_INT, "numeric"),
        (INFO_TYPE_LIST, "list"),
        (INFO_TYPE_DATE, "date")
    )
    info_type = models.PositiveSmallIntegerField(choices=INFO_TYPE_CHOICES, default=INFO_TYPE_STR)    
    config_info = models.CharField(max_length=1024)
    is_required = models.BooleanField(default=False, db_index=True)
    is_modified = models.BooleanField(default=True, db_index=True)

class BaseAccessProfile(BaseModel):
    """this model connects base profile with accessgatherinfo"""
    profile = models.ForeignKey(BaseProfile, on_delete=models.CASCADE)
    gatherinfo = models.ForeignKey(AssessGatherInfo)