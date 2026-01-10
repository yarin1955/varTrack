package routes

import (
	"gateway-service/internal/handlers"
	"net/http"
)

func HealthRoutes() http.Handler {
	h := handlers.NewHealthHandler()

	mux := http.NewServeMux()

	// Sub-router routes (relative path)
	// We do NOT write "/health" here
	mux.HandleFunc("GET /liveness", h.Liveness)
	mux.HandleFunc("GET /readiness", h.Readiness)

	//livenessHandler := http.HandlerFunc(h.Liveness)
	//mux.Handle("GET /liveness", middlewares.SpecialCheck(livenessHandler))

	return mux
}
