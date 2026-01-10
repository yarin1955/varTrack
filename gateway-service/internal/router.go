package internal

import (
	"gateway-service/internal/routes"
	"net/http"
)

func NewRouter() http.Handler {
	mux := http.NewServeMux()

	// 1. Mount Health Routes
	// http.StripPrefix removes "/health" from the path before passing to the sub-router
	// So requests to "/health/liveness" become "/liveness" inside healthRoutes()
	mux.Handle("/health/", http.StripPrefix("/health", routes.HealthRoutes()))

	// 2. Mount Webhook Routes
	// Requests to "/webhooks" or "/webhooks/" go here
	mux.Handle("/webhooks/", http.StripPrefix("/webhooks", routes.WebhookRoutes()))

	//globalHandler := middlewares.Logger(mux)
	//return globalHandler
	return mux
}
