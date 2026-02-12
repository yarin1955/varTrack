package models

import (
	"context"
	"fmt"
	pb_models "gateway-service/internal/gen/proto/go/vartrack/v1/models"
	"gateway-service/internal/utils"
)

type Platform interface {
	EventTypeHeader() string
	GetGitScmSignature() string
	IsPushEvent(eventType string) bool
	IsPREvent(eventType string) bool
	VerifyWebhook(payload []byte, signatureHeader string) bool
	ConstructCloneURL(repo string) string
	Auth(ctx context.Context) error
	Open(ctx context.Context, config *pb_models.Platform, resolver *utils.SecretRefResolver, managerName string) (Platform, error)
	Close(ctx context.Context) error
	GetRepos(ctx context.Context, patterns []string) ([]string, error)
	GetSecret() string
}

type PlatformConfig struct {
	Platform    *pb_models.Platform
	Resolver    *utils.SecretRefResolver
	ManagerName string
}

var PlatformRegistry = utils.NewDriverRegistry[Platform, PlatformConfig](
	"platform",
	func(driver Platform, ctx context.Context, config PlatformConfig) (Platform, error) {
		return driver.Open(ctx, config.Platform, config.Resolver, config.ManagerName)
	},
)

var PlatformFactory = utils.NewDriverFactory(
	PlatformRegistry,
	func(c PlatformConfig) string {
		if c.Platform == nil {
			return ""
		}
		return GetPlatformName(c.Platform)
	},
	func(c PlatformConfig) error {
		if c.Platform == nil {
			return fmt.Errorf("platform config cannot be nil")
		}
		return nil
	},
	"platform",
)

func GetPlatformName(p *pb_models.Platform) string {
	switch config := p.Config.(type) {
	case *pb_models.Platform_Github:
		return config.Github.Name
	default:
		return ""
	}
}