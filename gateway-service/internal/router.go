package internal

import (
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"gateway-service/internal/models"
	"gateway-service/internal/routes"
	"net/http"
)

type Router struct {
	mux           *http.ServeMux
	bundleService *models.Bundle
	grpcClient    pb.OrchestratorClient
}

func NewRouter(bundleService *models.Bundle, grpcClient pb.OrchestratorClient) *Router {
	r := &Router{
		mux:           http.NewServeMux(),
		bundleService: bundleService,
		grpcClient:    grpcClient,
	}
	r.setupRoutes()
	return r

	//	//globalHandler := middlewares.Logger(mux)
	//	//return globalHandler
}

func (r *Router) setupRoutes() {
	r.mux.Handle("/webhooks/", http.StripPrefix("/webhooks", routes.WebhookRoutes(r.bundleService, r.grpcClient)))
}

func (r *Router) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	r.mux.ServeHTTP(w, req)
}
