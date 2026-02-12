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
	"os"

	_ "gateway-service/internal/monitoring"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	ctx := context.Background()

	// 1. Load shared environment variables
	env, err := config.LoadEnv()
	if err != nil {
		log.Fatalf("Failed to load environment config: %v", err)
	}

	log.Printf("Starting gateway-service env=%s log_level=%s orchestrator=%s",
		env.AppEnv, env.LogLevel, env.GetOrchestratorAddr())

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

	// 4. Wire and start
	r := internal.NewRouter(bundleService, grpcClient)
	internal.Run(env.GetGatewayAddr(), r)
}

// buildTransportCredentials returns TLS credentials for production
// and plaintext credentials for test. All config comes from env.
func buildTransportCredentials(env *config.Env) (credentials.TransportCredentials, error) {
	if !env.IsProduction() {
		log.Println("gRPC transport: insecure (test mode)")
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

	log.Println("gRPC transport: TLS (production mode)")
	return credentials.NewTLS(tlsCfg), nil
}