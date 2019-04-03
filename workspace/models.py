from __future__ import unicode_literals
from django.db import models
from utils.models import BaseModel

class BaseOrganization(BaseModel):
    u"""base organization object"""

    name = models.CharField(max_length=200)
    parent_id = models.BigIntegerField(db_index=True)
    enterprise_id = models.BigIntegerField(db_index=True)

class BasePeopleOrganization(BaseModel):
    u"""base Person organization relation object"""

    people_id = models.BigIntegerField(db_index=True)
    user_id = models.BigIntegerField(db_index=True)
    organization_id = models.BigIntegerField(db_index=True)
    name = models.CharField(max_length=50)
    ismanager = models.BooleanField(default=False)
