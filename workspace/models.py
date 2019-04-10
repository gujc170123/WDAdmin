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
