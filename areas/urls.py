from django.urls import path
from . import views

app_name = 'areas'

urlpatterns = [
    path('heatmap/', views.heatmap_data, name='heatmap'),
    path('detail/', views.area_detail_by_code, name='detail_by_code'),
    path('rankings/', views.AreaRankingsView.as_view(), name='rankings'),
    path('geojson/', views.areas_geojson, name='geojson'),
]
