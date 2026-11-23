from decouple import config, Csv
from .base import *

# In QA, DEBUG can default to False (to closely simulate production) or be toggled via .env
DEBUG = config('DEBUG', default=False, cast=bool)

# In QA, match QA subdomains/preview apps via regex + local containers
QA_HOST_REGEX = config('QA_HOST_REGEX', default=r'^([a-zA-Z0-9-]+\.)*qa\.yourdomain\.com$')

ALLOWED_HOSTS = [
    RegexHost(QA_HOST_REGEX),
    'localhost',
    '127.0.0.1',
    'web',
]

# CSRF Trusted Origins for QA environment
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='https://*.qa.yourdomain.com', cast=Csv())

# QA email configuration (console backend prevents accidental emails to real users)
MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}
