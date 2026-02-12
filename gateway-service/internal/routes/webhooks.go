package routes

import (
	"gateway-service/internal/handlers"
	"gateway-service/internal/models"
	"net/http"

	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
)

// WebhookRoutes mounts all webhook endpoints under the /webhooks/ prefix.
// Fixed paths (like schema-registry) are registered before the wildcard
// so Go's ServeMux matches them first.
func WebhookRoutes(bundleService *models.Bundle, client pb.OrchestratorClient) http.Handler {
	h := handlers.NewWebhookHandler(bundleService, client)

	mux := http.NewServeMux()

	// Fixed path — matched before the wildcard
	mux.HandleFunc("POST /schema-registry", h.HandleSchemaRegistry)

	// Wildcard — regular datasource webhooks
	mux.HandleFunc("POST /{datasource}", h.Handle)

	return mux
}

//return middlewares.AuthMock(mux)
