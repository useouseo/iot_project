"""WSGI entry point for the live MariaDB deployment."""
from server import app, init_db

init_db()
