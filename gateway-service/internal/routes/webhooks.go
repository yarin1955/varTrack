package routes

import (
	"gateway-service/internal/handlers"
	"net/http"
)

func WebhookRoutes() http.Handler {
	h := handlers.NewWebhookHandler()

	mux := http.NewServeMux()

	// Matches only the root of this sub-router
	mux.HandleFunc("GET /", h.Handle)

	return mux

	//return middlewares.AuthMock(mux)
}
