Here's the corrected and properly formatted README.md:

```markdown
# varTrack

**varTrack** is a GitOps-based environment variable manager that enforces Policy as Code. It synchronizes configuration values directly from Git repositories to data stores like MongoDB while ensuring strict validation through Protobuf and CUE.

## Features

* **GitOps Driven**: Tracks configuration changes via Git Push and Pull Request events.
* **Policy as Code**: Uses Protobuf (with `protovalidate`) and CUE for strict schema enforcement.
* **Self-Healing**: A background service that automatically detects and reconciles drift between Git and data stores.
* **Dynamic Syncing**: Automatically chooses the most efficient sync mode (e.g., `git_upsert_all`, `git_smart_repair`, or `live_state`) based on network metrics.
* **Multi-Platform Support**: Built-in integration for GitHub authentication and webhook management.

## Prerequisites

* **Go**: Version 1.25.5 or higher
* **Python**: Version 3.10+ with dependencies in `requirements.txt`
* **Buf CLI**: For Protobuf orchestration and code generation
* **MongoDB**: Used for both document-based and file-based (GridFS) storage strategies

## Protobuf Management & Build Commands

The project uses the **Buf CLI** to manage schemas and dependencies.

### 1. Update Dependencies

Download external Protobuf dependencies (such as `protovalidate`):

```powershell
.\buf.exe dep update
```

### 2. Build and Validate

Verify the syntax and linting of all `.proto` files:

```powershell
.\buf.exe build
```

### 3. Generate Code

Generate Go and Python classes as defined in `buf.gen.yaml`:

```powershell
.\buf.exe generate
```

## Running the Services

### Gateway Service (Go)

The gateway handles incoming webhooks and health probes:

```bash
cd gateway-service
go run cmd/main.go
```

The service defaults to port `:5656`.

### Core Application (Python)

The backend manages the sync engine and Celery task orchestration.

#### Windows (Waitress)

```bash
python run_waitress.py
```

Starts the server on port `8000` with 8 threads.

#### Linux (Gunicorn)

```bash
gunicorn -c gunicorn_config.py wsgi:app
```

Configured with pre-fork workers and an initialization hook.

### Celery Workers

Start the background workers to process synchronization tasks:

```bash
celery -A celery_worker worker --loglevel=info
```

## Project Structure

* `proto/`: Protobuf definitions for bundle, platform, and rule models
* `cue/`: CUE schemas for deep validation of configurations
* `gateway-service/`: Go implementation of the webhook gateway
* `app/`: Python core logic including sync engines and platform drivers

## License

This project is licensed under the **GNU GENERAL PUBLIC LICENSE Version 3**.
```