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
ALLOWED_HOSTS = ['yxtest.iwedoing.com', '47.98.34.126']


# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases
# database settings
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'wdadmin_uat',
        'USER': 'appserver',
        'PASSWORD': 'AS@wdadmin',
        'HOST': 'rm-bp1628dsd6x9v4bse.mysql.rds.aliyuncs.com',
        'PORT': '3306',
    },
    'front': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'weidu_client',
        'USER': 'appserver',
        'PASSWORD': 'AS@wdadmin',
        'HOST': 'rm-bp1628dsd6x9v4bse.mysql.rds.aliyuncs.com',
        'PORT': '3306',
    }
}
#
# CLIENT_HOST = 'http://assessment.iwedoing.com'
CLIENT_HOST = 'http://47.98.34.126'
# REPORT_HOST = 'http://yxtest.iwedoing.com'
REPORT_HOST = 'http://172.16.124.92'
REPORT_HOSTS = ['http://172.16.124.92']
CUSTOM_HOSTS = ['http://172.16.124.92']
#
# redis config
# redis config
# stream redis config
CACHE = {
    'redis': {
        'default': {
            'host': '172.16.124.75',
            'port': 6379,
            'db': 0,
            'password': None
        },
        'celery': {
            'host': '172.16.124.75',
            'port': 6380,
            'db': 0,
            'password': None
        }
    }
}
