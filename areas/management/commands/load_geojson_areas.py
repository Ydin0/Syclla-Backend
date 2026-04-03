import json
import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from areas.models import PostcodeDistrict
from hmo.models import HmoScore


class Command(BaseCommand):
    help = 'Loads UK postcode districts from a GeoJSON file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to the GeoJSON file',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before loading',
        )

    def handle(self, *args, **options):
        file_path = options['file']

        # Load the GeoJSON file
        self.stdout.write(f'Loading GeoJSON from {file_path}...')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f'File not found: {file_path}'))
            return
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f'Invalid JSON: {e}'))
            return

        features = data.get('features', [])
        self.stdout.write(f'Found {len(features)} features')

        if options['clear']:
            self.stdout.write('Clearing existing area data...')
            HmoScore.objects.all().delete()
            PostcodeDistrict.objects.all().delete()

        created_count = 0
        updated_count = 0
        skipped_count = 0

        # Region price bases for generating realistic mock data
        region_price_base = {
            'London': 450000,
            'South East': 350000,
            'East of England': 275000,
            'South West': 300000,
            'West Midlands': 220000,
            'East Midlands': 200000,
            'Yorkshire and The Humber': 180000,
            'North West': 175000,
            'North East': 150000,
            'Wales': 175000,
            'Scotland': 165000,
            'Northern Ireland': 140000,
        }

        for feature in features:
            properties = feature.get('properties', {})
            geometry = feature.get('geometry', {})

            # Extract code from name property
            code = properties.get('name', '')
            if not code:
                skipped_count += 1
                continue

            # Extract coordinates (GeoJSON uses [longitude, latitude])
            coordinates = geometry.get('coordinates', [])
            if len(coordinates) < 2:
                skipped_count += 1
                continue

            longitude = coordinates[0]
            latitude = coordinates[1]

            # Extract other properties
            description = properties.get('description', '').strip()
            population = properties.get('population', 0) or None
            households = properties.get('households', 0) or None
            uk_region = properties.get('ukRegion', 'Unknown')

            # Use description as name if available, otherwise use code
            name = description.split(',')[0].strip() if description else code

            # Create or update the postcode district
            district, created = PostcodeDistrict.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'region': uk_region,
                    'latitude': Decimal(str(latitude)),
                    'longitude': Decimal(str(longitude)),
                    'population': population if population and population > 0 else None,
                    'households': households if households and households > 0 else None,
                    'description': description,
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            # Generate realistic-looking random scores for HmoScore
            hmo_score = random.randint(45, 95)
            avg_yield = Decimal(str(round(random.uniform(7.5, 14.5), 2)))

            # Price varies by region
            base_price = region_price_base.get(uk_region, 200000)
            avg_price = int(base_price * random.uniform(0.7, 1.4))

            # Rent based on yield and price
            monthly_rent = int((avg_price * float(avg_yield) / 100) / 12)

            # Demand score weighted by hmo_score
            if hmo_score >= 75:
                demand = random.randint(60, 95)
            elif hmo_score >= 60:
                demand = random.randint(35, 75)
            else:
                demand = random.randint(15, 50)

            transport = random.randint(4, 10)
            has_article_4 = random.random() < 0.3  # 30% chance
            # Student areas are typically in regions with major universities
            student_area = random.random() < 0.15  # 15% base chance

            # Create or update the score
            HmoScore.objects.update_or_create(
                postcode_district=district,
                defaults={
                    'hmo_score': hmo_score,
                    'average_yield': avg_yield,
                    'average_price': avg_price,
                    'average_rent': monthly_rent,
                    'demand_score': demand,
                    'transport_score': transport,
                    'has_article_4': has_article_4,
                    'student_area': student_area,
                }
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully loaded {created_count} new areas, '
                f'updated {updated_count} existing areas, '
                f'skipped {skipped_count} invalid features'
            )
        )
