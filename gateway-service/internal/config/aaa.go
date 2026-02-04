package config

import (
	"context"
	"fmt"
	"sync"

	"cuelang.org/go/cue"
	"cuelang.org/go/cue/cuecontext"
	"cuelang.org/go/cue/load"
	"google.golang.org/protobuf/encoding/protojson"

	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"

	// Import all platform drivers you want to support
	_ "gateway-service/internal/models/platforms"
)

type PlatformService struct {
	bundle          *pb_models.Bundle
	platformFactory *utils.PlatformFactory
	platforms       map[string]utils.Platform
	mu              sync.RWMutex
}

// getPlatformName extracts the platform name from the Platform message
func getPlatformName(p *pb_models.Platform) string {
	switch config := p.Config.(type) {
	case *pb_models.Platform_Github:
		return config.Github.Name
	// Add other platforms when you implement them
	// case *pb_models.Platform_Gitlab:
	//     return config.Gitlab.Name
	// case *pb_models.Platform_Bitbucket:
	//     return config.Bitbucket.Name
	default:
		return ""
	}
}

// NewPlatformService creates a new platform service from a bundle
func NewPlatformService(bundle *pb_models.Bundle) *PlatformService {
	return &PlatformService{
		bundle:          bundle,
		platformFactory: utils.New(),
		platforms:       make(map[string]utils.Platform),
	}
}

// NewPlatformServiceFromCue creates a new platform service by loading a CUE file
func NewPlatformServiceFromCue(cuePath string) (*PlatformService, error) {
	bundle, err := loadBundleFromCue(cuePath)
	if err != nil {
		return nil, fmt.Errorf("failed to load bundle from CUE: %w", err)
	}

	return NewPlatformService(bundle), nil
}

// NewPlatformServiceFromCueWithContext creates a new platform service by loading CUE files with custom context
func NewPlatformServiceFromCueWithContext(cuePaths []string, tags []string) (*PlatformService, error) {
	bundle, err := loadBundleFromCueFiles(cuePaths, tags)
	if err != nil {
		return nil, fmt.Errorf("failed to load bundle from CUE files: %w", err)
	}

	return NewPlatformService(bundle), nil
}

// loadBundleFromCue loads a bundle from a single CUE file
func loadBundleFromCue(cuePath string) (*pb_models.Bundle, error) {
	return loadBundleFromCueFiles([]string{cuePath}, nil)
}

// loadBundleFromCueFiles loads a bundle from multiple CUE files with optional tags
func loadBundleFromCueFiles(cuePaths []string, tags []string) (*pb_models.Bundle, error) {
	// Create load config
	cfg := &load.Config{
		Tags: tags,
	}

	// Load CUE files
	buildInstances := load.Instances(cuePaths, cfg)
	if len(buildInstances) == 0 {
		return nil, fmt.Errorf("no CUE instances found")
	}

	if buildInstances[0].Err != nil {
		return nil, fmt.Errorf("failed to load CUE files: %w", buildInstances[0].Err)
	}

	// Get CUE context
	ctx := cuecontext.New()

	// Build the instance
	value := ctx.BuildInstance(buildInstances[0])
	if value.Err() != nil {
		return nil, fmt.Errorf("failed to build CUE: %w", value.Err())
	}

	// Look up the bundle field
	bundleValue := value.LookupPath(cue.ParsePath("bundle"))
	if bundleValue.Err() != nil {
		return nil, fmt.Errorf("bundle not found in CUE: %w", bundleValue.Err())
	}

	// Validate the bundle
	if err := bundleValue.Validate(cue.Concrete(true)); err != nil {
		return nil, fmt.Errorf("bundle validation failed: %w", err)
	}

	// Convert to JSON
	jsonBytes, err := bundleValue.MarshalJSON()
	if err != nil {
		return nil, fmt.Errorf("failed to marshal bundle to JSON: %w", err)
	}

	// Unmarshal into protobuf
	bundle := &pb_models.Bundle{}
	if err := protojson.Unmarshal(jsonBytes, bundle); err != nil {
		return nil, fmt.Errorf("failed to unmarshal into protobuf: %w", err)
	}

	return bundle, nil
}

// GetPlatform gets or creates a platform by name (lazy initialization)
func (s *PlatformService) GetPlatform(ctx context.Context, name string) (utils.Platform, error) {
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
	var config *pb_models.Platform
	for _, p := range s.bundle.Platforms {
		platformName := getPlatformName(p)
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
func (s *PlatformService) Close(ctx context.Context) error {
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
func (s *PlatformService) ListConfiguredPlatforms() []string {
	names := make([]string, 0, len(s.bundle.Platforms))
	for _, p := range s.bundle.Platforms {
		platformName := getPlatformName(p)
		if platformName != "" {
			names = append(names, platformName)
		}
	}
	return names
}

// GetBundle returns the underlying bundle configuration
func (s *PlatformService) GetBundle() *pb_models.Bundle {
	return s.bundle
}

// ReloadFromCue reloads the bundle configuration from a CUE file and resets all platforms
func (s *PlatformService) ReloadFromCue(ctx context.Context, cuePath string) error {
	// Load new bundle
	newBundle, err := loadBundleFromCue(cuePath)
	if err != nil {
		return fmt.Errorf("failed to reload bundle: %w", err)
	}

	// Close all existing platforms
	if err := s.Close(ctx); err != nil {
		return fmt.Errorf("failed to close existing platforms: %w", err)
	}

	// Update bundle and reset platforms map
	s.mu.Lock()
	s.bundle = newBundle
	s.platforms = make(map[string]utils.Platform)
	s.mu.Unlock()

	return nil
}
