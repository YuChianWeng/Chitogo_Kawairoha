import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request


GOOGLE_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
DEFAULT_DATA_SERVICE_BASE = "http://localhost:8800"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "google_seed_targets.json"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.primaryType",
        "places.types",
        "places.formattedAddress",
        "places.addressComponents",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.businessStatus",
        "places.googleMapsUri",
        "places.websiteUri",
        "places.nationalPhoneNumber",
        "places.regularOpeningHours",
    ]
)


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> tuple[int, dict]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )

    try:
        with request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw_body}
        return exc.code, parsed
    except error.URLError as exc:
        return 0, {"error": str(exc)}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect Taipei Google Places POIs and import them into the local data service."
    )
    parser.add_argument(
        "--district",
        help="Run only one configured Taipei district.",
    )
    parser.add_argument(
        "--include-secondary-transport",
        action="store_true",
        help="Include lower-priority transport queries such as bus stations.",
    )
    return parser.parse_args()


def _load_config() -> dict:
    if not CONFIG_PATH.is_file():
        print(f"Missing config file: {CONFIG_PATH}", file=sys.stderr)
        raise SystemExit(1)

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    if not isinstance(config, dict):
        print(f"Invalid config format in {CONFIG_PATH}: expected an object", file=sys.stderr)
        raise SystemExit(1)

    type_groups = config.get("poi_type_groups")
    districts = config.get("districts")
    if not isinstance(type_groups, list) or not isinstance(districts, list):
        print(
            f"Invalid config format in {CONFIG_PATH}: expected poi_type_groups[] and districts[]",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return config


def _select_districts(districts: list[dict], district: str | None) -> list[dict]:
    if district is None:
        return districts

    for target in districts:
        if target.get("district") == district:
            return [target]

    known_districts = ", ".join(target.get("district", "<missing>") for target in districts)
    print(
        f"Unknown district: {district}. Configured districts: {known_districts}",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _build_nearby_request(seed_point: dict, included_type: str) -> dict:
    return _build_nearby_request_for_mode(seed_point, included_type, "includedTypes")


def _build_nearby_request_for_mode(seed_point: dict, place_type: str, query_mode: str) -> dict:
    center = seed_point.get("center", {})
    request_payload = {
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": center.get("latitude"),
                    "longitude": center.get("longitude"),
                },
                "radius": float(seed_point.get("radius", 1200)),
            }
        },
    }
    request_payload[query_mode] = [place_type]
    return request_payload


def _enabled_type_groups(
    type_groups: list[dict], include_secondary_transport: bool
) -> list[dict]:
    enabled_groups = []
    for group in type_groups:
        if group.get("enabledByDefault", True):
            enabled_groups.append(group)
            continue
        if include_secondary_transport:
            enabled_groups.append(group)
    return enabled_groups


def _resolve_group_query_specs(group: dict) -> list[tuple[str, str]]:
    query_specs: list[tuple[str, str]] = []

    for place_type in group.get("includedTypes", []):
        query_specs.append(("includedTypes", place_type))

    for place_type in group.get("includedPrimaryTypes", []):
        query_specs.append(("includedPrimaryTypes", place_type))

    return query_specs


def _new_stats() -> dict[str, int]:
    return {
        "queries": 0,
        "google_returned": 0,
        "imported": 0,
        "skipped_non_taipei": 0,
        "failed": 0,
    }


def _merge_stats(total: dict[str, int], delta: dict[str, int]) -> None:
    for key, value in delta.items():
        total[key] += value


def _import_place(import_url: str, district: str, type_group: str, place_type: str, place: dict) -> dict[str, int]:
    import_status, import_response = _post_json(import_url, {"payload": place}, headers={})
    if import_status != 200:
        place_id = place.get("id", "<missing id>")
        print(
            f"[{district}] group={type_group} type={place_type} import failed "
            f"for {place_id} ({import_status}): {json.dumps(import_response, ensure_ascii=False)}"
        )
        return {"queries": 0, "google_returned": 0, "imported": 0, "skipped_non_taipei": 0, "failed": 1}

    action = import_response.get("action")
    if action in {"created", "updated"}:
        return {"queries": 0, "google_returned": 0, "imported": 1, "skipped_non_taipei": 0, "failed": 0}
    if action == "filtered_out":
        return {"queries": 0, "google_returned": 0, "imported": 0, "skipped_non_taipei": 1, "failed": 0}
    return {"queries": 0, "google_returned": 0, "imported": 0, "skipped_non_taipei": 0, "failed": 0}


def _run_type_query(
    api_key: str,
    import_url: str,
    district: str,
    seed_point: dict,
    type_group_name: str,
    query_mode: str,
    place_type: str,
) -> tuple[bool, dict[str, int]]:
    request_payload = _build_nearby_request_for_mode(seed_point, place_type, query_mode)
    stats = _new_stats()
    stats["queries"] = 1

    status, response = _post_json(
        GOOGLE_NEARBY_URL,
        request_payload,
        headers={
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )
    if status != 200:
        print(
            f"[{district}] seed={seed_point.get('name', '<unnamed>')} group={type_group_name} "
            f"mode={query_mode} type={place_type} Google API error ({status}): "
            f"{json.dumps(response, ensure_ascii=False)}",
            file=sys.stderr,
        )
        stats["failed"] += 1
        return False, stats

    places = response.get("places", [])
    stats["google_returned"] = len(places)
    for place in places:
        _merge_stats(
            stats,
            _import_place(import_url, district, type_group_name, place_type, place),
        )

    print(
        f"[{district}] seed={seed_point.get('name', '<unnamed>')} group={type_group_name} "
        f"mode={query_mode} type={place_type} google_returned={len(places)} "
        f"imported={stats['imported']} "
        f"skipped_non_taipei={stats['skipped_non_taipei']} failed={stats['failed']}"
    )
    return True, stats


def _run_district(target: dict, type_groups: list[dict], api_key: str, import_url: str) -> tuple[bool, dict[str, int]]:
    district = target.get("district", "<missing district>")
    seed_points = target.get("seed_points", [])
    district_stats = _new_stats()
    ok = True

    print(f"[{district}] starting seed_points={len(seed_points)} type_groups={len(type_groups)}")

    for group in type_groups:
        group_name = group.get("name", "<unnamed>")
        query_specs = _resolve_group_query_specs(group)
        seed_point_limit = group.get("seedPointLimit")
        active_seed_points = seed_points[:seed_point_limit] if isinstance(seed_point_limit, int) else seed_points
        group_stats = _new_stats()

        for seed_point in active_seed_points:
            for query_mode, place_type in query_specs:
                query_ok, query_stats = _run_type_query(
                    api_key=api_key,
                    import_url=import_url,
                    district=district,
                    seed_point=seed_point,
                    type_group_name=group_name,
                    query_mode=query_mode,
                    place_type=place_type,
                )
                if not query_ok:
                    ok = False
                _merge_stats(group_stats, query_stats)
                _merge_stats(district_stats, query_stats)

        print(
            f"[{district}] group={group_name} seed_points={len(active_seed_points)} "
            f"queries_spec={query_specs} "
            f"queries={group_stats['queries']} google_returned={group_stats['google_returned']} "
            f"imported={group_stats['imported']} skipped_non_taipei={group_stats['skipped_non_taipei']} "
            f"failed={group_stats['failed']}"
        )

    print(
        f"[{district}] complete seed_points={len(seed_points)} queries={district_stats['queries']} "
        f"google_returned={district_stats['google_returned']} imported={district_stats['imported']} "
        f"skipped_non_taipei={district_stats['skipped_non_taipei']} failed={district_stats['failed']}"
    )
    return ok, district_stats


def main() -> int:
    args = _parse_args()
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Missing required environment variable: GOOGLE_MAPS_API_KEY", file=sys.stderr)
        return 1

    config = _load_config()
    type_groups = _enabled_type_groups(
        config["poi_type_groups"],
        include_secondary_transport=args.include_secondary_transport,
    )
    districts = _select_districts(config["districts"], args.district)
    data_service_base = os.getenv("DATA_SERVICE_BASE", DEFAULT_DATA_SERVICE_BASE).rstrip("/")
    import_url = f"{data_service_base}/api/v1/places/import/google"

    all_ok = True
    total_stats = _new_stats()

    for target in districts:
        ok, district_stats = _run_district(target, type_groups, api_key, import_url)
        if not ok:
            all_ok = False
        _merge_stats(total_stats, district_stats)

    print(
        "[summary] "
        f"districts={len(districts)} "
        f"type_groups={len(type_groups)} "
        f"queries={total_stats['queries']} "
        f"google_returned={total_stats['google_returned']} "
        f"imported={total_stats['imported']} "
        f"skipped_non_taipei={total_stats['skipped_non_taipei']} "
        f"failed={total_stats['failed']}"
    )

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
