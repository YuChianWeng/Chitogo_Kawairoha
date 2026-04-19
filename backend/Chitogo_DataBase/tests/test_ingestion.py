import unittest

from app.models.place import Place
from app.models.place_features import PlaceFeatures
from app.models.place_source_google import PlaceSourceGoogle
from app.services.ingestion import ingest_google_place, normalize_district_name


def _payload_for_district(google_place_id: str, district_name: str) -> dict:
    return {
        "id": google_place_id,
        "displayName": {"text": f"Test Place {google_place_id}"},
        "primaryType": "tourist_attraction",
        "types": ["tourist_attraction", "point_of_interest"],
        "formattedAddress": f"Taipei {district_name}",
        "addressComponents": [
            {
                "longText": district_name,
                "types": ["administrative_area_level_2", "political"],
            }
        ],
        "location": {"latitude": 25.0, "longitude": 121.5},
    }


class FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters = kwargs
        return self

    def first(self):
        if self.model is Place:
            google_place_id = self.filters.get("google_place_id")
            for place in self.session.places:
                if place.google_place_id == google_place_id:
                    return place
            return None

        if self.model is PlaceFeatures:
            place_id = self.filters.get("place_id")
            for feature in self.session.features:
                if feature.place_id == place_id:
                    return feature
            return None

        raise AssertionError(f"Unexpected model queried: {self.model}")


class FakeSession:
    def __init__(self):
        self.places = []
        self.raw_records = []
        self.features = []
        self._next_place_id = 1

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, obj):
        if isinstance(obj, Place):
            if obj not in self.places:
                self.places.append(obj)
            return
        if isinstance(obj, PlaceSourceGoogle):
            self.raw_records.append(obj)
            return
        if isinstance(obj, PlaceFeatures):
            if obj not in self.features:
                self.features.append(obj)
            return
        raise AssertionError(f"Unexpected object added: {obj!r}")

    def flush(self):
        for place in self.places:
            if place.id is None:
                place.id = self._next_place_id
                self._next_place_id += 1

    def commit(self):
        return None

    def refresh(self, _obj):
        return None


class NormalizeDistrictNameTests(unittest.TestCase):
    def test_daan_variants_normalize_to_big5_name(self):
        self.assertEqual(normalize_district_name("Da’an District"), "大安區")
        self.assertEqual(normalize_district_name("Da'an District"), "大安區")
        self.assertEqual(normalize_district_name("Daan District"), "大安區")


class IngestGooglePlaceTests(unittest.TestCase):
    def test_valid_taipei_district_is_inserted_with_chinese_name(self):
        session = FakeSession()

        result = ingest_google_place(
            session,
            _payload_for_district("place-valid", "Zhongzheng District"),
        )

        self.assertEqual(result["action"], "created")
        self.assertEqual(len(session.places), 1)
        self.assertEqual(session.places[0].district, "中正區")
        self.assertEqual(session.places[0].internal_category, "attraction")
        self.assertEqual(len(session.raw_records), 1)
        self.assertEqual(session.raw_records[0].place_id, session.places[0].id)

    def test_non_taipei_district_is_not_inserted(self):
        session = FakeSession()

        result = ingest_google_place(
            session,
            _payload_for_district("place-yonghe", "Yonghe District"),
        )

        self.assertEqual(result["action"], "filtered_out")
        self.assertIsNone(result["place_id"])
        self.assertEqual(len(session.places), 0)
        self.assertEqual(len(session.raw_records), 1)
        self.assertIsNone(session.raw_records[0].place_id)

    def test_unknown_district_is_not_inserted(self):
        session = FakeSession()

        result = ingest_google_place(
            session,
            _payload_for_district("place-unknown", "Unknown District"),
        )

        self.assertEqual(result["action"], "filtered_out")
        self.assertEqual(len(session.places), 0)
        self.assertEqual(len(session.raw_records), 1)

    def test_missing_district_is_not_inserted(self):
        session = FakeSession()
        payload = _payload_for_district("place-missing", "Ignored")
        payload["addressComponents"] = []

        result = ingest_google_place(session, payload)

        self.assertEqual(result["action"], "filtered_out")
        self.assertEqual(len(session.places), 0)
        self.assertEqual(len(session.raw_records), 1)

    def test_reimport_updates_existing_place_without_duplication(self):
        session = FakeSession()
        first_payload = _payload_for_district("place-repeat", "Da’an District")
        second_payload = _payload_for_district("place-repeat", "Daan District")
        second_payload["displayName"] = {"text": "Updated Test Place"}
        second_payload["primaryType"] = None
        second_payload["types"] = ["shopping_mall", "point_of_interest"]

        first_result = ingest_google_place(session, first_payload)
        second_result = ingest_google_place(session, second_payload)

        self.assertEqual(first_result["action"], "created")
        self.assertEqual(second_result["action"], "updated")
        self.assertEqual(len(session.places), 1)
        self.assertEqual(session.places[0].district, "大安區")
        self.assertEqual(session.places[0].display_name, "Updated Test Place")
        self.assertEqual(session.places[0].internal_category, "shopping")
        self.assertEqual(len(session.raw_records), 2)

    def test_ingest_uses_other_when_type_mapping_is_unknown(self):
        session = FakeSession()
        payload = _payload_for_district("place-other", "Zhongzheng District")
        payload["primaryType"] = "unknown_type"
        payload["types"] = ["still_unknown"]

        result = ingest_google_place(session, payload)

        self.assertEqual(result["action"], "created")
        self.assertEqual(session.places[0].internal_category, "other")

    def test_ingest_uses_regular_opening_hours(self):
        session = FakeSession()
        payload = _payload_for_district("place-hours", "Zhongzheng District")
        payload["regularOpeningHours"] = {"periods": [{"open": {"day": 1, "hour": 9}}]}
        payload["currentOpeningHours"] = {"periods": [{"open": {"day": 2, "hour": 10}}]}

        result = ingest_google_place(session, payload)

        self.assertEqual(result["action"], "created")
        self.assertEqual(
            session.places[0].opening_hours_json,
            payload["regularOpeningHours"],
        )


if __name__ == "__main__":
    unittest.main()
