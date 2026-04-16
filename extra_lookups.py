"""Extra lookup modules: Radaris people search + smart links."""
import re

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False


def search_person(name, city="", state="FL"):
    """Search for phone/email using Radaris (free, no API key)."""
    if not HAS_CFFI or not name or name == "N/A":
        return None

    # Clean name
    name = name.strip()
    if "REFERENCE ONLY" in name:
        return None

    # Skip if it looks like a company
    company_words = ["LLC", "INC", "CORP", "LTD", "LP", "TRUST", "ASSOC",
                     "BANK", "GROUP", "HOLDINGS", "PROPERTIES", "REALTY",
                     "INVESTMENT", "MANAGEMENT", "DEVELOPMENT", "PARTNERS",
                     "ESTATE", "FUND", "VENTURES", "CAPITAL", "ASSETS"]
    if any(w in name.upper().split() for w in company_words):
        return {"is_company": True, "name": name}

    # Remove "&W", "&H", "ETAL", "TR", "JTRS" suffixes (spouse/trustee markers)
    clean = re.sub(r"\s*&[WH]\s+.*", "", name)  # "&W ANA SMITH" -> remove
    clean = re.sub(r"\s+ETAL$", "", clean)
    clean = re.sub(r"\s+TR$", "", clean)
    clean = re.sub(r"\s+JTRS$", "", clean)
    clean = re.sub(r"\s+JR$", "", clean)
    clean = re.sub(r"\s+SR$", "", clean)
    clean = re.sub(r"\s+[IV]+$", "", clean)
    clean = clean.strip()

    # Handle "LAST, FIRST" format
    if "," in clean:
        parts = clean.split(",", 1)
        last = parts[0].strip()
        first = parts[1].strip().split()[0] if parts[1].strip() else ""
    else:
        words = clean.split()
        if len(words) < 2:
            return None
        first = words[0]
        last = words[-1]

    if not first or not last or len(first) < 2 or len(last) < 2:
        return None

    first = first.title()
    last = last.title()

    try:
        url = f"https://radaris.com/p/{first}/{last}/"
        r = cffi_requests.get(url, impersonate="chrome120", timeout=10)
        if r.status_code != 200:
            return {"first": first, "last": last, "error": "lookup_failed"}

        # Extract phones
        phones = list(set(re.findall(r"\(\d{3}\)\s*\d{3}-\d{4}", r.text)))

        # Extract emails (filter out site/framework emails)
        skip_domains = ["example.", "sentry.", "radaris.", "googleapis.", "gstatic.",
                        "google.", "facebook.", "cloudflare.", "jquery.", "bootstrap."]
        raw_emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", r.text)
        emails = list(set(
            e.rstrip(".")
            for e in raw_emails
            if not any(d in e.lower() for d in skip_domains) and len(e) > 5
        ))

        # Extract age
        age_match = re.search(r"Age\s*(\d+)", r.text)
        age = age_match.group(1) if age_match else None

        if not phones and not emails:
            return {"first": first, "last": last, "found": False}

        return {
            "first": first,
            "last": last,
            "found": True,
            "phones": phones[:5],
            "emails": emails[:5],
            "age": age,
        }
    except Exception:
        return {"first": first, "last": last, "error": "timeout"}


def generate_smart_links(owner_name, parcel_id, address, city, county_no):
    """Generate direct links to external public record sources."""
    links = {}

    # Sunbiz LLC lookup
    if owner_name and owner_name != "N/A":
        clean_name = owner_name.replace(" ", "+").replace(",", "")
        links["sunbiz"] = (
            f"https://search.sunbiz.org/Inquiry/CorporationSearch/SearchResults"
            f"?inquiryType=EntityName&searchTerm={clean_name}"
            f"&searchNameOrder=&inquiryDirectionType=ForwardList"
        )

    # County Tax Collector (using folio/parcel)
    if parcel_id and parcel_id != "N/A":
        folio = str(parcel_id).replace("-", "")
        # Miami-Dade = county 13
        if str(county_no) == "13":
            links["tax_collector"] = f"https://miamidade.county-taxes.com/public/search/property_tax?search_query={folio}"
            links["clerk_records"] = f"https://onlineservices.miamidadeclerk.gov/officialrecords/#/s/r"
            links["property_appraiser"] = f"https://www.miamidadepa.gov/propertysearch/#/?folio={folio}"
        # Broward = county 6
        elif str(county_no) == "6":
            links["tax_collector"] = f"https://broward.county-taxes.com/public/search/property_tax?search_query={folio}"
            links["property_appraiser"] = f"https://web.bcpa.net/BcpaClient/#/Record-Search"
        # Palm Beach = county 50
        elif str(county_no) == "50":
            links["tax_collector"] = f"https://pbctax.com/"
            links["property_appraiser"] = f"https://pbcpao.gov/"
        # Orange = county 48
        elif str(county_no) == "48":
            links["tax_collector"] = f"https://www.octaxcol.com/"
            links["property_appraiser"] = f"https://ocpaweb.ocpafl.org/"
        # Hillsborough = county 29
        elif str(county_no) == "29":
            links["tax_collector"] = f"https://hillsborough.county-taxes.com/public/search/property_tax"
            links["property_appraiser"] = f"https://gis.hcpafl.org/propertysearch/"
        else:
            # Generic Florida county
            links["property_appraiser"] = "https://floridarevenue.com/property/Pages/Researchers.aspx"

    # TruePeopleSearch link (user clicks manually - we can't scrape it)
    if owner_name and owner_name != "N/A":
        company_words = ["LLC", "INC", "CORP", "LTD", "LP", "TRUST"]
        if not any(w in owner_name for w in company_words):
            name_parts = owner_name.replace(",", " ").split()
            if len(name_parts) >= 2:
                name_slug = "+".join(name_parts[:2])
                city_state = f"{city}+FL" if city else "FL"
                links["truepeoplesearch"] = f"https://www.truepeoplesearch.com/results?name={name_slug}&citystatezip={city_state}"

    return links
