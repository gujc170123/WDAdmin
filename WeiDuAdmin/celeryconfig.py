# -*- coding:utf-8 -*-
from __future__ import absolute_import
import os
from django.conf import settings
from kombu import Queue, Exchange
from celery.schedules import crontab


# set the default Django settings module for the 'celery' program.
# see reference: http://docs.jinkan.org/docs/celery/django/first-steps-with-django.html

BROKER_URL = 'redis://'+settings.CACHE['redis']["celery"]["host"]+\
                   ':'+str(settings.CACHE['redis']["celery"]["port"])+'/'+\
                   str(settings.CACHE['redis']["celery"]["db"])
CELERY_RESULT_BACKEND = BROKER_URL


CELERY_QUEUES = (
    Queue('default', Exchange('default'), routing_key='default'),
    Queue('low', Exchange('low'), routing_key='low_celery'),
    Queue('middle', Exchange('middle'), routing_key='middle_celery'),
    Queue('high', Exchange('high'), routing_key='high_celery')
)
CELERY_DEFAULT_QUEUE = 'default'
CELERY_DEFAULT_EXCHANGE = 'default'
CELERY_DEFAULT_ROUTING_KEY = 'default'

CELERY_TIMEZONE = 'Asia/Shanghai'

CELERYBEAT_SCHEDULE = {

    'add': {

        'task': 'console.tasks.auto_update_database',

        'schedule': crontab(minute="*/10"),

        'args': ()
    },

    'update': {

        'task': 'console.tasks.auto_update_clean_status',

        'schedule': crontab(minute="*/10"),

        'args': ()
    }
}


# TODO: start different work for different queue, http://docs.celeryproject.org/en/latest/userguide/routing.html
#
# CELERY_IMPORTS = (
#     ''
# )
# CELERY_INCLUDE = (
#     ''
# )

CELERY_ROUTES = (

    ############################################################
    # high
    # fortune
    # {'fortune.tasks.user_fortune_task': {'queue': 'high', 'routing_key': 'high_celery'}},

    ############################################################
    # middle
    # company
    # {'company.tasks.company_accept_works': {'queue': 'middle', 'routing_key': 'middle_celery'}},

    ############################################################
    # low
    # knowledge
    # {'knowledge.tasks.knowledge_search_record': {'queue': 'low', 'routing_key': 'low_celery'}},

)
