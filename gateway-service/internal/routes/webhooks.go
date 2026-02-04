package routes

import (
	"gateway-service/internal/config"
	"gateway-service/internal/handlers"
	"net/http"
)

// WebhookRoutes now accepts the PlatformRegistry as a dependency.
// This allows the router to pass the explicitly wired registry down to the handler.
func WebhookRoutes(platformService *config.PlatformService) http.Handler {
    h := handlers.NewWebhookHandler(platformService)
    mux := http.NewServeMux()

	// Matches only the root of this sub-router
	mux.HandleFunc("GET /", h.Handle)

	return mux

	//return middlewares.AuthMock(mux)
}

//package routes
//
//import (
//	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
//	"gateway-service/internal/handlers"
//	"gateway-service/internal/models"
//	"net/http"
//)
//
//func WebhookRoutes(bundle *models.Bundle, client pb.OrchestratorClient) http.Handler {
//	h := handlers.NewWebhookHandler(bundle, client)
//
//	mux := http.NewServeMux()
//
//	// Matches only the root of this sub-router
//	mux.HandleFunc("POST /{platform}/{datasource}", h.Handle)
//
//	return mux
//
//	//return middlewares.AuthMock(mux)
//}
