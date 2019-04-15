from __future__ import unicode_literals
from django.conf.urls import url
from workspace.views import UserLoginView,OrganizationlRetrieveUpdateDestroyView,\
                            OrganizationListCreateView, UserListCreateView, UserDetailView
from workspace.dashboard import Dashboard

urlpatterns = [
    #login
    url(r"^login/$", UserLoginView.as_view(), name="user-login"),
    #list organizations
    url(r"^listorg/$", OrganizationListCreateView.as_view(), name="org-list"),
    #manage organizations
    url(r"^updateorg/(?P<pk>\d+)/$", OrganizationlRetrieveUpdateDestroyView.as_view(), name="org-manage"),
    #bi
    url(r"^bi/$", Dashboard.as_view(),name="bi"),
    #create/list user
    url(r"^user/$", UserListCreateView.as_view(),name="user-list-create"),
    #put/get/del user
    url(r"^user/(?P<pk>\d+)/$", UserDetailView.as_view(),name='user-detail'),
]