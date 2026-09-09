-- ==========================================
-- ABC DAIRY DATABASE
-- ==========================================


-- ==========================================
-- FARMERS
-- ==========================================

CREATE TABLE IF NOT EXISTS farmers (

    id SERIAL PRIMARY KEY,

    cid VARCHAR(20) UNIQUE NOT NULL,

    name VARCHAR(100) NOT NULL,

    phone VARCHAR(20),

    address TEXT,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

);


-- ==========================================
-- RATE SETTINGS
-- ==========================================

CREATE TABLE IF NOT EXISTS rate_settings (

    id SERIAL PRIMARY KEY,

    pricing_mode VARCHAR(20) NOT NULL
        CHECK (pricing_mode IN ('FAT_ONLY', 'FAT_SNF')),

    fat_rate DECIMAL(10,4) NOT NULL,

    snf_rate DECIMAL(10,4) DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

);


-- ==========================================
-- MILK COLLECTION
-- ==========================================

CREATE TABLE IF NOT EXISTS collection_entries (

    id BIGSERIAL PRIMARY KEY,

    farmer_id INTEGER NOT NULL
        REFERENCES farmers(id),

    collection_date DATE NOT NULL,

    session VARCHAR(2) NOT NULL
        CHECK (session IN ('AM', 'PM')),

    fat DECIMAL(5,2) NOT NULL,

    snf DECIMAL(5,2),

    quantity DECIMAL(10,2) NOT NULL,

    rate DECIMAL(10,4) NOT NULL,

    amount DECIMAL(12,2) NOT NULL,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

);


-- ==========================================
-- BORROWINGS
-- ==========================================

CREATE TABLE IF NOT EXISTS borrowings (

    id BIGSERIAL PRIMARY KEY,

    farmer_id INTEGER NOT NULL
        REFERENCES farmers(id),

    amount DECIMAL(12,2) NOT NULL,

    description TEXT,

    borrowing_date DATE NOT NULL,

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP

);


-- ==========================================
-- INDEXES
-- ==========================================

CREATE INDEX IF NOT EXISTS idx_collection_date
ON collection_entries(collection_date);

CREATE INDEX IF NOT EXISTS idx_collection_farmer
ON collection_entries(farmer_id);

CREATE INDEX IF NOT EXISTS idx_borrowing_farmer
ON borrowings(farmer_id);

CREATE INDEX IF NOT EXISTS idx_borrowing_date
ON borrowings(borrowing_date);