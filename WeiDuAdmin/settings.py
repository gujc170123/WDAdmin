import os
from env import *

from django.conf import global_settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = 'w*th*hgssf^t^idv1vwe92hxjgm@7y!mltt4mbp2s6cma7_()$'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',    
    'rest_framework',
    'corsheaders',    
    'wduser',
    'assessment',
    'research',
    'survey',
    'question',
    'front',
    'service',
    'console',
]
DATABASE_ROUTERS = ['WeiDuAdmin.db_router.DbRouter']
MIDDLEWARE_CLASSES = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'WeiDuAdmin.PermissionMiddleware.PermissionMiddleware',
]

ROOT_URLCONF = 'WeiDuAdmin.urls'

WSGI_APPLICATION = 'WeiDuAdmin.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['./templates', './templates/front', './templates/operation'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_L10N = True

USE_TZ = False

STATIC_URL = '/static/'

CSRF_COOKIE_NAME = global_settings.CSRF_COOKIE_NAME
CSRF_HEADER_NAME = global_settings.CSRF_HEADER_NAME
#
CORS_ORIGIN_ALLOW_ALL = True
#
AUTH_USER_MODEL = "wduser.AuthUser"
#
MAIN_LOG_NAME = "web"
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[%(asctime)s] %(levelname)s [%(pathname)s %(funcName)s %(lineno)d] %(process)d:%(thread)d %(message)s'
        },
        'simple': {
            'format': '[%(asctime)s] %(levelname)s %(message)s'
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'null': {
            'level': 'DEBUG',
            'class': 'logging.NullHandler',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
    },
    'loggers': {
        #  'django.db.backends': {
        #     'handlers': ['console'],
        #     'propagate': True,
        #     'level':'DEBUG',
        # },
    },
}
# django rest framework
REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ('rest_framework.filters.DjangoFilterBackend',),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.BasicAuthentication',
        'WeiDuAdmin.authentication.WdSessionAuthentication'

    ),
    'DEFAULT_PERMISSION_CLASSES': (
        # 'rest_framework.permissions.DjangoModelPermissions',
    ),
    # 'PAGINATE_BY': 8,
    'DEFAULT_PAGINATION_CLASS': 'utils.pagination.WdPageNumberPagination',
    'PAGINATE_SIZE_PARAM': 'page_size_count',
    'PAGEPARAM_NAME': 'page',
    'PAGE_SIZE': 8,
    #
    'ORDER_BY_NAME': 'order_by',
    'FILTER_BACKEND': 'rest_framework.filters.DjangoFilterBackend',
    'DATETIME_FORMAT': ("%Y-%m-%d %H:%M:%S"),
}

LOGDEDUG = True

dingzhi_DEBUG = None

dingzhi_assess_ids = [172, '172']

dingzhi_assess_id = 172