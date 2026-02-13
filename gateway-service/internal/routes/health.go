package routes

import (
	"gateway-service/internal/handlers"
	"net/http"
)

// HealthRoutes registers liveness and readiness probe endpoints.
// It accepts a shared *HealthHandler so the router can call
// SetUnavailable() on the same instance during graceful shutdown.
func HealthRoutes(h *handlers.HealthHandler) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /liveness", h.Liveness)
	mux.HandleFunc("GET /readiness", h.Readiness)
	return mux
}
