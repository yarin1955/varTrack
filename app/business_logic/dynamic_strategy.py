import time
from app.utils.enums.sync_mode import SyncMode
from app.pipeline.sinks.mongo import MongoSink


class DynamicStrategySelector:
    # --- Tunable Constants ---
    AVG_BANDWIDTH_MBPS = 20.0  # Speed of link between Worker and Mongo
    WRITE_COST_MS = 0.5  # Cost to write 1 document
    READ_ID_COST_MS = 0.05  # Cost to read 1 ID from Index
    DRIFT_RATE = 0.05  # Assumption: Only 5% of unchanged keys need repair

    @staticmethod
    def measure_latency(sink: MongoSink) -> float:
        """Pings DB to get current network latency (in seconds)."""
        try:
            start = time.time()
            sink.collection.database.command('ping')
            return time.time() - start
        except:
            return 0.1  # Default 100ms if ping fails

    @staticmethod
    def decide(content: str, sink: MongoSink, is_file_strategy: bool) -> SyncMode:
        # 1. If user set a specific mode (e.g. LIVE_STATE), obey it.

        # 2. Safety check for empty content
        if not content:
            return SyncMode.GIT_SMART_REPAIR

        # 3. Gather Metrics
        N = content.count('\n') or 1  # Approx Number of Keys
        S = len(content)  # Size in Bytes
        L = DynamicStrategySelector.measure_latency(sink)  # Latency

        # 4. Calculate Costs (in Seconds)

        # --- Option 3: LIVE STATE ---
        # Cost = Latency + Download Time
        download_time = (S / (DynamicStrategySelector.AVG_BANDWIDTH_MBPS * 1024 * 1024))
        # Penalty: GridFS (File Strategy) is slower to seek/read than Docs
        if is_file_strategy: download_time *= 2.0
        cost_live = L + download_time

        # --- Option 1: UPSERT ALL ---
        # Cost = Latency + Write Time (Blind writes)
        write_time = (N * DynamicStrategySelector.WRITE_COST_MS) / 1000
        cost_upsert = L + write_time

        # --- Option 2: SMART REPAIR ---
        # Cost = 2 * Latency (Read+Write RTT) + Read Time + Partial Write Time
        read_time = (N * DynamicStrategySelector.READ_ID_COST_MS) / 1000
        repair_write_time = (N * DynamicStrategySelector.DRIFT_RATE * DynamicStrategySelector.WRITE_COST_MS) / 1000
        cost_repair = (2 * L) + read_time + repair_write_time

        # 5. Pick Winner
        if cost_live <= cost_upsert and cost_live <= cost_repair:
            return SyncMode.LIVE_STATE
        elif cost_upsert <= cost_repair:
            return SyncMode.GIT_UPSERT_ALL
        else:
            return SyncMode.GIT_SMART_REPAIR