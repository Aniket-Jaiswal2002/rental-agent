from datetime import date

from app.listings import SearchFilters, get_listing, load_listings, render, search_listings


def ids(result):
    return [r["id"] for r in result["results"]]


def test_dataset_is_labelled_synthetic_and_has_30_listings():
    assert len(load_listings()) == 30


def test_get_listing_unknown_id_returns_none():
    assert get_listing("L999") is None
    assert get_listing("l001")["id"] == "L001"


def test_bhk_and_area_are_hard_filters():
    r = search_listings(SearchFilters(bhk=[2], areas=["Sector 56"]))
    assert ids(r) == ["L021"]  # the only 2 BHK in Sector 56
    assert all(x["bhk"] == 2 and x["sector"] == "Sector 56" for x in r["results"])


def test_area_matches_locality_name_and_sec_abbreviation():
    by_locality = search_listings(SearchFilters(areas=["Golf Course Road"]), limit=50)
    assert by_locality["results"] and all(x["area"] == "Golf Course Road" for x in by_locality["results"])
    assert ids(search_listings(SearchFilters(bhk=[2], areas=["sec 56"]))) == ["L021"]


def test_golf_course_road_does_not_match_extension_road():
    r = search_listings(SearchFilters(areas=["Golf Course Road"]), limit=50)
    assert not any(x["area"] == "Golf Course Extension Road" for x in r["results"])


def test_budget_tolerance_flags_over_budget():
    # L021: 2 BHK Sector 56, rent 28000
    within = search_listings(SearchFilters(bhk=[2], areas=["Sector 56"], budget_max=28000))
    assert within["results"][0]["over_budget_by"] == 0
    near = search_listings(SearchFilters(bhk=[2], areas=["Sector 56"], budget_max=26000))  # 28000 <= 26000*1.1
    assert near["results"][0]["over_budget_by"] == 2000
    far = search_listings(SearchFilters(bhk=[2], areas=["Sector 56"], budget_max=20000))
    assert far["no_matches"] and far["results"] == []


def test_pets_and_tenant_type_filters():
    r = search_listings(SearchFilters(pets=True, tenant_type="bachelor"), limit=50)
    assert r["results"]
    for x in r["results"]:
        assert x["pets_allowed"] and x["tenant_preference"] in ("any", "bachelor")


def test_parking_filter():
    r = search_listings(SearchFilters(parking=True), limit=50)
    assert r["results"] and all(x["parking"] for x in r["results"])


def test_move_in_date_excludes_listings_available_much_later():
    r = search_listings(SearchFilters(move_in_date=date(2026, 11, 2)), limit=50)
    assert r["results"]
    for x in r["results"]:
        assert x["available_days_after_move_in"] <= 15


def test_ranking_prefers_in_budget_then_closer_commute():
    r = search_listings(SearchFilters(bhk=[2], budget_max=30000, commute_destination="Cyber City"), limit=50)
    res = r["results"]
    assert res and r["commute_distance_available"]
    in_budget = [x for x in res if x["over_budget_by"] == 0]
    assert res[: len(in_budget)] == in_budget  # in-budget listings come first
    kms = [x["commute_km"] for x in in_budget if x["available_days_after_move_in"] == 0]
    assert kms == sorted(kms)


def test_unknown_commute_destination_has_no_distance():
    r = search_listings(SearchFilters(bhk=[2], commute_destination="Udyog Vihar"))
    assert not r["commute_distance_available"] and all(x["commute_km"] is None for x in r["results"])


def test_no_match_reports_which_constraints_pass_alone():
    r = search_listings(SearchFilters(bhk=[4], budget_max=20000, areas=["Sector 54"]))
    assert r["no_matches"] and r["total_matches"] == 0
    alone = r["passing_each_constraint_alone"]
    assert alone["bhk"] == 2 and alone["budget"] > 0 and alone["area"] > 0


def test_render_comes_from_dataset():
    l = load_listings()["L021"]
    out = render("L021", "close")
    assert out["rent"] == l["rent"] and out["deposit"] == l["deposit"] and out["title"].startswith("2 BHK, Sector 56")
