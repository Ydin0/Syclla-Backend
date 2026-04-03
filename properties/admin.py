from django.contrib import admin
from .models import (
    PropertyTransaction, OutcodePropertyStats, OutcodePropertyStatsByType,
    EPCImportProgress,
)


@admin.register(PropertyTransaction)
class PropertyTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id', 'price', 'date_of_transfer', 'postcode',
        'outcode', 'property_type', 'total_floor_area_sqm', 'price_per_sqm',
    ]
    list_filter = ['property_type', 'old_new', 'duration']
    search_fields = ['postcode', 'outcode', 'street', 'town_city']
    date_hierarchy = 'date_of_transfer'


@admin.register(OutcodePropertyStats)
class OutcodePropertyStatsAdmin(admin.ModelAdmin):
    list_display = [
        'outcode', 'avg_price', 'median_price', 'avg_price_per_sqm',
        'transaction_count', 'avg_floor_area_sqm',
    ]
    search_fields = ['outcode']


@admin.register(OutcodePropertyStatsByType)
class OutcodePropertyStatsByTypeAdmin(admin.ModelAdmin):
    list_display = [
        'outcode', 'property_type', 'avg_price',
        'avg_price_per_sqm', 'transaction_count',
    ]
    list_filter = ['property_type']
    search_fields = ['outcode']


@admin.register(EPCImportProgress)
class EPCImportProgressAdmin(admin.ModelAdmin):
    list_display = [
        'outcode', 'status', 'records_fetched', 'records_matched',
        'started_at', 'completed_at',
    ]
    list_filter = ['status']
    search_fields = ['outcode']
