import os

from decimal import Decimal, InvalidOperation
from datetime import date, timedelta

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash
)

from db import (
    get_db_connection,
    release_db_connection
)


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "abc-dairy-local-key"
)

_last_cleanup_date = None


# =========================================================
# HELPERS
# =========================================================

def decimal_value(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def get_billing_cycle(selected_date):
    """
    Billing cycles:

    1 - 10
    11 - 20
    21 - end of month
    """

    if selected_date.day <= 10:

        cycle_start = selected_date.replace(day=1)
        cycle_end = selected_date.replace(day=10)

    elif selected_date.day <= 20:

        cycle_start = selected_date.replace(day=11)
        cycle_end = selected_date.replace(day=20)

    else:

        cycle_start = selected_date.replace(day=21)

        if selected_date.month == 12:

            next_month = selected_date.replace(
                year=selected_date.year + 1,
                month=1,
                day=1
            )

        else:

            next_month = selected_date.replace(
                month=selected_date.month + 1,
                day=1
            )

        cycle_end = next_month - timedelta(days=1)

    return cycle_start, cycle_end


def parse_date(value):

    try:

        return date.fromisoformat(value)

    except (ValueError, TypeError):

        return date.today()


# =========================================================
# AUTOMATIC 3-MONTH CLEANUP
# =========================================================

def cleanup_old_collection_data():
    """
    Automatically remove collection records
    older than 3 months.
    """

    connection = None
    cursor = None

    try:

        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            DELETE FROM collection_entries
            WHERE collection_date < (
                CURRENT_DATE - INTERVAL '3 months'
            )
        """)

        connection.commit()

    except Exception:

        if connection:
            connection.rollback()

    finally:

        if cursor:
            cursor.close()

        if connection:
            release_db_connection(connection)


@app.before_request
def auto_cleanup_old_collection_data():

    # Run cleanup only once per application process
    # per calendar day so normal page navigation
    # is not unnecessarily slowed down.

    global _last_cleanup_date

    today = date.today()

    if _last_cleanup_date == today:
        return

    cleanup_old_collection_data()

    _last_cleanup_date = today


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
        # TODAY SUMMARY
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COALESCE(SUM(quantity), 0),
                COALESCE(SUM(amount), 0),
                COUNT(*)
            FROM collection_entries
            WHERE collection_date = %s
        """, (today,))

        today_milk, today_amount, today_entries = (
            cursor.fetchone()
        )

        # -------------------------------------------------
        # FARMERS
        # -------------------------------------------------

        cursor.execute("""
            SELECT COUNT(*)
            FROM farmers
        """)

        active_farmers = cursor.fetchone()[0]

        # -------------------------------------------------
        # TODAY COLLECTIONS
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
                CASE
                    WHEN ce.session = 'PM' THEN 2
                    ELSE 1
                END DESC,
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

@app.route(
    "/collection",
    methods=["GET", "POST"]
)
def collection():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # CURRENT RATE
        # -------------------------------------------------

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

        # -------------------------------------------------
        # DEFAULT DATE + SESSION
        # -------------------------------------------------

        selected_date = request.args.get(
            "date",
            date.today().isoformat()
        )

        selected_session = request.args.get(
            "session",
            "AM"
        )

        # -------------------------------------------------
        # EDIT DATA
        # -------------------------------------------------

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

        # -------------------------------------------------
        # SAVE COLLECTION
        # -------------------------------------------------

        if request.method == "POST":

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

            # ---------------------------------------------
            # VALIDATION
            # ---------------------------------------------

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

            # ---------------------------------------------
            # CONVERT NUMBERS
            # ---------------------------------------------

            try:

                fat = float(fat_value)

                quantity = float(
                    quantity_value
                )

                # SNF is optional.
                # When not enabled/not entered,
                # store it as 0.

                snf = (
                    float(snf_value)
                    if snf_value
                    else 0
                )

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

            # ---------------------------------------------
            # NUMBER VALIDATION
            # ---------------------------------------------

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

            if snf < 0:

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

            # ---------------------------------------------
            # RATE CHECK
            # ---------------------------------------------

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

            # ---------------------------------------------
            # FIND FARMER
            # ---------------------------------------------

            cursor.execute("""
                SELECT id
                FROM farmers
                WHERE cid = %s
            """, (cid,))

            farmer = cursor.fetchone()

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

            # ---------------------------------------------
            # CALCULATE RATE
            # ---------------------------------------------

            if (
                pricing_mode == "FAT_SNF"
                and snf_value
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

            amount = (
                milk_rate * quantity
            )

            # ---------------------------------------------
            # CHECK EXISTING
            # ---------------------------------------------

            cursor.execute("""
                SELECT id
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

            # ---------------------------------------------
            # INSERT / UPDATE
            #
            # SAME CID + SAME DATE + SAME SESSION
            # = UPDATE EXISTING RECORD
            #
            # DIFFERENT DATE OR SESSION
            # = NEW RECORD
            # ---------------------------------------------

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

            connection.commit()

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

            return redirect(
                url_for(
                    "collection",
                    saved="1",
                    date=collection_date,
                    session=session
                )
            )

        # -------------------------------------------------
        # SAVED FLAG
        # -------------------------------------------------

        saved = (
            request.args.get("saved") == "1"
        )

        # -------------------------------------------------
        # RECENT COLLECTIONS
        # -------------------------------------------------

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
                    WHEN ce.session = 'PM' THEN 2
                    ELSE 1
                END DESC,
                ce.id DESC
            LIMIT 10
        """)

        recent_collections = (
            cursor.fetchall()
        )

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
        release_db_connection(connection)


# =========================================================
# FARMERS
# =========================================================

@app.route(
    "/farmers",
    methods=["GET", "POST"]
)
def farmers():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # ADD FARMER
        # -------------------------------------------------

        if request.method == "POST":

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

            cursor.execute("""
                SELECT id
                FROM farmers
                WHERE cid = %s
            """, (cid,))

            existing_farmer = (
                cursor.fetchone()
            )

            if existing_farmer:

                flash(
                    f"CID {cid} already exists.",
                    "error"
                )

                return redirect(
                    url_for("farmers")
                )

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

        # -------------------------------------------------
        # SEARCH
        # -------------------------------------------------

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

        farmers_list = (
            cursor.fetchall()
        )

        # -------------------------------------------------
        # EDIT
        # -------------------------------------------------

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

            edit_farmer = (
                cursor.fetchone()
            )

        return render_template(
            "farmers.html",
            farmers=farmers_list,
            edit_farmer=edit_farmer,
            search=search
        )

    finally:

        cursor.close()
        release_db_connection(connection)


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

        cursor.execute("""
            SELECT id
            FROM farmers
            WHERE cid = %s
              AND id != %s
        """, (
            cid,
            farmer_id
        ))

        duplicate_cid = (
            cursor.fetchone()
        )

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
        release_db_connection(connection)


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

        cursor.execute("""
            SELECT COUNT(*)
            FROM collection_entries
            WHERE farmer_id = %s
        """, (farmer_id,))

        collection_count = (
            cursor.fetchone()[0]
        )

        if collection_count > 0:

            flash(
                "This farmer cannot be deleted because collection records already exist.",
                "error"
            )

            return redirect(
                url_for("farmers")
            )

        cursor.execute("""
            SELECT COUNT(*)
            FROM borrowings
            WHERE farmer_id = %s
        """, (farmer_id,))

        borrowing_count = (
            cursor.fetchone()[0]
        )

        if borrowing_count > 0:

            flash(
                "This farmer cannot be deleted because borrowing records already exist.",
                "error"
            )

            return redirect(
                url_for("farmers")
            )

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
        release_db_connection(connection)


# =========================================================
# FARMER VIEW
# =========================================================

@app.route(
    "/farmers/view/<int:farmer_id>"
)
def view_farmer(farmer_id):

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # FARMER
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                cid,
                name,
                phone,
                address,
                created_at
            FROM farmers
            WHERE id = %s
        """, (farmer_id,))

        farmer = cursor.fetchone()

        if not farmer:

            flash(
                "Farmer not found.",
                "error"
            )

            return redirect(
                url_for("farmers")
            )

        # -------------------------------------------------
        # COLLECTION HISTORY
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                collection_date,
                session,
                fat,
                snf,
                quantity,
                rate,
                amount
            FROM collection_entries
            WHERE farmer_id = %s
            ORDER BY
                collection_date DESC,
                id DESC
        """, (farmer_id,))

        collections = (
            cursor.fetchall()
        )

        # -------------------------------------------------
        # ANALYTICS
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(quantity), 0),
                COALESCE(SUM(amount), 0),
                COALESCE(AVG(quantity), 0),
                COALESCE(AVG(fat), 0),
                COALESCE(AVG(snf), 0)
            FROM collection_entries
            WHERE farmer_id = %s
        """, (farmer_id,))

        analysis = (
            cursor.fetchone()
        )

        # -------------------------------------------------
        # BORROWING SUMMARY
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COALESCE(SUM(amount), 0),
                COALESCE(SUM(deducted_amount), 0),
                COALESCE(SUM(remaining_amount), 0)
            FROM borrowings
            WHERE farmer_id = %s
        """, (farmer_id,))

        borrowing_summary = (
            cursor.fetchone()
        )

        # -------------------------------------------------
        # BORROWING HISTORY
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                b.id,
                b.amount,
                b.deducted_amount,
                b.remaining_amount,
                b.description,
                b.borrowing_date
            FROM borrowings b
            WHERE b.farmer_id = %s
            ORDER BY
                b.borrowing_date DESC,
                b.id DESC
        """, (farmer_id,))

        borrowings = (
            cursor.fetchall()
        )

        # -------------------------------------------------
        # BILLING HISTORY
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                cycle_start,
                cycle_end,
                gross_amount,
                borrowing_deduction,
                net_amount,
                created_at
            FROM billing_cycles
            WHERE farmer_id = %s
            ORDER BY
                cycle_start DESC,
                id DESC
        """, (farmer_id,))

        billing_history = (
            cursor.fetchall()
        )

        return render_template(
            "farmer_view.html",
            farmer=farmer,
            collections=collections,
            analysis=analysis,
            borrowing_summary=borrowing_summary,
            borrowings=borrowings,
            billing_history=billing_history
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# REPORTS
# =========================================================

@app.route("/reports")
def reports():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        today = date.today()

        default_from = today.replace(day=1)

        from_date = parse_date(
            request.args.get(
                "from_date"
            ) or default_from.isoformat()
        )

        to_date = parse_date(
            request.args.get(
                "to_date"
            ) or today.isoformat()
        )

        cid = request.args.get(
            "cid",
            ""
        ).strip()

        cid_from = request.args.get(
            "cid_from",
            ""
        ).strip()

        cid_to = request.args.get(
            "cid_to",
            ""
        ).strip()

        session = request.args.get(
            "session",
            ""
        ).strip().upper()

        if from_date > to_date:

            from_date, to_date = (
                to_date,
                from_date
            )

        conditions = [
            "ce.collection_date BETWEEN %s AND %s"
        ]

        params = [
            from_date,
            to_date
        ]

        # -------------------------------------------------
        # EXACT CID
        # -------------------------------------------------

        if cid:

            conditions.append(
                "f.cid = %s"
            )

            params.append(cid)

        # -------------------------------------------------
        # CID RANGE
        # -------------------------------------------------

        else:

            try:

                cid_from_value = (
                    int(cid_from)
                    if cid_from
                    else None
                )

                cid_to_value = (
                    int(cid_to)
                    if cid_to
                    else None
                )

            except ValueError:

                cid_from_value = None
                cid_to_value = None

                cid_from = ""
                cid_to = ""

                flash(
                    "CID range must contain numbers only.",
                    "error"
                )

            if cid_from_value is not None:

                conditions.append("""
                    CAST(
                        NULLIF(
                            regexp_replace(
                                f.cid,
                                '[^0-9]',
                                '',
                                'g'
                            )
                            ,
                            ''
                        ) AS BIGINT
                    ) >= %s
                """)

                params.append(
                    cid_from_value
                )

            if cid_to_value is not None:

                conditions.append("""
                    CAST(
                        NULLIF(
                            regexp_replace(
                                f.cid,
                                '[^0-9]',
                                '',
                                'g'
                            )
                            ,
                            ''
                        ) AS BIGINT
                    ) <= %s
                """)

                params.append(
                    cid_to_value
                )

        # -------------------------------------------------
        # SESSION
        # -------------------------------------------------

        if session in ("AM", "PM"):

            conditions.append(
                "ce.session = %s"
            )

            params.append(
                session
            )

        else:

            session = ""

        where_sql = (
            " AND ".join(
                conditions
            )
        )

        # -------------------------------------------------
        # OVERALL SUMMARY
        # -------------------------------------------------

        cursor.execute(f"""
            SELECT
                COUNT(*) AS total_entries,

                COALESCE(
                    SUM(ce.quantity),
                    0
                ) AS total_quantity,

                COALESCE(
                    SUM(ce.amount),
                    0
                ) AS total_amount,

                COALESCE(
                    AVG(ce.quantity),
                    0
                ) AS avg_quantity,

                COALESCE(
                    AVG(ce.fat),
                    0
                ) AS avg_fat,

                COALESCE(
                    AVG(ce.snf),
                    0
                ) AS avg_snf,

                COALESCE(
                    AVG(ce.rate),
                    0
                ) AS avg_rate

            FROM collection_entries ce

            JOIN farmers f
                ON f.id = ce.farmer_id

            WHERE {where_sql}
        """, tuple(params))

        summary_row = cursor.fetchone()

        class Summary:

            total_entries = summary_row[0]
            total_quantity = summary_row[1]
            total_amount = summary_row[2]
            avg_quantity = summary_row[3]
            avg_fat = summary_row[4]
            avg_snf = summary_row[5]
            avg_rate = summary_row[6]

        # -------------------------------------------------
        # DAY-WISE SUMMARY
        # -------------------------------------------------

        cursor.execute(f"""
            SELECT
                ce.collection_date,
                COUNT(*),
                COALESCE(
                    SUM(ce.quantity),
                    0
                ),
                COALESCE(
                    AVG(ce.fat),
                    0
                ),
                COALESCE(
                    AVG(ce.snf),
                    0
                ),
                COALESCE(
                    AVG(ce.rate),
                    0
                ),
                COALESCE(
                    SUM(ce.amount),
                    0
                )

            FROM collection_entries ce

            JOIN farmers f
                ON f.id = ce.farmer_id

            WHERE {where_sql}

            GROUP BY
                ce.collection_date

            ORDER BY
                ce.collection_date DESC
        """, tuple(params))

        daywise = cursor.fetchall()

        # -------------------------------------------------
        # FARMER-WISE SUMMARY
        # -------------------------------------------------

        cursor.execute(f"""
            SELECT
                f.cid,
                f.name,
                COUNT(*),
                COALESCE(
                    SUM(ce.quantity),
                    0
                ),
                COALESCE(
                    AVG(ce.fat),
                    0
                ),
                COALESCE(
                    AVG(ce.snf),
                    0
                ),
                COALESCE(
                    AVG(ce.rate),
                    0
                ),
                COALESCE(
                    SUM(ce.amount),
                    0
                )

            FROM collection_entries ce

            JOIN farmers f
                ON f.id = ce.farmer_id

            WHERE {where_sql}

            GROUP BY
                f.id,
                f.cid,
                f.name

            ORDER BY
                CAST(
                    NULLIF(
                        regexp_replace(
                            f.cid,
                            '[^0-9]',
                            '',
                            'g'
                        ),
                        ''
                    ) AS BIGINT
                ) NULLS LAST,
                f.cid
        """, tuple(params))

        farmerwise = cursor.fetchall()

        # -------------------------------------------------
        # COLLECTION DETAILS
        # -------------------------------------------------

        cursor.execute(f"""
            SELECT
                ce.collection_date,
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

            WHERE {where_sql}

            ORDER BY
                CAST(
                    NULLIF(
                        regexp_replace(
                            f.cid,
                            '[^0-9]',
                            '',
                            'g'
                        ),
                        ''
                    ) AS BIGINT
                ) NULLS LAST,

                f.cid,

                ce.collection_date ASC,

                CASE
                    WHEN ce.session = 'AM'
                    THEN 1
                    ELSE 2
                END ASC,

                ce.id ASC
        """, tuple(params))

        details = cursor.fetchall()

        return render_template(
            "reports.html",
            summary=Summary,
            daywise=daywise,
            farmerwise=farmerwise,
            details=details,
            from_date=from_date.isoformat(),
            to_date=to_date.isoformat(),
            cid=cid,
            cid_from=cid_from,
            cid_to=cid_to,
            session=session
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# BORROWING
# =========================================================

@app.route(
    "/borrowing",
    methods=["GET", "POST"]
)
def borrowing():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # ADD BORROWING
        # -------------------------------------------------

        if request.method == "POST":

            cid = request.form.get(
                "cid",
                ""
            ).strip()

            amount_value = request.form.get(
                "amount",
                ""
            ).strip()

            borrowing_date = request.form.get(
                "borrowing_date",
                ""
            ).strip()

            description = request.form.get(
                "description",
                ""
            ).strip()

            if not cid:

                flash(
                    "CID is required.",
                    "error"
                )

                return redirect(
                    url_for("borrowing")
                )

            if not amount_value:

                flash(
                    "Borrowing amount is required.",
                    "error"
                )

                return redirect(
                    url_for("borrowing")
                )

            try:

                amount = Decimal(
                    amount_value
                )

            except InvalidOperation:

                flash(
                    "Borrowing amount must be valid.",
                    "error"
                )

                return redirect(
                    url_for("borrowing")
                )

            if amount <= 0:

                flash(
                    "Borrowing amount must be greater than 0.",
                    "error"
                )

                return redirect(
                    url_for("borrowing")
                )

            if not borrowing_date:

                borrowing_date = (
                    date.today().isoformat()
                )

            # ---------------------------------------------
            # FIND FARMER
            # ---------------------------------------------

            cursor.execute("""
                SELECT id
                FROM farmers
                WHERE cid = %s
            """, (cid,))

            farmer = cursor.fetchone()

            if not farmer:

                flash(
                    f"Farmer with CID {cid} was not found.",
                    "error"
                )

                return redirect(
                    url_for("borrowing")
                )

            farmer_id = farmer[0]

            # ---------------------------------------------
            # INSERT
            # ---------------------------------------------

            cursor.execute("""
                INSERT INTO borrowings
                (
                    farmer_id,
                    amount,
                    deducted_amount,
                    remaining_amount,
                    description,
                    borrowing_date
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
            """, (
                farmer_id,
                amount,
                Decimal("0"),
                amount,
                description,
                borrowing_date
            ))

            connection.commit()

            flash(
                f"Borrowing of ₹{amount:.2f} added successfully.",
                "success"
            )

            return redirect(
                url_for("borrowing")
            )

        # -------------------------------------------------
        # BORROWING HISTORY
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                b.id,
                f.cid,
                f.name,
                b.amount,
                COALESCE(
                    b.deducted_amount,
                    0
                ),
                COALESCE(
                    b.remaining_amount,
                    b.amount
                ),
                b.description,
                b.borrowing_date

            FROM borrowings b

            JOIN farmers f
                ON f.id = b.farmer_id

            ORDER BY
                b.borrowing_date DESC,
                b.id DESC
        """)

        borrowings = (
            cursor.fetchall()
        )

        # -------------------------------------------------
        # SUMMARY
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COALESCE(
                    SUM(amount),
                    0
                ),
                COALESCE(
                    SUM(deducted_amount),
                    0
                ),
                COALESCE(
                    SUM(remaining_amount),
                    0
                )
            FROM borrowings
        """)

        borrowing_summary = (
            cursor.fetchone()
        )

        return render_template(
            "borrowing.html",
            borrowings=borrowings,
            borrowing_summary=borrowing_summary
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# EDIT BORROWING
# =========================================================

@app.route(
    "/borrowing/edit/<int:borrowing_id>",
    methods=["POST"]
)
def edit_borrowing(borrowing_id):

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        farmer_id_redirect = request.form.get(
            "farmer_id",
            ""
        ).strip()

        amount_value = request.form.get(
            "amount",
            ""
        ).strip()

        borrowing_date = request.form.get(
            "borrowing_date",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        if not amount_value or not borrowing_date:

            flash(
                "Amount and date are required.",
                "error"
            )

            return redirect(
                url_for(
                    "view_farmer",
                    farmer_id=int(
                        farmer_id_redirect
                    )
                )
                if farmer_id_redirect.isdigit()
                else url_for("borrowing")
            )

        try:

            amount = Decimal(
                amount_value
            )

        except InvalidOperation:

            flash(
                "Borrowing amount must be valid.",
                "error"
            )

            return redirect(
                url_for(
                    "view_farmer",
                    farmer_id=int(
                        farmer_id_redirect
                    )
                )
                if farmer_id_redirect.isdigit()
                else url_for("borrowing")
            )

        if amount <= 0:

            flash(
                "Borrowing amount must be greater than 0.",
                "error"
            )

            return redirect(
                url_for(
                    "view_farmer",
                    farmer_id=int(
                        farmer_id_redirect
                    )
                )
                if farmer_id_redirect.isdigit()
                else url_for("borrowing")
            )

        cursor.execute("""
            SELECT
                amount,
                COALESCE(
                    deducted_amount,
                    0
                )
            FROM borrowings
            WHERE id = %s
        """, (borrowing_id,))

        record = cursor.fetchone()

        if not record:

            flash(
                "Borrowing record not found.",
                "error"
            )

            return redirect(
                url_for(
                    "view_farmer",
                    farmer_id=int(
                        farmer_id_redirect
                    )
                )
                if farmer_id_redirect.isdigit()
                else url_for("borrowing")
            )

        deducted_amount = decimal_value(
            record[1]
        )

        if amount < deducted_amount:

            flash(
                f"Amount cannot be less than already deducted amount ₹{deducted_amount:.2f}.",
                "error"
            )

            return redirect(
                url_for(
                    "view_farmer",
                    farmer_id=int(
                        farmer_id_redirect
                    )
                )
                if farmer_id_redirect.isdigit()
                else url_for("borrowing")
            )

        remaining_amount = (
            amount - deducted_amount
        )

        cursor.execute("""
            UPDATE borrowings
            SET
                amount = %s,
                remaining_amount = %s,
                borrowing_date = %s,
                description = %s
            WHERE id = %s
        """, (
            amount,
            remaining_amount,
            borrowing_date,
            description,
            borrowing_id
        ))

        connection.commit()

        flash(
            "Borrowing updated successfully.",
            "success"
        )

        return redirect(
            url_for(
                "view_farmer",
                farmer_id=int(
                    farmer_id_redirect
                )
            )
            if farmer_id_redirect.isdigit()
            else url_for("borrowing")
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# DELETE BORROWING
# =========================================================

@app.route(
    "/borrowing/delete/<int:borrowing_id>",
    methods=["POST"]
)
def delete_borrowing(borrowing_id):

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                amount,
                COALESCE(
                    deducted_amount,
                    0
                )
            FROM borrowings
            WHERE id = %s
        """, (borrowing_id,))

        record = cursor.fetchone()

        if not record:

            flash(
                "Borrowing record not found.",
                "error"
            )

            return redirect(
                url_for("borrowing")
            )

        amount = decimal_value(
            record[0]
        )

        deducted_amount = decimal_value(
            record[1]
        )

        if deducted_amount > 0:

            flash(
                "This borrowing cannot be deleted because part of it has already been deducted.",
                "error"
            )

            return redirect(
                url_for("borrowing")
            )

        cursor.execute("""
            DELETE FROM borrowings
            WHERE id = %s
        """, (borrowing_id,))

        connection.commit()

        flash(
            f"Borrowing of ₹{amount:.2f} deleted successfully.",
            "success"
        )

        return redirect(
            url_for("borrowing")
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# PRINT RECEIPT
# =========================================================

@app.route("/reports/receipt")
def reports_receipt():

    cid = request.args.get(
        "cid",
        ""
    ).strip()

    date_from = request.args.get(
        "date_from",
        ""
    ).strip()

    date_to = request.args.get(
        "date_to",
        ""
    ).strip()

    if not cid:

        flash(
            "Please select a CID to print the receipt.",
            "error"
        )

        return redirect(
            url_for("reports")
        )

    # Use valid defaults if dates are missing.

    if not date_from:

        date_from = (
            date.today()
            .replace(day=1)
            .isoformat()
        )

    if not date_to:

        date_to = (
            date.today()
            .isoformat()
        )

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        cursor.execute("""
            SELECT
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

            WHERE f.cid = %s

              AND ce.collection_date
                  BETWEEN %s AND %s

            ORDER BY
                ce.collection_date ASC,

                CASE
                    WHEN ce.session = 'AM'
                    THEN 1
                    ELSE 2
                END ASC,

                ce.id ASC
        """, (
            cid,
            date_from,
            date_to
        ))

        entries = cursor.fetchall()

        if not entries:

            flash(
                "No collection records found for this CID.",
                "error"
            )

            return redirect(
                url_for(
                    "reports",
                    from_date=date_from,
                    to_date=date_to,
                    cid=cid
                )
            )

        return render_template(
            "reports_receipt.html",
            entries=entries,
            cid=cid,
            date_from=date_from,
            date_to=date_to
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# BILLING HOME
# =========================================================

@app.route("/billing")
def billing_home():

    return redirect(
        url_for("farmers")
    )


# =========================================================
# BILLING
# =========================================================

@app.route(
    "/billing/<int:farmer_id>"
)
def billing(farmer_id):

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # FARMER
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                cid,
                name,
                phone,
                address
            FROM farmers
            WHERE id = %s
        """, (farmer_id,))

        farmer = cursor.fetchone()

        if not farmer:

            flash(
                "Farmer not found.",
                "error"
            )

            return redirect(
                url_for("farmers")
            )

        # -------------------------------------------------
        # SELECT DATE
        # -------------------------------------------------

        selected_date = parse_date(
            request.args.get(
                "date",
                date.today().isoformat()
            )
        )

        cycle_start, cycle_end = (
            get_billing_cycle(
                selected_date
            )
        )

        # -------------------------------------------------
        # GROSS BILL
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(quantity), 0),
                COALESCE(SUM(amount), 0),
                COALESCE(AVG(fat), 0),
                COALESCE(AVG(snf), 0)

            FROM collection_entries

            WHERE farmer_id = %s

              AND collection_date
                  BETWEEN %s AND %s
        """, (
            farmer_id,
            cycle_start,
            cycle_end
        ))

        summary = cursor.fetchone()

        collection_count = summary[0]

        total_quantity = decimal_value(
            summary[1]
        )

        gross_amount = decimal_value(
            summary[2]
        )

        average_fat = decimal_value(
            summary[3]
        )

        average_snf = decimal_value(
            summary[4]
        )

        # -------------------------------------------------
        # CHECK FINALIZED BILL
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                gross_amount,
                borrowing_deduction,
                net_amount,
                created_at

            FROM billing_cycles

            WHERE farmer_id = %s
              AND cycle_start = %s
              AND cycle_end = %s
        """, (
            farmer_id,
            cycle_start,
            cycle_end
        ))

        finalized_bill = (
            cursor.fetchone()
        )

        borrowings = []

        # -------------------------------------------------
        # ALREADY FINALIZED
        # -------------------------------------------------

        if finalized_bill:

            billing_cycle_id = (
                finalized_bill[0]
            )

            cursor.execute("""
                SELECT
                    b.id,
                    b.amount,
                    b.deducted_amount,
                    b.remaining_amount,
                    b.description,
                    b.borrowing_date,
                    bbd.deducted_amount

                FROM billing_borrowing_deductions bbd

                JOIN borrowings b
                    ON b.id = bbd.borrowing_id

                WHERE bbd.billing_cycle_id = %s

                ORDER BY
                    b.borrowing_date ASC,
                    b.id ASC
            """, (
                billing_cycle_id
            ))

            rows = cursor.fetchall()

            for row in rows:

                borrowings.append({
                    "id": row[0],
                    "amount": decimal_value(row[1]),
                    "deducted_amount": decimal_value(row[2]),
                    "remaining_amount": decimal_value(row[3]),
                    "description": row[4],
                    "borrowing_date": row[5],
                    "deduction": decimal_value(row[6])
                })

            borrowing_deduction = decimal_value(
                finalized_bill[2]
            )

            net_amount = decimal_value(
                finalized_bill[3]
            )

        # -------------------------------------------------
        # PROPOSED DEDUCTIONS
        # -------------------------------------------------

        else:

            cursor.execute("""
                SELECT
                    id,
                    amount,
                    COALESCE(
                        deducted_amount,
                        0
                    ),
                    COALESCE(
                        remaining_amount,
                        amount
                    ),
                    description,
                    borrowing_date

                FROM borrowings

                WHERE farmer_id = %s

                  AND COALESCE(
                        remaining_amount,
                        amount
                      ) > 0

                ORDER BY
                    borrowing_date ASC,
                    id ASC
            """, (
                farmer_id
            ))

            rows = cursor.fetchall()

            remaining_bill = (
                gross_amount
            )

            for row in rows:

                amount = decimal_value(
                    row[1]
                )

                deducted_amount = decimal_value(
                    row[2]
                )

                remaining_amount = decimal_value(
                    row[3]
                )

                if remaining_bill > 0:

                    deduction = min(
                        remaining_amount,
                        remaining_bill
                    )

                    remaining_bill -= (
                        deduction
                    )

                else:

                    deduction = Decimal("0")

                borrowings.append({
                    "id": row[0],
                    "amount": amount,
                    "deducted_amount": deducted_amount,
                    "remaining_amount": remaining_amount,
                    "description": row[4],
                    "borrowing_date": row[5],
                    "deduction": deduction
                })

            borrowing_deduction = (
                gross_amount
                -
                remaining_bill
            )

            net_amount = (
                gross_amount
                -
                borrowing_deduction
            )

        return render_template(
            "billing.html",

            farmer=farmer,

            cycle_start=cycle_start,
            cycle_end=cycle_end,

            collection_count=collection_count,
            total_quantity=total_quantity,
            average_fat=average_fat,
            average_snf=average_snf,

            gross_amount=gross_amount,
            borrowing_deduction=borrowing_deduction,
            net_amount=net_amount,

            borrowings=borrowings,

            finalized_bill=finalized_bill
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# FINALIZE BILL
# =========================================================

@app.route(
    "/billing/<int:farmer_id>/finalize",
    methods=["POST"]
)
def finalize_billing(farmer_id):

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # BILLING DATE
        # -------------------------------------------------

        selected_date = parse_date(
            request.form.get(
                "billing_date",
                date.today().isoformat()
            )
        )

        cycle_start, cycle_end = (
            get_billing_cycle(
                selected_date
            )
        )

        # -------------------------------------------------
        # CHECK FARMER
        # -------------------------------------------------

        cursor.execute("""
            SELECT id
            FROM farmers
            WHERE id = %s
        """, (
            farmer_id
        ))

        farmer = cursor.fetchone()

        if not farmer:

            flash(
                "Farmer not found.",
                "error"
            )

            return redirect(
                url_for("farmers")
            )

        # -------------------------------------------------
        # CHECK EXISTING BILL
        # -------------------------------------------------

        cursor.execute("""
            SELECT id

            FROM billing_cycles

            WHERE farmer_id = %s
              AND cycle_start = %s
              AND cycle_end = %s

            FOR UPDATE
        """, (
            farmer_id,
            cycle_start,
            cycle_end
        ))

        existing_bill = (
            cursor.fetchone()
        )

        if existing_bill:

            flash(
                "This billing cycle has already been finalized.",
                "error"
            )

            return redirect(
                url_for(
                    "billing",
                    farmer_id=farmer_id,
                    date=selected_date.isoformat()
                )
            )

        # -------------------------------------------------
        # GROSS BILL
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                COALESCE(
                    SUM(amount),
                    0
                )

            FROM collection_entries

            WHERE farmer_id = %s

              AND collection_date
                  BETWEEN %s AND %s
        """, (
            farmer_id,
            cycle_start,
            cycle_end
        ))

        gross_amount = decimal_value(
            cursor.fetchone()[0]
        )

        # -------------------------------------------------
        # CREATE BILL
        # -------------------------------------------------

        cursor.execute("""
            INSERT INTO billing_cycles
            (
                farmer_id,
                cycle_start,
                cycle_end,
                gross_amount,
                borrowing_deduction,
                net_amount
            )

            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )

            RETURNING id
        """, (
            farmer_id,
            cycle_start,
            cycle_end,
            gross_amount,
            Decimal("0"),
            gross_amount
        ))

        billing_cycle_id = (
            cursor.fetchone()[0]
        )

        # -------------------------------------------------
        # OUTSTANDING BORROWINGS
        # OLDEST FIRST
        # -------------------------------------------------

        cursor.execute("""
            SELECT
                id,
                COALESCE(
                    remaining_amount,
                    amount
                )

            FROM borrowings

            WHERE farmer_id = %s

              AND COALESCE(
                    remaining_amount,
                    amount
                  ) > 0

            ORDER BY
                borrowing_date ASC,
                id ASC

            FOR UPDATE
        """, (
            farmer_id
        ))

        borrowing_rows = (
            cursor.fetchall()
        )

        remaining_bill = (
            gross_amount
        )

        total_deduction = (
            Decimal("0")
        )

        # -------------------------------------------------
        # APPLY DEDUCTIONS
        # -------------------------------------------------

        for borrowing_id, remaining_value in (
            borrowing_rows
        ):

            if remaining_bill <= 0:
                break

            remaining_amount = decimal_value(
                remaining_value
            )

            deduction = min(
                remaining_amount,
                remaining_bill
            )

            if deduction <= 0:
                continue

            total_deduction += (
                deduction
            )

            remaining_bill -= (
                deduction
            )

            # ---------------------------------------------
            # UPDATE BORROWING
            # ---------------------------------------------

            cursor.execute("""
                UPDATE borrowings

                SET
                    deducted_amount =
                        COALESCE(
                            deducted_amount,
                            0
                        ) + %s,

                    remaining_amount =
                        COALESCE(
                            remaining_amount,
                            amount
                        ) - %s

                WHERE id = %s
            """, (
                deduction,
                deduction,
                borrowing_id
            ))

            # ---------------------------------------------
            # RECORD ALLOCATION
            # ---------------------------------------------

            cursor.execute("""
                INSERT INTO
                    billing_borrowing_deductions
                (
                    billing_cycle_id,
                    borrowing_id,
                    deducted_amount
                )

                VALUES
                (
                    %s,
                    %s,
                    %s
                )
            """, (
                billing_cycle_id,
                borrowing_id,
                deduction
            ))

        # -------------------------------------------------
        # NET PAYABLE
        # -------------------------------------------------

        net_amount = (
            gross_amount
            -
            total_deduction
        )

        # -------------------------------------------------
        # UPDATE BILL
        # -------------------------------------------------

        cursor.execute("""
            UPDATE billing_cycles

            SET
                borrowing_deduction = %s,
                net_amount = %s

            WHERE id = %s
        """, (
            total_deduction,
            net_amount,
            billing_cycle_id
        ))

        # -------------------------------------------------
        # COMMIT EVERYTHING
        # -------------------------------------------------

        connection.commit()

        flash(
            f"Bill finalized successfully. "
            f"Net payable: ₹{net_amount:.2f}",
            "success"
        )

        return redirect(
            url_for(
                "billing",
                farmer_id=farmer_id,
                date=selected_date.isoformat()
            )
        )

    except Exception as e:

        connection.rollback()

        print(
            "FINALIZE BILL ERROR:",
            e
        )

        flash(
            "Bill could not be finalized. No changes were saved.",
            "error"
        )

        return redirect(
            url_for(
                "billing",
                farmer_id=farmer_id
            )
        )

    finally:

        cursor.close()
        release_db_connection(connection)


# =========================================================
# RATE SETTINGS
# =========================================================

@app.route(
    "/settings",
    methods=["GET", "POST"]
)
def settings():

    connection = get_db_connection()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # SAVE RATE
        # -------------------------------------------------

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

            try:

                fat_rate = float(
                    fat_rate_value
                )

                snf_rate = float(
                    snf_rate_value or 0
                )

            except ValueError:

                flash(
                    "Rate values must be valid numbers.",
                    "error"
                )

                return redirect(
                    url_for("settings")
                )

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

            # ---------------------------------------------
            # REMOVE OLD RATE
            # ---------------------------------------------

            cursor.execute("""
                DELETE FROM rate_settings
            """)

            # ---------------------------------------------
            # INSERT NEW RATE
            # ---------------------------------------------

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

            connection.commit()

            flash(
                "Rate settings saved successfully.",
                "success"
            )

            return redirect(
                url_for("settings")
            )

        # -------------------------------------------------
        # CURRENT RATE
        # -------------------------------------------------

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

        return render_template(
            "rate_settings.html",
            rate=rate
        )

    finally:

        cursor.close()
        release_db_connection(connection)


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
        release_db_connection(connection)


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )