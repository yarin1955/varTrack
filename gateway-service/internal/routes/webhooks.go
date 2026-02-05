package routes

import (
	"gateway-service/internal/handlers"
	"gateway-service/internal/models"
	"net/http"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"

)

// WebhookRoutes now accepts the PlatformRegistry as a dependency.
// This allows the router to pass the explicitly wired registry down to the handler.
func WebhookRoutes(bundleService *models.Bundle, client pb.OrchestratorClient) http.Handler {
	h := handlers.NewWebhookHandler(bundleService, client)
    mux := http.NewServeMux()

	// Matches only the root of this sub-router
	mux.HandleFunc("POST /{platform}/{datasource}", h.Handle)

	return mux

	//return middlewares.AuthMock(mux)
}
