from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import F

from .models import PostcodeDistrict
from hmo.models import HmoScore
from .serializers import (
    PostcodeDistrictSerializer,
    PostcodeDistrictListSerializer,
)


@api_view(['GET'])
@permission_classes([AllowAny])
def areas_geojson(request):
    """
    Returns GeoJSON FeatureCollection with all postcode districts that have coordinates.
    This is used by the frontend map to display only areas that exist in the database.

    Response format:
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "code": "SS1",
                        "name": "Southend Central",
                        "region": "East of England"
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [-0.7128, 51.5361]
                    }
                },
                ...
            ]
        }
    """
    areas = PostcodeDistrict.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).values('code', 'name', 'region', 'latitude', 'longitude')

    features = []
    for area in areas:
        feature = {
            "type": "Feature",
            "properties": {
                "code": area['code'],
                "name": area['name'],
                "region": area['region'],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [float(area['longitude']), float(area['latitude'])]
            }
        }
        features.append(feature)

    return Response({
        "type": "FeatureCollection",
        "features": features
    })


class AreaPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
@permission_classes([AllowAny])
def heatmap_data(request):
    """
    Returns heatmap data as a dictionary mapping postcode codes to metric values.

    Query params:
        - metric: 'hmo_score' (default), 'average_yield', or 'demand'

    Response format:
        {
            "SS1": 84,
            "CO1": 78,
            ...
        }
    """
    metric = request.query_params.get('metric', 'hmo_score')

    # Get all areas with scores
    areas = PostcodeDistrict.objects.select_related('score').filter(score__isnull=False)

    data = {}
    for area in areas:
        if metric == 'hmo_score':
            data[area.code] = area.score.hmo_score
        elif metric == 'average_yield':
            data[area.code] = float(area.score.average_yield) if area.score.average_yield else 0
        elif metric == 'demand':
            data[area.code] = area.score.demand_score
        elif metric == 'article4':
            data[area.code] = 1 if area.score.has_article_4 else 0
        else:
            data[area.code] = area.score.hmo_score

    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def area_detail_by_code(request):
    """
    Returns full details for a single area by postcode code.

    Query params:
        - code: postcode district code (e.g., 'SS1', 'CO1')
    """
    code = request.query_params.get('code', '').upper()

    if not code:
        return Response(
            {'error': 'code parameter is required'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        area = PostcodeDistrict.objects.select_related('score').get(code=code)
    except PostcodeDistrict.DoesNotExist:
        return Response(
            {'error': f'Area with code {code} not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = PostcodeDistrictSerializer(area)
    return Response(serializer.data)


class AreaRankingsView(generics.ListAPIView):
    """
    Returns paginated ranked list of areas.

    Query params:
        - sort_by: 'hmo_score' (default), 'average_yield', 'average_price', 'transport_score'
        - order: 'desc' (default) or 'asc'
        - region: filter by region name
        - min_score: minimum HMO score
        - min_yield: minimum yield percentage
        - demand: filter by demand level (LOW, MEDIUM, HIGH)
        - page: page number
        - page_size: items per page (max 100)
    """
    serializer_class = PostcodeDistrictListSerializer
    pagination_class = AreaPagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        queryset = PostcodeDistrict.objects.select_related('score').filter(score__isnull=False)

        # Filters
        region = self.request.query_params.get('region')
        if region:
            queryset = queryset.filter(region__icontains=region)

        min_score = self.request.query_params.get('min_score')
        if min_score:
            queryset = queryset.filter(score__hmo_score__gte=int(min_score))

        min_yield = self.request.query_params.get('min_yield')
        if min_yield:
            queryset = queryset.filter(score__average_yield__gte=float(min_yield))

        min_demand = self.request.query_params.get('min_demand')
        if min_demand:
            queryset = queryset.filter(score__demand_score__gte=int(min_demand))

        # Sorting
        sort_by = self.request.query_params.get('sort_by', 'hmo_score')
        order = self.request.query_params.get('order', 'desc')

        sort_field_map = {
            'hmo_score': 'score__hmo_score',
            'average_yield': 'score__average_yield',
            'average_price': 'score__average_price',
            'transport_score': 'score__transport_score',
        }

        sort_field = sort_field_map.get(sort_by, 'score__hmo_score')
        if order == 'desc':
            sort_field = f'-{sort_field}'

        return queryset.order_by(sort_field)
