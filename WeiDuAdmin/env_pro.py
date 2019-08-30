# -*- coding:utf-8 -*-
from __future__ import unicode_literals
"""
settings related with environment: development or production
default is development env
deploy in production env, need replaced with env_pro.py
"""
import os
# base dir settings
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# debug settings
DEBUG = False
# allow host settings
ALLOWED_HOSTS = ['assess.admin.iwedoing.com', 'admin.iwedoing.com', 'assess.iwedoing.com',  'new.admin.iwedoing.com',
                 'reportsrv.iwedoing.com','127.0.0.1:3000','new.iwedoing.com','crm.iwedoing.com','report.iwedoing.com',
                ]
# csrf setting
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = True
CORS_ORIGIN_WHITELIST = ('127.0.0.1:3000')
CORS_ALLOW_METHODS = (
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
    'VIEW',
)
CORS_ALLOW_HEADERS = (
    'XMLHttpRequest',
    'X_FILENAME',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'Pragma',
)
# Database
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
    },
}
Reports = {
    'mbti2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/NewBehavioralStyle/?people_result_id=%s&emulateScreenMedia=false",
    'disc2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/ProfessionalPersonality/?people_result_id=%s&emulateScreenMedia=false",
    'co2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/ProfessionalOrientation/?people_result_id=%s&emulateScreenMedia=false",
    'mc2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/TheHighLevel/?people_result_id=%s&emulateScreenMedia=false",
    'peoi2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/PersonalHappiness/?people_result_id=%s&emulateScreenMedia=false",
    'ppsy2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/ProfessionalPsychology/?people_result_id=%s&emulateScreenMedia=false",
    'ls2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/LeaderStyle/?people_result_id=%s&emulateScreenMedia=false",
    'wv2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/WorkValues/?people_result_id=%s&emulateScreenMedia=false",
    'pc2019':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/PsychologicalCapital/?people_result_id=%s&emulateScreenMedia=false", 
    'mc201990':"http://reportsrv.iwedoing.com/api/render?url=http://report.iwedoing.com/TheHighLevel90/?people_result_id=%s&emulateScreenMedia=false",       
}
#
# CLIENT_HOST = 'http://wd-user.exuetech.com'
CLIENT_HOST = 'http://assess.iwedoing.com'
REPORT_HOST = 'http://172.16.124.77'
REPORT_HOSTS = ['http://172.16.124.77']
CUSTOM_HOSTS = ['http://172.16.124.77']
FRONT_HOST = 'wdfront'
ROOT_HOST = 'http://assess.iwedoing.com/#/'
# redis config
CACHE = {
    'redis': {
        'default': {
            'host': '127.0.0.1',
            'port': 6379,
            'db': 0,
            'password': None
        },
        'celery': {
            'host': '127.0.0.1',
            'port': 6380,
            'db': 0,
            'password': None
        }
    }
}
