from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import pandas as pd
import requests
import os
import time

def launch_browser() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Use webdriver-manager to automatically download and manage ChromeDriver
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

# ─── STEP 3: DemandStar handler using Selenium ────────────────────────────────
HEADER_TEXT = "Bids & RFPs | OpenBids"
TIMEOUT_SEC = 15

def validate_demandstar_selenium(url: str) -> bool:
    print(f"  [DemandStar] Launching headless browser for {url}")
    driver = launch_browser()
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, TIMEOUT_SEC).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.listGroupWrapper.clearfix")),
                    EC.presence_of_element_located((By.TAG_NAME, "h1"))
                )
            )
        except Exception:
            print("    [TIMEOUT] Timed out waiting for page to render.")

        html = driver.page_source
    finally:
        driver.quit()

    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if h1 is None:
        print("    [ERROR] No <h1> found — aborting.")
        return False

    actual_header = h1.get_text(strip=True)
    print(f"    <h1> Text: {actual_header}")
    if HEADER_TEXT not in actual_header:
        print(f"    [ERROR] Unexpected header: {actual_header}")
        return False

    print("    [SUCCESS] DemandStar page passed validation.")
    return True

# ─── STEP 4: Other platform validators ────────────────────────────────────────
OPEN_SOLICITATION_TT = "Open Solicitations"
PAGE_HEADER_ID = "ctl00_mainContent_lblPageHeader"

def validate_bonfire_selenium(url: str) -> tuple[bool, str]:
    print(f"  [Bonfire] Modifying URL path to portal...")
    
    # Extract the base URL (protocol + domain) and set the portal path
    parsed = urlparse(url)
    portal_url = f"{parsed.scheme}://{parsed.netloc}/portal/?tab=openOpportunities"
    
    print(f"    Testing portal URL: {portal_url}")
    
    driver = launch_browser()
    try:
        driver.get(portal_url)
        time.sleep(3)  # Wait for page to load
        
        print(f"    [SUCCESS] Portal URL loaded successfully")
        return True, portal_url
            
    except Exception as e:
        print(f"    [ERROR] Error loading portal URL: {e}")
        return False, url  # Return original URL if validation fails
    finally:
        driver.quit()

def validate_ionwave_selenium(url: str) -> tuple[bool, str]:
    print(f"  [IonWave] Modifying URL path to sourcing events...")
    
    # Extract the base URL (protocol + domain) and set the sourcing events path
    parsed = urlparse(url)
    sourcing_url = f"{parsed.scheme}://{parsed.netloc}/SourcingEvents.aspx?SourceType=1"
    
    print(f"    Testing sourcing events URL: {sourcing_url}")
    
    driver = launch_browser()
    try:
        driver.get(sourcing_url)
        time.sleep(3)  # Wait for page to load
        
        print(f"    [SUCCESS] Sourcing events URL loaded successfully")
        return True, sourcing_url
            
    except Exception as e:
        print(f"    [ERROR] Error loading sourcing events URL: {e}")
        return False, url  # Return original URL if validation fails
    finally:
        driver.quit()

def validate_bonfire(url, soup):
    print(f"  [Bonfire] Checking resolved URL suffix...")
    print(f"  [Bonfire] DEBUG - URL being checked: {url}")
    if "/portal/?tab=openOpportunities" not in url:
        print("    [ERROR] URL suffix missing.")
        print(f"    Expected '/portal/?tab=openOpportunities' in: {url}")
        return False
    
    # Additional validation: check for specific Bonfire elements in the page
    print(f"  [Bonfire] Checking page content...")
    
    # Look for common Bonfire page indicators
    bonfire_indicators = [
        soup.find(attrs={"class": lambda x: x and "bonfire" in x.lower()}),
        soup.find(attrs={"id": lambda x: x and "bonfire" in x.lower()}),
        soup.find("title", string=lambda x: x and "bonfire" in x.lower()),
        soup.find(string=lambda x: x and "bonfire" in x.lower()),
        soup.find(attrs={"title": OPEN_SOLICITATION_TT}),
        soup.find("h1", string=lambda x: x and ("opportunities" in x.lower() or "solicitations" in x.lower()))
    ]
    
    if any(bonfire_indicators):
        print("    [SUCCESS] Bonfire page content validated.")
        return True
    else:
        print("    [ERROR] No Bonfire page indicators found.")
        return False

def validate_ionwave(url, soup):
    print(f"  [IonWave] Checking resolved URL and header span...")
    if "/SourcingEvents.aspx?SourceType=1" not in url:
        print("    [ERROR] URL suffix missing.")
        return False
    hdr = soup.find("span", id=PAGE_HEADER_ID)
    if not hdr:
        print("    [ERROR] Header span not found.")
        return False
    header_text = hdr.get_text(strip=True)
    print(f"    Found header: {header_text}")
    if "Current Bid Opportunities" in header_text:
        print("    [SUCCESS] IonWave page validated.")
        return True
    else:
        print("    [ERROR] Expected header text not found.")
        return False

def validate_bidnetdirect(url, soup):
    print(f"  [BidNetDirect] Checking resolved URL and looking for title='Open Solicitations'...")
    print(f"    Resolved URL: {url}")
    element = soup.find(attrs={"title": OPEN_SOLICITATION_TT})
    if element:
        print("    [SUCCESS] BidNetDirect page validated.")
        return True
    else:
        print("    [ERROR] Open Solicitations element not found.")
        return False

def validate_generic(url, soup):
    print(f"  [Generic] Checking resolved URL and looking for title='Open Solicitations'...")
    print(f"    Resolved URL: {url}")
    element = soup.find(attrs={"title": OPEN_SOLICITATION_TT})
    if element:
        print("    [SUCCESS] Generic page validated.")
        return True
    else:
        print("    [ERROR] Open Solicitations element not found.")
        return False

# ─── STEP 5: Main validation dispatcher ───────────────────────────────────────
def validate_entry(url, platform):
    print(f"\n[VALIDATING] Validating ({platform}): {url}")
    platform = platform.strip().lower()

    if platform == "demandstar":
        return validate_demandstar_selenium(url), url
    elif platform == "bonfire" or platform == "bonfirehub":
        return validate_bonfire_selenium(url)  # This already returns (bool, str)
    elif platform == "ionwave":
        return validate_ionwave_selenium(url)  # This already returns (bool, str)

    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        response.raise_for_status()
        resolved_url = response.url
        print(f"  Resolved URL: {resolved_url}")
        print(f"  DEBUG - Original URL: {url}")
        print(f"  DEBUG - URLs are different: {url != resolved_url}")
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"   Failed to fetch URL: {e}")
        return False, url

    if platform == "bidnetdirect":
        return validate_bidnetdirect(resolved_url, soup), resolved_url
    else:
        return validate_generic(resolved_url, soup), resolved_url

# ─── STEP 6: Load CSV and validate rows ───────────────────────────────────────
# Replace with the actual path to your CSV
input_filename = "C:\\Users\\plgg4\\Downloads\\RFP Test CSV - Link Validation Test.csv"

if not os.path.exists(input_filename):
    raise FileNotFoundError(f"[ERROR] File not found: {input_filename}")

df = pd.read_csv(input_filename)
df = df.dropna(subset=["rfp_landing_page", "Platform"])

print(f"[INFO] Processing {len(df)} rows...")

# Optional: Limit for testing
# df = df.head(10)

# Add progress tracking
def validate_with_progress(row, index, total):
    print(f"\n[{index+1}/{total}] Processing row {index+1}...")
    is_valid, updated_url = validate_entry(row["rfp_landing_page"], row["Platform"])
    
    # Update the URL in the row if it changed
    row["rfp_landing_page"] = updated_url
    
    if is_valid:
        print(f"  Row {index+1}: VALID")
    else:
        print(f"  Row {index+1}: INVALID")
    return is_valid

# Apply validation and get results
results = []
for idx, row in df.iterrows():
    is_valid = validate_with_progress(row, idx, len(df))
    results.append(is_valid)

df["Valid"] = results
cleaned_df = df[df["Valid"]].drop(columns=["Valid"])

# ─── STEP 7: Save result ──────────────────────────────────────────────────────
# Try Desktop first, fallback to user directory if Desktop doesn't exist
desktop_path = "C:\\Users\\plgg4\\Desktop\\Cleaned_RFP_Scrape.csv"
fallback_path = "C:\\Users\\plgg4\\Cleaned_RFP_Scrape.csv"

if os.path.exists("C:\\Users\\plgg4\\Desktop"):
    output_filename = desktop_path
else:
    output_filename = fallback_path

try:
    cleaned_df.to_csv(output_filename, index=False)
    print(f"\n[SUCCESS] Done! Cleaned file saved as {output_filename}")
    print(f"[INFO] Original rows: {len(df)}, Valid rows: {len(cleaned_df)}")
except PermissionError:
    # If there's a permission error, try saving with a timestamp
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"C:\\Users\\plgg4\\Cleaned_RFP_Scrape_{timestamp}.csv"
    cleaned_df.to_csv(output_filename, index=False)
    print(f"\n[SUCCESS] Done! Cleaned file saved as {output_filename}")
    print(f"[INFO] Original rows: {len(df)}, Valid rows: {len(cleaned_df)}")
except Exception as e:
    print(f"\n[ERROR] Error saving file: {e}")
    print("Trying alternative location...")
    output_filename = f"C:\\Users\\plgg4\\Cleaned_RFP_Scrape_backup.csv"
    cleaned_df.to_csv(output_filename, index=False)
    print(f"\n[SUCCESS] Done! Cleaned file saved as {output_filename}")
    print(f"[INFO] Original rows: {len(df)}, Valid rows: {len(cleaned_df)}")
