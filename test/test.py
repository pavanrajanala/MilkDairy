from playwright.sync_api import sync_playwright
from datetime import date, timedelta
import time


BASE_URL = "http://127.0.0.1:5000"

# Test configuration
FARMER_COUNT = 100
TEST_DAYS = 3

# Keep browser visible so you can watch it.
SLOW_MO = 150


def add_farmer(page, cid, name, phone, address):
    page.locator("#cid").fill(cid)
    page.locator("#name").fill(name)
    page.locator("#phone").fill(phone)
    page.locator("#address").fill(address)

    page.get_by_role(
        "button",
        name="+ Add Farmer"
    ).click()

    page.wait_for_load_state("domcontentloaded")


def enter_collection(page, collection_date, session, cid, fat, snf, quantity):
    page.locator("#collection_date").fill(collection_date)

    page.locator("#session").select_option(session)

    page.locator("#cid").fill(cid)
    page.locator("#fat").fill(str(fat))

    if snf is not None:
        page.locator("#snf").fill(str(snf))
    else:
        page.locator("#snf").fill("")

    page.locator("#quantity").fill(str(quantity))

    page.get_by_role(
        "button",
        name="✓ Save & Next"
    ).click()

    page.wait_for_load_state("domcontentloaded")


with sync_playwright() as p:

    print("=" * 60)
    print("ABC DAIRY AUTOMATED WEBSITE TEST")
    print("=" * 60)

    browser = p.chromium.launch(
        headless=False,
        slow_mo=SLOW_MO
    )

    page = browser.new_page()

    page.set_default_timeout(15000)

    # --------------------------------------------------
    # OPEN WEBSITE
    # --------------------------------------------------

    print("\n[1] Opening ABC Dairy...")

    page.goto(BASE_URL)

    print("    Website opened.")
    print("    Title:", page.title())

    # --------------------------------------------------
    # ADD 100 FARMERS
    # --------------------------------------------------

    print("\n[2] ADDING 100 FARMERS")
    print("-" * 40)

    page.goto(f"{BASE_URL}/farmers")

    farmer_success = 0
    farmer_failed = []

    for i in range(1, FARMER_COUNT + 1):

        cid = f"C{i}"
        name = f"Test Farmer {i}"
        phone = f"900000{i:04d}"
        address = f"Test Address {i}"

        try:

            add_farmer(
                page,
                cid,
                name,
                phone,
                address
            )

            farmer_success += 1

            print(
                f"Farmer {i:03d}/100 "
                f"-> {cid} SUCCESS"
            )

        except Exception as e:

            farmer_failed.append(
                (cid, str(e))
            )

            print(
                f"Farmer {i:03d}/100 "
                f"-> {cid} FAILED"
            )

    print("\nFarmers completed:")
    print("Success:", farmer_success)
    print("Failed :", len(farmer_failed))

    # --------------------------------------------------
    # COLLECTION TEST
    # --------------------------------------------------

    print("\n[3] MILK COLLECTION TEST")
    print("-" * 40)

    page.goto(f"{BASE_URL}/collection")

    start_date = date.today() - timedelta(
        days=TEST_DAYS - 1
    )

    collection_success = 0
    collection_failed = []

    for day_number in range(TEST_DAYS):

        current_date = (
            start_date +
            timedelta(days=day_number)
        )

        collection_date = current_date.isoformat()

        print(
            f"\nDATE: {collection_date}"
        )

        for session in ["AM", "PM"]:

            print(
                f"  SESSION: {session}"
            )

            for i in range(
                1,
                FARMER_COUNT + 1
            ):

                cid = f"C{i}"

                # Test data
                fat = 3.5 + ((i % 5) * 0.1)

                # Use SNF for some records.
                snf = 8.5 + ((i % 4) * 0.1)

                quantity = 2.0 + (i % 6)

                try:

                    enter_collection(
                        page,
                        collection_date,
                        session,
                        cid,
                        fat,
                        snf,
                        quantity
                    )

                    collection_success += 1

                    print(
                        f"    {cid:4s} "
                        f"{session} "
                        f"SUCCESS"
                    )

                except Exception as e:

                    collection_failed.append(
                        (
                            collection_date,
                            session,
                            cid,
                            str(e)
                        )
                    )

                    print(
                        f"    {cid:4s} "
                        f"{session} "
                        f"FAILED"
                    )

    expected_collections = (
        FARMER_COUNT *
        TEST_DAYS *
        2
    )

    # --------------------------------------------------
    # FINAL REPORT
    # --------------------------------------------------

    print("\n")
    print("=" * 60)
    print("ABC DAIRY AUTOMATED TEST RESULT")
    print("=" * 60)

    print("\nFARMERS")
    print("Expected :", FARMER_COUNT)
    print("Success  :", farmer_success)
    print("Failed   :", len(farmer_failed))

    print("\nCOLLECTION")
    print("Days     :", TEST_DAYS)
    print("Sessions : AM + PM")
    print("Expected :", expected_collections)
    print("Success  :", collection_success)
    print("Failed   :", len(collection_failed))

    if farmer_failed:

        print("\nFAILED FARMERS")

        for item in farmer_failed:
            print(item)

    if collection_failed:

        print("\nFAILED COLLECTIONS")

        for item in collection_failed[:20]:
            print(item)

    print("\nFINAL RESULT")

    if (
        farmer_success == FARMER_COUNT
        and
        collection_success == expected_collections
        and
        not farmer_failed
        and
        not collection_failed
    ):
        print("PASS - ALL UI AUTOMATION COMPLETED")

    else:
        print("FAIL - CHECK FAILED RECORDS")

    print("=" * 60)

    print("\nBrowser will remain open for 10 seconds...")
    time.sleep(10)

    browser.close()