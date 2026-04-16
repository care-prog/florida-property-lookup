import re
import requests
import json
from typing import Optional


# Free US Census Geocoder
GEOCODE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# Free Florida Statewide Cadastral (all 67 counties, 10.8M+ parcels)
CADASTRAL_URL = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query"

OUT_FIELDS = ",".join([
    "OWN_NAME", "OWN_ADDR1", "OWN_ADDR2", "OWN_CITY", "OWN_STATE", "OWN_ZIPCD",
    "FIDU_NAME", "FIDU_ADDR1", "FIDU_ADDR2", "FIDU_CITY", "FIDU_STATE", "FIDU_ZIPCD",
    "PHY_ADDR1", "PHY_ADDR2", "PHY_CITY", "PHY_ZIPCD",
    "JV", "AV_SD", "AV_NSD", "TV_SD", "TV_NSD", "LND_VAL",
    "JV_HMSTD", "AV_HMSTD",
    "SALE_PRC1", "SALE_YR1", "SALE_MO1", "OR_BOOK1", "OR_PAGE1", "QUAL_CD1",
    "SALE_PRC2", "SALE_YR2", "SALE_MO2", "OR_BOOK2", "OR_PAGE2", "QUAL_CD2",
    "ACT_YR_BLT", "EFF_YR_BLT", "TOT_LVG_AR", "LND_SQFOOT",
    "NO_BULDNG", "NO_RES_UNT", "DOR_UC", "PA_UC",
    "PARCEL_ID", "PARCELNO", "CO_NO", "S_LEGAL",
    "IMP_QUAL", "CONST_CLAS", "SPEC_FEAT_",
    "NCONST_VAL", "DEL_VAL",
    "TAX_AUTH_C", "NBRHD_CD", "SPASS_CD",
])

# Florida DOR land use codes
LAND_USE_CODES = {
    "000": "Vacant Residential", "001": "Single Family", "002": "Mobile Home",
    "003": "Multifamily (2-9)", "004": "Condominium", "005": "Cooperatives",
    "006": "Retirement Homes", "007": "Misc Residential", "008": "Multifamily (10+)",
    "009": "Undefined Residential", "010": "Vacant Commercial", "011": "Stores",
    "012": "Mixed Use (Store+Office)", "014": "Supermarket", "016": "Community Shopping",
    "017": "Office (1-story)", "018": "Office (Multi-story)", "019": "Medical Office",
    "020": "Airport/Marina", "021": "Restaurant/Cafeteria", "022": "Drive-in Restaurant",
    "023": "Financial Institution", "024": "Insurance Company", "026": "Service Station",
    "027": "Auto Sales/Repair", "028": "Parking Lot", "029": "Wholesale/Manufacturing",
    "030": "Florist/Greenhouse", "033": "Night Club/Bar", "034": "Bowling/Skating",
    "035": "Tourist Attraction", "038": "Golf Course", "039": "Hotel/Motel",
    "040": "Vacant Industrial", "041": "Light Manufacturing", "042": "Heavy Manufacturing",
    "048": "Warehouse", "049": "Open Storage",
    "050": "Vacant Agricultural", "051": "Cropland", "052": "Timberland",
    "060": "Grazing Land", "070": "Vacant Institutional", "071": "Church",
    "072": "Private School", "073": "Private Hospital", "080": "Undefined",
    "086": "County - Other", "089": "Municipal - Other",
}


def extract_street_number(address: str) -> str:
    """Extract the street number from an address string."""
    match = re.match(r"(\d+)", address.strip())
    return match.group(1) if match else ""


def geocode_address(address: str) -> Optional[dict]:
    """Convert address to lat/lon using free US Census geocoder."""
    try:
        r = requests.get(GEOCODE_URL, params={
            "address": address,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }, timeout=15)
        matches = r.json().get("result", {}).get("addressMatches", [])
        if matches:
            coords = matches[0]["coordinates"]
            return {
                "lat": coords["y"],
                "lon": coords["x"],
                "matched_address": matches[0].get("matchedAddress", address),
            }
    except Exception:
        pass
    return None


def query_cadastral(lat: float, lon: float) -> list:
    """Spatial query on Florida Cadastral layer by lat/lon."""
    buffer = 0.0003
    envelope = {
        "xmin": lon - buffer,
        "ymin": lat - buffer,
        "xmax": lon + buffer,
        "ymax": lat + buffer,
        "spatialReference": {"wkid": 4326},
    }
    try:
        r = requests.post(CADASTRAL_URL, data={
            "geometry": json.dumps(envelope),
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326",
            "outFields": OUT_FIELDS,
            "f": "json",
            "returnGeometry": "false",
        }, timeout=30)
        data = r.json()
        return data.get("features", [])
    except Exception:
        return []


def find_best_match(features: list, input_address: str) -> list:
    """Filter features to find the exact address match."""
    input_num = extract_street_number(input_address)
    if not input_num:
        return features

    # Filter out REFERENCE ONLY
    real = [f for f in features if (f["attributes"].get("OWN_NAME") or "").strip() != "REFERENCE ONLY"]
    if not real:
        real = features

    # Match by street number
    exact = [f for f in real if extract_street_number(f["attributes"].get("PHY_ADDR1", "")) == input_num]
    if exact:
        return exact

    return real[:1]


def fmt(val, default="N/A"):
    """Format a value, treating 0, None, and whitespace as N/A."""
    if val is None:
        return default
    if isinstance(val, str) and val.strip() == "":
        return default
    if isinstance(val, (int, float)) and val == 0:
        return default
    return val


def format_mailing(attrs: dict, prefix: str) -> str:
    """Format a mailing address from fields with given prefix."""
    parts = [
        str(fmt(attrs.get(f"{prefix}_ADDR1"), "")),
        str(fmt(attrs.get(f"{prefix}_ADDR2"), "")),
        str(fmt(attrs.get(f"{prefix}_CITY"), "")),
        str(fmt(attrs.get(f"{prefix}_STATE"), "")),
    ]
    zipcd = attrs.get(f"{prefix}_ZIPCD")
    if zipcd and str(zipcd).strip() and str(zipcd).strip() != "0":
        parts.append(str(int(float(str(zipcd)))) if isinstance(zipcd, (int, float)) else str(zipcd))
    return ", ".join(p for p in parts if p) or "N/A"


def format_property(attrs: dict) -> dict:
    """Format raw cadastral attributes into clean result dict."""
    sale1_date = ""
    if fmt(attrs.get("SALE_YR1")) != "N/A":
        mo = str(fmt(attrs.get("SALE_MO1"), "")).strip()
        yr = int(attrs.get("SALE_YR1", 0))
        sale1_date = f"{mo}/{yr}" if mo else str(yr)

    sale2_date = ""
    if fmt(attrs.get("SALE_YR2")) != "N/A":
        mo = str(fmt(attrs.get("SALE_MO2"), "")).strip()
        yr = int(attrs.get("SALE_YR2", 0))
        sale2_date = f"{mo}/{yr}" if mo else str(yr)

    land_use_code = str(fmt(attrs.get("DOR_UC"), "")).strip()
    land_use_desc = LAND_USE_CODES.get(land_use_code, land_use_code)

    homestead = fmt(attrs.get("JV_HMSTD")) != "N/A" and attrs.get("JV_HMSTD", 0) > 0

    return {
        # Owner
        "owner_name": fmt(attrs.get("OWN_NAME")),
        "owner_mailing": format_mailing(attrs, "OWN"),
        "fiduciary_name": fmt(attrs.get("FIDU_NAME")),
        "fiduciary_mailing": format_mailing(attrs, "FIDU") if fmt(attrs.get("FIDU_NAME")) != "N/A" else "N/A",
        "homestead": homestead,
        # Property
        "address": f"{fmt(attrs.get('PHY_ADDR1'), '')}, {fmt(attrs.get('PHY_CITY'), '')} {fmt(attrs.get('PHY_ZIPCD'), '')}".strip(", "),
        "parcel_id": fmt(attrs.get("PARCEL_ID")),
        "parcelno": fmt(attrs.get("PARCELNO")),
        "legal_desc": fmt(attrs.get("S_LEGAL")),
        "land_use_code": land_use_code,
        "land_use": land_use_desc,
        "year_built": fmt(attrs.get("ACT_YR_BLT")),
        "eff_year_built": fmt(attrs.get("EFF_YR_BLT")),
        "living_area": fmt(attrs.get("TOT_LVG_AR")),
        "lot_size": fmt(attrs.get("LND_SQFOOT")),
        "buildings": fmt(attrs.get("NO_BULDNG")),
        "units": fmt(attrs.get("NO_RES_UNT")),
        "construction_class": fmt(attrs.get("CONST_CLAS")),
        "quality": fmt(attrs.get("IMP_QUAL")),
        "special_features_value": fmt(attrs.get("SPEC_FEAT_")),
        "neighborhood": fmt(attrs.get("NBRHD_CD")),
        "tax_authority": fmt(attrs.get("TAX_AUTH_C")),
        # Values
        "just_value": fmt(attrs.get("JV")),
        "assessed_value": fmt(attrs.get("AV_SD")),
        "taxable_value": fmt(attrs.get("TV_SD")),
        "land_value": fmt(attrs.get("LND_VAL")),
        "homestead_value": fmt(attrs.get("JV_HMSTD")),
        # Sales
        "sale1_price": fmt(attrs.get("SALE_PRC1")),
        "sale1_date": sale1_date or "N/A",
        "sale1_book_page": f"{fmt(attrs.get('OR_BOOK1'), '')}/{fmt(attrs.get('OR_PAGE1'), '')}".strip("/") or "N/A",
        "sale2_price": fmt(attrs.get("SALE_PRC2")),
        "sale2_date": sale2_date or "N/A",
        "sale2_book_page": f"{fmt(attrs.get('OR_BOOK2'), '')}/{fmt(attrs.get('OR_PAGE2'), '')}".strip("/") or "N/A",
    }


def lookup_property(address: str) -> dict:
    """Main lookup: geocode address, then query Florida cadastral data."""
    geo = geocode_address(address)
    if not geo:
        return {"error": "Address not found. Make sure it's a valid Florida address."}

    features = query_cadastral(geo["lat"], geo["lon"])
    if not features:
        return {"error": "No property records found at this location."}

    matched = find_best_match(features, address)
    results = [format_property(f["attributes"]) for f in matched]

    return {
        "matched_address": geo["matched_address"],
        "results": results,
    }
