package internal

import (
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"gateway-service/internal/handlers"
	"gateway-service/internal/middlewares"
	"gateway-service/internal/models"
	"gateway-service/internal/routes"
	"net/http"
	"net/http/pprof"
)

type Router struct {
	mux           *http.ServeMux
	bundleService *models.Bundle
	grpcClient    pb.OrchestratorClient
	grpcConn      handlers.GRPCConnChecker
	limiter       *middlewares.RateLimiter
	healthHandler *handlers.HealthHandler
	enablePprof   bool
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

// WithPprof enables /debug/pprof/* endpoints. Inspired by Jaeger's
// AdminServer.registerPprofHandlers() and Bytebase's registerPprof().
// Should be disabled in production unless explicitly requested.
func WithPprof(enable bool) RouterOption {
	return func(r *Router) {
		r.enablePprof = enable
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

	r.setupRoutes()
	r.buildMiddlewareChain()
	return r
}

// SetUnavailable marks the server as shutting down so readiness probes
// return 503, allowing the load balancer to drain traffic. Mirrors
// ArgoCD's shutdownFunc: server.available.Store(false).
func (r *Router) SetUnavailable() {
	r.healthHandler.SetUnavailable()
}

func (r *Router) setupRoutes() {
	// Health routes — /health/liveness, /health/readiness
	// Registered directly on the mux so they bypass rate limiting,
	// same pattern as Bytebase's /healthz which sits outside the
	// middleware stack that includes auth and rate limits.
	r.mux.Handle("/health/", http.StripPrefix("/health",
		routes.HealthRoutes(r.healthHandler)))

	// Webhook routes — /webhooks/{datasource}, /webhooks/schema-registry
	// These go through rate limiting. Rate limiting is applied per-route
	// group rather than globally, so health probes are never throttled.
	r.mux.Handle("/webhooks/", http.StripPrefix("/webhooks",
		r.limiter.Middleware(routes.WebhookRoutes(r.bundleService, r.grpcClient)),
	))

	// Debug endpoints — mirrors Jaeger's AdminServer.registerPprofHandlers()
	// and Bytebase's registerPprof(). Disabled by default; enable via
	// WithPprof(true) for production debugging.
	if r.enablePprof {
		r.mux.HandleFunc("/debug/pprof/", pprof.Index)
		r.mux.HandleFunc("/debug/pprof/cmdline", pprof.Cmdline)
		r.mux.HandleFunc("/debug/pprof/profile", pprof.Profile)
		r.mux.HandleFunc("/debug/pprof/symbol", pprof.Symbol)
		r.mux.HandleFunc("/debug/pprof/trace", pprof.Trace)
		r.mux.Handle("/debug/pprof/goroutine", pprof.Handler("goroutine"))
		r.mux.Handle("/debug/pprof/heap", pprof.Handler("heap"))
		r.mux.Handle("/debug/pprof/threadcreate", pprof.Handler("threadcreate"))
		r.mux.Handle("/debug/pprof/block", pprof.Handler("block"))
	}
}

func (r *Router) buildMiddlewareChain() {
	// Outermost → innermost:
	//   Recovery → SecurityHeaders → RequestLog → CorrelationID → mux
	//
	// This mirrors Bytebase's configureEchoRouters ordering:
	//   recoverMiddleware → securityHeadersMiddleware → requestLogger → routes
	//
	// CorrelationID is innermost so the ID is available to RequestLog
	// for including correlation_id in log entries.
	var h http.Handler = r.mux
	h = middlewares.CorrelationID(h)
	h = middlewares.RequestLog(h)
	h = middlewares.SecurityHeaders(h)
	h = middlewares.Recovery()(h)
	r.handler = h
}

func (r *Router) ServeHTTP(w http.ResponseWriter, req *http.Request) {
	r.handler.ServeHTTP(w, req)
}
