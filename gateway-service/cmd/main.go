package main

import (
	"context"
	"fmt"
	"gateway-service/internal"
	"gateway-service/internal/config"
	"log"
)

func main() {
	ctx := context.Background()

	// Load from CUE file
	bundleService, err := config.NewBundle("./cmd/config.cue")
	if err != nil {
		log.Fatalf("Failed to load config: %v", err)
	}
	defer bundleService.Close(ctx)

	// Test: Get GitHub platform (name is "github" as defined in the proto const)
	github, err := bundleService.GetPlatform(ctx, "github")
	if err != nil {
		log.Fatalf("Failed to get GitHub: %v", err)
	}

	fmt.Println("GitHub Signature Header:", github.GetGitScmSignature())

	// Create router with bundleService
	r := internal.NewRouter(bundleService)

	// Start server
	internal.Run(":5657", r)
}
