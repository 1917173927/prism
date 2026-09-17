CREATE TABLE portfolio_ocr_confirmation_versions (
    confirmation_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    image_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);

INSERT INTO portfolio_ocr_confirmation_versions
    (confirmation_id, owner_id, image_digest, payload_json, confirmed_at)
SELECT confirmation_id, owner_id, image_digest, payload_json, confirmed_at
FROM portfolio_ocr_confirmations;

DROP TABLE portfolio_ocr_confirmations;

ALTER TABLE portfolio_ocr_confirmation_versions
RENAME TO portfolio_ocr_confirmations;

CREATE INDEX idx_ocr_confirmations_owner_confirmed
    ON portfolio_ocr_confirmations (owner_id, confirmed_at DESC, confirmation_id DESC);

CREATE INDEX idx_ocr_confirmations_owner_image
    ON portfolio_ocr_confirmations (owner_id, image_digest);
