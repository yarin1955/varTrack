from enum import Enum

class ApplyStrategy(Enum):
    """
    CLIENT_SIDE: varTrack calculates the diff locally and sends specific patches.
    SERVER_SIDE: varTrack sends the desired state; for DBs this typically means 'Upsert All'.
    """
    CLIENT_SIDE = "client_side"
    SERVER_SIDE = "server_side"

class SyncMode(Enum):
    # Option 1: Git vs Git (Upsert All)
    # Writes everything (even unchanged) to DB.
    GIT_UPSERT_ALL = "git_upsert_all"

    # Option 2: Git vs Git (Smart Repair)
    # Checks if unchanged keys exist in DB (IDs only) and writes only if missing.
    GIT_SMART_REPAIR = "git_smart_repair"

    # Option 3: Git vs DB (Live State)
    # Compares Git directly against current DB state.
    LIVE_STATE = "live_state"

    # Automatic Decision
    AUTO = "auto"