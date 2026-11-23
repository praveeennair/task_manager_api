from decouple import config, Csv
from .base import *

# In development, DEBUG defaults to True
DEBUG = config('DEBUG', default=True, cast=bool)

# In development, allow all hosts (no need to specify in .env)
ALLOWED_HOSTS = ['*']
