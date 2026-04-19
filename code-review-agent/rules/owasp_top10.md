# OWASP Top 10 Security Rules

## A01: Broken Access Control

Access control enforces policy so that users cannot act outside their intended permissions. Failures lead to unauthorized information disclosure, modification, or destruction.

**Check for:**
- Missing function-level access control (no auth decorators/middleware)
- Insecure direct object references (e.g., `user_id` taken from URL without ownership check)
- CORS misconfiguration allowing unauthorized origins
- Privilege escalation (user can access admin endpoints)
- JWT token not validated or easily forged

**Example bug:**
```python
# INSECURE: no ownership check
def get_document(doc_id):
    return db.query(Document).filter(Document.id == doc_id).first()

# SECURE:
def get_document(doc_id, current_user):
    return db.query(Document).filter(Document.id == doc_id, Document.owner_id == current_user.id).first()
```

## A02: Cryptographic Failures

Sensitive data must be encrypted in transit and at rest. Weak or missing cryptography is a critical flaw.

**Check for:**
- Passwords stored in plaintext or with weak hashing (MD5, SHA1 without salt)
- Sensitive data transmitted over HTTP (not HTTPS)
- Hardcoded secrets, API keys, or passwords in source code
- Weak random number generation (use `secrets` module, not `random`)
- Deprecated algorithms (DES, RC4, ECB mode)

**Example bug:**
```python
# INSECURE: MD5 for passwords
import hashlib
password_hash = hashlib.md5(password.encode()).hexdigest()

# SECURE:
import bcrypt
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
```

## A03: Injection

Injection flaws occur when untrusted data is sent to an interpreter as part of a command or query.

**Check for:**
- SQL injection: string concatenation or % formatting in SQL queries
- Command injection: `os.system()`, `subprocess.call(shell=True)` with user input
- LDAP injection, XPath injection, NoSQL injection
- Template injection (user input rendered directly in templates)

**Example bug:**
```python
# INSECURE: SQL injection
query = f"SELECT * FROM users WHERE username = '{username}'"
db.execute(query)

# SECURE: parameterized query
db.execute("SELECT * FROM users WHERE username = ?", (username,))
```

## A04: Insecure Design

Design flaws that cannot be fixed by secure implementation alone.

**Check for:**
- Missing rate limiting on authentication endpoints
- No account lockout after failed login attempts
- Sensitive business logic client-side only
- Missing input validation at trust boundaries

## A05: Security Misconfiguration

**Check for:**
- Debug mode enabled in production (`DEBUG=True`, `app.debug = True`)
- Default credentials not changed
- Overly permissive file permissions
- Verbose error messages exposing stack traces to users
- Unnecessary features/endpoints enabled

## A06: Vulnerable and Outdated Components

**Check for:**
- Dependencies with known CVEs
- Pinned to very old versions

## A07: Identification and Authentication Failures

**Check for:**
- Weak passwords permitted (no complexity requirements)
- Session IDs exposed in URLs
- Session not invalidated on logout
- Missing multi-factor authentication for sensitive operations
- Predictable session tokens

**Example bug:**
```python
# INSECURE: predictable token
import random
token = str(random.randint(100000, 999999))

# SECURE:
import secrets
token = secrets.token_hex(32)
```

## A08: Software and Data Integrity Failures

**Check for:**
- Deserializing untrusted data with `pickle`, `yaml.load()` (use `yaml.safe_load()`)
- No integrity verification of downloaded files
- Auto-update mechanisms without signature checks

## A09: Security Logging and Monitoring Failures

**Check for:**
- Login failures not logged
- No audit trail for sensitive operations
- Logs containing sensitive data (passwords, tokens)
- Logs not monitored or alerting not configured

## A10: Server-Side Request Forgery (SSRF)

**Check for:**
- User-supplied URLs fetched server-side without validation
- Internal services reachable via URL parameters
- No allowlist for permitted URL schemes/hosts

**Example bug:**
```python
# INSECURE: SSRF
url = request.args.get("url")
response = requests.get(url)  # attacker can reach internal services

# SECURE:
from urllib.parse import urlparse
parsed = urlparse(url)
if parsed.netloc not in ALLOWED_HOSTS:
    raise ValueError("URL not allowed")
```
