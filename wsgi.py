import threading
from app import create_app
from app.settings import load_config
from app.business_logic.initializer import initializer

config_data = load_config()

app = create_app(config_data)

if __name__ == "__main__":
    thread = threading.Thread(
        target=initializer,
        args=(config_data,),
        daemon=True,
    )
    thread.start()
    app.run(debug=True, host="127.0.0.1", port=5000, threaded=True, use_reloader=False)