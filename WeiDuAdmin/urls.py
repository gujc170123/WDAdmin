"""WeiDuAdmin URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.10/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include
from django.contrib import admin

V1_URL_PREFIX = 'api/v1/'
CLIENT_URL_PREFIX = 'api/client/v1/'
WORKSPACE_URL_PREFIX = 'api/ws/v1/'

def v1_url(regex, view, kwargs=None, name=None):
    url_prefix = r'^' + V1_URL_PREFIX
    regex = url_prefix + regex
    return url(regex, view, kwargs, name)


def client_url(regex, view, kwargs=None, name=None):
    url_prefix = r'^' + CLIENT_URL_PREFIX
    regex = url_prefix + regex
    return url(regex, view, kwargs, name)

def ws_url(regex, view, kwargs=None, name=None):
    url_prefix = r'^' + WORKSPACE_URL_PREFIX
    regex = url_prefix + regex
    return url(regex, view, kwargs, name)    

urlpatterns = [
    # template
    # url(r'^console/admin/', admin.site.urls),
    url(r'people/', include('front.template_urls')),
    url(r'operation/', include('wduser.template_urls')),
    # admin api
    v1_url(r'utils/', include('utils.urls')),
    v1_url(r'user/', include('wduser.urls')),
    v1_url(r'assessment/', include('assessment.urls')),
    v1_url(r'research/', include('research.urls')),
    v1_url(r'survey/', include('survey.urls')),
    v1_url(r'question/', include('question.urls')),
    v1_url(r'console/', include('console.urls')),
    # workspace api
    ws_url(r'workspace/', include('workspace.urls')),
    # front api 
    client_url(r'front/', include('front.urls')),
]
