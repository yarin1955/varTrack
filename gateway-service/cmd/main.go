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

	_ "gateway-service/internal/monitoring"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	// Top-level panic recovery — mirrors ArgoCD's server.Run() which
	// defers recover(), logs the stack with debug.Stack(), and exits
	// instead of crashing silently.
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

	// 1. Load shared environment variables
	env, err := config.LoadEnv()
	if err != nil {
		log.Fatalf("Failed to load environment config: %v", err)
	}

	slog.Info("starting gateway-service",
		"env", env.AppEnv,
		"log_level", env.LogLevel,
		"orchestrator", env.GetOrchestratorAddr(),
	)

	// 2. Load bundle from CUE file (path from CONFIG_PATH env var, default: config.cue)
	bundleService, err := config.NewBundle(env.ConfigPath)
	if err != nil {
		log.Fatalf("Failed to load config from %s: %v", env.ConfigPath, err)
	}
	defer bundleService.Close(ctx)

	// 3. Connect to orchestrator — TLS in production, plaintext in test
	transportCreds, err := buildTransportCredentials(env)
	if err != nil {
		log.Fatalf("Failed to build transport credentials: %v", err)
	}

	conn, err := grpc.NewClient(
		env.GetOrchestratorAddr(),
		grpc.WithTransportCredentials(transportCreds),
	)
	if err != nil {
		log.Fatalf("Failed to connect to orchestrator: %v", err)
	}
	defer conn.Close()

	grpcClient := pb.NewOrchestratorClient(conn)

	// 4. Wire router — pass conn so health checks can inspect gRPC state.
	r := internal.NewRouter(bundleService, grpcClient, conn)

	// 5. Graceful shutdown — mirrors ArgoCD's signal handling:
	//    signal.Notify(stopCh, os.Interrupt, syscall.SIGTERM)
	//    then server.available.Store(false) → server.Shutdown()
	stopCh := make(chan os.Signal, 1)
	signal.Notify(stopCh, os.Interrupt, syscall.SIGTERM)

	go func() {
		sig := <-stopCh
		slog.Info("received shutdown signal", "signal", sig.String())
		// Mark health unavailable so K8s drains traffic before the
		// listener closes — mirrors ArgoCD's shutdownFunc which calls
		// server.available.Store(false) before closing servers.
		r.SetUnavailable()
		cancel()
	}()

	internal.Run(ctx, env.GetGatewayAddr(), r)
}

// buildTransportCredentials returns TLS credentials for production
// and plaintext credentials for test. All config comes from env.
func buildTransportCredentials(env *config.Env) (credentials.TransportCredentials, error) {
	if !env.IsProduction() {
		slog.Info("gRPC transport: insecure (test mode)")
		return insecure.NewCredentials(), nil
	}

	tlsCfg := &tls.Config{}

	// Custom CA — if not set, Go uses the system cert pool automatically
	if env.GRPCTlsCa != "" {
		caPEM, err := os.ReadFile(env.GRPCTlsCa)
		if err != nil {
			return nil, fmt.Errorf("failed to read CA cert %s: %w", env.GRPCTlsCa, err)
		}
		pool := x509.NewCertPool()
		if !pool.AppendCertsFromPEM(caPEM) {
			return nil, fmt.Errorf("failed to parse CA certificate from %s", env.GRPCTlsCa)
		}
		tlsCfg.RootCAs = pool
	}

	// Client certificate for mTLS — both must be present
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