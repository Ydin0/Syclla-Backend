from django.contrib import admin
from .models import RailwayStation, StationCityJourney, MajorCity


@admin.register(RailwayStation)
class RailwayStationAdmin(admin.ModelAdmin):
    list_display = [
        'station_name', 'tlc_code', 'latitude', 'longitude',
        'outcode', 'annual_entries_exits',
    ]
    search_fields = ['station_name', 'tlc_code']


@admin.register(StationCityJourney)
class StationCityJourneyAdmin(admin.ModelAdmin):
    list_display = ['station', 'city_name', 'journey_time_mins']
    list_filter = ['city_name']
    search_fields = ['station__station_name', 'city_name']


@admin.register(MajorCity)
class MajorCityAdmin(admin.ModelAdmin):
    list_display = ['name', 'population', 'station_codes']
