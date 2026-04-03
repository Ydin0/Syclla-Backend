"""
Flag outcodes with Article 4 HMO directions.

Matches hardcoded council names to LocalAuthorityDemand records,
then sets has_article_4=True on HmoScore for every outcode in that LA.

Usage:
    python manage.py import_article4
"""

import re

from django.core.management.base import BaseCommand

from hmo.models import HmoScore, LocalAuthorityDemand, OutcodeLAMapping


# Manual alias → exact la_name for known mismatches
ALIASES = {
    "Kingston upon Hull": "Kingston upon Hull",
    "York": "York",
    "Bristol": "Bristol",
    "Derby": "Derby",
    "Leicester": "Leicester",
    "Lincoln": "Lincoln",
    "Liverpool": "Liverpool",
    "Manchester": "Manchester",
    "Nottingham": "Nottingham",
    "Oxford": "Oxford",
    "Plymouth": "Plymouth",
    "Portsmouth": "Portsmouth",
    "Southampton": "Southampton",
    "Wolverhampton": "Wolverhampton",
    "Worcester": "Worcester",
    "Newcastle upon Tyne": "Newcastle upon Tyne",
    "Brighton and Hove": "Brighton and Hove",
    "Bournemouth Christchurch and Poole": "Bournemouth, Christchurch and Poole",
}

STRIP_RE = re.compile(
    r"\b(council|borough|city|metropolitan|district|of|the|london|royal)\b",
    re.IGNORECASE,
)

ARTICLE_4_COUNCILS = [
    "Arun", "Ashford", "Barnet", "Barnsley", "Basildon",
    "Basingstoke and Deane", "Bassetlaw", "Bath and North East Somerset",
    "Bedford", "Birmingham", "Blackburn with Darwen", "Blackpool", "Bolton",
    "Bournemouth Christchurch and Poole", "Brent", "Brighton and Hove",
    "Bristol", "Burnley", "Canterbury", "Charnwood", "Cheltenham",
    "Cheshire East", "Cheshire West and Chester", "Chorley", "Doncaster",
    "York", "Cornwall", "Coventry", "Crawley", "Croydon", "Dartford",
    "Derby", "Dudley", "Durham", "Ealing", "East Staffordshire",
    "East Suffolk", "Eastbourne", "Enfield", "Exeter", "Fenland",
    "Great Yarmouth", "Halton", "Haringey", "Harlow", "Hastings",
    "Hounslow", "Kingston upon Hull", "Hyndburn", "Ipswich", "Lambeth",
    "Lancaster", "Leeds", "Leicester", "Lincoln", "Liverpool",
    "Barking and Dagenham", "Bexley", "Bromley", "Havering", "Hillingdon",
    "Lewisham", "Newham", "Redbridge", "Tower Hamlets", "Manchester",
    "Medway", "Merton", "Middlesbrough", "Milton Keynes",
    "Newcastle upon Tyne", "Newcastle-under-Lyme",
    "North Northamptonshire", "North West Leicestershire", "Nottingham",
    "Oldham", "Oxford", "Plymouth", "Portsmouth", "Preston", "Reading",
    "Rossendale", "Greenwich", "Rugby", "Salford", "Sefton", "Sheffield",
    "Somerset", "South Gloucestershire", "South Tyneside", "Southampton",
    "Southwark", "Spelthorne", "Stevenage", "Sunderland", "Sutton",
    "Tameside", "Tendring", "Thanet", "Trafford", "Wakefield", "Walsall",
    "Waltham Forest", "Warwick", "Welwyn Hatfield", "West Lancashire",
    "West Northamptonshire", "Wigan", "Winchester", "Wolverhampton",
    "Worcester",
]


def _normalise(name):
    """Strip common council prefixes/suffixes for fuzzy comparison."""
    s = STRIP_RE.sub("", name.lower())
    return re.sub(r"\s+", " ", s).strip()


class Command(BaseCommand):
    help = "Set has_article_4 on HmoScore for councils with Article 4 directions"

    def handle(self, *args, **options):
        # Load all LAs with normalised name index
        la_by_exact = {}   # lowercase exact name -> LA
        la_by_norm = {}    # normalised name -> LA
        for la in LocalAuthorityDemand.objects.all():
            la_by_exact[la.la_name.lower()] = la
            la_by_norm[_normalise(la.la_name)] = la

        matched_las = []
        unmatched = []

        for council in ARTICLE_4_COUNCILS:
            la = None

            # 1. Check manual alias
            alias = ALIASES.get(council)
            if alias:
                la = la_by_exact.get(alias.lower())

            # 2. Exact match
            if la is None:
                la = la_by_exact.get(council.lower())

            # 3. Normalised match
            if la is None:
                la = la_by_norm.get(_normalise(council))

            # 4. Contains fallback (council name in la_name or vice versa)
            if la is None:
                council_lower = council.lower()
                for la_obj in LocalAuthorityDemand.objects.all():
                    la_lower = la_obj.la_name.lower()
                    if council_lower in la_lower or la_lower in council_lower:
                        la = la_obj
                        break

            if la:
                matched_las.append((council, la))
            else:
                unmatched.append(council)

        self.stdout.write(f"Councils matched: {len(matched_las)}/{len(ARTICLE_4_COUNCILS)}")

        # Reset all has_article_4 to False first
        HmoScore.objects.all().update(has_article_4=False)

        total_outcodes_updated = 0
        for council, la in matched_las:
            # Get all outcodes mapped to this LA
            outcode_ids = list(
                OutcodeLAMapping.objects.filter(local_authority=la)
                .values_list("outcode_id", flat=True)
            )
            count = HmoScore.objects.filter(
                postcode_district__code__in=outcode_ids
            ).update(has_article_4=True)

            total_outcodes_updated += count
            self.stdout.write(
                f"  Matched: {council} ({la.la_code}) → {count} outcodes updated"
            )

        # Summary
        total_true = HmoScore.objects.filter(has_article_4=True).count()
        total_false = HmoScore.objects.filter(has_article_4=False).count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("Article 4 import complete"))
        self.stdout.write(f"  Councils matched:       {len(matched_las)}")
        self.stdout.write(f"  Councils NOT matched:   {len(unmatched)}")
        if unmatched:
            for name in unmatched:
                self.stdout.write(self.style.WARNING(f"    - {name}"))
        self.stdout.write(f"  Outcodes has_article_4=True:  {total_true}")
        self.stdout.write(f"  Outcodes has_article_4=False: {total_false}")
        self.stdout.write(self.style.SUCCESS("=" * 60))
