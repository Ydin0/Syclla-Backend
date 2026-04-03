from django.core.management.base import BaseCommand
from hmo.models import SpareRoomRent


# SpareRoom average monthly room rent data.
# Source: SpareRoom.co.uk national rent index.
# Corrections applied:
#   - "Garlow" → "Harlow" (alphabetical position between Gravesend & Harrogate)
#   - "Sale£h£726" → "Salford £726" (corrupted text; Salford is the likely match)
SPAREROOM_DATA = [
    ("Aberdeen", 517),
    ("Aldershot", 668),
    ("Ashford", 694),
    ("Aylesbury", 691),
    ("Barnet", 853),
    ("Barnsley", 492),
    ("Barry", 569),
    ("Basildon", 720),
    ("Basingstoke", 669),
    ("Bath", 832),
    ("Bedford", 628),
    ("Belfast", 589),
    ("Benfleet", 815),
    ("Birkenhead", 525),
    ("Birmingham", 618),
    ("Blackburn", 485),
    ("Blackpool", 518),
    ("Bognor Regis", 676),
    ("Bolton", 575),
    ("Bootle", 527),
    ("Bournemouth", 661),
    ("Bracknell", 707),
    ("Bradford", 472),
    ("Brentwood", 807),
    ("Brighton", 750),
    ("Bristol", 737),
    ("Bromley", 807),
    ("Burnley", 470),
    ("Bury", 620),
    ("Cambridge", 788),
    ("Cannock", 598),
    ("Canterbury", 600),
    ("Cardiff", 666),
    ("Carlisle", 586),
    ("Chatham", 642),
    ("Cheadle", 689),
    ("Chelmsford", 704),
    ("Cheltenham", 655),
    ("Chester", 628),
    ("Chesterfield", 553),
    ("Clacton-on-Sea", 628),
    ("Colchester", 642),
    ("Corby", 576),
    ("Coventry", 560),
    ("Crawley", 719),
    ("Crewe", 516),
    ("Croydon", 823),
    ("Darlington", 493),
    ("Dartford", 768),
    ("Derby", 585),
    ("Dewsbury", 553),
    ("Doncaster", 499),
    ("Dorchester", 645),
    ("Dudley", 551),
    ("Dumfries", 564),
    ("Dundee", 596),
    ("Dunstable", 660),
    ("Durham", 638),
    ("Eastbourne", 671),
    ("Eastleigh", 673),
    ("Edinburgh", 778),
    ("Ellesmere Port", 605),
    ("Enfield", 820),
    ("Epsom", 792),
    ("Esher", 740),
    ("Exeter", 674),
    ("Falkirk", 658),
    ("Fareham", 668),
    ("Farnborough", 684),
    ("Gateshead", 568),
    ("Gillingham", 639),
    ("Glasgow", 690),
    ("Gloucester", 617),
    ("Gosport", 643),
    ("Gravesend", 710),
    ("Harlow", 700),
    ("Harrogate", 623),
    ("Harrow", 821),
    ("Hartlepool", 499),
    ("Hastings", 666),
    ("Hemel Hempstead", 705),
    ("Hereford", 622),
    ("High Wycombe", 705),
    ("Horsham", 735),
    ("Hove", 773),
    ("Huddersfield", 485),
    ("Hull", 512),
    ("Ilford", 781),
    ("Inverness", 649),
    ("Ipswich", 629),
    ("Isle of Man", 696),
    ("Isle of Wight", 596),
    ("Keighley", 598),
    ("Kettering", 569),
    ("Kidderminster", 541),
    ("Kilmarnock", 624),
    ("Kingston upon Thames", 922),
    ("Kirkcaldy", 587),
    ("Lancaster", 574),
    ("Leamington Spa", 616),
    ("Leeds", 565),
    ("Leicester", 566),
    ("Lincoln", 517),
    ("Lisburn", 609),
    ("Littlehampton", 653),
    ("Liverpool", 555),
    ("Livingston", 597),
    ("London", 985),
    ("Londonderry", 566),
    ("Loughborough", 582),
    ("Lowestoft", 589),
    ("Luton", 624),
    ("Macclesfield", 602),
    ("Maidenhead", 757),
    ("Maidstone", 709),
    ("Manchester", 691),
    ("Mansfield", 523),
    ("Margate", 655),
    ("Middlesbrough", 477),
    ("Milton Keynes", 693),
    ("Morecambe", 656),
    ("Motherwell", 552),
    ("Newcastle upon Tyne", 605),
    ("Newcastle-under-Lyme", 530),
    ("Newport", 573),
    ("Northampton", 595),
    ("Norwich", 603),
    ("Nottingham", 589),
    ("Nuneaton", 560),
    ("Oldbury", 548),
    ("Oldham", 591),
    ("Oxford", 831),
    ("Paisley", 542),
    ("Perth", 546),
    ("Peterborough", 587),
    ("Plymouth", 573),
    ("Poole", 699),
    ("Portsmouth", 650),
    ("Preston", 529),
    ("Reading", 712),
    ("Redditch", 564),
    ("Redhill", 818),
    ("Reigate", 791),
    ("Rochdale", 591),
    ("Rotherham", 492),
    ("Rugby", 595),
    ("Runcorn", 565),
    ("Salford", 726),
    ("Smethwick", 603),
    ("Solihull", 647),
    ("South Shields", 523),
    ("Southall", 790),
    ("Southampton", 660),
    ("Southend-on-Sea", 683),
    ("Southport", 583),
    ("St. Albans", 813),
    ("St. Helens", 532),
    ("Stafford", 569),
    ("Staines", 799),
    ("Stevenage", 711),
    ("Stockport", 681),
    ("Stockton-on-Tees", 482),
    ("Stoke-on-Trent", 505),
    ("Stourbridge", 649),
    ("Sunderland", 516),
    ("Sutton Coldfield", 649),
    ("Swansea", 528),
    ("Swindon", 671),
    ("Tamworth", 590),
    ("Taunton", 679),
    ("Telford", 559),
    ("Tonbridge", 706),
    ("Torquay", 576),
    ("Truro", 676),
    ("Tunbridge Wells", 747),
    ("Twickenham", 914),
    ("Wakefield", 521),
    ("Wallasey", 526),
    ("Walsall", 534),
    ("Waltham Cross", 753),
    ("Warrington", 613),
    ("Waterlooville", 637),
    ("Watford", 791),
    ("West Bromwich", 520),
    ("Weston-Super-Mare", 643),
    ("Widnes", 590),
    ("Wigan", 565),
    ("Woking", 803),
    ("Wolverhampton", 553),
    ("Worcester", 597),
    ("Worthing", 711),
    ("York", 732),
]


class Command(BaseCommand):
    help = "Load SpareRoom average monthly room rent data into the SpareRoomRent table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quarter",
            type=str,
            default="Q4",
            help='Quarter label, e.g. "Q4" (default: Q4)',
        )
        parser.add_argument(
            "--year",
            type=int,
            default=2025,
            help="Year, e.g. 2025 (default: 2025)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing SpareRoomRent rows for the given quarter/year before loading.",
        )

    def handle(self, *args, **options):
        quarter = options["quarter"]
        year = options["year"]

        if options["clear"]:
            deleted, _ = SpareRoomRent.objects.filter(
                quarter=quarter, year=year
            ).delete()
            self.stdout.write(f"Deleted {deleted} existing rows for {quarter} {year}.")

        created = 0
        updated = 0

        for location_name, rent in SPAREROOM_DATA:
            _, was_created = SpareRoomRent.objects.update_or_create(
                location_name=location_name,
                quarter=quarter,
                year=year,
                defaults={"avg_room_rent": rent},
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done — {quarter} {year}: {created} created, {updated} updated "
                f"({len(SPAREROOM_DATA)} total locations)."
            )
        )
