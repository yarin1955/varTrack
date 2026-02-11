package main

import (
	"context"
	"gateway-service/internal"
	"gateway-service/internal/config"
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/services"
	"log"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	ctx := context.Background()

	// Load from CUE file
	bundleService, err := config.NewBundle("./../config.cue")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}
	defer bundleService.Close(ctx)

	conn, err := grpc.Dial(
		"localhost:50051", // Update with your orchestrator address
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Fatalf("Failed to connect to orchestrator: %v", err)
	}
	defer conn.Close()

	grpcClient := pb.NewOrchestratorClient(conn)

	// Create router with both dependencies
	r := internal.NewRouter(bundleService, grpcClient)

	// Start server
	internal.Run(":5657", r)
}
