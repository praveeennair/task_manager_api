from decouple import config, Csv
from .base import *

# In production, DEBUG must be False
DEBUG = config('DEBUG', default=False, cast=bool)

# In production: match production root domain and all subdomains via regex + local containers
PROD_HOST_REGEX = config('PROD_HOST_REGEX', default=r'^([a-zA-Z0-9-]+\.)*yourdomain\.com$')

ALLOWED_HOSTS = [
    RegexHost(PROD_HOST_REGEX),
    'localhost',
    '127.0.0.1',
    'web',
]

# CSRF Trusted Origins for reverse proxies / domains (e.g., https://example.com,https://*.example.com)
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://*.yourdomain.com,https://yourdomain.com', cast=Csv())

# Security & SSL Settings (can be toggled in .env)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=False, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=False, cast=bool)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
