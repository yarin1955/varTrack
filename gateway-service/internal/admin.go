package internal

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"net/http/pprof"
	"time"

	"gateway-service/internal/handlers"
)

// AdminServer runs internal endpoints (health, pprof, metrics) on a
// separate listener isolated from public webhook traffic.
//
// This directly mirrors two production patterns:
//
// 1. Jaeger's AdminServer (cmd/internal/flags/admin.go):
//   - Runs on a separate "admin.http.host-port"
//   - Registers pprof handlers via registerPprofHandlers()
//   - Mounts health check on "/"
//   - Wraps with recovery handler
//
// 2. ArgoCD's MetricsServer (server-metrics/metrics.go):
//   - Creates a new http.Server on a dedicated port (MetricsHost:MetricsPort)
//   - Registers /metrics and pprof on its own mux
//   - Started via: go func() { server.checkServeErr("metrics", metricsServ.Serve(listeners.Metrics)) }()
//
// Benefits over a single listener:
//   - Public traffic cannot reach internal debug tools if a firewall rule
//     is misconfigured
//   - Prometheus can scrape /metrics even if the webhook port is saturated
//   - pprof is never accidentally exposed to the internet
type AdminServer struct {
	server        *http.Server
	healthHandler *handlers.HealthHandler
}

// AdminConfig configures the admin server.
type AdminConfig struct {
	// Addr is the listen address (e.g. ":9090"). Mirrors Jaeger's
	// adminHTTPHostPort flag and ArgoCD's MetricsHost + MetricsPort.
	Addr string

	// EnablePprof controls whether /debug/pprof/* endpoints are mounted.
	// ArgoCD's RegisterProfiler (util-profile/profile.go) gates pprof
	// behind a config file check; Jaeger always registers them on the
	// admin server since it's internal-only.
	EnablePprof bool
}

// NewAdminServer creates an admin server with health and optional debug
// endpoints. The healthHandler is shared with the main router so that
// SetUnavailable() affects both the public readiness probe and the
// admin health endpoint.
//
// Pattern: Jaeger's NewAdminServer(hostPort) which returns an AdminServer
// with its own mux, and ArgoCD's NewMetricsServer(host, port) which
// creates a dedicated http.Server.
func NewAdminServer(cfg AdminConfig, healthHandler *handlers.HealthHandler) *AdminServer {
	mux := http.NewServeMux()

	// Health check on root — Jaeger's AdminServer mounts health on "/".
	// ArgoCD's healthz.ServeHealthCheck registers on "/healthz".
	// We register both for compatibility.
	mux.HandleFunc("/healthz", healthHandler.Readiness)
	mux.HandleFunc("GET /health/liveness", healthHandler.Liveness)
	mux.HandleFunc("GET /health/readiness", healthHandler.Readiness)

	// pprof — Jaeger's registerPprofHandlers() and ArgoCD's
	// profile.RegisterProfiler(mux) both register the same set of
	// endpoints on the admin/metrics mux.
	if cfg.EnablePprof {
		mux.HandleFunc("/debug/pprof/", pprof.Index)
		mux.HandleFunc("/debug/pprof/cmdline", pprof.Cmdline)
		mux.HandleFunc("/debug/pprof/profile", pprof.Profile)
		mux.HandleFunc("/debug/pprof/symbol", pprof.Symbol)
		mux.HandleFunc("/debug/pprof/trace", pprof.Trace)
		mux.Handle("/debug/pprof/goroutine", pprof.Handler("goroutine"))
		mux.Handle("/debug/pprof/heap", pprof.Handler("heap"))
		mux.Handle("/debug/pprof/threadcreate", pprof.Handler("threadcreate"))
		mux.Handle("/debug/pprof/block", pprof.Handler("block"))
	}

	return &AdminServer{
		server: &http.Server{
			Addr:              cfg.Addr,
			Handler:           mux,
			ReadHeaderTimeout: 5 * time.Second,
			ReadTimeout:       10 * time.Second,
			WriteTimeout:      30 * time.Second, // pprof profiles can take time
			IdleTimeout:       60 * time.Second,
		},
		healthHandler: healthHandler,
	}
}

// Serve starts the admin server. It blocks until the server stops.
//
// Mirrors ArgoCD's server.go:
//
//	go func() { server.checkServeErr("metrics", metricsServ.Serve(listeners.Metrics)) }()
//
// And Jaeger's AdminServer.serveWithListener which logs the address and
// starts serving in a goroutine.
func (a *AdminServer) Serve() error {
	slog.Info("admin server starting",
		"addr", a.server.Addr,
	)
	err := a.server.ListenAndServe()
	if err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("admin server error: %w", err)
	}
	return nil
}

// Shutdown gracefully stops the admin server.
// Mirrors Jaeger's AdminServer.Close() which calls server.Shutdown.
func (a *AdminServer) Shutdown(ctx context.Context) error {
	return a.server.Shutdown(ctx)
}
