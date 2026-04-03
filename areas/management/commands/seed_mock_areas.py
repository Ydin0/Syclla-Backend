import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from areas.models import PostcodeDistrict
from hmo.models import HmoScore


# Sample UK postcode districts with coordinates
MOCK_AREAS = [
    # East of England
    {'code': 'CO1', 'name': 'Colchester Central', 'region': 'East of England', 'lat': 51.8891, 'lng': 0.9040},
    {'code': 'CO2', 'name': 'Colchester South', 'region': 'East of England', 'lat': 51.8714, 'lng': 0.9033},
    {'code': 'CO3', 'name': 'Colchester West', 'region': 'East of England', 'lat': 51.8894, 'lng': 0.8687},
    {'code': 'CO4', 'name': 'Colchester North', 'region': 'East of England', 'lat': 51.9127, 'lng': 0.9117},
    {'code': 'SS1', 'name': 'Southend Central', 'region': 'East of England', 'lat': 51.5384, 'lng': 0.7094},
    {'code': 'SS2', 'name': 'Southend East', 'region': 'East of England', 'lat': 51.5411, 'lng': 0.7406},
    {'code': 'SS3', 'name': 'Shoeburyness', 'region': 'East of England', 'lat': 51.5340, 'lng': 0.8108},
    {'code': 'SS14', 'name': 'Basildon', 'region': 'East of England', 'lat': 51.5762, 'lng': 0.4886},
    {'code': 'CM1', 'name': 'Chelmsford Central', 'region': 'East of England', 'lat': 51.7361, 'lng': 0.4798},
    {'code': 'CM2', 'name': 'Chelmsford South', 'region': 'East of England', 'lat': 51.7156, 'lng': 0.4734},
    {'code': 'CM3', 'name': 'Maldon', 'region': 'East of England', 'lat': 51.7309, 'lng': 0.6739},
    {'code': 'IP1', 'name': 'Ipswich Central', 'region': 'East of England', 'lat': 52.0567, 'lng': 1.1482},
    {'code': 'IP2', 'name': 'Ipswich South', 'region': 'East of England', 'lat': 52.0364, 'lng': 1.1477},
    {'code': 'IP3', 'name': 'Ipswich East', 'region': 'East of England', 'lat': 52.0523, 'lng': 1.1842},
    {'code': 'IP4', 'name': 'Ipswich North', 'region': 'East of England', 'lat': 52.0726, 'lng': 1.1630},
    {'code': 'NR1', 'name': 'Norwich Central', 'region': 'East of England', 'lat': 52.6269, 'lng': 1.3016},
    {'code': 'NR2', 'name': 'Norwich South', 'region': 'East of England', 'lat': 52.6165, 'lng': 1.2756},
    {'code': 'NR3', 'name': 'Norwich North', 'region': 'East of England', 'lat': 52.6452, 'lng': 1.2940},
    {'code': 'CB1', 'name': 'Cambridge Central', 'region': 'East of England', 'lat': 52.2053, 'lng': 0.1218},
    {'code': 'CB2', 'name': 'Cambridge South', 'region': 'East of England', 'lat': 52.1903, 'lng': 0.1174},
    {'code': 'CB3', 'name': 'Cambridge West', 'region': 'East of England', 'lat': 52.2117, 'lng': 0.0890},
    {'code': 'CB4', 'name': 'Cambridge North', 'region': 'East of England', 'lat': 52.2288, 'lng': 0.1264},
    {'code': 'LU1', 'name': 'Luton Central', 'region': 'East of England', 'lat': 51.8787, 'lng': -0.4200},
    {'code': 'LU2', 'name': 'Luton East', 'region': 'East of England', 'lat': 51.8876, 'lng': -0.3876},
    {'code': 'LU3', 'name': 'Luton North', 'region': 'East of England', 'lat': 51.9052, 'lng': -0.4287},

    # South East
    {'code': 'RG1', 'name': 'Reading Central', 'region': 'South East', 'lat': 51.4551, 'lng': -0.9787},
    {'code': 'RG2', 'name': 'Reading South', 'region': 'South East', 'lat': 51.4286, 'lng': -0.9580},
    {'code': 'OX1', 'name': 'Oxford Central', 'region': 'South East', 'lat': 51.7520, 'lng': -1.2577},
    {'code': 'OX2', 'name': 'Oxford North', 'region': 'South East', 'lat': 51.7689, 'lng': -1.2780},
    {'code': 'OX3', 'name': 'Headington', 'region': 'South East', 'lat': 51.7581, 'lng': -1.2152},
    {'code': 'MK1', 'name': 'Milton Keynes Central', 'region': 'South East', 'lat': 52.0406, 'lng': -0.7594},
    {'code': 'MK2', 'name': 'Milton Keynes South', 'region': 'South East', 'lat': 52.0206, 'lng': -0.7594},
    {'code': 'SL1', 'name': 'Slough', 'region': 'South East', 'lat': 51.5105, 'lng': -0.5950},
    {'code': 'BN1', 'name': 'Brighton Central', 'region': 'South East', 'lat': 50.8225, 'lng': -0.1372},
    {'code': 'BN2', 'name': 'Brighton East', 'region': 'South East', 'lat': 50.8206, 'lng': -0.0940},
    {'code': 'BN3', 'name': 'Hove', 'region': 'South East', 'lat': 50.8342, 'lng': -0.1788},
    {'code': 'PO1', 'name': 'Portsmouth Central', 'region': 'South East', 'lat': 50.7989, 'lng': -1.0917},
    {'code': 'PO2', 'name': 'Portsmouth North', 'region': 'South East', 'lat': 50.8148, 'lng': -1.0755},
    {'code': 'SO14', 'name': 'Southampton Central', 'region': 'South East', 'lat': 50.9025, 'lng': -1.4042},
    {'code': 'SO15', 'name': 'Southampton West', 'region': 'South East', 'lat': 50.9153, 'lng': -1.4306},

    # London
    {'code': 'E1', 'name': 'Whitechapel', 'region': 'London', 'lat': 51.5152, 'lng': -0.0607},
    {'code': 'E2', 'name': 'Bethnal Green', 'region': 'London', 'lat': 51.5280, 'lng': -0.0556},
    {'code': 'E3', 'name': 'Bow', 'region': 'London', 'lat': 51.5288, 'lng': -0.0193},
    {'code': 'E14', 'name': 'Canary Wharf', 'region': 'London', 'lat': 51.5005, 'lng': -0.0196},
    {'code': 'E15', 'name': 'Stratford', 'region': 'London', 'lat': 51.5430, 'lng': 0.0003},
    {'code': 'N1', 'name': 'Islington', 'region': 'London', 'lat': 51.5416, 'lng': -0.1025},
    {'code': 'N7', 'name': 'Holloway', 'region': 'London', 'lat': 51.5575, 'lng': -0.1175},
    {'code': 'SE1', 'name': 'Southwark', 'region': 'London', 'lat': 51.5037, 'lng': -0.0880},
    {'code': 'SE15', 'name': 'Peckham', 'region': 'London', 'lat': 51.4710, 'lng': -0.0627},
    {'code': 'SW2', 'name': 'Brixton', 'region': 'London', 'lat': 51.4571, 'lng': -0.1175},
    {'code': 'SW9', 'name': 'Stockwell', 'region': 'London', 'lat': 51.4720, 'lng': -0.1218},
    {'code': 'W10', 'name': 'North Kensington', 'region': 'London', 'lat': 51.5243, 'lng': -0.2106},
    {'code': 'NW1', 'name': 'Camden', 'region': 'London', 'lat': 51.5346, 'lng': -0.1435},
    {'code': 'NW10', 'name': 'Willesden', 'region': 'London', 'lat': 51.5425, 'lng': -0.2396},

    # North West
    {'code': 'M1', 'name': 'Manchester Central', 'region': 'North West', 'lat': 53.4808, 'lng': -2.2426},
    {'code': 'M4', 'name': 'Ancoats', 'region': 'North West', 'lat': 53.4853, 'lng': -2.2232},
    {'code': 'M14', 'name': 'Fallowfield', 'region': 'North West', 'lat': 53.4446, 'lng': -2.2212},
    {'code': 'M15', 'name': 'Hulme', 'region': 'North West', 'lat': 53.4686, 'lng': -2.2559},
    {'code': 'L1', 'name': 'Liverpool Central', 'region': 'North West', 'lat': 53.4084, 'lng': -2.9916},
    {'code': 'L6', 'name': 'Everton', 'region': 'North West', 'lat': 53.4310, 'lng': -2.9579},
    {'code': 'L15', 'name': 'Wavertree', 'region': 'North West', 'lat': 53.4033, 'lng': -2.9171},

    # Yorkshire
    {'code': 'LS1', 'name': 'Leeds Central', 'region': 'Yorkshire', 'lat': 53.7983, 'lng': -1.5499},
    {'code': 'LS2', 'name': 'Leeds University', 'region': 'Yorkshire', 'lat': 53.8040, 'lng': -1.5520},
    {'code': 'LS6', 'name': 'Headingley', 'region': 'Yorkshire', 'lat': 53.8220, 'lng': -1.5784},
    {'code': 'S1', 'name': 'Sheffield Central', 'region': 'Yorkshire', 'lat': 53.3811, 'lng': -1.4701},
    {'code': 'S2', 'name': 'Sheffield South', 'region': 'Yorkshire', 'lat': 53.3657, 'lng': -1.4558},
    {'code': 'S10', 'name': 'Broomhill', 'region': 'Yorkshire', 'lat': 53.3840, 'lng': -1.5011},
    {'code': 'BD1', 'name': 'Bradford Central', 'region': 'Yorkshire', 'lat': 53.7960, 'lng': -1.7594},
    {'code': 'HU1', 'name': 'Hull Central', 'region': 'Yorkshire', 'lat': 53.7676, 'lng': -0.3274},

    # West Midlands
    {'code': 'B1', 'name': 'Birmingham Central', 'region': 'West Midlands', 'lat': 52.4862, 'lng': -1.8904},
    {'code': 'B5', 'name': 'Digbeth', 'region': 'West Midlands', 'lat': 52.4775, 'lng': -1.8803},
    {'code': 'B15', 'name': 'Edgbaston', 'region': 'West Midlands', 'lat': 52.4636, 'lng': -1.9230},
    {'code': 'B29', 'name': 'Selly Oak', 'region': 'West Midlands', 'lat': 52.4389, 'lng': -1.9397},
    {'code': 'CV1', 'name': 'Coventry Central', 'region': 'West Midlands', 'lat': 52.4068, 'lng': -1.5197},

    # East Midlands
    {'code': 'NG1', 'name': 'Nottingham Central', 'region': 'East Midlands', 'lat': 52.9548, 'lng': -1.1581},
    {'code': 'NG7', 'name': 'Lenton', 'region': 'East Midlands', 'lat': 52.9461, 'lng': -1.1883},
    {'code': 'LE1', 'name': 'Leicester Central', 'region': 'East Midlands', 'lat': 52.6369, 'lng': -1.1398},
    {'code': 'LE2', 'name': 'Leicester South', 'region': 'East Midlands', 'lat': 52.6151, 'lng': -1.1234},
    {'code': 'DE1', 'name': 'Derby Central', 'region': 'East Midlands', 'lat': 52.9225, 'lng': -1.4746},

    # North East
    {'code': 'NE1', 'name': 'Newcastle Central', 'region': 'North East', 'lat': 54.9783, 'lng': -1.6178},
    {'code': 'NE6', 'name': 'Byker', 'region': 'North East', 'lat': 54.9710, 'lng': -1.5678},
    {'code': 'SR1', 'name': 'Sunderland Central', 'region': 'North East', 'lat': 54.9069, 'lng': -1.3838},
    {'code': 'TS1', 'name': 'Middlesbrough Central', 'region': 'North East', 'lat': 54.5742, 'lng': -1.2346},

    # South West
    {'code': 'BS1', 'name': 'Bristol Central', 'region': 'South West', 'lat': 51.4545, 'lng': -2.5879},
    {'code': 'BS2', 'name': 'St Pauls', 'region': 'South West', 'lat': 51.4638, 'lng': -2.5777},
    {'code': 'BS6', 'name': 'Redland', 'region': 'South West', 'lat': 51.4732, 'lng': -2.5971},
    {'code': 'EX1', 'name': 'Exeter Central', 'region': 'South West', 'lat': 50.7236, 'lng': -3.5275},
    {'code': 'PL1', 'name': 'Plymouth Central', 'region': 'South West', 'lat': 50.3755, 'lng': -4.1427},
    {'code': 'BA1', 'name': 'Bath Central', 'region': 'South West', 'lat': 51.3751, 'lng': -2.3617},

    # Wales
    {'code': 'CF10', 'name': 'Cardiff Central', 'region': 'Wales', 'lat': 51.4816, 'lng': -3.1791},
    {'code': 'CF24', 'name': 'Cathays', 'region': 'Wales', 'lat': 51.4953, 'lng': -3.1695},
    {'code': 'SA1', 'name': 'Swansea Central', 'region': 'Wales', 'lat': 51.6214, 'lng': -3.9436},
    {'code': 'NP20', 'name': 'Newport', 'region': 'Wales', 'lat': 51.5842, 'lng': -2.9977},

    # Scotland
    {'code': 'G1', 'name': 'Glasgow Central', 'region': 'Scotland', 'lat': 55.8642, 'lng': -4.2518},
    {'code': 'G3', 'name': 'Finnieston', 'region': 'Scotland', 'lat': 55.8653, 'lng': -4.2820},
    {'code': 'G12', 'name': 'Hillhead', 'region': 'Scotland', 'lat': 55.8751, 'lng': -4.2919},
    {'code': 'EH1', 'name': 'Edinburgh Old Town', 'region': 'Scotland', 'lat': 55.9533, 'lng': -3.1883},
    {'code': 'EH8', 'name': 'Holyrood', 'region': 'Scotland', 'lat': 55.9490, 'lng': -3.1676},
    {'code': 'AB10', 'name': 'Aberdeen Central', 'region': 'Scotland', 'lat': 57.1437, 'lng': -2.0981},
    {'code': 'DD1', 'name': 'Dundee Central', 'region': 'Scotland', 'lat': 56.4620, 'lng': -2.9707},
]


class Command(BaseCommand):
    help = 'Seeds the database with mock UK postcode district data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing area data...')
            HmoScore.objects.all().delete()
            PostcodeDistrict.objects.all().delete()

        self.stdout.write('Seeding mock area data...')

        created_count = 0
        updated_count = 0

        for area_data in MOCK_AREAS:
            # Create or update the postcode district
            district, created = PostcodeDistrict.objects.update_or_create(
                code=area_data['code'],
                defaults={
                    'name': area_data['name'],
                    'region': area_data['region'],
                    'latitude': Decimal(str(area_data['lat'])),
                    'longitude': Decimal(str(area_data['lng'])),
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

            # Generate realistic-looking random scores
            hmo_score = random.randint(45, 95)
            avg_yield = Decimal(str(round(random.uniform(7.5, 14.5), 2)))

            # Price varies by region
            region_price_base = {
                'London': 450000,
                'South East': 350000,
                'East of England': 275000,
                'South West': 300000,
                'West Midlands': 220000,
                'East Midlands': 200000,
                'Yorkshire': 180000,
                'North West': 175000,
                'North East': 150000,
                'Wales': 175000,
                'Scotland': 165000,
            }
            base_price = region_price_base.get(area_data['region'], 200000)
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
            student_area = 'University' in area_data['name'] or random.random() < 0.2

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
                f'Seeded {created_count} new areas, '
                f'updated {updated_count} existing areas'
            )
        )

        # Backfill HmoScore for all PostcodeDistricts that don't have one yet
        missing = PostcodeDistrict.objects.filter(score__isnull=True)
        backfill_count = 0

        region_price_base = {
            'London': 450000,
            'South East': 350000,
            'East of England': 275000,
            'South West': 300000,
            'West Midlands': 220000,
            'East Midlands': 200000,
            'Yorkshire': 180000,
            'Yorkshire and The Humber': 180000,
            'North West': 175000,
            'North East': 150000,
            'Wales': 175000,
            'Scotland': 165000,
            'Northern Ireland': 140000,
        }

        for district in missing:
            hmo_score = random.randint(45, 95)
            avg_yield = Decimal(str(round(random.uniform(7.5, 14.5), 2)))
            base_price = region_price_base.get(district.region, 200000)
            avg_price = int(base_price * random.uniform(0.7, 1.4))
            monthly_rent = int((avg_price * float(avg_yield) / 100) / 12)

            if hmo_score >= 75:
                demand = random.randint(60, 95)
            elif hmo_score >= 60:
                demand = random.randint(35, 75)
            else:
                demand = random.randint(15, 50)

            HmoScore.objects.create(
                postcode_district=district,
                hmo_score=hmo_score,
                average_yield=avg_yield,
                average_price=avg_price,
                average_rent=monthly_rent,
                demand_score=demand,
                transport_score=random.randint(4, 10),
                council_attitude_score=random.randint(3, 9),
                has_article_4=random.random() < 0.3,
                student_area=random.random() < 0.15,
            )
            backfill_count += 1

        if backfill_count:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Backfilled HmoScore for {backfill_count} remaining districts'
                )
            )
