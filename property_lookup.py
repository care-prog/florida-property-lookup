import re
import requests
import json
from typing import Optional


# Free US Census Geocoder
GEOCODE_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# Free Florida Statewide Cadastral (all 67 counties, 10.8M+ parcels)
CADASTRAL_URL = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query"

# Free FEMA National Flood Hazard Layer
FEMA_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"

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

FLOOD_ZONE_DESC = {
    "X": "Minimal Risk (outside flood zone)",
    "A": "High Risk - 1% annual flood chance",
    "AE": "High Risk - 1% annual flood chance (with BFE)",
    "AH": "High Risk - Shallow flooding",
    "AO": "High Risk - Sheet flow flooding",
    "VE": "High Risk - Coastal flooding with waves",
    "V": "High Risk - Coastal flooding",
    "D": "Undetermined Risk",
    "AREA NOT INCLUDED": "Not mapped by FEMA",
}


def extract_street_number(address):
    match = re.match(r"(\d+)", address.strip())
    return match.group(1) if match else ""


def geocode_address(address):
    try:
        r = requests.get(GEOCODE_URL, params={
            "address": address, "benchmark": "Public_AR_Current", "format": "json",
        }, timeout=15)
        matches = r.json().get("result", {}).get("addressMatches", [])
        if matches:
            coords = matches[0]["coordinates"]
            return {"lat": coords["y"], "lon": coords["x"],
                    "matched_address": matches[0].get("matchedAddress", address)}
    except Exception:
        pass
    return None


def query_cadastral(lat, lon):
    buffer = 0.0003
    envelope = {"xmin": lon - buffer, "ymin": lat - buffer,
                "xmax": lon + buffer, "ymax": lat + buffer,
                "spatialReference": {"wkid": 4326}}
    try:
        r = requests.post(CADASTRAL_URL, data={
            "geometry": json.dumps(envelope),
            "geometryType": "esriGeometryEnvelope",
            "spatialRel": "esriSpatialRelIntersects",
            "inSR": "4326", "outFields": OUT_FIELDS,
            "f": "json", "returnGeometry": "false",
        }, timeout=30)
        return r.json().get("features", [])
    except Exception:
        return []


def query_flood_zone(lat, lon):
    """Query FEMA flood zone by coordinates."""
    try:
        r = requests.get(FEMA_URL, params={
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DEPTH",
            "returnGeometry": "false",
            "f": "json",
        }, timeout=15)
        features = r.json().get("features", [])
        if features:
            attrs = features[0]["attributes"]
            zone = attrs.get("FLD_ZONE", "Unknown")
            sfha = attrs.get("SFHA_TF", "F")
            bfe = attrs.get("STATIC_BFE")
            if bfe == -9999 or bfe is None:
                bfe = None
            return {
                "flood_zone": zone,
                "flood_zone_desc": FLOOD_ZONE_DESC.get(zone, zone),
                "in_flood_hazard_area": sfha == "T",
                "base_flood_elevation": bfe,
                "zone_subtype": attrs.get("ZONE_SUBTY") or "N/A",
            }
    except Exception:
        pass
    return {
        "flood_zone": "N/A", "flood_zone_desc": "Unable to determine",
        "in_flood_hazard_area": None, "base_flood_elevation": None,
        "zone_subtype": "N/A",
    }


def find_best_match(features, input_address):
    input_num = extract_street_number(input_address)
    if not input_num:
        return features
    real = [f for f in features if (f["attributes"].get("OWN_NAME") or "").strip() != "REFERENCE ONLY"]
    if not real:
        real = features
    exact = [f for f in real if extract_street_number(f["attributes"].get("PHY_ADDR1", "")) == input_num]
    return exact if exact else real[:1]


def fmt(val, default="N/A"):
    if val is None:
        return default
    if isinstance(val, str) and val.strip() == "":
        return default
    if isinstance(val, (int, float)) and val == 0:
        return default
    return val


def format_mailing(attrs, prefix):
    parts = [str(fmt(attrs.get(f"{prefix}_ADDR1"), "")),
             str(fmt(attrs.get(f"{prefix}_ADDR2"), "")),
             str(fmt(attrs.get(f"{prefix}_CITY"), "")),
             str(fmt(attrs.get(f"{prefix}_STATE"), ""))]
    zipcd = attrs.get(f"{prefix}_ZIPCD")
    if zipcd and str(zipcd).strip() and str(zipcd).strip() != "0":
        parts.append(str(int(float(str(zipcd)))) if isinstance(zipcd, (int, float)) else str(zipcd))
    return ", ".join(p for p in parts if p) or "N/A"


def format_property(attrs):
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

    luc = str(fmt(attrs.get("DOR_UC"), "")).strip()
    homestead = fmt(attrs.get("JV_HMSTD")) != "N/A" and attrs.get("JV_HMSTD", 0) > 0

    return {
        "owner_name": fmt(attrs.get("OWN_NAME")),
        "owner_mailing": format_mailing(attrs, "OWN"),
        "fiduciary_name": fmt(attrs.get("FIDU_NAME")),
        "fiduciary_mailing": format_mailing(attrs, "FIDU") if fmt(attrs.get("FIDU_NAME")) != "N/A" else "N/A",
        "homestead": homestead,
        "address": f"{fmt(attrs.get('PHY_ADDR1'), '')}, {fmt(attrs.get('PHY_CITY'), '')} {fmt(attrs.get('PHY_ZIPCD'), '')}".strip(", "),
        "parcel_id": fmt(attrs.get("PARCEL_ID")),
        "parcelno": fmt(attrs.get("PARCELNO")),
        "legal_desc": fmt(attrs.get("S_LEGAL")),
        "land_use_code": luc,
        "land_use": LAND_USE_CODES.get(luc, luc),
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
        "just_value": fmt(attrs.get("JV")),
        "assessed_value": fmt(attrs.get("AV_SD")),
        "taxable_value": fmt(attrs.get("TV_SD")),
        "land_value": fmt(attrs.get("LND_VAL")),
        "homestead_value": fmt(attrs.get("JV_HMSTD")),
        "sale1_price": fmt(attrs.get("SALE_PRC1")),
        "sale1_date": sale1_date or "N/A",
        "sale1_book_page": f"{fmt(attrs.get('OR_BOOK1'), '')}/{fmt(attrs.get('OR_PAGE1'), '')}".strip("/") or "N/A",
        "sale2_price": fmt(attrs.get("SALE_PRC2")),
        "sale2_date": sale2_date or "N/A",
        "sale2_book_page": f"{fmt(attrs.get('OR_BOOK2'), '')}/{fmt(attrs.get('OR_PAGE2'), '')}".strip("/") or "N/A",
    }


def lookup_property(address):
    """Main lookup: geocode → cadastral → flood → people → LLC → links."""
    from scrapers import search_radaris, search_sunbiz, generate_smart_links

    geo = geocode_address(address)
    if not geo:
        return {"error": "Address not found. Make sure it's a valid Florida address."}

    features = query_cadastral(geo["lat"], geo["lon"])
    if not features:
        return {"error": "No property records found at this location."}

    matched = find_best_match(features, address)
    results = [format_property(f["attributes"]) for f in matched]
    flood = query_flood_zone(geo["lat"], geo["lon"])

    person = None
    sunbiz = None
    smart_links = {}

    if results:
        r0 = results[0]
        owner = r0.get("owner_name", "")
        addr = r0.get("address", "")
        # Extract city from "123 MAIN ST, Miami Beach 33149"
        city = ""
        if "," in addr:
            after_comma = addr.split(",", 1)[1].strip()
            # Remove zip code at end
            city = re.sub(r"\s*\d{5}(-\d{4})?\s*$", "", after_comma).strip()

        # People search (phone/email via Radaris)
        person = search_radaris(owner, city, "FL")

        # Sunbiz LLC lookup (if owner is a company)
        sunbiz = search_sunbiz(owner)

        # Smart links
        county_no = matched[0]["attributes"].get("CO_NO") if matched else None
        smart_links = generate_smart_links(
            owner, r0.get("parcel_id"), addr, city, county_no
        )

    return {
        "matched_address": geo["matched_address"],
        "results": results,
        "flood": flood,
        "person": person,
        "sunbiz": sunbiz,
        "links": smart_links,
    }
