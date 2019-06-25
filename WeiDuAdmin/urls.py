from django.conf.urls import url, include
import xadmin

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
    
    url(r'^xadmin/', xadmin.site.urls),
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
    ws_url(r'application/', include('application.urls')),
    # front api 
    client_url(r'front/', include('front.urls')),
]
