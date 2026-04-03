from django.contrib import admin
from .models import PostcodeDistrict
from hmo.models import HmoScore


class HmoScoreInline(admin.StackedInline):
    model = HmoScore
    can_delete = False


@admin.register(PostcodeDistrict)
class PostcodeDistrictAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'region', 'get_hmo_score', 'get_demand']
    list_filter = ['region', 'score__demand_score']
    search_fields = ['code', 'name', 'region']
    inlines = [HmoScoreInline]

    def get_hmo_score(self, obj):
        if hasattr(obj, 'score'):
            return obj.score.hmo_score
        return '-'
    get_hmo_score.short_description = 'HMO Score'

    def get_demand(self, obj):
        if hasattr(obj, 'score'):
            return obj.score.demand_score
        return '-'
    get_demand.short_description = 'Demand'
