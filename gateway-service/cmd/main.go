package main

import (
	"context"
	"fmt"
	"gateway-service/internal"
	"gateway-service/internal/config"
	"log"
)

//func main() {
//	// Initialize the Loader (using the path to your CUE entrypoint)
//	loader := config.NewLoader("../config.cue")
//
//	// Initialize the Factory
//	factory := business_logic.NewPlatformFactory()
//
//	// Initialize the Handler with dependencies
//	webhookHandler := handlers.NewWebhookHandler(factory, loader)
//
//	// Set up routes and start server
//	mux := http.NewServeMux()
//	mux.HandleFunc("POST /webhooks/{platform}", webhookHandler.Handle)
//
//	http.ListenAndServe(":5656", mux)
//}

func main() {
	ctx := context.Background()

	// Load from CUE file
	platformService, err := config.NewPlatformServiceFromCue("./cmd/config.cue")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}
	defer platformService.Close(ctx)

	// Test: Get GitHub platform (name is "github" as defined in the proto const)
	github, err := platformService.GetPlatform(ctx, "github")
	if err != nil {
		log.Fatalf("Failed to get GitHub: %v", err)
	}

	fmt.Println("GitHub Signature Header:", github.GetGitScmSignature())

	// Create router with platformService
	r := internal.NewRouter(platformService)

	// Start server
	internal.Run(":5657", r)
}

//func main() {
//	// 1. Load CUE config
//	pbBundle, _ := config.LoadFromCue("config.cue")
//	bundle := models.NewBundle(pbBundle)
//
//	// 2. Dial the Python Orchestrator Service
//	conn, err := grpc.Dial("orchestrator:50051", grpc.WithTransportCredentials(insecure.NewCredentials()))
//	if err != nil {
//		log.Fatalf("did not connect: %v", err)
//	}
//	defer conn.Close()
//
//	client := pb.NewOrchestratorClient(conn)
//
//	// 3. Start server with injected dependencies
//	r := internal.NewRouter(bundle, client)
//	internal.Run(":5656", r)
//}
