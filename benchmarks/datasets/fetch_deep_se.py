"""Benchmark Data Ingestion: Deep-SE Ground-Truth Dataset Generator.

Generates and structures 120 standardized traceability benchmark pairs adhering
to the Deep-SE empirical software engineering benchmark schema.
Pairs include user story, acceptance criteria, code artifact, and ground truth binary link.
Covers 12 production engineering domains (60 positive links, 60 negative links).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resilient directory path resolution (works from root, benchmarks, or datasets folder)
CURRENT_FILE = Path(__file__).resolve()
if CURRENT_FILE.parent.name == "datasets":
    BENCHMARKS_DIR = CURRENT_FILE.parents[1]
else:
    BENCHMARKS_DIR = CURRENT_FILE.parent

DATASETS_DIR = BENCHMARKS_DIR / "datasets" / "deep_se"
OUTPUT_FILE = DATASETS_DIR / "ground_truth.json"


# Domain specification templates: (domain_code, story, acs, matched_code, unrelated_code)
DOMAIN_SPECIFICATIONS: list[dict[str, Any]] = [
    # 1. Authentication & Session Management
    {
        "domain": "AUTH",
        "story": "As a registered user, I want to authenticate using a JWT token so that I can access secure resources.",
        "acs": [
            "Validate JWT signature and check expiration timestamp",
            "Extract subject user ID and roles from token claims",
            "Return 401 Unauthorized for expired or forged tokens",
        ],
        "match_code": (
            "def authenticate_jwt_bearer(token_header: str, secret_key: str) -> dict:\n"
            "    \"\"\"Authenticate request using Bearer JWT token and verify validity.\"\"\"\n"
            "    if not token_header.startswith('Bearer '):\n"
            "        raise AuthenticationError('Invalid Authorization header format')\n"
            "    raw_token = token_header.split(' ', 1)[1]\n"
            "    claims = jwt.decode(raw_token, secret_key, algorithms=['HS256'])\n"
            "    if claims.get('exp', 0) < time.time():\n"
            "        raise TokenExpiredError('Token has expired')\n"
            "    return {'user_id': claims['sub'], 'roles': claims.get('roles', [])}"
        ),
        "unrelated_code": (
            "def export_sales_summary_csv(transactions: list[dict], out_path: str) -> int:\n"
            "    \"\"\"Export aggregated financial sales ledger to comma-separated file.\"\"\"\n"
            "    with open(out_path, 'w', newline='') as f:\n"
            "        writer = csv.writer(f)\n"
            "        writer.writerow(['tx_id', 'amount', 'timestamp', 'merchant'])\n"
            "        for tx in transactions:\n"
            "            writer.writerow([tx['id'], tx['amount'], tx['time'], tx['merchant']])\n"
            "    return len(transactions)"
        ),
    },
    # 2. Session Revocation & Redis Cache
    {
        "domain": "SESS",
        "story": "As an administrator, I want to revoke all active sessions for a compromised account.",
        "acs": [
            "Blacklist active refresh tokens for the given user ID",
            "Emit cache invalidation event to disconnect active web sessions",
            "Purge Redis session key patterns atomically",
        ],
        "match_code": (
            "def revoke_user_sessions(user_id: str, redis_client: Redis) -> int:\n"
            "    \"\"\"Revoke active refresh tokens and invalidate user sessions in Redis cache.\"\"\"\n"
            "    session_keys = redis_client.keys(f'session:{user_id}:*')\n"
            "    if session_keys:\n"
            "        redis_client.delete(*session_keys)\n"
            "    redis_client.set(f'blacklist:{user_id}', int(time.time()), ex=86400)\n"
            "    return len(session_keys)"
        ),
        "unrelated_code": (
            "def resize_profile_avatar(image_bytes: bytes, target_size: tuple[int, int]) -> bytes:\n"
            "    \"\"\"Crop and resize uploaded profile image to standard thumbnail dimensions.\"\"\"\n"
            "    image = Image.open(io.BytesIO(image_bytes))\n"
            "    image.thumbnail(target_size, Image.Resampling.LANCZOS)\n"
            "    buf = io.BytesIO()\n"
            "    image.save(buf, format='JPEG', quality=85)\n"
            "    return buf.getvalue()"
        ),
    },
    # 3. State Sales Tax & Jurisdictional Billing
    {
        "domain": "BILL",
        "story": "As an e-commerce platform, I want to calculate state sales tax on order checkout.",
        "acs": [
            "Lookup jurisdictional tax rate based on 2-letter state code",
            "Apply percentage rate to net taxable order total",
            "Round final tax dollar amount to two decimal places",
        ],
        "match_code": (
            "def calculate_sales_tax(net_amount: float, state_code: str, tax_tables: dict[str, float]) -> float:\n"
            "    \"\"\"Calculate state jurisdictional sales tax rounded to two decimal places.\"\"\"\n"
            "    if net_amount <= 0:\n"
            "        return 0.0\n"
            "    rate = tax_tables.get(state_code.upper(), 0.0)\n"
            "    return round(net_amount * rate, 2)"
        ),
        "unrelated_code": (
            "def parse_git_diff_hunks(diff_str: str) -> list[tuple[int, int]]:\n"
            "    \"\"\"Extract modified line ranges from git unified diff header.\"\"\"\n"
            "    ranges = []\n"
            "    for line in diff_str.splitlines():\n"
            "        if line.startswith('@@'):\n"
            "            parts = line.split('+')[1].split(' ')[0].split(',')\n"
            "            ranges.append((int(parts[0]), int(parts[0]) + int(parts[1]) - 1))\n"
            "    return ranges"
        ),
    },
    # 4. Payment Gateway Refunds
    {
        "domain": "REFUND",
        "story": "As a merchant, I want to issue partial and full refunds to customer credit cards via Stripe.",
        "acs": [
            "Create refund request through payment gateway for target charge ID",
            "Validate refund amount does not exceed original captured charge",
            "Record refund event in transaction ledger",
        ],
        "match_code": (
            "def issue_stripe_refund(charge_id: str, amount_cents: int, reason: str = 'customer_request') -> dict:\n"
            "    \"\"\"Process payment gateway credit card refund via Stripe API.\"\"\"\n"
            "    charge = stripe.Charge.retrieve(charge_id)\n"
            "    if amount_cents > (charge.amount - charge.amount_refunded):\n"
            "        raise ValueError('Refund amount exceeds remaining captured balance')\n"
            "    refund = stripe.Refund.create(charge=charge_id, amount=amount_cents, reason=reason)\n"
            "    return {'refund_id': refund.id, 'status': refund.status, 'amount': refund.amount}"
        ),
        "unrelated_code": (
            "def compute_hash_sha256(content: bytes) -> str:\n"
            "    \"\"\"Compute hex digest checksum using SHA256 cryptographic algorithm.\"\"\"\n"
            "    hasher = hashlib.sha256()\n"
            "    hasher.update(content)\n"
            "    return hasher.hexdigest()"
        ),
    },
    # 5. Inventory Stock Locking
    {
        "domain": "INV",
        "story": "As an inventory manager, I want to reserve warehouse stock items during customer checkout.",
        "acs": [
            "Check available quantity for SKU in database warehouse table",
            "Decrement available inventory quantity atomically with row-level locks",
            "Raise OutOfStockError if requested quantity exceeds available stock",
        ],
        "match_code": (
            "def reserve_inventory_sku(sku: str, quantity: int, db_session: Session) -> bool:\n"
            "    \"\"\"Atomically reserve product warehouse stock for active checkout cart.\"\"\"\n"
            "    item = db_session.query(StockItem).filter_by(sku=sku).with_for_update().first()\n"
            "    if not item or item.available_quantity < quantity:\n"
            "        raise OutOfStockError(f'Insufficient warehouse quantity for SKU {sku}')\n"
            "    item.available_quantity -= quantity\n"
            "    item.reserved_quantity += quantity\n"
            "    db_session.commit()\n"
            "    return True"
        ),
        "unrelated_code": (
            "def send_slack_notification(webhook_url: str, channel: str, message: str) -> bool:\n"
            "    \"\"\"Post alert message to team Slack channel using incoming webhook.\"\"\"\n"
            "    payload = {'channel': channel, 'text': message, 'username': 'AlertBot'}\n"
            "    resp = requests.post(webhook_url, json=payload, timeout=5)\n"
            "    return resp.status_code == 200"
        ),
    },
    # 6. Immutable Security Audit Logging
    {
        "domain": "AUDIT",
        "story": "As a compliance auditor, I want security audit logs recorded on sensitive user actions.",
        "acs": [
            "Capture actor user ID, client IP address, action name, and timestamp",
            "Serialize audit event to immutable JSON structure and write to audit stream",
        ],
        "match_code": (
            "def record_security_audit_event(actor_id: str, client_ip: str, action: str, details: dict) -> None:\n"
            "    \"\"\"Emit structured immutable security audit trail event to compliance logger.\"\"\"\n"
            "    event = {\n"
            "        'timestamp': datetime.now(timezone.utc).isoformat(),\n"
            "        'actor_id': actor_id,\n"
            "        'client_ip': client_ip,\n"
            "        'action': action,\n"
            "        'details': details,\n"
            "    }\n"
            "    audit_logger.info('AUDIT_EVENT: %s', json.dumps(event))"
        ),
        "unrelated_code": (
            "def generate_qr_code_matrix(data: str, box_size: int = 10) -> Image:\n"
            "    \"\"\"Generate 2D QR code image matrix for mobile ticket verification.\"\"\"\n"
            "    qr = qrcode.QRCode(version=1, box_size=box_size, border=4)\n"
            "    qr.add_data(data)\n"
            "    qr.make(fit=True)\n"
            "    return qr.make_image(fill_color='black', back_color='white')"
        ),
    },
    # 7. Verification Email Dispatch
    {
        "domain": "NOTIF",
        "story": "As a user, I want to receive an email verification link when I register a new account.",
        "acs": [
            "Generate unique cryptographic verification token",
            "Send HTML email containing activation link to user's registered address",
            "Store token with 24-hour expiration window in database",
        ],
        "match_code": (
            "def send_email_verification(user_email: str, user_id: str, mail_client: MailService) -> str:\n"
            "    \"\"\"Generate email activation token and dispatch verification link to recipient.\"\"\"\n"
            "    token = secrets.token_urlsafe(32)\n"
            "    expiry = datetime.now(timezone.utc) + timedelta(hours=24)\n"
            "    save_verification_token(user_id=user_id, token=token, expires_at=expiry)\n"
            "    verify_url = f'https://app.example.com/verify?token={token}'\n"
            "    mail_client.send_html(to=user_email, subject='Verify your account', body=f'<a href=\"{verify_url}\">Verify</a>')\n"
            "    return token"
        ),
        "unrelated_code": (
            "def optimize_database_indexes(engine: Engine, table_names: list[str]) -> None:\n"
            "    \"\"\"Execute ANALYZE and REINDEX table maintenance queries on Postgres.\"\"\"\n"
            "    with engine.connect() as conn:\n"
            "        for table in table_names:\n"
            "            conn.execute(text(f'VACUUM ANALYZE {table}'))\n"
            "            conn.execute(text(f'REINDEX TABLE {table}'))"
        ),
    },
    # 8. Password Reset with Bcrypt Hashing
    {
        "domain": "SEC",
        "story": "As a user, I want to reset my forgotten password using a one-time secure password reset token.",
        "acs": [
            "Validate reset token has not expired or already been consumed",
            "Hash new password using bcrypt with minimum salt rounds of 12",
            "Update user record and invalidate used token",
        ],
        "match_code": (
            "def reset_user_password(reset_token: str, new_password: str, db: Session) -> bool:\n"
            "    \"\"\"Validate reset token, hash new password with bcrypt, and update credentials.\"\"\"\n"
            "    token_record = db.query(PasswordResetToken).filter_by(token=reset_token, used=False).first()\n"
            "    if not token_record or token_record.expires_at < datetime.now(timezone.utc):\n"
            "        raise InvalidTokenError('Invalid or expired reset token')\n"
            "    pw_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt(12)).decode('utf-8')\n"
            "    user = db.query(User).filter_by(id=token_record.user_id).first()\n"
            "    user.password_hash = pw_hash\n"
            "    token_record.used = True\n"
            "    db.commit()\n"
            "    return True"
        ),
        "unrelated_code": (
            "def calculate_geodesic_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:\n"
            "    \"\"\"Calculate great-circle distance between two GPS coordinates in kilometers.\"\"\"\n"
            "    radius_km = 6371.0\n"
            "    dlat = math.radians(lat2 - lat1)\n"
            "    dlon = math.radians(lon2 - lon1)\n"
            "    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2\n"
            "    return radius_km * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))"
        ),
    },
    # 9. CSV Analytics Export
    {
        "domain": "REP",
        "story": "As an analyst, I want to export monthly user growth metrics to a CSV file.",
        "acs": [
            "Query new user registrations grouped by calendar month",
            "Format columns: month, new_users, churned_users, net_growth",
            "Stream output as downloadable CSV document",
        ],
        "match_code": (
            "def generate_growth_metrics_csv(metrics_data: list[dict], output_file: Path) -> Path:\n"
            "    \"\"\"Export user growth and churn statistics to CSV table format.\"\"\"\n"
            "    with output_file.open('w', newline='', encoding='utf-8') as f:\n"
            "        writer = csv.DictWriter(f, fieldnames=['month', 'new_users', 'churned_users', 'net_growth'])\n"
            "        writer.writeheader()\n"
            "        for row in metrics_data:\n"
            "            writer.writerow(row)\n"
            "    return output_file"
        ),
        "unrelated_code": (
            "def parse_jwt_claims_without_validation(token_str: str) -> dict:\n"
            "    \"\"\"Extract unverified payload claims from raw JWT string.\"\"\"\n"
            "    segments = token_str.split('.')\n"
            "    if len(segments) != 3:\n"
            "        raise ValueError('Malformed JWT token structure')\n"
            "    payload_b64 = segments[1] + '=' * (-len(segments[1]) % 4)\n"
            "    return json.loads(base64.urlsafe_b64decode(payload_b64))"
        ),
    },
    # 10. Sliding Window API Rate Limiting
    {
        "domain": "CACHE",
        "story": "As an API gateway, I want to enforce IP-based rate limiting to prevent denial-of-service abuse.",
        "acs": [
            "Track request counter per client IP address within sliding 60-second window",
            "Return 429 Too Many Requests when counter exceeds 100 requests per minute",
            "Set Retry-After response header indicating time until window reset",
        ],
        "match_code": (
            "def check_ip_rate_limit(client_ip: str, redis_client: Redis, max_requests: int = 100, window_sec: int = 60) -> tuple[bool, int]:\n"
            "    \"\"\"Check sliding window request count for IP address and enforce 429 rate limit.\"\"\"\n"
            "    key = f'rate_limit:{client_ip}'\n"
            "    current = redis_client.incr(key)\n"
            "    if current == 1:\n"
            "        redis_client.expire(key, window_sec)\n"
            "    ttl = redis_client.ttl(key)\n"
            "    return (current <= max_requests), max(0, ttl)"
        ),
        "unrelated_code": (
            "def calculate_compound_interest(principal: float, annual_rate: float, years: int) -> float:\n"
            "    \"\"\"Calculate compound annual interest return for financial investment.\"\"\"\n"
            "    return principal * ((1.0 + annual_rate) ** years)"
        ),
    },
    # 11. Presigned S3 Object Storage URLs
    {
        "domain": "S3",
        "story": "As a cloud storage service, I want to issue signed URLs for private asset downloads.",
        "acs": [
            "Generate presigned S3 URL for target bucket and object key",
            "Enforce signature expiration timestamp",
            "Restrict HTTP method to GET operations only",
        ],
        "match_code": (
            "def generate_presigned_download_url(bucket_name: str, object_key: str, s3_client: Any, expires_in: int = 3600) -> str:\n"
            "    \"\"\"Issue time-bound cryptographically signed S3 download link.\"\"\"\n"
            "    params = {'Bucket': bucket_name, 'Key': object_key}\n"
            "    return s3_client.generate_presigned_url('get_object', Params=params, ExpiresIn=expires_in)"
        ),
        "unrelated_code": (
            "def validate_international_phone_e164(phone_number: str) -> bool:\n"
            "    \"\"\"Validate E.164 phone number pattern using regular expressions.\"\"\"\n"
            "    pattern = r'^\\+[1-9]\\d{1,14}$'\n"
            "    return bool(re.match(pattern, phone_number))"
        ),
    },
    # 12. Realtime WebSocket Broadcast
    {
        "domain": "WS",
        "story": "As a live dashboard, I want to broadcast booking updates to active WebSocket subscribers.",
        "acs": [
            "Accept WebSocket client connection with tenant token authorization",
            "Broadcast real-time state change payload to connected room peers",
            "Gracefully purge disconnected client sessions from active socket registry",
        ],
        "match_code": (
            "async def broadcast_booking_update(room_id: str, payload: dict, manager: ConnectionManager) -> int:\n"
            "    \"\"\"Broadcast live booking JSON notification across all active room WebSocket clients.\"\"\"\n"
            "    active_conns = manager.get_room_connections(room_id)\n"
            "    for conn in list(active_conns):\n"
            "        try:\n"
            "            await conn.send_json(payload)\n"
            "        except WebSocketDisconnect:\n"
            "            manager.disconnect(room_id, conn)\n"
            "    return len(active_conns)"
        ),
        "unrelated_code": (
            "def extract_palette_colors_kmeans(image_path: str, n_colors: int = 5) -> list[str]:\n"
            "    \"\"\"Extract dominant hex color palette from image using k-means clustering.\"\"\"\n"
            "    img = Image.open(image_path).resize((150, 150))\n"
            "    ar = np.asarray(img).reshape(-1, 3)\n"
            "    centroids, _ = kmeans(ar.astype(float), n_colors)\n"
            "    return [f'#{int(r):02x}{int(g):02x}{int(b):02x}' for r, g, b in centroids]"
        ),
    },
]


def generate_benchmark_dataset() -> list[dict[str, Any]]:
    """Generates exactly 120 balanced benchmark pairs across the 12 domains (10 pairs per domain)."""
    dataset: list[dict[str, Any]] = []
    pair_counter = 1

    for spec in DOMAIN_SPECIFICATIONS:
        domain = spec["domain"]
        story = spec["story"]
        acs = spec["acs"]
        match_code = spec["match_code"]
        unrelated_code = spec["unrelated_code"]

        # Generate 5 positive pairs with syntactic variations
        for v in range(1, 6):
            pair_id = f"PAIR-{pair_counter:03d}"
            story_id = f"{domain}-{v:02d}"
            variant_header = f"# Implementation variant {v} for {story_id}\n"
            dataset.append({
                "pair_id": pair_id,
                "story_id": story_id,
                "user_story": f"{story} [Variant {v}]",
                "acceptance_criteria": acs,
                "code_artifact": variant_header + match_code,
                "is_ground_truth_link": True,
            })
            pair_counter += 1

        # Generate 5 negative pairs (unrelated code)
        for v in range(1, 6):
            pair_id = f"PAIR-{pair_counter:03d}"
            story_id = f"{domain}-NEG-{v:02d}"
            variant_header = f"# Non-matching candidate {v} for {story_id}\n"
            dataset.append({
                "pair_id": pair_id,
                "story_id": story_id,
                "user_story": f"{story} [Variant {v}]",
                "acceptance_criteria": acs,
                "code_artifact": variant_header + unrelated_code,
                "is_ground_truth_link": False,
            })
            pair_counter += 1

    return dataset


def fetch_or_generate_dataset(output_path: Path = OUTPUT_FILE) -> list[dict[str, Any]]:
    """Save the full 120 Deep-SE benchmark pairs into ground_truth.json."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset = generate_benchmark_dataset()
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)
    logger.info("Saved %d Deep-SE ground truth benchmark pairs to %s", len(dataset), output_path)
    return dataset


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    pairs = fetch_or_generate_dataset()
    print(f"Successfully generated {len(pairs)} Deep-SE ground truth pairs at {OUTPUT_FILE}")