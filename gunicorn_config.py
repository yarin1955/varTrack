import multiprocessing
import os
import sys

# Ensure the current directory is in the python path
sys.path.append(os.getcwd())

# Server Socket
bind = "0.0.0.0:5000"

# Worker Options
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
timeout = 120

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Process Naming
proc_name = "vartrack_gunicorn"

# Preload App
# This is crucial for 'on_starting' to work effectively as a pre-hook for workers.
# It ensures the app is loaded in the master process after initialization
# and then copied to workers via fork().
preload_app = True


def on_starting(server):
    """
    Run the initializer logic once when the master process starts.
    This acts as a 'pre-hook' for the entire application server.
    """
    # Import inside the function to avoid circular dependency issues
    # or premature loading before logging is ready.
    from app.settings import load_config
    from app.business_logic.initializer import initializer

    server.log.info("Starting Application Initializer (Pre-Hook)...")
    try:
        config_data = load_config()

        # Run initializer synchronously.
        # The server will NOT start workers until this function returns.
        initializer(config_data)

        server.log.info("Initialization completed successfully.")
    except Exception as e:
        server.log.error(f"Initialization failed: {e}")
        # If initialization is critical, you might want to stop the server here:
        sys.exit(1)