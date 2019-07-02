from rest_framework.routers import DefaultRouter
from django.conf.urls import url
from useroperate import views

router = DefaultRouter()
router.register(r'(?P<enterprise_id>\d+)/assesslist', views.AssessViewset, base_name='assess')
router.register(r'(?P<enterprise_id>\d+)/notifylist', views.MessagePushViewset, base_name='notify')
router.register(r'messagelist', views.MessageViewset, base_name='message')
router.register(r'(?P<enterprise_id>\d+)/trialorglist', views.TrialOrganizationViewset, base_name='trailorglist')
urlpatterns = [
    url(r'(?P<enterprise_id>\d+)/menulist/$',views.MenuListView.as_view(), name='menu-list'),
    url(r'spu/(?P<key>\d+)/$',views.SPUView.as_view(), name='spu'),
    url(r'(?P<enterprise_id>\d+)/trialmsg/(?P<key>\d+)/$',views.TrialMessageView.as_view(), name='trialmsg'),
]
urlpatterns += router.urls