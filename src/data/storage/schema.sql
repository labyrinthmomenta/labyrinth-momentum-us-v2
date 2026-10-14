CREATE TABLE issuers (
 issuer_id INTEGER PRIMARY KEY,
 name TEXT NOT NULL CHECK(length(trim(name)) > 0),
 cik TEXT UNIQUE CHECK(cik IS NULL OR (length(cik)=10 AND cik NOT GLOB '*[^0-9]*')),
 evidence TEXT NOT NULL CHECK(length(trim(evidence)) > 0)
);
CREATE TABLE securities (
 security_id INTEGER PRIMARY KEY AUTOINCREMENT,
 issuer_id INTEGER REFERENCES issuers(issuer_id),
 share_class TEXT NOT NULL,
 instrument_type TEXT NOT NULL,
 evidence TEXT NOT NULL CHECK(length(trim(evidence)) > 0)
);
CREATE TABLE listings (
 listing_id INTEGER PRIMARY KEY,
 security_id INTEGER NOT NULL REFERENCES securities(security_id),
 mic TEXT NOT NULL CHECK(mic IN ('XNAS','XNYS','XASE')),
 currency TEXT NOT NULL CHECK(currency='USD'),
 valid_from TEXT NOT NULL CHECK(length(valid_from)=10 AND date(valid_from,'+0 days') IS NOT NULL AND date(valid_from,'+0 days')=valid_from),
 valid_to TEXT CHECK(valid_to IS NULL OR (length(valid_to)=10 AND date(valid_to,'+0 days') IS NOT NULL AND date(valid_to,'+0 days')=valid_to AND valid_to>valid_from)),
 evidence TEXT NOT NULL CHECK(length(trim(evidence)) > 0)
);
CREATE TABLE identifiers (
 identifier_id INTEGER PRIMARY KEY,
 security_id INTEGER NOT NULL REFERENCES securities(security_id),
 namespace TEXT NOT NULL CHECK(length(trim(namespace))>0),
 value TEXT NOT NULL CHECK(length(trim(value))>0),
 valid_from TEXT NOT NULL CHECK(length(valid_from)=10 AND date(valid_from,'+0 days') IS NOT NULL AND date(valid_from,'+0 days')=valid_from),
 valid_to TEXT CHECK(valid_to IS NULL OR (length(valid_to)=10 AND date(valid_to,'+0 days') IS NOT NULL AND date(valid_to,'+0 days')=valid_to AND valid_to>valid_from)),
 known_at TEXT NOT NULL,
 evidence TEXT NOT NULL CHECK(length(trim(evidence))>0)
);
CREATE INDEX identifier_lookup ON identifiers(namespace,value,valid_from,valid_to);
CREATE TRIGGER identifier_insert_overlap BEFORE INSERT ON identifiers
WHEN EXISTS (SELECT 1 FROM identifiers i WHERE i.namespace=NEW.namespace AND i.value=NEW.value
 AND (NEW.valid_to IS NULL OR i.valid_from<NEW.valid_to)
 AND (i.valid_to IS NULL OR NEW.valid_from<i.valid_to))
BEGIN SELECT RAISE(ABORT,'identifier interval overlap'); END;
CREATE TRIGGER identifier_update_overlap BEFORE UPDATE ON identifiers
WHEN EXISTS (SELECT 1 FROM identifiers i WHERE i.identifier_id<>OLD.identifier_id
 AND i.namespace=NEW.namespace AND i.value=NEW.value
 AND (NEW.valid_to IS NULL OR i.valid_from<NEW.valid_to)
 AND (i.valid_to IS NULL OR NEW.valid_from<i.valid_to))
BEGIN SELECT RAISE(ABORT,'identifier interval overlap'); END;
CREATE TRIGGER listing_insert_overlap BEFORE INSERT ON listings
WHEN EXISTS (SELECT 1 FROM listings l WHERE l.security_id=NEW.security_id AND l.mic=NEW.mic
 AND (NEW.valid_to IS NULL OR l.valid_from<NEW.valid_to)
 AND (l.valid_to IS NULL OR NEW.valid_from<l.valid_to))
BEGIN SELECT RAISE(ABORT,'listing interval overlap'); END;
CREATE TRIGGER listing_update_overlap BEFORE UPDATE ON listings
WHEN EXISTS (SELECT 1 FROM listings l WHERE l.listing_id<>OLD.listing_id
 AND l.security_id=NEW.security_id AND l.mic=NEW.mic
 AND (NEW.valid_to IS NULL OR l.valid_from<NEW.valid_to)
 AND (l.valid_to IS NULL OR NEW.valid_from<l.valid_to))
BEGIN SELECT RAISE(ABORT,'listing interval overlap'); END;
