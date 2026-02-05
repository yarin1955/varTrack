package models

import (
	pb "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"context"
	"fmt"
	"gateway-service/internal/utils"
	"sync"
)

type Bundle struct {
	bundle          *pb.Bundle
	platformFactory *utils.PlatformFactory
	platforms       map[string]utils.Platform
	mu              sync.RWMutex
}

func NewBundle(pbBundle *pb.Bundle) *Bundle {
	return &Bundle{
		bundle:          pbBundle,
		platformFactory: utils.New(),
		platforms:       make(map[string]utils.Platform),
	}
}

func (s *Bundle) GetPlatform(ctx context.Context, name string) (utils.Platform, error) {
	// Check if already initialized
	s.mu.RLock()
	if plat, ok := s.platforms[name]; ok {
		s.mu.RUnlock()
		return plat, nil
	}
	s.mu.RUnlock()

	// Not initialized, create it
	s.mu.Lock()
	defer s.mu.Unlock()

	// Double-check after acquiring write lock
	if plat, ok := s.platforms[name]; ok {
		return plat, nil
	}

	// Find the config in bundle
	var config *pb.Platform
	for _, p := range s.bundle.Platforms {
		platformName := utils.GetPlatformName(p)
		if platformName == name {
			config = p
			break
		}
	}

	if config == nil {
		return nil, fmt.Errorf("platform %q not found in bundle configuration", name)
	}

	// Create the platform instance
	plat, err := s.platformFactory.GetPlatform(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("failed to create platform %q: %w", name, err)
	}

	// Cache it
	s.platforms[name] = plat

	return plat, nil
}

// Close closes all initialized platforms
func (s *Bundle) Close(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	var errs []error
	for name, plat := range s.platforms {
		if err := plat.Close(ctx); err != nil {
			errs = append(errs, fmt.Errorf("failed to close platform %q: %w", name, err))
		}
	}

	if len(errs) > 0 {
		return fmt.Errorf("errors closing platforms: %v", errs)
	}
	return nil
}

// ListConfiguredPlatforms returns names of all platforms in the bundle (without initializing them)
func (s *Bundle) ListConfiguredPlatforms() []string {
	names := make([]string, 0, len(s.bundle.Platforms))
	for _, p := range s.bundle.Platforms {
		platformName := utils.GetPlatformName(p)
		if platformName != "" {
			names = append(names, platformName)
		}
	}
	return names
}

// GetBundle returns the underlying bundle configuration
func (s *Bundle) GetBundle() *pb.Bundle {
	return s.bundle
}
