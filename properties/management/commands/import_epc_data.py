"""
Async management command to enrich PropertyTransaction rows with EPC data.

For each outcode:
1. Load transactions into a dict keyed by (normalised_postcode, normalised_paon)
2. Paginate through the EPC API collecting all records for that outcode
3. Deduplicate EPCs: keep most recent lodgement-date per (postcode, address1)
4. Match EPCs to transactions by normalised address and bulk-update
5. Recalculate outcode-level aggregates (avg_floor_area_sqm, avg_price_per_sqm)

Usage:
    python manage.py import_epc_data
    python manage.py import_epc_data --outcode SW1A
    python manage.py import_epc_data --concurrency 15
    python manage.py import_epc_data --resume
    python manage.py import_epc_data --retry-errors
    python manage.py import_epc_data --reset
"""

import asyncio
import io
import csv
import re
import signal
import time
from decimal import Decimal, InvalidOperation

import aiohttp
from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Avg
from django.utils import timezone

from properties.models import (
    EPCImportProgress,
    OutcodePropertyStats,
    OutcodePropertyStatsByType,
    PropertyTransaction,
)

# EPC API base URL
EPC_API_URL = "https://epc.opendatacommunities.org/api/v1/domestic/search"
EPC_PAGE_SIZE = 5000

# Fields we need from EPC CSV response
EPC_FIELDS = {
    "postcode", "address1", "total-floor-area", "number-habitable-rooms",
    "property-type", "built-form", "construction-age-band", "lodgement-date",
}

_NORMALISE_RE = re.compile(r"[^A-Z0-9 ]")
_MULTI_SPACE_RE = re.compile(r"\s+")
_FIRST_NUMBER_RE = re.compile(r"\b(\d+[A-Z]?)\b")


def normalise_address(value: str) -> str:
    """Strip, uppercase, remove punctuation, collapse spaces."""
    s = value.strip().upper()
    s = _NORMALISE_RE.sub(" ", s)
    s = _MULTI_SPACE_RE.sub(" ", s).strip()
    return s


def extract_first_number(value: str) -> str | None:
    """Extract the first number (with optional letter suffix) from a string.

    e.g. "Flat 2, 14A Blythe Way" -> "14A"
         "42 BLYTHE WAY" -> "42"
         "THE OLD SCHOOL" -> None
    """
    # Search on the normalised (uppercased, punctuation-stripped) form
    m = _FIRST_NUMBER_RE.search(normalise_address(value))
    return m.group(1) if m else None


class Command(BaseCommand):
    help = "Enrich PropertyTransaction rows with EPC data via the EPC API."

    def add_arguments(self, parser):
        parser.add_argument(
            "--concurrency",
            type=int,
            default=10,
            help="Max concurrent outcode fetches (default 10, max 20).",
        )
        parser.add_argument(
            "--outcode",
            type=str,
            default=None,
            help="Process a single outcode only (e.g. SW1A).",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip outcodes already marked as complete.",
        )
        parser.add_argument(
            "--retry-errors",
            action="store_true",
            help="Reprocess only outcodes with status=error.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Reset all EPCImportProgress rows to pending.",
        )

    def handle(self, *args, **options):
        if not settings.EPC_API_KEY:
            raise CommandError(
                "EPC_API_KEY not set. Add it to your .env file."
            )

        concurrency = min(options["concurrency"], 20)
        asyncio.run(self._run(
            concurrency=concurrency,
            single_outcode=options["outcode"],
            resume=options["resume"],
            retry_errors=options["retry_errors"],
            reset=options["reset"],
        ))

    async def _run(self, *, concurrency, single_outcode, resume, retry_errors, reset):
        # Graceful shutdown event
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, shutdown_event.set)

        # Reset all progress if requested
        if reset:
            count = await sync_to_async(
                EPCImportProgress.objects.all().update
            )(status="pending", error_message="", records_fetched=0, records_matched=0)
            self.stdout.write(self.style.SUCCESS(f"Reset {count} progress rows to pending."))
            return

        # Determine which outcodes to process
        outcodes = await self._get_outcodes(single_outcode, resume, retry_errors)
        if not outcodes:
            self.stdout.write("No outcodes to process.")
            return

        self.stdout.write(f"Processing {len(outcodes)} outcodes with concurrency={concurrency}")

        # Ensure EPCImportProgress rows exist
        await self._ensure_progress_rows(outcodes)

        semaphore = asyncio.Semaphore(concurrency)
        t0 = time.monotonic()

        auth = aiohttp.BasicAuth(
            login=settings.EPC_API_EMAIL,
            password=settings.EPC_API_KEY,
        )

        async with aiohttp.ClientSession(
            auth=auth,
            headers={"Accept": "text/csv"},
        ) as session:
            tasks = [
                self._process_outcode(session, semaphore, oc, shutdown_event)
                for oc in outcodes
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Count results
        success = sum(1 for r in results if r is True)
        errors = sum(1 for r in results if isinstance(r, Exception) or r is False)
        skipped = len(results) - success - errors

        elapsed = time.monotonic() - t0
        self.stdout.write(self.style.SUCCESS(
            f"Done — {success} complete, {errors} errors, {skipped} skipped "
            f"in {elapsed:.1f}s"
        ))

    async def _get_outcodes(self, single_outcode, resume, retry_errors):
        if single_outcode:
            return [single_outcode.upper()]

        all_outcodes = await sync_to_async(list)(
            PropertyTransaction.objects.values_list("outcode", flat=True).distinct()
        )

        if retry_errors:
            error_outcodes = set(await sync_to_async(list)(
                EPCImportProgress.objects.filter(status="error")
                .values_list("outcode", flat=True)
            ))
            return [oc for oc in all_outcodes if oc in error_outcodes]

        if resume:
            complete_outcodes = set(await sync_to_async(list)(
                EPCImportProgress.objects.filter(status="complete")
                .values_list("outcode", flat=True)
            ))
            return [oc for oc in all_outcodes if oc not in complete_outcodes]

        return all_outcodes

    async def _ensure_progress_rows(self, outcodes):
        existing = set(await sync_to_async(list)(
            EPCImportProgress.objects.values_list("outcode", flat=True)
        ))
        new_rows = [
            EPCImportProgress(outcode=oc, status="pending")
            for oc in outcodes if oc not in existing
        ]
        if new_rows:
            await sync_to_async(
                EPCImportProgress.objects.bulk_create
            )(new_rows, ignore_conflicts=True)

    async def _process_outcode(self, session, semaphore, outcode, shutdown_event):
        """Fetch EPC data for one outcode, match to transactions, and update."""
        async with semaphore:
            if shutdown_event.is_set():
                return None

            try:
                await self._update_progress(outcode, status="in_progress", started_at=timezone.now())
                self.stdout.write(f"  [{outcode}] Starting...")

                # Step 1: Load transactions for this outcode
                txn_dict = await self._load_transactions(outcode)
                if not txn_dict:
                    self.stdout.write(f"  [{outcode}] No transactions found, skipping")
                    await self._update_progress(outcode, status="complete", records_fetched=0, records_matched=0)
                    return True

                # Step 2: Fetch all EPC records for this outcode
                epc_records = await self._fetch_epc_records(session, outcode, shutdown_event)
                if shutdown_event.is_set():
                    await self._update_progress(outcode, status="pending")
                    return None

                # Step 3: Deduplicate EPCs — keep most recent per address
                deduped = self._deduplicate_epcs(epc_records)

                # Step 4: Match and update transactions
                matched_txns = self._match_and_enrich(deduped, txn_dict)

                # Step 5: Bulk update
                if matched_txns:
                    await sync_to_async(PropertyTransaction.objects.bulk_update)(
                        matched_txns,
                        fields=[
                            "total_floor_area_sqm",
                            "price_per_sqm",
                            "property_type_epc",
                            "number_habitable_rooms",
                            "construction_age_band",
                        ],
                        batch_size=5000,
                    )

                # Step 6: Recalculate aggregates for this outcode
                await self._recalculate_aggregates(outcode)

                await self._update_progress(
                    outcode,
                    status="complete",
                    records_fetched=len(epc_records),
                    records_matched=len(matched_txns),
                    completed_at=timezone.now(),
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  [{outcode}] Done — {len(epc_records)} EPC records, "
                    f"{len(matched_txns)} transactions enriched"
                ))
                return True

            except Exception as e:
                await self._update_progress(
                    outcode, status="error", error_message=str(e)[:500]
                )
                self.stderr.write(self.style.ERROR(f"  [{outcode}] Error: {e}"))
                return False

    # ------------------------------------------------------------------
    # Step 1: Load transactions with multi-key lookup
    # ------------------------------------------------------------------

    async def _load_transactions(self, outcode):
        """Load all transactions for an outcode into a multi-key lookup dict.

        Each transaction is indexed under multiple keys so different matching
        strategies can find it:
        - (postcode, normalised_paon)              — exact match
        - (postcode, first_number_from_paon)        — numeric extract
        - (postcode, normalised_saon + " " + normalised_paon) — SAON+PAON combo

        Returns dict: key -> list[PropertyTransaction]
        """
        txns = await sync_to_async(list)(
            PropertyTransaction.objects.filter(outcode=outcode)
        )

        lookup = {}
        for txn in txns:
            norm_pc = normalise_address(txn.postcode)
            norm_paon = normalise_address(txn.paon)
            norm_saon = normalise_address(txn.saon)

            # Strategy 1: exact PAON
            if norm_paon:
                key_exact = (norm_pc, norm_paon)
                lookup.setdefault(key_exact, []).append(txn)

            # Strategy 2: first number extracted from PAON
            paon_num = extract_first_number(txn.paon)
            if paon_num and paon_num != norm_paon:
                key_num = (norm_pc, paon_num)
                lookup.setdefault(key_num, []).append(txn)

            # Strategy 4: SAON + PAON combined
            if norm_saon and norm_paon:
                key_combo = (norm_pc, f"{norm_saon} {norm_paon}")
                lookup.setdefault(key_combo, []).append(txn)

        return lookup

    # ------------------------------------------------------------------
    # Step 2: Fetch EPC records with pagination
    # ------------------------------------------------------------------

    async def _fetch_epc_records(self, session, outcode, shutdown_event):
        """Paginate through the EPC API collecting all records for an outcode."""
        all_records = []
        search_after = None

        while True:
            if shutdown_event.is_set():
                return all_records

            params = {"postcode": outcode, "size": EPC_PAGE_SIZE}
            if search_after:
                params["search-after"] = search_after

            data, next_search_after = await self._fetch_page(session, params)
            all_records.extend(data)

            if not next_search_after or len(data) < EPC_PAGE_SIZE:
                break

            search_after = next_search_after

        return all_records

    async def _fetch_page(self, session, params, retries=3):
        """Fetch a single page from the EPC API with retry logic."""
        for attempt in range(retries):
            try:
                async with session.get(EPC_API_URL, params=params) as resp:
                    if resp.status == 429:
                        wait = 5 * (attempt + 1)
                        self.stderr.write(f"    Rate limited, waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status == 404:
                        # No results for this outcode
                        return [], None

                    resp.raise_for_status()
                    body = await resp.text()
                    next_after = resp.headers.get("X-Next-Search-After")

                    records = self._parse_csv_response(body)
                    return records, next_after

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    self.stderr.write(f"    Retry {attempt + 1}/{retries} after {wait}s: {e}")
                    await asyncio.sleep(wait)
                else:
                    raise

        return [], None

    def _parse_csv_response(self, body):
        """Parse the EPC CSV response into a list of dicts."""
        records = []
        reader = csv.DictReader(io.StringIO(body))
        for row in reader:
            record = {field: row.get(field, "") for field in EPC_FIELDS}
            records.append(record)
        return records

    # ------------------------------------------------------------------
    # Step 3: Deduplicate EPCs
    # ------------------------------------------------------------------

    def _deduplicate_epcs(self, records):
        """Keep only the most recent EPC record per (postcode, address1)."""
        grouped = {}
        for rec in records:
            key = (
                normalise_address(rec.get("postcode", "")),
                normalise_address(rec.get("address1", "")),
            )
            existing = grouped.get(key)
            if existing is None or rec.get("lodgement-date", "") > existing.get("lodgement-date", ""):
                grouped[key] = rec
        return grouped

    # ------------------------------------------------------------------
    # Step 4: Match EPCs to transactions (multi-strategy)
    # ------------------------------------------------------------------

    def _find_transactions(self, norm_pc, epc_address1, txn_dict):
        """Try multiple strategies to match an EPC record to transactions.

        Strategies (tried in order, first hit wins):
        1. Exact: (postcode, normalised_address1) == (postcode, normalised_paon)
        2. Numeric extract: (postcode, first_number_from_address1) == (postcode, first_number_from_paon)
        3. Substring: PAON is a number and appears as a word in ADDRESS1
        4. SAON+PAON combo: (postcode, normalised_address1) == (postcode, saon + " " + paon)
        """
        norm_addr = normalise_address(epc_address1)

        # Strategy 1: exact match on normalised address
        txns = txn_dict.get((norm_pc, norm_addr))
        if txns:
            return txns

        # Strategy 4 (SAON+PAON combo): the combined key may equal norm_addr
        # This is checked via the same lookup since combo keys are in txn_dict
        # (already tried above — combo keys are stored alongside exact keys)

        # Strategy 2: numeric extract from address1
        addr_num = extract_first_number(epc_address1)
        if addr_num:
            txns = txn_dict.get((norm_pc, addr_num))
            if txns:
                return txns

        # Strategy 3: PAON appears as word anywhere in ADDRESS1.
        # Iterate txn_dict keys for this postcode to find substring matches.
        # Only try if norm_addr has content to search within.
        if norm_addr:
            for (pc, paon_key), txns in txn_dict.items():
                if pc != norm_pc:
                    continue
                # Only match numeric PAONs (with optional letter) to avoid
                # false positives from name-based PAONs like "THE OLD SCHOOL"
                if not paon_key or not paon_key[0].isdigit():
                    continue
                # Check PAON appears as a whole word in address1
                if re.search(r'\b' + re.escape(paon_key) + r'\b', norm_addr):
                    return txns

        return None

    def _match_and_enrich(self, deduped_epcs, txn_dict):
        """Match deduplicated EPCs to transactions and enrich fields.

        Uses multi-strategy matching. Tracks already-enriched transaction PKs
        to avoid double-enriching from a lower-priority strategy.

        Returns list of modified PropertyTransaction objects.
        """
        matched = []
        enriched_pks = set()

        for (norm_pc, _norm_addr), epc in deduped_epcs.items():
            raw_addr = epc.get("address1", "")
            txns = self._find_transactions(norm_pc, raw_addr, txn_dict)
            if not txns:
                continue

            # Parse EPC fields
            try:
                floor_area = Decimal(epc.get("total-floor-area", ""))
            except (InvalidOperation, ValueError):
                continue

            if floor_area <= 0:
                continue

            try:
                num_rooms = int(epc.get("number-habitable-rooms", "") or 0)
            except (ValueError, TypeError):
                num_rooms = None

            prop_type = epc.get("property-type", "").strip()
            built_form = epc.get("built-form", "").strip()
            property_type_epc = f"{prop_type} {built_form}".strip() if prop_type else None

            construction_age = epc.get("construction-age-band", "").strip() or None

            for txn in txns:
                if txn.transaction_id in enriched_pks:
                    continue
                enriched_pks.add(txn.transaction_id)
                txn.total_floor_area_sqm = floor_area
                txn.price_per_sqm = Decimal(txn.price) / floor_area
                txn.property_type_epc = property_type_epc
                txn.number_habitable_rooms = num_rooms if num_rooms else None
                txn.construction_age_band = construction_age
                matched.append(txn)

        return matched

    # ------------------------------------------------------------------
    # Step 6: Recalculate aggregates for a single outcode
    # ------------------------------------------------------------------

    async def _recalculate_aggregates(self, outcode):
        """Update avg_floor_area_sqm and avg_price_per_sqm for one outcode."""
        await self._update_outcode_stats(outcode)
        await self._update_outcode_stats_by_type(outcode)

    async def _update_outcode_stats(self, outcode):
        agg = await sync_to_async(
            lambda: PropertyTransaction.objects.filter(outcode=outcode).aggregate(
                avg_floor_area_sqm=Avg("total_floor_area_sqm"),
                avg_price_per_sqm=Avg("price_per_sqm"),
            )
        )()

        await sync_to_async(
            lambda: OutcodePropertyStats.objects.filter(outcode=outcode).update(
                avg_floor_area_sqm=agg["avg_floor_area_sqm"],
                avg_price_per_sqm=agg["avg_price_per_sqm"],
            )
        )()

    async def _update_outcode_stats_by_type(self, outcode):
        type_aggs = await sync_to_async(list)(
            PropertyTransaction.objects
            .filter(outcode=outcode)
            .values("property_type")
            .annotate(
                avg_floor_area_sqm=Avg("total_floor_area_sqm"),
                avg_price_per_sqm=Avg("price_per_sqm"),
            )
        )

        for agg in type_aggs:
            await sync_to_async(
                lambda a=agg: OutcodePropertyStatsByType.objects.filter(
                    outcode=outcode, property_type=a["property_type"]
                ).update(
                    avg_floor_area_sqm=a["avg_floor_area_sqm"],
                    avg_price_per_sqm=a["avg_price_per_sqm"],
                )
            )()

    # ------------------------------------------------------------------
    # Progress tracking
    # ------------------------------------------------------------------

    async def _update_progress(self, outcode, **kwargs):
        await sync_to_async(
            lambda: EPCImportProgress.objects.update_or_create(
                outcode=outcode,
                defaults=kwargs,
            )
        )()
