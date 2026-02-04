package utils

import (
	"context"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
)

type PlatformFactory struct {
}

// New creates a new database driver factory.
func New() *PlatformFactory {
	return &PlatformFactory{}
}

func (f *PlatformFactory) GetPlatform(ctx context.Context, config *pb_models.Platform) (Platform, error) {
	if config == nil {
		return nil, fmt.Errorf("platform config cannot be nil")
	}

	// Extract platform name from the config
	platformName := GetPlatformName(config)
	if platformName == "" {
		return nil, fmt.Errorf("platform name must be specified")
	}

	driver, err := Open(ctx, platformName, config)
	if err != nil {
		return nil, err
	}

	return driver, nil
}
