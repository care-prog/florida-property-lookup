"""Scrapers using Playwright (Sunbiz) and curl_cffi (Radaris)."""
import re
import os

# ── Radaris People Search (curl_cffi) ──────────────────────────────

try:
    from curl_cffi import requests as cffi_requests
    HAS_CFFI = True
except ImportError:
    HAS_CFFI = False


def _clean_owner_name(name):
    """Clean cadastral owner name to extract first+last for people search."""
    if not name or name == "N/A" or "REFERENCE ONLY" in name:
        return None, None

    company_words = ["LLC", "INC", "CORP", "LTD", "LP", "TRUST", "ASSOC",
                     "BANK", "GROUP", "HOLDINGS", "PROPERTIES", "REALTY",
                     "INVESTMENT", "MANAGEMENT", "DEVELOPMENT", "PARTNERS",
                     "ESTATE", "FUND", "VENTURES", "CAPITAL", "ASSETS"]
    if any(w in name.upper().split() for w in company_words):
        return None, None

    clean = re.sub(r"\s*&[WH]\s+.*", "", name)
    clean = re.sub(r"\s+(ETAL|TR|JTRS|JR|SR|[IV]+)$", "", clean).strip()

    if "," in clean:
        parts = clean.split(",", 1)
        last = parts[0].strip().title()
        first = parts[1].strip().split()[0].title() if parts[1].strip() else ""
    else:
        words = clean.split()
        if len(words) < 2:
            return None, None
        first, last = words[0].title(), words[-1].title()

    return (first, last) if first and last and len(first) > 1 and len(last) > 1 else (None, None)


def search_radaris(owner_name, city="", state="FL"):
    """Search Radaris for phone/email. Returns dict or None."""
    if not HAS_CFFI:
        return None

    first, last = _clean_owner_name(owner_name)
    if not first:
        is_company = any(w in (owner_name or "").upper().split()
                         for w in ["LLC", "INC", "CORP", "TRUST", "LTD", "LP"])
        if is_company:
            return {"is_company": True, "name": owner_name}
        return None

    try:
        url = f"https://radaris.com/p/{first}/{last}/"
        r = cffi_requests.get(url, impersonate="chrome120", timeout=10)
        if r.status_code != 200:
            return {"first": first, "last": last, "found": False}

        skip = ["example.", "sentry.", "radaris.", "googleapis.", "gstatic.",
                "google.", "facebook.", "cloudflare.", "jquery.", "bootstrap."]
        phones = list(set(re.findall(r"\(\d{3}\)\s*\d{3}-\d{4}", r.text)))[:5]
        raw_emails = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", r.text)
        emails = list(set(e.rstrip(".") for e in raw_emails
                          if not any(d in e.lower() for d in skip) and len(e) > 5))[:5]
        age_m = re.search(r"Age\s*(\d+)", r.text)

        return {
            "first": first, "last": last,
            "found": bool(phones or emails),
            "phones": phones, "emails": emails,
            "age": age_m.group(1) if age_m else None,
        }
    except Exception:
        return {"first": first, "last": last, "found": False}


# ── Sunbiz LLC/Corp Search (Playwright) ───────────────────────────

def search_sunbiz(company_name):
    """Search Sunbiz for LLC/Corp officers. Returns dict or None."""
    if not company_name or company_name == "N/A":
        return None

    # Only search if it looks like a company
    company_words = ["LLC", "INC", "CORP", "LTD", "LP", "TRUST", "ASSOC",
                     "HOLDINGS", "PROPERTIES", "REALTY", "GROUP", "PARTNERS"]
    if not any(w in company_name.upper().split() for w in company_words):
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"error": "playwright_not_installed"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = ctx.new_page()

            # Search
            page.goto("https://search.sunbiz.org/Inquiry/CorporationSearch/ByName", timeout=15000)
            page.wait_for_load_state("networkidle")
            page.fill("#SearchTerm", company_name.split(",")[0].strip())
            page.click("input[type=submit]")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(page.content(), "html.parser")
            link = soup.find("a", href=lambda x: x and "SearchResultDetail" in str(x))

            if not link:
                browser.close()
                return {"found": False, "name": company_name}

            # Get detail page
            page.goto("https://search.sunbiz.org" + link["href"], timeout=15000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            dsoup = BeautifulSoup(page.content(), "html.parser")

            result = {"found": True, "name": link.get_text(strip=True)}

            # Parse sections
            for sec in dsoup.find_all("div", class_="detailSection"):
                txt = sec.get_text("|", strip=True)
                if "Filing Information" in txt:
                    m = re.search(r"Status\|(\w+)", txt)
                    result["status"] = m.group(1) if m else "N/A"
                    m2 = re.search(r"Date Filed\|([^\|]+)", txt)
                    result["date_filed"] = m2.group(1) if m2 else "N/A"
                    m3 = re.search(r"FEI/EIN Number\|([^\|]+)", txt)
                    result["ein"] = m3.group(1) if m3 else "N/A"
                elif "Principal Address" in txt:
                    addr = txt.replace("Principal Address|", "").replace("|", ", ")
                    addr = re.sub(r",\s*Changed:.*", "", addr)
                    result["principal_address"] = addr.strip()
                elif "Mailing Address" in txt:
                    addr = txt.replace("Mailing Address|", "").replace("|", ", ")
                    addr = re.sub(r",\s*Changed:.*", "", addr)
                    result["mailing_address"] = addr.strip()
                elif "Registered Agent" in txt:
                    parts = txt.replace("Registered Agent Name & Address|", "").split("|")
                    parts = [p for p in parts if "Changed:" not in p]
                    result["registered_agent"] = parts[0] if parts else "N/A"
                    result["agent_address"] = ", ".join(parts[1:3]) if len(parts) > 1 else "N/A"
                elif "Officer/Director" in txt:
                    officers = []
                    raw = txt.replace("Officer/Director Detail|Name & Address|", "")
                    chunks = re.split(r"Title\s+", raw)
                    for chunk in chunks:
                        if not chunk.strip():
                            continue
                        lines = chunk.split("|")
                        title = lines[0].strip() if lines else ""
                        name = lines[1].strip() if len(lines) > 1 else ""
                        addr = ", ".join(l.strip() for l in lines[2:4] if l.strip())
                        if name:
                            officers.append({"title": title, "name": name, "address": addr})
                    result["officers"] = officers

            browser.close()
            return result

    except Exception as e:
        return {"error": str(e)[:100], "name": company_name}


# ── Smart Links Generator ─────────────────────────────────────────

def generate_smart_links(owner_name, parcel_id, address, city, county_no):
    """Generate direct links to external public record sources."""
    links = {}

    if owner_name and owner_name != "N/A":
        clean_name = owner_name.replace(" ", "+").replace(",", "")
        links["sunbiz"] = (
            f"https://search.sunbiz.org/Inquiry/CorporationSearch/SearchResults"
            f"?inquiryType=EntityName&searchTerm={clean_name}"
            f"&searchNameOrder=&inquiryDirectionType=ForwardList"
        )

    if parcel_id and parcel_id != "N/A":
        folio = str(parcel_id).replace("-", "")
        cn = str(county_no) if county_no else ""
        if cn == "13":  # Miami-Dade
            links["tax_collector"] = f"https://miamidade.county-taxes.com/public/search/property_tax?search_query={folio}"
            links["clerk_records"] = "https://onlineservices.miamidadeclerk.gov/officialrecords/#/s/r"
            links["property_appraiser"] = f"https://www.miamidadepa.gov/propertysearch/#/?folio={folio}"
        elif cn == "6":  # Broward
            links["tax_collector"] = f"https://broward.county-taxes.com/public/search/property_tax?search_query={folio}"
            links["property_appraiser"] = "https://web.bcpa.net/BcpaClient/#/Record-Search"
        elif cn == "50":  # Palm Beach
            links["tax_collector"] = "https://pbctax.com/"
            links["property_appraiser"] = "https://pbcpao.gov/"
        elif cn == "48":  # Orange
            links["tax_collector"] = "https://www.octaxcol.com/"
            links["property_appraiser"] = "https://ocpaweb.ocpafl.org/"
        elif cn == "29":  # Hillsborough
            links["tax_collector"] = "https://hillsborough.county-taxes.com/public/search/property_tax"
            links["property_appraiser"] = "https://gis.hcpafl.org/propertysearch/"
        else:
            links["property_appraiser"] = "https://floridarevenue.com/property/Pages/Researchers.aspx"

    if owner_name and owner_name != "N/A":
        cw = ["LLC", "INC", "CORP", "LTD", "LP", "TRUST"]
        if not any(w in owner_name for w in cw):
            parts = owner_name.replace(",", " ").split()
            if len(parts) >= 2:
                name_slug = "+".join(parts[:2])
                city_state = f"{city}+FL" if city else "FL"
                links["truepeoplesearch"] = f"https://www.truepeoplesearch.com/results?name={name_slug}&citystatezip={city_state}"

    return links
