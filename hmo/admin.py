from django.contrib import admin
from .models import (
    HmoScore,
    LocalAuthorityDemand,
    SpareRoomRent,
    OutcodeLAMapping,
)


@admin.register(HmoScore)
class HmoScoreAdmin(admin.ModelAdmin):
    list_display = [
        'postcode_district',
        'hmo_score',
        'average_yield',
        'demand_score',
        'transport_score',
        'council_attitude_score',
    ]
    list_filter = ['demand_score', 'has_article_4', 'student_area']
    search_fields = ['postcode_district__code', 'postcode_district__name']


@admin.register(LocalAuthorityDemand)
class LocalAuthorityDemandAdmin(admin.ModelAdmin):
    list_display = [
        'la_code', 'la_name', 'region', 'total_population',
        'demand_score', 'demand_classification', 'national_rank',
    ]
    list_filter = ['region', 'demand_classification']
    search_fields = ['la_code', 'la_name']
    ordering = ['national_rank']


@admin.register(SpareRoomRent)
class SpareRoomRentAdmin(admin.ModelAdmin):
    list_display = ['location_name', 'avg_room_rent', 'quarter', 'year']
    list_filter = ['quarter', 'year']
    search_fields = ['location_name']
    ordering = ['-year', 'quarter']


@admin.register(OutcodeLAMapping)
class OutcodeLAMappingAdmin(admin.ModelAdmin):
    list_display = ['outcode', 'local_authority']
    search_fields = ['outcode__code', 'local_authority__la_name']
