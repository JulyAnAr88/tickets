from werkzeug.middleware.dispatcher import DispatcherMiddleware
from flask import Flask

# Import the actual app
from app import app as flask_app

# Mount under /abm prefix
application = DispatcherMiddleware(
    Flask("root_app"),
    {"/abm": flask_app}
)

