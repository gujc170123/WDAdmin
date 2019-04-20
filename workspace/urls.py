from __future__ import unicode_literals
from django.conf.urls import url, include
from workspace.views import UserLoginView,OrganizationlRetrieveUpdateDestroyView,\
                            OrganizationListCreateView, UserListCreateView, UserDetailView,\
                            AssessCreateView,AssessDetailView,AssessSurveyRelationDistributeView,\
                            AssessProgressView,AssessProgressTotalView
from workspace.dashboard import Dashboard

urlpatterns = [
    #login
    url(r"^login/$", UserLoginView.as_view(), name="user-login"),
    #list organizations
    url(r"^listorg/$", OrganizationListCreateView.as_view(), name="org-list"),
    #manage organizations
    url(r"^updateorg/(?P<pk>\d+)/$", OrganizationlRetrieveUpdateDestroyView.as_view(), name="org-manage"),
    #bi show
    url(r"^bi/$", Dashboard.as_view(),name="bi"),
    #create/list user
    url(r"^user/$", UserListCreateView.as_view(),name="user-list-create"),
    #put/get/del user
    url(r"^user/(?P<pk>\d+)/$", UserDetailView.as_view(),name='user-detail'),
    #create/list assessment
    url(r"^assess/$", AssessCreateView.as_view(),name='assess-list-create'),
    #put/get/del assessment
    url(r"^assess/(?P<pk>\d+)/$", AssessDetailView.as_view(),name='assess-detail'),
    #assess distribution/info statics(close mode)
    url(r"^assess/closedist/(?P<pk>\d+)/$", AssessSurveyRelationDistributeView.as_view(),name='closedist-list'),
    #assess detail info progress(close mode)
    url(r"^assess/closedist/progressdetail/(?P<pk>\d+)/$", AssessProgressView.as_view(),name='closedist-progress-detail'),
    #assess total info progress(close mode)
    url(r"^assess/closedist/progresstotal/(?P<pk>\d+)/$", AssessProgressTotalView.as_view(),name='closedist-progress-total'),        

]