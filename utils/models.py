# -*- coding:utf-8 -*-
from __future__ import unicode_literals

from django.db import models


class Manager(models.Manager):

    def filter_active(self, *args, **kwargs):
        return self.filter(is_active=True, *args, **kwargs)

    def filter_one_or_create(self, **kwargs):
        u"""代替get_or_create，不是很重要的场合，不必要加锁的地方"""
        qs = self.filter_active(**kwargs)
        if qs.exists():
            return qs[0], False
        else:
            return self.create(**kwargs), True


class BaseModel(models.Model):
    u"""base model of project,
    usually all model need subclass of this model"""

    create_time = models.DateTimeField(u"创建时间", auto_now_add=True)
    is_active = models.BooleanField(u"是否有效", default=True, db_index=True)
    update_time = models.DateTimeField(u"更新时间", auto_now=True, db_index=True)
    creator_id = models.BigIntegerField(u"用户ID", db_index=True, default=0)
    last_modify_user_id = models.BigIntegerField(u"用户ID", db_index=True, default=0)

    objects = Manager()

    class Meta:
        abstract = True

