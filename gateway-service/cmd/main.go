package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"gateway-service/internal"
	"gateway-service/internal/config"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"log"
	"log/slog"
	"os"
	"os/signal"
	"runtime/debug"
	"syscall"
	"time"

	_ "gateway-service/internal/monitoring"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/keepalive"
)

func main() {
	// Top-level panic recovery — mirrors ArgoCD's server.Run():
	//   defer func() {
	//       if r := recover(); r != nil {
	//           log.WithField("trace", string(debug.Stack())).Error("Recovered from panic: ", r)
	defer func() {
		if r := recover(); r != nil {
			slog.Error("fatal panic in main",
				"panic", fmt.Sprint(r),
				"stack", string(debug.Stack()),
			)
			os.Exit(1)
		}
	}()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// 1. Load and validate environment variables
	env, err := config.LoadEnv()
	if err != nil {
		log.Fatalf("Failed to load environment config: %v", err)
	}

	slog.Info("starting gateway-service",
		"env", env.AppEnv,
		"log_level", env.LogLevel,
		"orchestrator", env.GetOrchestratorAddr(),
	)

	// 2. Load bundle from CUE file
	bundleService, err := config.NewBundle(env.ConfigPath)
	if err != nil {
		log.Fatalf("Failed to load config from %s: %v", env.ConfigPath, err)
	}
	defer bundleService.Close(ctx)

	// 3. Connect to orchestrator with resilience
	transportCreds, err := buildTransportCredentials(env)
	if err != nil {
		log.Fatalf("Failed to build transport credentials: %v", err)
	}

	conn, err := grpc.NewClient(
		env.GetOrchestratorAddr(),
		grpc.WithTransportCredentials(transportCreds),

		// Keepalive — ArgoCD common.GetGRPCKeepAliveTime() returns
		// 2× enforcementMinimum (10s) = 20s. Prevents idle connections
		// from being silently dropped by intermediate LBs/firewalls.
		grpc.WithKeepaliveParams(keepalive.ClientParameters{
			Time:                20 * time.Second,
			Timeout:             5 * time.Second,
			PermitWithoutStream: true,
		}),

		// User-agent — ArgoCD apiclient.go line 541:
		//   dialOpts = append(dialOpts, grpc.WithUserAgent(c.UserAgent))
		grpc.WithUserAgent("gateway-service"),
	)
	if err != nil {
		log.Fatalf("Failed to connect to orchestrator: %v", err)
	}
	defer conn.Close()

	grpcClient := pb.NewOrchestratorClient(conn)

	// 4. Wire router
	r := internal.NewRouter(bundleService, grpcClient, conn)

	// 5. Start admin server on a separate port.
	//
	// Mirrors ArgoCD's server.go which starts metricsServ on a dedicated
	// port in a goroutine:
	//   metricsServ := metrics.NewMetricsServer(server.MetricsHost, server.MetricsPort)
	//   go func() { server.checkServeErr("metrics", metricsServ.Serve(listeners.Metrics)) }()
	//
	// And Jaeger's AdminServer (cmd/internal/flags/admin.go) which runs
	// health, pprof, and version on "admin.http.host-port", separate
	// from the main query/collector ports.
	adminAddr := envOr("ADMIN_ADDR", ":9090")
	adminSrv := internal.NewAdminServer(internal.AdminConfig{
		Addr:        adminAddr,
		EnablePprof: !env.IsProduction(),
	}, r.HealthHandler())

	go func() {
		if err := adminSrv.Serve(); err != nil {
			slog.Error("admin server error", "error", err)
		}
	}()

	// 6. Graceful shutdown — ArgoCD's signal → available.Store(false) → Shutdown
	stopCh := make(chan os.Signal, 1)
	signal.Notify(stopCh, os.Interrupt, syscall.SIGTERM)

	go func() {
		sig := <-stopCh
		slog.Info("received shutdown signal", "signal", sig.String())
		r.SetUnavailable()

		// Shutdown admin server alongside main — Jaeger's AdminServer.Close()
		// calls server.Shutdown(context.Background()).
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		if err := adminSrv.Shutdown(shutdownCtx); err != nil {
			slog.Error("admin server shutdown error", "error", err)
		}

		cancel()
	}()

	// 7. Resolve inbound TLS config from environment.
	//
	// Three modes (mirroring ArgoCD's CreateServerTLSConfig):
	//   a) GATEWAY_TLS_CERT + GATEWAY_TLS_KEY set → load from files
	//   b) Neither set + test mode → self-signed cert (ArgoCD's fallback)
	//   c) Neither set + production → plaintext (behind Ingress/LB)
	tlsCfg := resolveInboundTLS(env)

	internal.Run(ctx, env.GetGatewayAddr(), r, tlsCfg)
}

// resolveInboundTLS builds the inbound TLS config based on environment.
func resolveInboundTLS(env *config.Env) *internal.TLSConfig {
	cert := os.Getenv("GATEWAY_TLS_CERT")
	key := os.Getenv("GATEWAY_TLS_KEY")

	if cert != "" && key != "" {
		slog.Info("inbound TLS: loading certificate from files",
			"cert", cert, "key", key)
		return &internal.TLSConfig{CertFile: cert, KeyFile: key}
	}

	// In non-production, generate a self-signed cert so local dev always
	// uses HTTPS. Mirrors ArgoCD's CreateServerTLSConfig which logs:
	//   "Generating self-signed TLS certificate for this session"
	if !env.IsProduction() {
		slog.Info("inbound TLS: self-signed cert for local dev (non-production)")
		return &internal.TLSConfig{SelfSignedIfMissing: true}
	}

	// Production without explicit certs: plaintext behind Ingress/LB.
	slog.Info("inbound TLS: disabled (expects TLS termination upstream)")
	return nil
}

// buildTransportCredentials returns TLS credentials for the outbound gRPC
// connection to the orchestrator.
//
// Uses ArgoCD's tls util BestEffortSystemCertPool pattern: when no custom
// CA is specified, the system cert pool is used (with a fallback to an
// empty pool if system certs can't be loaded).
func buildTransportCredentials(env *config.Env) (credentials.TransportCredentials, error) {
	if !env.IsProduction() {
		slog.Info("gRPC transport: insecure (test mode)")
		return insecure.NewCredentials(), nil
	}

	tlsCfg := &tls.Config{}

	if env.GRPCTlsCa != "" {
		// Custom CA provided — load it into a fresh pool.
		caPEM, err := os.ReadFile(env.GRPCTlsCa)
		if err != nil {
			return nil, fmt.Errorf("failed to read CA cert %s: %w", env.GRPCTlsCa, err)
		}
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM(caPEM) {
			return nil, fmt.Errorf("failed to parse CA certificate from %s", env.GRPCTlsCa)
		}
		tlsCfg.RootCAs = pool
	} else {
		// No custom CA — use system cert pool. Mirrors ArgoCD's
		// BestEffortSystemCertPool:
		//   func BestEffortSystemCertPool() *x509.CertPool {
		//       rootCAs, _ := x509.SystemCertPool()
		//       if rootCAs == nil { return x509.NewCertPool() }
		//       return rootCAs
		//   }
		pool, _ := x509.SystemCertPool()
		if pool == nil {
			pool = x509.NewCertPool()
		}
		tlsCfg.RootCAs = pool
	}

	// Client cert for mTLS — both must be present.
	// ArgoCD apiclient.go line ~235:
	//   "ClientCertificateData and ClientCertificateKeyData must always
	//    be specified together"
	if env.GRPCTlsCert != "" && env.GRPCTlsKey != "" {
		cert, err := tls.LoadX509KeyPair(env.GRPCTlsCert, env.GRPCTlsKey)
		if err != nil {
			return nil, fmt.Errorf("failed to load client TLS keypair: %w", err)
		}
		tlsCfg.Certificates = []tls.Certificate{cert}
	}

	slog.Info("gRPC transport: TLS (production mode)")
	return credentials.NewTLS(tlsCfg), nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
