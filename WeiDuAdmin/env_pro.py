# -*- coding:utf-8 -*-
from __future__ import unicode_literals

"""
settings related with environment: production
"""

import os

# base dir settings
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# debug settings
DEBUG = True

# allow host settings
ALLOWED_HOSTS = ['assess.admin.iwedoing.com', 'assess.iwedoing.com']


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases
# database settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'wdadmin',
        'USER': 'ad_wd',
        'PASSWORD': 'Admin@Weidu2018',
        'HOST': 'rm-bp1i2yah9e5d27k26.mysql.rds.aliyuncs.com',
        'PORT': '3306',
    },
    'front': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'wdfront',
        'USER': 'ad_wd',
        'PASSWORD': 'Admin@Weidu2018',
        'HOST': 'rm-bp1i2yah9e5d27k26.mysql.rds.aliyuncs.com',
        'PORT': '3306',
    }
}
#
CLIENT_HOST = 'http://assess.iwedoing.com'
# REPORT_HOST = 'http://assess.admin.iwedoing.com'
REPORT_HOST = 'http://172.16.124.77'
REPORT_HOSTS = ['http://172.16.124.77']
CUSTOM_HOSTS = ['http://172.16.124.96']
#
# redis config
# redis config
# stream redis config
CACHE = {
    'redis': {
        'default': {
            'host': '172.16.124.81',
            'port': 6379,
            'db': 0,
            'password': None
        },
        'celery': {
            'host': '172.16.124.81',
            'port': 6380,
            'db': 0,
            'password': None
        }
    }
}
