"""Generate data/listings.json: 30 SYNTHETIC Gurugram rental listings.

Everything here is made up (seeded RNG). Sector/locality names are real places,
but prices, distances, availability and descriptions are fabricated for a demo.

    python scripts/gen_listings.py
"""
import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42
AS_OF = date(2026, 11, 2)  # availability dates are generated relative to this

# (sector, locality, km to Cyber City, km to Golf Course Road, price tier)
LOCALITIES = [
    ("Sector 54", "Golf Course Road", 5.5, 0.8, "high"),
    ("Sector 42", "Golf Course Road", 7.5, 1.2, "high"),
    ("Sector 43", "Golf Course Road", 6.8, 1.5, "high"),
    ("Sector 56", "Golf Course Extension Road", 9.0, 2.5, "mid"),
    ("Sector 57", "Golf Course Extension Road", 10.5, 4.0, "mid"),
    ("Sector 65", "Golf Course Extension Road", 12.5, 4.0, "mid"),
    ("Sector 67", "Golf Course Extension Road", 14.0, 5.5, "low"),
    ("Sector 49", "Sohna Road", 12.0, 4.5, "mid"),
    ("Sector 109", "Dwarka Expressway", 15.5, 11.0, "low"),
    ("DLF Phase 2", "DLF Phase 2", 2.5, 6.5, "premium"),
    ("DLF Phase 3", "DLF Phase 3", 3.5, 6.0, "premium"),
    ("DLF Phase 4", "DLF Phase 4", 4.5, 5.5, "high"),
    ("Sushant Lok 1", "Sushant Lok", 7.0, 4.5, "mid"),
    ("Sector 14", "Old Gurgaon", 9.5, 9.0, "low"),
    ("Sector 45", "Sector 45", 7.5, 4.0, "mid"),
]

BASE_RENT = {  # tier -> {bhk: monthly rent for a semi-furnished flat}
    "low": {1: 14000, 2: 22000, 3: 32000, 4: 55000},
    "mid": {1: 19000, 2: 32000, 3: 48000, 4: 80000},
    "high": {1: 28000, 2: 48000, 3: 70000, 4: 115000},
    "premium": {1: 38000, 2: 62000, 3: 95000, 4: 150000},
}
FURN_FACTOR = {"unfurnished": 0.9, "semi-furnished": 1.0, "fully-furnished": 1.15}

PET_YES = ["pets ok", "dog friendly society", "pets allowed (small dog ok)", "pet friendly"]
PET_NO = ["no pets pls", "NO PETS", "pets not allowed"]
TENANT_TEXT = {
    "family": ["family only", "only family pref", "family tenants preferred, no bachelors"],
    "bachelor": ["bachelors welcome", "working prof / bachelors ok", "bachelor ok no issue"],
    "any": ["family/bachelor both ok", "anyone decent will do", "bachelors n family both"],
}
PARK_YES = ["1 covered parking", "parking available", "stilt parking incl", "2 car parking"]
PARK_NO = ["no parking, street only", "parking nahi hai", "parking not available"]
FURN_TEXT = {
    "unfurnished": ["unfurnished, only wardrobes n kitchen cabinets", "bare shell, only light fittings"],
    "semi-furnished": ["semi furnished - wardrobes, geysers, chimney", "semi furnished with modular kitchen"],
    "fully-furnished": ["fully furnished, AC in all rooms, bed sofa fridge washing machine", "FULLY FURNISHED ready 2 move, AC + TV + fridge"],
}
OPENERS = [
    "Spacious {bhk}bhk in {sector} {area}.",
    "{bhk}BHK FLAT AVAILABLE {sector}!!",
    "Ready 2 move {bhk} bhk, {sector}.",
    "Owner direct, no brokrage*, {bhk}BHK {sector}",
    "Newly painted {bhk} bhk flat {area} side.",
]
EXTRAS = [
    "{floor} floor, lift + power backup",
    "gated society, 24x7 guard",
    "near market n metro feeder",
    "vastu compliant, east facing",
    "nego a little for long tenure",
    "society has gym n pool",
    "pls call b/w 10-7 only",
    "water 24x7",
    "park facing balcony",
    "khula hawadar flat, lots of sunlight",
    "tenant should be ready for 11 month agreement",
    "maintenance extra",
]


def round_to(x: float, step: int) -> int:
    return int(round(x / step) * step)


def messy(rng: random.Random, text: str) -> str:
    if rng.random() < 0.2:
        text = text.upper()
    if rng.random() < 0.3:
        text = text.replace(", ", " ,").replace(".", "..")
    if rng.random() < 0.25:
        text = text.replace("and", "n").replace("with", "wd")
    return text


def make_listing(rng: random.Random, idx: int, loc: tuple, bhk: int) -> dict:
    sector, area, d_cc, d_gcr, tier = loc
    furnishing = rng.choices(list(FURN_FACTOR), weights=[3, 4, 3])[0]
    rent = round_to(BASE_RENT[tier][bhk] * FURN_FACTOR[furnishing] * rng.uniform(0.92, 1.08), 500)
    deposit = rent * rng.choice([1, 2, 2, 3])
    pets = rng.random() < 0.3
    tenant = rng.choices(["family", "bachelor", "any"], weights=[4, 2, 4])[0]
    parking = rng.random() < (0.85 if bhk >= 3 else 0.6)
    available = AS_OF + timedelta(days=rng.choice([0, 3, 7, 14, 21, 30, 45, 60, 75]))

    parts = [
        rng.choice(OPENERS).format(bhk=bhk, sector=sector, area=area),
        rng.choice(FURN_TEXT[furnishing]),
        rng.choice(PET_YES if pets else PET_NO),
        rng.choice(TENANT_TEXT[tenant]),
        rng.choice(PARK_YES if parking else PARK_NO),
    ]
    parts += rng.sample(EXTRAS, 2)
    parts = [p.format(floor=rng.choice(["2nd", "3rd", "5th", "7th", "ground"])) for p in parts]
    description = messy(rng, " | ".join(parts))

    return {
        "id": f"L{idx:03d}",
        "sector": sector,
        "area": area,
        "bhk": bhk,
        "rent": rent,
        "deposit": deposit,
        "furnishing": furnishing,
        "available_from": available.isoformat(),
        "pets_allowed": pets,
        "tenant_preference": tenant,
        "parking": parking,
        "description": description,
        "distance_cyber_city_km": round(max(0.3, d_cc + rng.uniform(-0.6, 0.6)), 1),
        "distance_golf_course_road_km": round(max(0.3, d_gcr + rng.uniform(-0.6, 0.6)), 1),
    }


def main() -> None:
    rng = random.Random(SEED)
    bhks = [1] * 7 + [2] * 13 + [3] * 8 + [4] * 2
    rng.shuffle(bhks)
    locs = LOCALITIES + rng.sample(LOCALITIES, 30 - len(LOCALITIES))
    rng.shuffle(locs)
    listings = [make_listing(rng, i + 1, loc, bhk) for i, (loc, bhk) in enumerate(zip(locs, bhks))]
    out = {
        "SYNTHETIC": True,
        "disclaimer": (
            "SYNTHETIC DATA: every listing below is fabricated for a portfolio demo. "
            "Prices, distances, availability and descriptions do not describe real properties."
        ),
        "as_of": AS_OF.isoformat(),
        "listings": listings,
    }
    path = Path(__file__).resolve().parent.parent / "data" / "listings.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(listings)} listings to {path}")


if __name__ == "__main__":
    main()
