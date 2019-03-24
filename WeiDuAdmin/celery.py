# -*- coding:utf-8 -*-
from __future__ import absolute_import

import os
from celery import Celery
from django.conf import settings


__author__ = 'exue'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'WeiDuAdmin.settings')

app = Celery("WeiDuAdmin")
app.config_from_object("WeiDuAdmin.celeryconfig")
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
