package handlers

import (
	"context"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"net/http"
	"time"

	"google.golang.org/grpc/connectivity"
)

// GRPCConnChecker is the subset of grpc.ClientConn we need.
type GRPCConnChecker interface {
	GetState() connectivity.State
}

type HealthHandler struct {
	conn   GRPCConnChecker       // nil-safe; if nil readiness is degraded
	client pb.OrchestratorClient // unused for now; kept for future deep-health RPCs
}

func NewHealthHandler(conn GRPCConnChecker, client pb.OrchestratorClient) *HealthHandler {
	return &HealthHandler{conn: conn, client: client}
}

func (h *HealthHandler) Liveness(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
	w.Write([]byte("OK"))
}

// Readiness verifies the gateway can reach the orchestrator before
// declaring itself ready to accept traffic.
func (h *HealthHandler) Readiness(w http.ResponseWriter, r *http.Request) {
	if h.conn == nil {
		// No connection configured — degrade gracefully.
		http.Error(w, "gRPC connection not configured", http.StatusServiceUnavailable)
		return
	}

	_, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	state := h.conn.GetState()
	switch state {
	case connectivity.Ready, connectivity.Idle:
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("READY"))
	default:
		http.Error(w, "orchestrator connection: "+state.String(), http.StatusServiceUnavailable)
	}
}
