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
// It tracks graceful-shutdown state via two atomic bools, mirroring
// ArgoCD's ArgoCDServer which uses terminateRequested + available
// atomics to prevent accepting work during shutdown.
type HealthHandler struct {
	conn   GRPCConnChecker
	client pb.OrchestratorClient

	available          atomic.Bool
	terminateRequested atomic.Bool
}

func NewHealthHandler(conn GRPCConnChecker, client pb.OrchestratorClient) *HealthHandler {
	h := &HealthHandler{conn: conn, client: client}
	h.available.Store(true)
	return h
}

// SetUnavailable marks the server as shutting down.
func (h *HealthHandler) SetUnavailable() {
	h.terminateRequested.Store(true)
	h.available.Store(false)
}

// Liveness returns 200 as long as the process is alive.
func (h *HealthHandler) Liveness(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

// Readiness verifies the gateway can serve traffic.
//
// Check order mirrors ArgoCD's server.healthCheck:
// 1. terminateRequested? 2. available? 3. gRPC backend reachable?
//
// Duration logged on failure (ArgoCD healthz.ServeHealthCheck pattern).
func (h *HealthHandler) Readiness(w http.ResponseWriter, _ *http.Request) {
	start := time.Now()

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
		detail := "orchestrator connection: " + state.String()
		slog.Warn("readiness check failed",
			"state", state.String(),
			"duration", time.Since(start),
		)
		writeHealthJSON(w, http.StatusServiceUnavailable, "NOT_READY", detail)
	}
}

type healthResponse struct {
	Status string `json:"status"`
	Detail string `json:"detail,omitempty"`
}

func writeHealthJSON(w http.ResponseWriter, httpStatus int, status, detail string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(httpStatus)
	_ = json.NewEncoder(w).Encode(healthResponse{Status: status, Detail: detail})
}
