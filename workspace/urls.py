from __future__ import unicode_literals
from django.conf.urls import url
from workspace.views import PeopleLoginView

urlpatterns = [
    #login
    url(r"^login/$", PeopleLoginView.as_view(), name="user-login"),
]