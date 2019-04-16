# -*- coding: UTF-8 -*-
from __future__ import unicode_literals

FRONT_DB = 'front'
DEFAULT_DB = 'default'

FRONT_MODEL_APPS = [
    'front'
]

class DbRouter(object):
    u"""
    数据库路由
    将测评前端的操作，用在另一个数据库中
    """

    def db_for_read(self, model, **hints):
        if model._meta.app_label in FRONT_MODEL_APPS:
            return FRONT_DB
        else:
            return DEFAULT_DB

    def db_for_write(self, model, **hints):
        """
        Attempts to write app02 models go to hvdb DB.
        """
        if model._meta.app_label in FRONT_MODEL_APPS:
            return FRONT_DB
        else:
            return DEFAULT_DB

    def allow_relation(self, obj1, obj2, **hints):
        """
        当 obj1 和 obj2 之间允许有关系时返回 True ，不允许时返回 False ，或者没有 意见时返回 None 。
        """
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        u"""
        Make sure the app only appears in the db
        database.
        """
        if app_label in FRONT_MODEL_APPS:
            return db == FRONT_DB
        else:
            return db == DEFAULT_DB
