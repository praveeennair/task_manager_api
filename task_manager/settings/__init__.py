from decouple import config

# Determine environment: 'development' (default), 'qa', or 'production'
DJANGO_ENV = config('DJANGO_ENV', default='development').lower()

if DJANGO_ENV == 'production':
    from .production import *
elif DJANGO_ENV in ('qa', 'staging', 'test'):
    from .QA import *
else:
    from .development import *
