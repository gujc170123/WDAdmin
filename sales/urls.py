from rest_framework.routers import DefaultRouter
from django.conf.urls import url
from sales import views

router = DefaultRouter()
router.register(r'(?P<enterprise_id>\d+)/balancelist', views.BalanceModelViewset, base_name='balance')
router.register(r'(?P<enterprise_id>\d+)/consumelist', views.ConsumeModelViewset, base_name='consume')
router.register(r'(?P<enterprise_id>\d+)/orderlist', views.OrderModelViewset, base_name='order')
router.register(r'(?P<enterprise_id>\d+)/orderdetaillist', views.OrderDetailModelViewset, base_name='orderdetail')
urlpatterns = []
urlpatterns += router.urls