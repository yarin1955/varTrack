package business_logic

import (
	"context"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"
)

type PlatformFactory struct{}

func NewPlatformFactory() *PlatformFactory {
	return &PlatformFactory{}
}

func (f *PlatformFactory) GetPlatformDriver(ctx context.Context, config *pb_models.Platform) (utils.Platform, error) {
	if config == nil {
		return nil, fmt.Errorf("platform configuration is nil")
	}

	var name string
	if config.GetGithub() != nil {
		name = "github"
	}

	if name == "" {
		return nil, fmt.Errorf("unsupported platform type in config")
	}

	return utils.Open(ctx, name, config)
}
