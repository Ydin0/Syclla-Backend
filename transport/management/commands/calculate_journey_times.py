"""
Calculate real train journey times from stations to major cities using
Google Directions API, then derive a transport score (0-100) for each outcode.

For each station-city pair, uses alternatives=True to get multiple route
options in a single API call and picks the fastest.

Usage:
    python manage.py calculate_journey_times              # full run
    python manage.py calculate_journey_times --station GLD # single station
    python manage.py calculate_journey_times --resume      # skip already-calculated
    python manage.py calculate_journey_times --skip-api    # re-score only
"""

import math
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from areas.models import PostcodeDistrict
from hmo.models import HmoScore
from transport.models import MajorCity, RailwayStation, StationCityJourney

def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km between two points."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def next_monday_8am():
    """Return a timezone-aware datetime for next Monday at 08:00 UTC."""
    now = timezone.now()
    days_ahead = 7 - now.weekday()  # 0=Monday
    if days_ahead == 7:
        days_ahead = 0
    if days_ahead == 0 and now.hour >= 8:
        days_ahead = 7
    return now.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)


def parse_arrival_station(result):
    """Extract the arrival station name from the last rail transit step."""
    if not result or not result[0].get("legs"):
        return None
    for step in result[0]["legs"][0].get("steps", []):
        td = step.get("transit_details")
        if td and td.get("line", {}).get("vehicle", {}).get("type") in ("HEAVY_RAIL", "COMMUTER_TRAIN", "HIGH_SPEED_TRAIN"):
            return td["arrival_stop"]["name"]
    # Fallback: return arrival stop from any transit step
    for step in result[0]["legs"][0].get("steps", []):
        td = step.get("transit_details")
        if td:
            return td["arrival_stop"]["name"]
    return None


class Command(BaseCommand):
    help = "Calculate journey times from stations to major cities and score outcodes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--station",
            type=str,
            help="Test a single station by TLC code (e.g. GLD).",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip stations that already have StationCityJourney records.",
        )
        parser.add_argument(
            "--skip-api",
            action="store_true",
            help="Skip API calls (step 2), only run scoring (step 3).",
        )

    def handle(self, *args, **options):
        self.cities = list(MajorCity.objects.all())
        if not self.cities:
            raise CommandError("No MajorCity records found. Run seed_major_cities first.")

        self.london = next((c for c in self.cities if c.name == "London"), None)
        self.non_london = [c for c in self.cities if c.name != "London"]

        if not options["skip_api"]:
            self._run_api(options)

        self._run_scoring(options)

    # ------------------------------------------------------------------
    # Step 1 + 2: Pre-filter stations & call Google Directions API
    # ------------------------------------------------------------------

    def _run_api(self, options):
        api_key = settings.GOOGLE_MAPS_API_KEY
        if not api_key:
            raise CommandError(
                "GOOGLE_MAPS_API_KEY is not set. Add it to your .env file."
            )

        import googlemaps

        gmaps = googlemaps.Client(key=api_key)
        departure = next_monday_8am()
        self.stdout.write(f"Departure: {departure.isoformat()} (alternatives=True)")

        # Load stations
        if options.get("station"):
            stations = list(
                RailwayStation.objects.filter(tlc_code=options["station"].upper())
            )
            if not stations:
                raise CommandError(f"Station '{options['station']}' not found.")
        else:
            stations = list(RailwayStation.objects.all())

        # Step 1: Pre-filter by haversine distance
        relevant = []
        for s in stations:
            s_lat, s_lon = float(s.latitude), float(s.longitude)

            near_london = False
            if self.london:
                d = haversine_km(s_lat, s_lon, self.london.latitude, self.london.longitude)
                if d <= 150:
                    near_london = True

            near_city = False
            for c in self.non_london:
                d = haversine_km(s_lat, s_lon, c.latitude, c.longitude)
                if d <= 100:
                    near_city = True
                    break

            if near_london or near_city:
                relevant.append((s, near_london))

        skipped_count = len(stations) - len(relevant)
        self.stdout.write(
            f"Stations: {len(relevant)} relevant, {skipped_count} skipped (too far)"
        )

        # Step 2: API calls — multi-departure, station-specific destinations
        api_calls = 0
        for idx, (station, near_london) in enumerate(relevant, 1):
            s_lat, s_lon = float(station.latitude), float(station.longitude)

            # --resume: skip if already has journeys
            if options.get("resume"):
                existing = StationCityJourney.objects.filter(station=station).count()
                if existing > 0:
                    self.stdout.write(f"  [{idx}/{len(relevant)}] {station.tlc_code} — skipped (resume)")
                    continue

            origin = f"{station.station_name} station"
            destinations = []

            # London route
            if near_london and self.london:
                destinations.append("London")

            # Nearest 3 non-London cities within 100km
            city_distances = []
            for c in self.non_london:
                d = haversine_km(s_lat, s_lon, c.latitude, c.longitude)
                if d <= 100:
                    city_distances.append((c, d))
            city_distances.sort(key=lambda x: x[1])
            for c, _ in city_distances[:3]:
                destinations.append(c.name)

            verbose = bool(options.get("station"))
            route_details = []
            for city_name in destinations:
                best_mins = None
                best_arrival_station = None
                try:
                    results = gmaps.directions(
                        origin,
                        city_name,
                        mode="transit",
                        transit_mode="rail",
                        departure_time=departure,
                        alternatives=True,
                    )
                    for i, route in enumerate(results):
                        legs = route.get("legs", [{}])[0]
                        duration_sec = legs.get("duration", {}).get("value")
                        if duration_sec is None:
                            continue
                        mins = round(duration_sec / 60)
                        # Parse arrival station from this route
                        arrival = None
                        for step in legs.get("steps", []):
                            td = step.get("transit_details")
                            if td:
                                vtype = td.get("line", {}).get("vehicle", {}).get("type")
                                if vtype in ("HEAVY_RAIL", "COMMUTER_TRAIN", "HIGH_SPEED_TRAIN"):
                                    arrival = td["arrival_stop"]["name"]
                                    break
                        if arrival is None:
                            for step in legs.get("steps", []):
                                td = step.get("transit_details")
                                if td:
                                    arrival = td["arrival_stop"]["name"]
                                    break
                        if verbose:
                            self.stdout.write(
                                f"    Route {i}: {mins} mins via {arrival or '?'}"
                            )
                        if best_mins is None or mins < best_mins:
                            best_mins = mins
                            best_arrival_station = arrival
                except Exception as e:
                    self.stderr.write(
                        f"    API error {station.tlc_code}→{city_name}: {e}"
                    )

                api_calls += 1
                if api_calls % 50 == 0:
                    self.stdout.write(f"    ... {api_calls} API calls, pausing briefly")
                    time.sleep(2)

                if verbose and best_mins is not None:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"    -> Fastest: {best_mins} mins via {best_arrival_station}"
                        )
                    )

                StationCityJourney.objects.update_or_create(
                    station=station,
                    city_name=city_name,
                    defaults={
                        "journey_time_mins": best_mins,
                        "destination_station": best_arrival_station,
                    },
                )
                route_details.append(
                    f"{city_name} via {best_arrival_station or '?'} = {best_mins or '?'}min"
                )

            self.stdout.write(
                f"  [{idx}/{len(relevant)}] {station.tlc_code} {station.station_name} — "
                + ", ".join(route_details)
            )

        self.stdout.write(self.style.SUCCESS(f"API complete: {api_calls} calls made."))

    # ------------------------------------------------------------------
    # Step 3: Score outcodes
    # ------------------------------------------------------------------

    def _run_scoring(self, options):
        self.stdout.write("\nScoring outcodes...")

        outcodes_with_stations = (
            PostcodeDistrict.objects.filter(
                stations__isnull=False,
                latitude__isnull=False,
                longitude__isnull=False,
            )
            .distinct()
        )

        to_update = []
        scored = 0

        for outcode in outcodes_with_stations:
            oc_lat, oc_lon = float(outcode.latitude), float(outcode.longitude)
            stations = list(outcode.stations.all())

            # Find nearest station by haversine
            nearest_station = None
            nearest_dist = float("inf")
            for s in stations:
                d = haversine_km(oc_lat, oc_lon, float(s.latitude), float(s.longitude))
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_station = s

            if nearest_station is None or nearest_dist > 5:
                score_obj, _ = HmoScore.objects.get_or_create(
                    postcode_district=outcode,
                )
                score_obj.transport_score = 0
                score_obj.nearest_station_name = (
                    nearest_station.station_name if nearest_station else None
                )
                score_obj.nearest_station_distance_km = (
                    round(nearest_dist, 2) if nearest_station else None
                )
                score_obj.london_journey_mins = None
                score_obj.nearest_city_journey_mins = None
                score_obj.nearest_city_name = None
                score_obj.cities_within_60_mins = 0
                to_update.append(score_obj)
                continue

            journeys = list(
                StationCityJourney.objects.filter(station=nearest_station)
            )

            london_journey = None
            non_london_journeys = []

            for j in journeys:
                if j.city_name == "London" and j.journey_time_mins is not None:
                    london_journey = j
                elif j.city_name != "London" and j.journey_time_mins is not None:
                    non_london_journeys.append(j)

            nearest_city_j = None
            if non_london_journeys:
                nearest_city_j = min(non_london_journeys, key=lambda j: j.journey_time_mins)

            cities_60 = sum(
                1 for j in non_london_journeys if j.journey_time_mins <= 60
            )

            base_score = self._tier_base(nearest_city_j)
            london_score = self._tier_london(london_journey)
            multi_score = self._tier_multi(cities_60)

            final = round(base_score * 0.40 + london_score * 0.35 + multi_score * 0.25)
            final = max(0, min(100, final))

            score_obj, _ = HmoScore.objects.get_or_create(
                postcode_district=outcode,
            )
            score_obj.transport_score = final
            score_obj.nearest_station_name = nearest_station.station_name
            score_obj.nearest_station_distance_km = round(nearest_dist, 2)
            score_obj.london_journey_mins = (
                london_journey.journey_time_mins if london_journey else None
            )
            score_obj.nearest_city_journey_mins = (
                nearest_city_j.journey_time_mins if nearest_city_j else None
            )
            score_obj.nearest_city_name = (
                nearest_city_j.city_name if nearest_city_j else None
            )
            score_obj.cities_within_60_mins = cities_60
            to_update.append(score_obj)
            scored += 1

        if to_update:
            HmoScore.objects.bulk_update(
                to_update,
                [
                    "transport_score",
                    "nearest_station_name",
                    "nearest_station_distance_km",
                    "london_journey_mins",
                    "nearest_city_journey_mins",
                    "nearest_city_name",
                    "cities_within_60_mins",
                ],
                batch_size=500,
            )

        self.stdout.write(self.style.SUCCESS(f"Scored {scored} outcodes ({len(to_update)} total updated)."))
        self._print_distribution(to_update)

    # ------------------------------------------------------------------
    # Tier helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tier_base(journey):
        """Base score from nearest non-London city journey time (0-100)."""
        if journey is None:
            return 0
        mins = journey.journey_time_mins
        if mins <= 20:
            return 100
        if mins <= 30:
            return 90
        if mins <= 45:
            return 75
        if mins <= 60:
            return 60
        if mins <= 90:
            return 40
        if mins <= 120:
            return 20
        return 5

    @staticmethod
    def _tier_london(journey):
        """London score from journey time to London (0-100)."""
        if journey is None:
            return 0
        mins = journey.journey_time_mins
        if mins <= 60:
            return 100
        if mins <= 90:
            return 85
        if mins <= 120:
            return 70
        if mins <= 150:
            return 50
        if mins <= 180:
            return 30
        return 10

    @staticmethod
    def _tier_multi(count):
        """Multi-city score from cities reachable within 60 mins (0-100)."""
        if count >= 4:
            return 100
        if count == 3:
            return 85
        if count == 2:
            return 65
        if count == 1:
            return 40
        return 0

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def _print_distribution(self, scores):
        """Print score distribution and top/bottom 10."""
        if not scores:
            return

        buckets = {
            "0":     0,
            "1-20":  0,
            "21-40": 0,
            "41-60": 0,
            "61-80": 0,
            "81-100": 0,
        }
        for s in scores:
            v = s.transport_score
            if v == 0:
                buckets["0"] += 1
            elif v <= 20:
                buckets["1-20"] += 1
            elif v <= 40:
                buckets["21-40"] += 1
            elif v <= 60:
                buckets["41-60"] += 1
            elif v <= 80:
                buckets["61-80"] += 1
            else:
                buckets["81-100"] += 1

        self.stdout.write("\nScore distribution:")
        for label, count in buckets.items():
            bar = "#" * min(count, 50)
            self.stdout.write(f"  {label:>7}: {count:>4}  {bar}")

        sorted_scores = sorted(scores, key=lambda s: s.transport_score, reverse=True)
        self.stdout.write("\nTop 10 outcodes:")
        for s in sorted_scores[:10]:
            self.stdout.write(
                f"  {s.postcode_district_id:<8} score={s.transport_score:>3}  "
                f"station={s.nearest_station_name or '?'}  "
                f"london={s.london_journey_mins or '-'}min  "
                f"city={s.nearest_city_name or '-'} {s.nearest_city_journey_mins or '-'}min  "
                f"60m_cities={s.cities_within_60_mins}"
            )

        non_zero = [s for s in sorted_scores if s.transport_score > 0]
        if non_zero:
            self.stdout.write("\nBottom 10 outcodes (non-zero):")
            for s in non_zero[-10:]:
                self.stdout.write(
                    f"  {s.postcode_district_id:<8} score={s.transport_score:>3}  "
                    f"station={s.nearest_station_name or '?'}  "
                    f"london={s.london_journey_mins or '-'}min  "
                    f"city={s.nearest_city_name or '-'} {s.nearest_city_journey_mins or '-'}min  "
                    f"60m_cities={s.cities_within_60_mins}"
                )
