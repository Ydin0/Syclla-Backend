from rest_framework import serializers
from .models import PostcodeDistrict
from hmo.models import HmoScore


class HmoScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = HmoScore
        fields = [
            'hmo_score',
            'average_yield',
            'average_price',
            'average_rent',
            'demand_score',
            'transport_score',
            'has_article_4',
            'council_attitude_score',
            'student_area',
        ]


class PostcodeDistrictSerializer(serializers.ModelSerializer):
    """Full detail serializer for a postcode district"""
    score = HmoScoreSerializer(read_only=True)
    hmo_score = serializers.IntegerField(source='score.hmo_score', read_only=True)
    average_yield = serializers.DecimalField(
        source='score.average_yield',
        max_digits=5,
        decimal_places=2,
        read_only=True
    )
    average_price = serializers.IntegerField(source='score.average_price', read_only=True)
    average_rent = serializers.IntegerField(source='score.average_rent', read_only=True)
    demand_score = serializers.IntegerField(source='score.demand_score', read_only=True)
    transport_score = serializers.IntegerField(source='score.transport_score', read_only=True)
    has_article_4 = serializers.BooleanField(source='score.has_article_4', read_only=True)
    council_attitude_score = serializers.IntegerField(source='score.council_attitude_score', read_only=True)
    student_area = serializers.BooleanField(source='score.student_area', read_only=True)

    class Meta:
        model = PostcodeDistrict
        fields = [
            'id',
            'code',
            'name',
            'post_town',
            'region',
            'uk_region',
            'latitude',
            'longitude',
            'population',
            'households',
            'hmo_score',
            'average_yield',
            'average_price',
            'average_rent',
            'demand_score',
            'transport_score',
            'has_article_4',
            'council_attitude_score',
            'student_area',
            'score',
        ]


class PostcodeDistrictListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views"""
    hmo_score = serializers.IntegerField(source='score.hmo_score', read_only=True)
    average_yield = serializers.DecimalField(
        source='score.average_yield',
        max_digits=5,
        decimal_places=2,
        read_only=True
    )
    average_price = serializers.IntegerField(source='score.average_price', read_only=True)
    average_rent = serializers.IntegerField(source='score.average_rent', read_only=True)
    demand_score = serializers.IntegerField(source='score.demand_score', read_only=True)
    transport_score = serializers.IntegerField(source='score.transport_score', read_only=True)

    class Meta:
        model = PostcodeDistrict
        fields = [
            'id',
            'code',
            'name',
            'post_town',
            'region',
            'uk_region',
            'hmo_score',
            'average_yield',
            'average_price',
            'average_rent',
            'demand_score',
            'transport_score',
        ]


class HeatmapDataSerializer(serializers.Serializer):
    """Serializer for heatmap response"""
    code = serializers.CharField()
    value = serializers.FloatField()
