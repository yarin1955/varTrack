import sys
from waitress import serve
from app.settings import load_config
from app.business_logic.initializer import initializer
from wsgi import app  # Import your Flask app

if __name__ == "__main__":
    print("--- Starting varTrack on Windows (Waitress) ---")

    # 1. Run the Initializer (Simulating the Gunicorn 'on_starting' hook)
    print("Running Application Initializer...")
    try:
        config_data = load_config()
        initializer(config_data)
        print("✅ Initialization completed successfully.")
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        sys.exit(1)

    # 2. Start the Server
    # threads=8 simulates multiple workers handling requests concurrently
    print("🚀 Serving on http://0.0.0.0:5000")
    serve(app, host='0.0.0.0', port=8000, threads=8)