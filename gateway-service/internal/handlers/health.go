package handlers

import (
	"encoding/json"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"log/slog"
	"net/http"
	"sync/atomic"
	"time"

	"google.golang.org/grpc/connectivity"
)

// GRPCConnChecker is the subset of grpc.ClientConn needed by the health
// handler. Keeping it as an interface makes unit testing straightforward.
type GRPCConnChecker interface {
	GetState() connectivity.State
}

// HealthHandler serves liveness and readiness probes.
//
// It tracks graceful-shutdown state via two atomic bools
type HealthHandler struct {
	conn   GRPCConnChecker
	client pb.OrchestratorClient // reserved for future deep-health RPCs

	// available is set to true once the server is fully started and
	// set to false when graceful shutdown begins.
	available atomic.Bool

	// terminateRequested is set when the process receives SIGTERM.
	// Once true, readiness always returns 503 so the load balancer
	// drains traffic before the process exits.
	terminateRequested atomic.Bool
}

func NewHealthHandler(conn GRPCConnChecker, client pb.OrchestratorClient) *HealthHandler {
	h := &HealthHandler{conn: conn, client: client}
	h.available.Store(true) // ready by default; call SetUnavailable during shutdown
	return h
}

// SetUnavailable marks the server as shutting down. Subsequent
// readiness probes will return 503 to drain traffic.
func (h *HealthHandler) SetUnavailable() {
	h.terminateRequested.Store(true)
	h.available.Store(false)
}

// Liveness returns 200 as long as the process is alive.
// Mirrors Bytebase's /healthz endpoint — unconditional OK.
func (h *HealthHandler) Liveness(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}


func (h *HealthHandler) Readiness(w http.ResponseWriter, _ *http.Request) {
	start := time.Now()

	// 1. Shutdown guard
	if h.terminateRequested.Load() {
		writeHealthJSON(w, http.StatusServiceUnavailable, "NOT_READY",
			"server is terminating and unable to serve requests")
		return
	}
	if !h.available.Load() {
		writeHealthJSON(w, http.StatusServiceUnavailable, "NOT_READY",
			"server is not available: it either hasn't started or is restarting")
		return
	}

	// 2. gRPC backend check.
	if h.conn == nil {
		writeHealthJSON(w, http.StatusServiceUnavailable, "NOT_READY",
			"gRPC connection not configured")
		return
	}

	state := h.conn.GetState()

	switch state {
	case connectivity.Ready, connectivity.Idle:
		writeHealthJSON(w, http.StatusOK, "READY", "")

	case connectivity.Connecting:
		writeHealthJSON(w, http.StatusOK, "READY", "orchestrator connecting")

	default:
		// TransientFailure, Shutdown — not ready.
		detail := "orchestrator connection: " + state.String()
		slog.Warn("readiness check failed",
			"state", state.String(),
			"duration", time.Since(start),
		)
		writeHealthJSON(w, http.StatusServiceUnavailable, "NOT_READY", detail)
	}
}

// healthResponse is a small JSON envelope for health probes so that
// monitoring tools get machine-readable output.
type healthResponse struct {
	Status string `json:"status"`
	Detail string `json:"detail,omitempty"`
}

func writeHealthJSON(w http.ResponseWriter, httpStatus int, status, detail string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(httpStatus)
	_ = json.NewEncoder(w).Encode(healthResponse{Status: status, Detail: detail})
}