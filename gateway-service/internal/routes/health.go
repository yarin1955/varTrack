package routes

import (
	"gateway-service/internal/handlers"
	"net/http"

	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
)

func HealthRoutes(conn handlers.GRPCConnChecker, client pb.OrchestratorClient) http.Handler {
	h := handlers.NewHealthHandler(conn, client)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /liveness", h.Liveness)
	mux.HandleFunc("GET /readiness", h.Readiness)
	return mux
}

//livenessHandler := http.HandlerFunc(h.Liveness)
//mux.Handle("GET /liveness", middlewares.SpecialCheck(livenessHandler))
