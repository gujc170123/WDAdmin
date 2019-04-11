from __future__ import unicode_literals
from django.conf.urls import url
from workspace.views import PeopleLoginView,OrganizationlRetrieveUpdateDestroyView,OrganizationListCreateView
from workspace.dashboard import Dashboard

urlpatterns = [
    #login
    url(r"^login/$", PeopleLoginView.as_view(), name="user-login"),
    #list organizations
    url(r"^listorg/$", OrganizationListCreateView.as_view(), name="org-list"),
    #manage organizations
    url(r"^updateorg/(?P<pk>\d+)/$", OrganizationlRetrieveUpdateDestroyView.as_view(), name="org-manage"),
    #bi
    url(r"^bi/$", Dashboard.as_view()  , name="bi"),    
]