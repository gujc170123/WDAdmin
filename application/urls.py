from rest_framework.routers import DefaultRouter
from django.conf.urls import url
from application import views

router = DefaultRouter()
router.register(r'eventlist', views.EventModelViewset, base_name='event')
router.register(r'applicationlist', views.ApplicationModelViewset, base_name='application')
router.register(r'applierlist', views.ApplierModelViewset, base_name='applier')
urlpatterns = [
    url(r'^choice/$',views.ChoiceView.as_view()),
]
urlpatterns += router.urls
