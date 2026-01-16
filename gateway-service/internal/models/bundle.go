package models

import (
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"
)

type Bundle struct {
	*pb.Bundle
	// FIX: Change *pb.Platform to *Platform (your custom wrapper)
	platformIdx map[string]*Platform
}

func NewBundle(pbBundle *pb.Bundle) *Bundle {
	b := &Bundle{
		Bundle:      pbBundle,
		platformIdx: make(map[string]*Platform), // Now types match
	}

	for _, p := range pbBundle.GetPlatforms() {
		// Use your registry to resolve the platform name (e.g. "github")
		name := utils.ResolveKey(p)
		if name != "" {
			// Create the platform logic implementation
			impl, _ := utils.Create(p)

			// Store the wrapper in the index
			b.platformIdx[name] = &Platform{
				pb:       p,
				instance: impl,
			}
		}
	}
	return b
}

func (b *Bundle) GetPlatformByName(name string) *Platform {
	return b.platformIdx[name]
}
