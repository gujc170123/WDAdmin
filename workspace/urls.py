from __future__ import unicode_literals
from django.conf.urls import url, include
from workspace.views import UserLoginView,OrganizationlRetrieveUpdateDestroyView,\
                            OrganizationListCreateView, UserListCreateView, UserDetailView,\
                            AssessCreateView,AssessDetailView,AssessSurveyRelationDistributeView,\
                            AssessProgressView,AssessProgressTotalView,UserImportExportView,\
                            AssessOrganizationView,OrganizationlUsersDestroyView,SurveyListView,\
                            UserBatchDeleteView,AssessShareView,OrganizationListView,LogoutView, ManagementAssess
from workspace.dashboard import Dashboard, redisStatus
from workspace.dedication import Dedication

urlpatterns = [
    #login
    url(r"^login/$", UserLoginView.as_view(), name="user-login"),
    #logout
    url(r"^logout/$", LogoutView.as_view(), name="user-logout"),    
    #list organizations
    url(r"^listorg/$", OrganizationListCreateView.as_view(), name="org-list"),
    #manage organizations
    url(r"^updateorg/(?P<pk>\d+)/$", OrganizationlRetrieveUpdateDestroyView.as_view(), name="org-manage"),
    #clear organization staff
    url(r"^cleareorg/(?P<pk>\d+)/$",OrganizationlUsersDestroyView.as_view(), name="org-clearstaff"),
    #bi show
    url(r"^bi/$", Dashboard.as_view(),name="bi"),
    #create/list user
    url(r"^user/$", UserListCreateView.as_view(),name="user-list-create"),
    #import user
    url(r"^userimport/$", UserImportExportView.as_view(),name="user-import"),    
    #update/get/del user
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
    #assess organization view
    url(r"^listassessorg/$",AssessOrganizationView.as_view(),name='assessorg-list'),
    #assess survey list view
    url(r"^listassesssurvey/$",SurveyListView.as_view(),name='assesssurvey-list'),
    #users batch delete view
    url(r"^userbatchdel/$",UserBatchDeleteView.as_view(),name='userbatchdelete'),
    #assess share view
    url(r"^assess/assessshare/(?P<pk>\d+)/$",AssessShareView.as_view(),name='assessshareview'),
    #organization list
    url(r"^listEntorg/$",OrganizationListView.as_view(), name="org-list-e"),
    url(r"^getStatus/$", redisStatus, name="redis_status"),
    # jing ye du
    url(r'^dedication/$', Dedication.as_view(), name='dedication'),
    url(r'^managementAssess/(?P<ass>\d+)/$', ManagementAssess.as_view()),
]