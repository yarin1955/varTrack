package internal

import (
	"gateway-service/internal/config"
	"gateway-service/internal/routes"
	"net/http"
)

type Router struct {
	mux             *http.ServeMux
	platformService *config.PlatformService
}

func NewRouter(platformService *config.PlatformService) *Router {
	r := &Router{
		mux:             http.NewServeMux(),
		platformService: platformService,
	}
	r.setupRoutes()
	return r
}

func (r *Router) setupRoutes() {
	// Pass platformService to webhook routes
	r.mux.Handle("/webhooks/", http.StripPrefix("/webhooks", routes.WebhookRoutes(r.platformService)))
}

func (r *Router) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	r.mux.ServeHTTP(w, req)
}

// package internal

// import (
// 	"gateway-service/internal/routes"
// 	"net/http"
// )

// type Router struct {
// 	mux *http.ServeMux
// }

// func NewRouter() *Router {
// 	r := &Router{
// 		mux: http.NewServeMux(),
// 		//platformReg: platformReg,
// 	}
// 	r.setupRoutes()
// 	return r
// }

// func (r *Router) setupRoutes() {
// 	// The field name 'PlatformReg' must exist in handlers.WebhookHandler
// 	//webhookHandler := &handlers.WebhookHandler{
// 	//	PlatformReg: r.platformReg,
// 	//}

// 	// The method name 'HandleWebhook' must exist on the handler
// 	//r.mux.HandleFunc("/webhooks", webhookHandler.HandleWebhook)
// 	r.mux.Handle("/webhooks/", http.StripPrefix("/webhooks", routes.WebhookRoutes()))

// }

// func (r *Router) ServeHTTP(w http.ResponseWriter, req *http.Request) {
// 	r.mux.ServeHTTP(w, req)
// }

//import (
//	utils "gateway-service/internal/gen/proto/go/vartrack/v1/utils"
//	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
//	"gateway-service/internal/routes"
//	"net/http"
//)
//
//func NewRouter(bundle *utils.Bundle, client pb.OrchestratorClient) http.Handler {
//	mux := http.NewServeMux()
//
//	// 1. Mount Health Routes
//	// http.StripPrefix removes "/health" from the path before passing to the sub-router
//	// So requests to "/health/liveness" become "/liveness" inside healthRoutes()
//	//mux.Handle("/webhooks/", http.StripPrefix("/webhooks", routes.WebhookRoutes(bundle, client)))
//
//	// 2. Mount Webhook Routes
//	// Requests to "/webhooks" or "/webhooks/" go here
//	mux.Handle("/webhooks/", http.StripPrefix("/webhooks", routes.WebhookRoutes(bundle, client)))
//
//	//globalHandler := middlewares.Logger(mux)
//	//return globalHandler
//	return mux
//}
