package internal

import (
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"gateway-service/internal/handlers"
	"gateway-service/internal/middlewares"
	"gateway-service/internal/models"
	"gateway-service/internal/routes"
	"net/http"
)

type Router struct {
	mux           *http.ServeMux
	bundleService *models.Bundle
	grpcClient    pb.OrchestratorClient
	grpcConn      handlers.GRPCConnChecker
	limiter       *middlewares.RateLimiter
	breaker       *middlewares.CircuitBreaker
	healthHandler *handlers.HealthHandler
	handler       http.Handler // final handler chain with middleware
}

// RouterOption configures optional Router behaviour.
// Mirrors ArgoCD's functional-option pattern used across its server,
// repo-server, and commit-server constructors.
type RouterOption func(*Router)

// WithRateLimiterConfig overrides the default rate limiter settings.
func WithRateLimiterConfig(cfg middlewares.RateLimiterConfig) RouterOption {
	return func(r *Router) {
		r.limiter = middlewares.NewRateLimiter(cfg)
	}
}

// WithCircuitBreakerConfig overrides the default circuit breaker settings.
func WithCircuitBreakerConfig(cfg middlewares.CircuitBreakerConfig) RouterOption {
	return func(r *Router) {
		r.breaker = middlewares.NewCircuitBreaker(cfg)
	}
}

func NewRouter(
	bundleService *models.Bundle,
	grpcClient pb.OrchestratorClient,
	grpcConn handlers.GRPCConnChecker,
	opts ...RouterOption,
) *Router {
	r := &Router{
		mux:           http.NewServeMux(),
		bundleService: bundleService,
		grpcClient:    grpcClient,
		grpcConn:      grpcConn,
		healthHandler: handlers.NewHealthHandler(grpcConn, grpcClient),
	}

	for _, o := range opts {
		o(r)
	}

	if r.limiter == nil {
		r.limiter = middlewares.NewRateLimiter(middlewares.DefaultRateLimiterConfig())
	}
	if r.breaker == nil {
		r.breaker = middlewares.NewCircuitBreaker(middlewares.DefaultCircuitBreakerConfig())
	}

	r.setupRoutes()
	r.buildMiddlewareChain()
	return r
}

// HealthHandler returns the shared health handler so the admin server can
// use the same instance. This mirrors ArgoCD's server.go where the
// metricsServ and main server share the same health state.
func (r *Router) HealthHandler() *handlers.HealthHandler {
	return r.healthHandler
}

// SetUnavailable marks the server as shutting down so readiness probes
// return 503, allowing the load balancer to drain traffic. Mirrors
// ArgoCD's shutdownFunc: server.available.Store(false).
func (r *Router) SetUnavailable() {
	r.healthHandler.SetUnavailable()
}

func (r *Router) setupRoutes() {
	// Health routes on the public mux — kept for backward compatibility.
	// The admin server also exposes these on a separate port.
	//
	// Registered directly on the mux so they bypass rate limiting,
	// same pattern as Bytebase's /healthz which sits outside the
	// middleware stack that includes auth and rate limits.
	r.mux.Handle("/health/", http.StripPrefix("/health",
		routes.HealthRoutes(r.healthHandler)))

	// Webhook routes — /webhooks/{datasource}, /webhooks/schema-registry
	// Rate limiting applied per-route group so health probes are never
	// throttled. Circuit breaker is injected into the handler itself.
	r.mux.Handle("/webhooks/", http.StripPrefix("/webhooks",
		r.limiter.Middleware(routes.WebhookRoutes(r.bundleService, r.grpcClient, r.breaker)),
	))
}

func (r *Router) buildMiddlewareChain() {
	// Outermost → innermost:
	//   Recovery → SecurityHeaders → RequestLog → RequestID → CorrelationID → mux
	//
	// This mirrors Bytebase's configureEchoRouters ordering:
	//   recoverMiddleware → securityHeadersMiddleware → requestLogger → routes
	//
	// RequestID (improvement #7) is placed before CorrelationID so both
	// IDs are available in all downstream handlers and log entries.
	// The key difference:
	//   - CorrelationID: preserved across retries and service hops
	//   - RequestID: unique per HTTP transaction at the gateway
	//
	// ArgoCD's gRPC logging interceptor (util-grpc/logging.go) attaches
	// per-call structured fields in a similar innermost position.
	var h http.Handler = r.mux
	h = middlewares.CorrelationID(h)
	h = middlewares.RequestID(h)
	h = middlewares.RequestLog(h)
	h = middlewares.SecurityHeaders(h)
	h = middlewares.Recovery()(h)
	r.handler = h
}

func (r *Router) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	r.handler.ServeHTTP(w, req)
}
