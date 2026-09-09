import os
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import date

from db import (
    get_db_connection,
    release_db_connection
)


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "abc-dairy-local-key")


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/")
def dashboard():

    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        today = date.today()

        # -------------------------------------------------
        # TODAY'S SUMMARY
        # -------------------------------------------------
        cursor.execute("""
            SELECT
                COALESCE(SUM(quantity), 0),
                COALESCE(SUM(amount), 0),
                COUNT(*)
            FROM collection_entries
            WHERE collection_date = %s
        """, (today,))

        today_milk, today_amount, today_entries = cursor.fetchone()

        # Total farmers currently registered.
        cursor.execute("""
            SELECT COUNT(*)
            FROM farmers
        """)
        active_farmers = cursor.fetchone()[0]

        # -------------------------------------------------
        # TODAY'S COLLECTION DETAILS
        # -------------------------------------------------
        cursor.execute("""
            SELECT
                f.cid,
                f.name,
                ce.session,
                ce.fat,
                ce.snf,
                ce.quantity,
                ce.rate,
                ce.amount
            FROM collection_entries ce
            JOIN farmers f
                ON f.id = ce.farmer_id
            WHERE ce.collection_date = %s
            ORDER BY
                CASE WHEN ce.session = 'PM' THEN 2 ELSE 1 END DESC,
                ce.id DESC
            LIMIT 10
        """, (today,))

        today_collections = cursor.fetchall()

        return render_template(
            "dashboard.html",
            today_milk=today_milk,
            today_amount=today_amount,
            active_farmers=active_farmers,
            today_entries=today_entries,
            today_collections=today_collections,
            today_date=today
        )
    finally:
        cursor.close()
        release_db_connection(connection)


# =========================================================
# COLLECTION
# =========================================================

@app.route("/collection", methods=["GET", "POST"])
def collection():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # =================================================
        # GET CURRENT RATE
        # =================================================

        cursor.execute("""
            SELECT
                pricing_mode,
                fat_rate,
                snf_rate
            FROM rate_settings
            ORDER BY id DESC
            LIMIT 1
        """)

        rate = cursor.fetchone()


        # =================================================
        # DEFAULT DATE + SESSION
        # =================================================

        selected_date = request.args.get(
            "date",
            date.today().isoformat()
        )

        selected_session = request.args.get(
            "session",
            "AM"
        )


        # =================================================
        # EDIT DATA
        # =================================================

        edit_id = request.args.get("edit_id")

        edit_collection = None

        if edit_id:

            cursor.execute("""
                SELECT
                    ce.id,
                    f.cid,
                    ce.collection_date,
                    ce.session,
                    ce.fat,
                    ce.snf,
                    ce.quantity
                FROM collection_entries ce
                JOIN farmers f
                    ON f.id = ce.farmer_id
                WHERE ce.id = %s
            """, (edit_id,))

            edit_collection = cursor.fetchone()

            if edit_collection:

                selected_date = str(
                    edit_collection[2]
                )

                selected_session = (
                    edit_collection[3]
                )


        # =================================================
        # SAVE COLLECTION
        # =================================================

        if request.method == "POST":

            # -------------------------------------------------
            # GET FORM VALUES
            # -------------------------------------------------

            cid = request.form.get(
                "cid",
                ""
            ).strip()

            collection_date = request.form.get(
                "collection_date"
            )

            session = request.form.get(
                "session"
            )

            fat_value = request.form.get(
                "fat",
                ""
            ).strip()

            quantity_value = request.form.get(
                "quantity",
                ""
            ).strip()

            snf_value = request.form.get(
                "snf",
                ""
            ).strip()


            # -------------------------------------------------
            # BASIC VALIDATION
            # -------------------------------------------------

            if not cid:

                flash(
                    "Please enter a CID.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            if not collection_date:

                flash(
                    "Please select a collection date.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        session=session
                    )
                )


            if not session:

                flash(
                    "Please select AM or PM session.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date
                    )
                )


            if not fat_value:

                flash(
                    "Please enter FAT value.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            if not quantity_value:

                flash(
                    "Please enter milk quantity.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            # -------------------------------------------------
            # CONVERT NUMBERS
            # -------------------------------------------------

            try:

                fat = float(fat_value)

                quantity = float(
                    quantity_value
                )

                if snf_value:

                    snf = float(
                        snf_value
                    )

                else:

                    snf = None

            except ValueError:

                flash(
                    "FAT, SNF and quantity must be valid numbers.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            # -------------------------------------------------
            # VALIDATE NUMBERS
            # -------------------------------------------------

            if fat <= 0:

                flash(
                    "FAT must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            if quantity <= 0:

                flash(
                    "Quantity must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            if snf is not None and snf < 0:

                flash(
                    "SNF cannot be negative.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            # =================================================
            # CHECK RATE
            # =================================================

            if not rate:

                flash(
                    "Please configure the milk rate first.",
                    "error"
                )

                return redirect(
                    url_for("settings")
                )


            pricing_mode = rate[0]

            fat_rate = float(
                rate[1]
            )

            snf_rate = float(
                rate[2]
            )


            # =================================================
            # FIND FARMER USING CID
            # =================================================

            cursor.execute("""
                SELECT
                    id
                FROM farmers
                WHERE cid = %s
            """, (cid,))

            farmer = cursor.fetchone()


            # -------------------------------------------------
            # CID NOT FOUND
            # -------------------------------------------------

            if not farmer:

                flash(
                    f"Farmer with CID {cid} was not found.",
                    "error"
                )

                return redirect(
                    url_for(
                        "collection",
                        date=collection_date,
                        session=session
                    )
                )


            farmer_id = farmer[0]


            # =================================================
            # CALCULATE MILK RATE
            # =================================================

            if (
                pricing_mode == "FAT_SNF"
                and snf is not None
            ):

                milk_rate = (
                    (fat * fat_rate)
                    +
                    (snf * snf_rate)
                )

            else:

                # FAT ONLY
                milk_rate = (
                    fat * fat_rate
                )


            # =================================================
            # CALCULATE TOTAL AMOUNT
            # =================================================

            amount = (
                milk_rate * quantity
            )


            # =================================================
            # CHECK EXISTING COLLECTION
            #
            # Same:
            # CID + DATE + SESSION
            #
            # If found -> UPDATE
            # If not found -> INSERT
            # =================================================

            cursor.execute("""
                SELECT
                    id
                FROM collection_entries
                WHERE farmer_id = %s
                  AND collection_date = %s
                  AND session = %s
            """, (
                farmer_id,
                collection_date,
                session
            ))

            existing_collection = (
                cursor.fetchone()
            )


            # =================================================
            # INSERT OR UPDATE
            # =================================================

            cursor.execute("""
                INSERT INTO collection_entries
                (
                    farmer_id,
                    collection_date,
                    session,
                    fat,
                    snf,
                    quantity,
                    rate,
                    amount
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )

                ON CONFLICT
                (
                    farmer_id,
                    collection_date,
                    session
                )

                DO UPDATE SET

                    fat = EXCLUDED.fat,

                    snf = EXCLUDED.snf,

                    quantity = EXCLUDED.quantity,

                    rate = EXCLUDED.rate,

                    amount = EXCLUDED.amount
            """, (
                farmer_id,
                collection_date,
                session,
                fat,
                snf,
                quantity,
                milk_rate,
                amount
            ))


            # =================================================
            # COMMIT
            # =================================================

            connection.commit()


            # =================================================
            # SUCCESS MESSAGE
            # =================================================

            if existing_collection:

                flash(
                    f"Collection for CID {cid} updated successfully.",
                    "success"
                )

            else:

                flash(
                    f"Collection for CID {cid} saved successfully.",
                    "success"
                )


            # =================================================
            # REDIRECT
            # =================================================

            return redirect(
                url_for(
                    "collection",
                    saved="1",
                    date=collection_date,
                    session=session
                )
            )


        # =================================================
        # SAVED FLAG
        # =================================================

        saved = (
            request.args.get("saved") == "1"
        )


        # =================================================
        # RECENT COLLECTIONS
        # =================================================

        cursor.execute("""
            SELECT
                ce.id,
                f.cid,
                f.name,
                ce.collection_date,
                ce.session,
                ce.fat,
                ce.snf,
                ce.quantity,
                ce.rate,
                ce.amount

            FROM collection_entries ce

            JOIN farmers f
                ON f.id = ce.farmer_id

            ORDER BY
                ce.collection_date DESC,

                CASE
                    WHEN ce.session = 'PM'
                    THEN 2
                    ELSE 1
                END DESC,

                ce.id DESC

            LIMIT 10
        """)

        recent_collections = (
            cursor.fetchall()
        )


        # =================================================
        # RENDER COLLECTION PAGE
        # =================================================

        return render_template(
            "collection.html",

            rate=rate,

            saved=saved,

            selected_date=selected_date,

            selected_session=selected_session,

            recent_collections=recent_collections,

            edit_collection=edit_collection
        )


    finally:

        cursor.close()

        release_db_connection(
            connection
        )


# =========================================================
# FARMERS
# =========================================================

# =========================================================
# FARMERS
# =========================================================

@app.route("/farmers", methods=["GET", "POST"])
def farmers():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # =================================================
        # ADD FARMER
        # =================================================

        if request.method == "POST":

            cid = request.form.get("cid", "").strip()
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            address = request.form.get("address", "").strip()

            # ---------------------------------------------
            # VALIDATION
            # ---------------------------------------------

            if not cid:

                flash(
                    "CID is required.",
                    "error"
                )

                return redirect(
                    url_for("farmers")
                )

            if not name:

                flash(
                    "Farmer name is required.",
                    "error"
                )

                return redirect(
                    url_for("farmers")
                )

            # ---------------------------------------------
            # CHECK DUPLICATE CID
            # ---------------------------------------------

            cursor.execute("""
                SELECT id
                FROM farmers
                WHERE cid = %s
            """, (cid,))

            existing_farmer = cursor.fetchone()

            if existing_farmer:

                flash(
                    f"CID {cid} already exists.",
                    "error"
                )

                return redirect(
                    url_for("farmers")
                )

            # ---------------------------------------------
            # INSERT FARMER
            # ---------------------------------------------

            cursor.execute("""
                INSERT INTO farmers
                (
                    cid,
                    name,
                    phone,
                    address,
                    created_at,
                    updated_at
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW(),
                    NOW()
                )
            """, (
                cid,
                name,
                phone,
                address
            ))

            connection.commit()

            flash(
                f"Farmer {name} added successfully.",
                "success"
            )

            return redirect(
                url_for("farmers")
            )


        # =================================================
        # SEARCH
        # =================================================

        search = request.args.get(
            "search",
            ""
        ).strip()


        if search:

            cursor.execute("""
                SELECT
                    id,
                    cid,
                    name,
                    phone,
                    address,
                    created_at,
                    updated_at
                FROM farmers
                WHERE
                    cid ILIKE %s
                    OR name ILIKE %s
                    OR phone ILIKE %s
                ORDER BY id DESC
            """, (
                f"%{search}%",
                f"%{search}%",
                f"%{search}%"
            ))

        else:

            cursor.execute("""
                SELECT
                    id,
                    cid,
                    name,
                    phone,
                    address,
                    created_at,
                    updated_at
                FROM farmers
                ORDER BY id DESC
            """)


        farmers_list = cursor.fetchall()


        # =================================================
        # EDIT FARMER
        # =================================================

        edit_id = request.args.get(
            "edit_id"
        )

        edit_farmer = None

        if edit_id:

            cursor.execute("""
                SELECT
                    id,
                    cid,
                    name,
                    phone,
                    address
                FROM farmers
                WHERE id = %s
            """, (edit_id,))

            edit_farmer = cursor.fetchone()


        # =================================================
        # RENDER
        # =================================================

        return render_template(
            "farmers.html",
            farmers=farmers_list,
            edit_farmer=edit_farmer,
            search=search
        )


    finally:

        cursor.close()

        release_db_connection(
            connection
        )


# =========================================================
# EDIT FARMER
# =========================================================

@app.route(
    "/farmers/edit/<int:farmer_id>",
    methods=["POST"]
)
def edit_farmer(farmer_id):

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        cid = request.form.get(
            "cid",
            ""
        ).strip()

        name = request.form.get(
            "name",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        address = request.form.get(
            "address",
            ""
        ).strip()


        # =================================================
        # VALIDATION
        # =================================================

        if not cid:

            flash(
                "CID is required.",
                "error"
            )

            return redirect(
                url_for(
                    "farmers",
                    edit_id=farmer_id
                )
            )


        if not name:

            flash(
                "Farmer name is required.",
                "error"
            )

            return redirect(
                url_for(
                    "farmers",
                    edit_id=farmer_id
                )
            )


        # =================================================
        # CHECK CID BELONGS TO ANOTHER FARMER
        # =================================================

        cursor.execute("""
            SELECT id
            FROM farmers
            WHERE cid = %s
              AND id != %s
        """, (
            cid,
            farmer_id
        ))

        duplicate_cid = cursor.fetchone()


        if duplicate_cid:

            flash(
                f"CID {cid} already belongs to another farmer.",
                "error"
            )

            return redirect(
                url_for(
                    "farmers",
                    edit_id=farmer_id
                )
            )


        # =================================================
        # UPDATE FARMER
        # =================================================

        cursor.execute("""
            UPDATE farmers
            SET
                cid = %s,
                name = %s,
                phone = %s,
                address = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (
            cid,
            name,
            phone,
            address,
            farmer_id
        ))


        connection.commit()


        flash(
            f"Farmer {name} updated successfully.",
            "success"
        )


        return redirect(
            url_for("farmers")
        )


    finally:

        cursor.close()

        release_db_connection(
            connection
        )


# =========================================================
# DELETE FARMER
# =========================================================

@app.route(
    "/farmers/delete/<int:farmer_id>",
    methods=["POST"]
)
def delete_farmer(farmer_id):

    connection = get_db_connection()

    try:

        cursor = connection.cursor()


        # =================================================
        # CHECK WHETHER FARMER HAS COLLECTION RECORDS
        # =================================================

        cursor.execute("""
            SELECT COUNT(*)
            FROM collection_entries
            WHERE farmer_id = %s
        """, (farmer_id,))

        collection_count = cursor.fetchone()[0]


        # =================================================
        # DON'T DELETE IF COLLECTION EXISTS
        # =================================================

        if collection_count > 0:

            flash(
                "This farmer cannot be deleted because collection records already exist.",
                "error"
            )

            return redirect(
                url_for("farmers")
            )


        # =================================================
        # DELETE FARMER
        # =================================================

        cursor.execute("""
            DELETE FROM farmers
            WHERE id = %s
        """, (farmer_id,))


        connection.commit()


        flash(
            "Farmer deleted successfully.",
            "success"
        )


        return redirect(
            url_for("farmers")
        )


    finally:

        cursor.close()

        release_db_connection(
            connection
        )


# =========================================================
# REPORTS
# =========================================================

@app.route("/reports")
def reports():

    return "Reports page - coming next"


# =========================================================
# BORROWING
# =========================================================

@app.route("/borrowing")
def borrowing():

    return "Borrowing page - coming next"


# =========================================================
# RATE SETTINGS
# =========================================================

@app.route("/settings", methods=["GET", "POST"])
def settings():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()


        # =================================================
        # SAVE RATE
        # =================================================

        if request.method == "POST":

            pricing_mode = request.form.get(
                "pricing_mode"
            )

            fat_rate_value = request.form.get(
                "fat_rate",
                ""
            ).strip()

            snf_rate_value = request.form.get(
                "snf_rate",
                ""
            ).strip()


            # -------------------------------------------------
            # CONVERT VALUES
            # -------------------------------------------------

            try:

                fat_rate = float(
                    fat_rate_value
                )

                snf_rate = float(
                    snf_rate_value
                    or 0
                )

            except ValueError:

                flash(
                    "Rate values must be valid numbers.",
                    "error"
                )

                return redirect(
                    url_for("settings")
                )


            # =================================================
            # VALIDATION
            # =================================================

            if fat_rate <= 0:

                flash(
                    "FAT rate must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for("settings")
                )


            if (
                pricing_mode == "FAT_SNF"
                and snf_rate <= 0
            ):

                flash(
                    "SNF rate must be greater than zero.",
                    "error"
                )

                return redirect(
                    url_for("settings")
                )


            # =================================================
            # REMOVE OLD RATE
            # =================================================

            cursor.execute("""
                DELETE FROM rate_settings
            """)


            # =================================================
            # INSERT NEW RATE
            # =================================================

            cursor.execute("""
                INSERT INTO rate_settings
                (
                    pricing_mode,
                    fat_rate,
                    snf_rate
                )

                VALUES
                (
                    %s,
                    %s,
                    %s
                )
            """, (
                pricing_mode,
                fat_rate,
                snf_rate
            ))


            # =================================================
            # COMMIT
            # =================================================

            connection.commit()


            # =================================================
            # SUCCESS MESSAGE
            # =================================================

            flash(
                "Rate settings saved successfully.",
                "success"
            )


            return redirect(
                url_for("settings")
            )


        # =================================================
        # GET CURRENT RATE
        # =================================================

        cursor.execute("""
            SELECT
                pricing_mode,
                fat_rate,
                snf_rate

            FROM rate_settings

            ORDER BY id DESC

            LIMIT 1
        """)

        rate = cursor.fetchone()


        # =================================================
        # RENDER SETTINGS
        # =================================================

        return render_template(
            "rate_settings.html",
            rate=rate
        )


    finally:

        cursor.close()

        release_db_connection(
            connection
        )


# =========================================================
# TEST DATABASE
# =========================================================

@app.route("/test-db")
def test_db():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        cursor.execute(
            "SELECT NOW()"
        )

        result = cursor.fetchone()


        return (
            "Database connected successfully!"
            "<br>"
            f"Neon time: {result[0]}"
        )


    finally:

        cursor.close()

        release_db_connection(
            connection
        )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )